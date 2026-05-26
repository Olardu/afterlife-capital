# claude_client.py
# Wrapper async sobre la Anthropic SDK para el Universe Selector
# (#UNIVERSE-SELECTION). Encapsula:
#   - Cliente AsyncAnthropic con timeout configurable.
#   - Prompt caching del system prompt (estable entre llamadas).
#   - Cost tracking en USD basado en pricing actual de Sonnet 4.6.
#   - Safety cap por llamada (UNIVERSE_SELECTION_MAX_COST_PER_CALL_USD).
#   - Manejo robusto de timeout y errores de la API — NUNCA crashea el bot.
#
# Usa structured outputs (output_config.format = json_schema) para garantizar
# que la respuesta sea JSON parseable directamente, sin regex post-hoc.
#
# IMPORTANTE: el bot está corriendo. Una llamada que falla aquí debe loggear
# y devolver {"success": False, ...} — el caller decide si reintenta o
# saltea el ciclo. Nunca propagar excepciones hacia main.py.

import logging
from typing import Optional

import anthropic

from config import (
    ANTHROPIC_API_KEY,
    ANTHROPIC_MODEL,
    UNIVERSE_SELECTION_MAX_COST_PER_CALL_USD,
    UNIVERSE_SELECTION_TIMEOUT_SECONDS,
)

logger = logging.getLogger("sentinel.claude_client")


# Pricing por 1M tokens (al 2026-04-27). Si Anthropic cambia precios,
# actualizar acá. La estimación se persiste en rotation_decisions.claude_cost_usd
# así que un cambio de precio no invalida los registros históricos.
_PRICING_USD_PER_M_TOKENS = {
    "claude-opus-4-7":   {"input": 5.00,  "output": 25.00},
    "claude-opus-4-6":   {"input": 5.00,  "output": 25.00},
    "claude-sonnet-4-6": {"input": 3.00,  "output": 15.00},
    "claude-haiku-4-5":  {"input": 1.00,  "output":  5.00},
}


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    """Costo en USD para una llamada según el pricing del modelo."""
    p = _PRICING_USD_PER_M_TOKENS.get(model)
    if p is None:
        # Modelo desconocido — no inventamos pricing. Logueamos y devolvemos 0.0.
        logger.warning(f"Modelo {model!r} sin pricing conocido — costo reportado como 0.0")
        return 0.0
    return (input_tokens * p["input"] / 1_000_000) + (output_tokens * p["output"] / 1_000_000)


class ClaudeClient:
    """
    Cliente Anthropic con timeout, cost tracking y manejo de error robusto.

    Uso:
        client = ClaudeClient()
        result = await client.call_json(
            system_prompt=SYSTEM,
            user_prompt=user,
            response_schema=SCHEMA,
            max_tokens=2000,
        )
        if result["success"]:
            data = result["parsed"]
        else:
            logger.warning(f"Claude falló: {result['error']}")
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model:   Optional[str] = None,
        timeout: Optional[float] = None,
        max_cost_per_call_usd: Optional[float] = None,
    ):
        self.model     = model or ANTHROPIC_MODEL
        self.timeout   = timeout if timeout is not None else UNIVERSE_SELECTION_TIMEOUT_SECONDS
        self.max_cost  = (max_cost_per_call_usd
                          if max_cost_per_call_usd is not None
                          else UNIVERSE_SELECTION_MAX_COST_PER_CALL_USD)

        key = api_key or ANTHROPIC_API_KEY
        if not key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY no configurada — agregar al .env antes de "
                "habilitar UNIVERSE_SELECTION_ENABLED."
            )
        # max_retries=2 por default del SDK; el timeout cubre toda la operación.
        self.client = anthropic.AsyncAnthropic(api_key=key, timeout=self.timeout)

    async def call_json(
        self,
        *,
        system_prompt:    str,
        user_prompt:      str,
        response_schema:  dict,
        max_tokens:       int = 2000,
    ) -> dict:
        """
        Llamada a messages.create con:
        - system_prompt cacheado (prompt caching ephemeral, 5 min TTL).
        - thinking disabled (Sonnet 4.6 default es high — evitamos costo extra).
        - output_config.format json_schema para garantizar JSON parseable.

        Retorna:
            {
                "success":         bool,
                "parsed":          dict | None,    # JSON ya parseado si success
                "raw_text":        str  | None,    # texto crudo de respuesta
                "input_tokens":    int,
                "output_tokens":   int,
                "cache_read_tokens": int,
                "cost_usd":        float,
                "model":           str,
                "stop_reason":     str | None,
                "error":           str | None,
            }
        """
        result_template = {
            "success":           False,
            "parsed":            None,
            "raw_text":          None,
            "input_tokens":      0,
            "output_tokens":     0,
            "cache_read_tokens": 0,
            "cost_usd":          0.0,
            "model":             self.model,
            "stop_reason":       None,
            "error":             None,
        }

        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=[
                    {
                        "type":          "text",
                        "text":          system_prompt,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": user_prompt}],
                # thinking explícitamente disabled — Sonnet 4.6 lo activa por
                # default a effort=high, lo cual triplica el costo de output.
                # Para selección de tickers no lo necesitamos.
                thinking={"type": "disabled"},
                output_config={
                    "format": {
                        "type":   "json_schema",
                        "schema": response_schema,
                    }
                },
            )
        except anthropic.APITimeoutError as e:
            logger.error(f"Claude timeout ({self.timeout}s): {e}")
            return {**result_template, "error": f"timeout_{int(self.timeout)}s"}
        except anthropic.RateLimitError as e:
            logger.error(f"Claude rate limit: {e}")
            return {**result_template, "error": "rate_limit"}
        except anthropic.APIStatusError as e:
            logger.error(f"Claude API status error {e.status_code}: {e.message}")
            return {**result_template, "error": f"http_{e.status_code}: {e.message[:200]}"}
        except anthropic.APIConnectionError as e:
            logger.error(f"Claude connection error: {e}")
            return {**result_template, "error": "connection_error"}
        except Exception as e:
            logger.exception("Error inesperado llamando a Claude")
            return {**result_template, "error": f"unexpected: {type(e).__name__}: {e!s}"[:300]}

        usage = response.usage
        input_tokens  = usage.input_tokens or 0
        output_tokens = usage.output_tokens or 0
        cache_read    = getattr(usage, "cache_read_input_tokens", 0) or 0
        # cache_creation_input_tokens cuesta 1.25× input, pero por simplicidad
        # lo contabilizamos como input regular en el costo estimado — la
        # diferencia es marginal y no superamos el cap por eso.
        cost = estimate_cost_usd(self.model, input_tokens, output_tokens)

        if cost > self.max_cost:
            logger.warning(
                f"Llamada a Claude costó ${cost:.4f}, supera el cap "
                f"${self.max_cost:.2f} — revisar tamaño del prompt."
            )

        # Extraer texto. Sonnet 4.6 con json_schema devuelve un solo TextBlock.
        raw_text: Optional[str] = None
        for block in response.content:
            if block.type == "text":
                raw_text = block.text
                break

        # #TECH-005: distinguir JSON malformado de respuesta TRUNCADA por
        # max_tokens. stop_reason='max_tokens' ⇒ el modelo se quedó sin budget y
        # cortó el JSON a media string (el caso NVDA→GLD del 26-may: corte en
        # char 6002 con max_tokens=2000). El error tipificado deja diagnóstico
        # claro en logs (el caller debe subir max_tokens, no es JSON inválido).
        truncated = response.stop_reason == "max_tokens"

        parsed: Optional[dict] = None
        if raw_text:
            try:
                import json
                parsed = json.loads(raw_text)
            except (ValueError, TypeError) as e:
                if truncated:
                    logger.error(
                        f"Respuesta de Claude TRUNCADA por max_tokens={max_tokens} "
                        f"(stop_reason=max_tokens) → JSON incompleto. Subir max_tokens "
                        f"del caller. raw[-120:]={raw_text[-120:]!r}"
                    )
                else:
                    logger.error(f"No se pudo parsear JSON de Claude: {e} | raw={raw_text[:300]}")

        if parsed is not None:
            error = None
        elif truncated:
            error = "truncated_max_tokens"
        else:
            error = "parse_failed"

        return {
            "success":           parsed is not None,
            "parsed":            parsed,
            "raw_text":          raw_text,
            "input_tokens":      input_tokens,
            "output_tokens":     output_tokens,
            "cache_read_tokens": cache_read,
            "cost_usd":          cost,
            "model":             self.model,
            "stop_reason":       response.stop_reason,
            "error":             error,
        }

    async def close(self):
        """Cierra el cliente HTTP subyacente. Llamar al shutdown del bot."""
        try:
            await self.client.close()
        except Exception as e:
            logger.debug(f"Error al cerrar cliente Anthropic: {e}")
