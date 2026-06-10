# deepseek_client.py
# Wrapper async sobre la API de DeepSeek (OpenAI-compatible) para The Ear
# (swap FinBERT→DeepSeek). Encapsula:
#   - POST {base_url}/chat/completions vía aiohttp (ya es dep del proyecto).
#   - response_format=json_object → respuesta JSON parseable sin regex.
#   - temperature=0 (determinismo para clasificación de riesgo).
#   - Cost tracking en USD (pricing DeepSeek V4) y timeout configurable.
#   - Manejo robusto de error — NUNCA crashea el bot. Una llamada que falla
#     loggea y devuelve {"success": False, ...}; el caller (The Ear) cae a
#     last_risk_score, igual que el fallback de NewsAPI hoy.
#
# DIP/testabilidad: el caller inyecta una instancia ya construida (mockeable
# en tests sin red), igual que ClaudeClient en el Universe Selector.

import json
import logging
from typing import Optional

import aiohttp

from config import (
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL,
    DEEPSEEK_MODEL,
    DEEPSEEK_TIMEOUT_SECONDS,
)

logger = logging.getLogger("sentinel.deepseek_client")


# Pricing por 1M tokens (catálogo DeepSeek V4, al 2026-05-30). Si DeepSeek
# cambia precios, actualizar acá. Solo para logging/observabilidad de costo;
# no bloquea nada.
_PRICING_USD_PER_M_TOKENS = {
    "deepseek-v4-flash": {"input": 0.14, "output": 0.28},
    "deepseek-v4-pro":   {"input": 1.74, "output": 3.48},
    "deepseek-chat":     {"input": 0.28, "output": 0.42},
    "deepseek-reasoner": {"input": 0.28, "output": 0.42},
}


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    """Costo en USD para una llamada según el pricing del modelo. 0.0 si desconocido."""
    p = _PRICING_USD_PER_M_TOKENS.get(model)
    if p is None:
        return 0.0
    return (input_tokens * p["input"] / 1_000_000) + (output_tokens * p["output"] / 1_000_000)


class DeepSeekClient:
    """
    Cliente DeepSeek (chat/completions OpenAI-compatible) con timeout, cost
    tracking y manejo de error robusto.

    Uso:
        client = DeepSeekClient()
        result = await client.call_json(system_prompt=SYSTEM, user_prompt=user)
        if result["success"]:
            data = result["parsed"]   # dict ya parseado
        else:
            logger.warning(f"DeepSeek falló: {result['error']}")  # caller → fallback
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model:   Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
    ):
        self.model    = model or DEEPSEEK_MODEL
        self.base_url = (base_url or DEEPSEEK_BASE_URL).rstrip("/")
        self.timeout  = timeout if timeout is not None else DEEPSEEK_TIMEOUT_SECONDS
        self.api_key  = api_key or DEEPSEEK_API_KEY
        if not self.api_key:
            raise RuntimeError(
                "DEEPSEEK_API_KEY no configurada — agregar al .env antes de "
                "habilitar The Ear con DeepSeek."
            )

    async def call_json(
        self,
        *,
        system_prompt: str,
        user_prompt:   str,
        max_tokens:    int = 512,
        temperature:   float = 0.0,
    ) -> dict:
        """
        Llamada a /chat/completions con response_format=json_object.

        Retorna SIEMPRE un dict (nunca lanza):
            {
                "success":       bool,
                "parsed":        dict | None,   # JSON parseado si success
                "raw_text":      str  | None,
                "input_tokens":  int,
                "output_tokens": int,
                "cost_usd":      float,
                "model":         str,
                "error":         str | None,
            }
        """
        result_template = {
            "success":       False,
            "parsed":        None,
            "raw_text":      None,
            "input_tokens":  0,
            "output_tokens": 0,
            "cost_usd":      0.0,
            "model":         self.model,
            "error":         None,
        }

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type":  "application/json",
        }
        body = {
            "model":       self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
            "temperature":     temperature,
            "max_tokens":      max_tokens,
            "response_format": {"type": "json_object"},
            "stream":          False,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url, json=body, headers=headers,
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                ) as resp:
                    status = resp.status
                    if status != 200:
                        snippet = (await resp.text())[:200]
                        logger.warning(f"DeepSeek respondió {status}: {snippet}")
                        return {**result_template, "error": f"http_{status}: {snippet}"}
                    data = await resp.json()
        except aiohttp.ServerTimeoutError:
            logger.warning(f"DeepSeek timeout ({self.timeout}s).")
            return {**result_template, "error": f"timeout_{int(self.timeout)}s"}
        except aiohttp.ClientError as e:
            logger.warning(f"DeepSeek error de red: {e}")
            return {**result_template, "error": f"connection_error: {e!s}"[:200]}
        except Exception as e:
            logger.exception("Error inesperado llamando a DeepSeek")
            return {**result_template, "error": f"unexpected: {type(e).__name__}: {e!s}"[:200]}

        # Parseo de la respuesta OpenAI-compatible.
        try:
            choice   = (data.get("choices") or [{}])[0]
            raw_text = ((choice.get("message") or {}).get("content")) or ""
            finish_reason = choice.get("finish_reason")
        except (AttributeError, IndexError, TypeError) as e:
            logger.error(f"Respuesta de DeepSeek con forma inesperada: {e} | data={str(data)[:200]}")
            return {**result_template, "error": "malformed_response"}

        usage = data.get("usage") or {}
        input_tokens  = int(usage.get("prompt_tokens") or 0)
        output_tokens = int(usage.get("completion_tokens") or 0)
        cost = estimate_cost_usd(self.model, input_tokens, output_tokens)

        parsed: Optional[dict] = None
        if raw_text:
            try:
                parsed = json.loads(raw_text)
            except (ValueError, TypeError) as e:
                logger.error(
                    f"No se pudo parsear JSON de DeepSeek: {e} | "
                    f"finish_reason={finish_reason} | raw={raw_text[:300]}"
                )

        if not isinstance(parsed, dict):
            parsed = None

        # #BUG-DEEPSEEK-TRUNC: tipificar el truncado por max_tokens (mismo
        # patrón que claude_client #TECH-005) — distingue "subir el presupuesto"
        # de "el modelo devolvió JSON inválido".
        if parsed is not None:
            error = None
        elif finish_reason == "length":
            error = "truncated_max_tokens"
        else:
            error = "parse_failed"

        return {
            "success":       parsed is not None,
            "parsed":        parsed,
            "raw_text":      raw_text or None,
            "input_tokens":  input_tokens,
            "output_tokens": output_tokens,
            "cost_usd":      cost,
            "model":         self.model,
            "error":         error,
        }
