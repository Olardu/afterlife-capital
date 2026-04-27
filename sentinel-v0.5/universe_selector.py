# universe_selector.py
# Módulo principal de Universe Selection (#UNIVERSE-SELECTION).
#
# Reemplaza tickers degradados de cada Sentinel usando Claude Sonnet 4.6,
# combinando:
#   - Estado de performance del Sentinel (decay/warning, win_rate, sharpe).
#   - Contexto macro reciente (risk_score, VIX/SPY, top titulares).
#   - Histórico de tickers que ya fallaron en este Sentinel.
#
# Modo de operación: COMPLETAMENTE AUTOMÁTICO (Modo A).
# - Pre-decay (warning): pide candidato pero queda en watchlist (TTL 7 días).
# - Decay confirmado: si hay candidato en watchlist → activa. Si no → request
#   urgente y rotación inmediata.
# - Toda decisión queda loggeada en rotation_decisions con costo USD.
# - Email automático al admin en cada ejecución.
#
# Errores en este módulo NUNCA crashean el bot — todos los flujos críticos
# están aislados con try/except. main.py lo llama bajo timeout adicional.

import asyncio
import json
import logging
from typing import Optional
from uuid import UUID

from claude_client import ClaudeClient
from config import (
    DECAY_THRESHOLD_SHARPE,
    DECAY_THRESHOLD_WIN_RATE,
    UNIVERSE_SELECTION_CANDIDATE_TTL_DAYS,
    WARNING_THRESHOLD_SHARPE,
    WARNING_THRESHOLD_WIN_RATE,
    WARMUP_TRADES_REQUIRED,
)


logger = logging.getLogger("sentinel.universe_selector")


# =============================================================================
# PROMPTS
# =============================================================================

SYSTEM_PROMPT = """Eres un analista cuantitativo experto especializado en selección de activos para estrategias algorítmicas de trading retail. Tu rol es proponer activos óptimos para una estrategia específica, balanceando dos objetivos:

1. **Compatibilidad estadística** entre el activo y el tipo de estrategia técnica.
2. **Diversificación factorial del portafolio agregado** — exposición balanceada a regímenes económicos distintos.

## Criterios de compatibilidad por tipo de estrategia

- **Trend Following** (sma_crossover, ema_triple, macd_volume): activos con tendencias direccionales claras, ADX > 25, volumen estable, beta moderado-alto.
- **Mean Reversion** (rsi_short, bollinger_bounce, vwap_reversion): activos que oscilan en rangos predecibles, Hurst < 0.5, baja autocorrelación direccional.
- **Breakout** (orb_breakout, bollinger_squeeze): activos con compresión de volatilidad seguida de expansiones, BBW en percentil bajo.
- **Reversal** (rsi_divergence): activos con sobreextensiones técnicas frecuentes y mean-reversion en timeframes intermedios.

## Marco de diversificación factorial (Bridgewater All Weather, AQR)

Los activos financieros responden a 4 ambientes económicos posibles según crecimiento (G) e inflación (I):

| Ambiente | Crecimiento | Inflación | Activos favorecidos                                       |
|---|---|---|---|
| 1 | G ↑ | I ↑ | Commodities, oro (GLD), TIPS, equity con pricing power     |
| 2 | G ↑ | I ↓ | Equity growth (QQQ, tech), corporate credit                |
| 3 | G ↓ | I ↑ | Oro (GLD), commodities, TIPS, equity defensivo (XLP, XLV)  |
| 4 | G ↓ | I ↓ | Bonos largos (TLT), bonos intermedios (IEF), defensivo     |

Cuando recibas información del portafolio actual del sistema (composición de tickers en otros Sentinels), evalúa explícitamente:

- ¿Está el portafolio sobreexpuesto a un solo ambiente económico? (ej: SPY/QQQ + tech individual = sobreexposición a Ambiente 2)
- ¿Hay regímenes sin cubrir? (ej: nada de oro/commodities = ciego al Ambiente 3)
- ¿La estrategia del Sentinel tiene afinidad técnica con activos que cubrirían un régimen subexpuesto?

Si la compatibilidad estadística es similar entre dos candidatos, **prefiere el que mejora la diversificación factorial del portafolio agregado**. Esto significa que a veces un candidato técnicamente "menos óptimo" pero estructuralmente descorrelacionado es la mejor recomendación. La decorrelación honesta requiere clases de activos distintas, no solo símbolos distintos sobre la misma clase.

## Restricciones operativas (Alpaca paper trading)

- Universo permitido: US stocks, ETFs (incluyendo GLD, TLT, IEF, VIXY, sectoriales XL*, commodities ETFs), crypto (BTC/USD, ETH/USD, etc.).
- NUNCA propongas penny stocks (precio < $10 USD).
- NUNCA propongas activos con volumen diario promedio < 1M shares (o equivalente en crypto).
- NUNCA propongas el mismo ticker que el actual a menos que sea explícitamente solicitado.
- Si el Sentinel ya falló en tickers correlacionados, propón algo descorrelacionado por construcción, no solo "otro tech que esté funcionando".

## Formato de respuesta

Devuelve SIEMPRE un JSON válido con esta estructura exacta:

{
  "recommended_ticker": "SYMBOL",
  "candidates": [
    {"ticker": "SYM1", "confidence": 0.85, "reason": "explicación corta incluyendo factor económico que cubre"},
    {"ticker": "SYM2", "confidence": 0.72, "reason": "explicación corta"},
    {"ticker": "SYM3", "confidence": 0.60, "reason": "explicación corta"}
  ],
  "overall_confidence": 0.85,
  "reasoning": "Análisis detallado: (1) compatibilidad técnica con el tipo de estrategia, (2) cómo afecta la diversificación del portafolio agregado, (3) por qué este ticker en este momento macro.",
  "factor_exposure_analysis": "Breve análisis: qué ambiente económico cubre la recomendación, qué ambientes ya están cubiertos por el portafolio, qué ambientes quedan descubiertos.",
  "risks": ["riesgo 1", "riesgo 2"],
  "expected_horizon_days": 30
}

## Honestidad sobre incertidumbre

Si el contexto macro es ambiguo o las opciones son todas marginales, dilo. Es mejor `recommended_ticker: null` con explicación honesta que forzar una recomendación débil. El sistema operador (Afterlife Capital) prefiere transparencia sobre confianza fingida.

No agregues texto fuera del JSON."""


_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "recommended_ticker": {
            "type": ["string", "null"],
            "description": "Symbol del ticker propuesto. Null si no hay candidato adecuado.",
        },
        "candidates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "ticker":     {"type": "string"},
                    "confidence": {"type": "number"},
                    "reason":     {"type": "string"},
                },
                "required": ["ticker", "confidence", "reason"],
                "additionalProperties": False,
            },
        },
        "overall_confidence": {"type": "number"},
        "reasoning":          {"type": "string"},
        # Campo nuevo del marco All Weather/AQR — qué ambiente económico
        # cubre la recomendación y cuáles quedan descubiertos. Persistido
        # concatenado al claude_reasoning en rotation_decisions (sin
        # cambios de schema en DB).
        "factor_exposure_analysis": {"type": "string"},
        "risks":              {"type": "array", "items": {"type": "string"}},
        "expected_horizon_days": {"type": "integer"},
    },
    "required": ["recommended_ticker", "candidates", "overall_confidence", "reasoning"],
    "additionalProperties": False,
}


def _format_news(titles: list[dict]) -> str:
    if not titles:
        return "(sin titulares macro relevantes en las últimas 6h)"
    lines = []
    for t in titles[:5]:
        title = t.get("title", "").strip()
        source = t.get("source", "?")
        kws = ", ".join(t.get("matched_keywords", []) or [])
        suffix = f" [{kws}]" if kws else ""
        lines.append(f"- {title} ({source}){suffix}")
    return "\n".join(lines)


def _format_failed(tickers: list[str]) -> str:
    if not tickers:
        return "(ninguno — primer evaluación)"
    return ", ".join(tickers[:20])


# Buckets de clasificación factorial usados para el resumen automático del
# portafolio. Lista no exhaustiva — los buckets cubren la composición típica
# que esperamos en los 9 Sentinels al 2026-04. Tickers fuera de esta tabla
# caen en "otros" (no clasificados). Mantener en sincronía con los activos
# que aparezcan en producción.
_FACTOR_BUCKETS: dict[str, set[str]] = {
    "broad_market":      {"SPY", "QQQ", "IWM", "DIA", "VTI", "VOO"},
    "tech_individual":   {"NVDA", "AMD", "MSFT", "GOOGL", "GOOG", "META", "AAPL",
                          "TSLA", "AMZN", "NFLX", "AVGO", "CRM", "ORCL", "ADBE",
                          "INTC", "QCOM", "AMAT"},
    "gold_commodities":  {"GLD", "GDX", "SLV", "IAU", "SLVO", "USO", "DBA", "DBC",
                          "PALL", "PPLT"},
    "bonds_long":        {"TLT", "ZROZ", "EDV"},
    "bonds_intermediate":{"IEF", "AGG", "BND", "LQD", "HYG", "TIP"},
    "defensive_sectors": {"XLP", "XLV", "XLU"},
    "volatility":        {"VIXY", "VXX", "UVXY", "SVXY"},
    "crypto":            {"BTC/USD", "ETH/USD", "BTCUSD", "ETHUSD"},
    "energy":            {"XLE", "XOP", "USO", "UNG"},
    "financials":        {"XLF", "KRE", "JPM", "BAC", "GS", "MS"},
    "healthcare":        {"XLV", "JNJ", "UNH", "PFE", "MRK"},
    "international":     {"EFA", "EEM", "VEA", "VWO", "IEMG"},
}


def _classify_ticker(ticker: str) -> str:
    """Devuelve el bucket factorial al que pertenece el ticker, o 'otros'."""
    if not ticker:
        return "otros"
    t = ticker.upper().strip()
    for bucket, tickers in _FACTOR_BUCKETS.items():
        if t in tickers:
            return bucket
    return "otros"


def _format_portfolio_composition(portfolio: list[dict]) -> str:
    """
    Renderiza una lista de Sentinels con sus tickers + un resumen automático
    de concentración factorial. portfolio es lista de
    {sentinel_codename, current_ticker, strategy_type}; si un Sentinel tiene
    múltiples tickers activos el caller los aplana en filas separadas.
    """
    if not portfolio:
        return "(sin información del portafolio agregado)"

    lines = []
    bucket_counts: dict[str, int] = {}
    for entry in portfolio:
        codename = entry.get("sentinel_codename", "?")
        ticker   = entry.get("current_ticker", "?")
        strategy = entry.get("strategy_type", "?")
        lines.append(f"  {codename} ({strategy}) -> {ticker}")
        bucket = _classify_ticker(ticker)
        bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1

    body = "\n".join(lines)

    # Resumen automático ordenado por count DESC para que la concentración
    # sea evidente (máxima primero).
    if bucket_counts:
        ordered = sorted(bucket_counts.items(), key=lambda kv: kv[1], reverse=True)
        summary = ", ".join(f"{count}× {bucket}" for bucket, count in ordered)
        body += f"\n\n[Resumen automático de exposición: {summary}]"
    return body


def build_user_prompt(
    *,
    sentinel: dict,
    macro: dict,
    failed_tickers: list[str],
    reason: str,
    portfolio_composition: Optional[list[dict]] = None,
) -> str:
    win_rate = sentinel.get("win_rate") or 0.0
    sharpe   = sentinel.get("sharpe_ratio") or 0.0
    trades   = sentinel.get("total_trades") or 0
    vix      = macro.get("vix_delta")
    spy      = macro.get("spy_delta")

    portfolio_section = _format_portfolio_composition(portfolio_composition or [])

    return f"""Necesito reemplazar el ticker para el siguiente Sentinel.

DISPARADOR: {reason}

SENTINEL:
- Codename: {sentinel.get('name', '?')}
- Tipo de estrategia: {sentinel.get('strategy_type', '?')}

TICKER ACTUAL (degradando):
- Symbol: {sentinel.get('ticker', '?')}
- Win rate: {win_rate:.2%}
- Sharpe ratio (anualizado): {sharpe:.2f}
- Total trades: {trades}

CONTEXTO DE MERCADO (últimas 6h):
- Régimen actual: NEUTRAL (S-10 RegimeClassifier desactivado por accuracy bajo)
- Risk score (The Ear): {macro.get('risk_score', 0.0):.2f}
- Circuit breaker: {macro.get('circuit_breaker', False)}
- VIXY cambio promedio (15min): {f'{vix:+.2f}%' if vix is not None else 'n/a'}
- SPY cambio promedio (15min): {f'{spy:+.2f}%' if spy is not None else 'n/a'}

NOTICIAS RELEVANTES:
{_format_news(macro.get('recent_titles', []))}

PORTAFOLIO AGREGADO (composición actual de los Sentinels activos):
{portfolio_section}

TICKERS YA ROTADOS POR ESTE SENTINEL (sin éxito):
{_format_failed(failed_tickers)}

Propón el mejor ticker de reemplazo siguiendo el schema. Considera explícitamente la diversificación factorial del portafolio agregado en tu reasoning y poblá el campo factor_exposure_analysis."""


# =============================================================================
# UNIVERSE SELECTOR
# =============================================================================

class UniverseSelector:
    """
    Coordina la rotación automática de tickers para los Sentinels del owner.

    Ciclo (llamado desde main_loop):
        1. Expira pending_candidates con TTL vencido.
        2. Para cada Sentinel, evalúa cada (sentinel, ticker):
           a. Calcula warning_in (pre-decay) y decay_in (decay confirmado).
           b. Persiste warning_status.
           c. Si decay confirmado → ejecuta rotación (con candidato pendiente
              o pidiendo nuevo a Claude inmediatamente).
           d. Si solo warning + sin candidato pendiente → pide candidato a Claude.
           e. Si recuperó performance + tiene candidato → descarta.
        3. Errores aislados: una falla en un Sentinel no detiene a los demás.
    """

    def __init__(
        self,
        *,
        historian,
        claude_client: ClaudeClient,
        owner_id: UUID,
        email_sender=None,   # async fn(decision: dict) → bool. None deshabilita email.
    ):
        self.historian     = historian
        self.claude        = claude_client
        self.owner_id      = owner_id
        self.email_sender  = email_sender
        self._sem          = asyncio.Semaphore(1)   # serializa llamadas a Claude

    # ---------------------------------------------------------------------
    # Entry point
    # ---------------------------------------------------------------------
    async def evaluate_all_sentinels(self) -> dict:
        """
        Ejecuta un ciclo completo. Retorna un resumen estadístico para
        loggeo: cuántos Sentinels se evaluaron, cuántos warning, cuántas
        rotaciones, costo total USD.
        """
        stats = {
            "evaluated":  0,
            "warning":    0,
            "rotations":  0,
            "candidates": 0,
            "errors":     0,
            "cost_usd":   0.0,
        }

        # 1. Expirar pending_candidates con TTL vencido
        try:
            await self.historian.expire_old_pending_candidates()
        except Exception as e:
            logger.warning(f"expire_old_pending_candidates falló: {e}")

        # 2. Listar performance scores del owner — la fuente de verdad
        try:
            scores = await self.historian.get_sentinel_scores(self.owner_id)
        except Exception as e:
            logger.error(f"No se pudo obtener sentinel_scores: {e}")
            stats["errors"] += 1
            return stats

        for score in scores:
            stats["evaluated"] += 1
            try:
                action = await self._evaluate_one(score)
                if action == "rotation":
                    stats["rotations"] += 1
                elif action == "candidate":
                    stats["candidates"] += 1
                elif action == "warning":
                    stats["warning"] += 1
            except Exception as e:
                logger.exception(
                    f"Universe Selection error en sentinel={score.get('sentinel_id')} "
                    f"ticker={score.get('ticker')}: {e}"
                )
                stats["errors"] += 1

        logger.info(
            f"Universe Selection ciclo: evaluated={stats['evaluated']} "
            f"warnings={stats['warning']} rotations={stats['rotations']} "
            f"new_candidates={stats['candidates']} errors={stats['errors']}"
        )
        return stats

    # ---------------------------------------------------------------------
    # Evaluación por (sentinel_id, ticker)
    # ---------------------------------------------------------------------
    async def _evaluate_one(self, score: dict) -> Optional[str]:
        """
        Procesa un performance_score row. Retorna:
            'rotation'  — se ejecutó una rotación
            'candidate' — se generó un pending_candidate (warning sin decay)
            'warning'   — solo se persistió warning, sin acciones
            None        — sin warning ni decay
        """
        sentinel_id = score["sentinel_id"]
        ticker      = score["ticker"]
        win_rate    = score.get("win_rate") or 0.0
        sharpe      = score.get("sharpe_ratio") or 0.0
        trades      = score.get("total_trades") or 0

        # No evaluar Sentinels sin historia suficiente.
        if trades < WARMUP_TRADES_REQUIRED:
            return None

        in_warning = (
            win_rate < WARNING_THRESHOLD_WIN_RATE
            or sharpe < WARNING_THRESHOLD_SHARPE
        )
        in_decay = (
            win_rate < DECAY_THRESHOLD_WIN_RATE
            or sharpe < DECAY_THRESHOLD_SHARPE
        )

        try:
            await self.historian.update_warning_status(
                sentinel_id, ticker, win_rate, sharpe,
                WARNING_THRESHOLD_WIN_RATE, WARNING_THRESHOLD_SHARPE,
            )
        except Exception as e:
            logger.warning(f"update_warning_status falló ({sentinel_id},{ticker}): {e}")

        # Caso 1: decay confirmado → rotar
        if in_decay:
            return await self._handle_decay(score)

        # Caso 2: warning sin decay → asegurar pending_candidate
        if in_warning:
            return await self._handle_warning(score)

        # Caso 3: salió del warning → descartar candidato pendiente
        try:
            existing = await self.historian.get_pending_candidate(sentinel_id)
            if existing is not None:
                await self.historian.discard_pending_candidate(
                    existing["candidate_id"],
                    reason="performance_recovered",
                )
                logger.info(
                    f"Sentinel {sentinel_id}/{ticker} recuperó performance "
                    f"— candidato {existing['proposed_ticker']} descartado"
                )
        except Exception as e:
            logger.warning(f"discard recovery candidate falló: {e}")

        return None

    # ---------------------------------------------------------------------
    # WARNING: pedir candidato si no existe
    # ---------------------------------------------------------------------
    async def _handle_warning(self, score: dict) -> Optional[str]:
        sentinel_id = score["sentinel_id"]

        existing = await self.historian.get_pending_candidate(sentinel_id)
        if existing is not None:
            # Ya hay candidato vigente — no gastamos otra llamada a Claude.
            return "warning"

        decision_id = await self._request_candidate(
            score, trigger_reason="pre_decay_warning",
        )
        if decision_id is None:
            return "warning"
        return "candidate"

    # ---------------------------------------------------------------------
    # DECAY: ejecutar rotación
    # ---------------------------------------------------------------------
    async def _handle_decay(self, score: dict) -> Optional[str]:
        sentinel_id = score["sentinel_id"]

        candidate = await self.historian.get_pending_candidate(sentinel_id)

        if candidate is not None and candidate.get("decision_id"):
            # Candidato pre-aprobado — ejecutar directo.
            decision_id = candidate["decision_id"]
            logger.info(
                f"Decay confirmado: ejecutando candidato pre-aprobado "
                f"sentinel={sentinel_id} → {candidate['proposed_ticker']}"
            )
        else:
            # Sin candidato — request urgente.
            decision_id = await self._request_candidate(
                score, trigger_reason="decay_confirmed",
            )
            if decision_id is None:
                logger.warning(
                    f"Decay sentinel={sentinel_id} pero Claude no propuso "
                    f"candidato — rotación omitida este ciclo"
                )
                return "warning"

        # Ejecutar atomicamente
        try:
            ok = await self.historian.execute_rotation_in_db(decision_id)
        except Exception as e:
            logger.error(f"execute_rotation_in_db lanzó excepción: {e}")
            ok = False

        if not ok:
            try:
                await self.historian.discard_rotation_decision(
                    decision_id, reason="execute_rotation_failed",
                )
            except Exception:
                pass
            return "warning"

        # Notificar por email (best-effort)
        if self.email_sender is not None:
            try:
                full = await self.historian.get_rotation_decision(decision_id)
                if full:
                    await self.email_sender(full)
            except Exception as e:
                logger.warning(f"email rotación falló (no bloquea): {e}")

        return "rotation"

    # ---------------------------------------------------------------------
    # Llamada a Claude
    # ---------------------------------------------------------------------
    async def _request_candidate(
        self,
        score: dict,
        *,
        trigger_reason: str,
    ) -> Optional[UUID]:
        """
        Pide a Claude un candidato. Persiste rotation_decision (incluso si
        Claude falla — para auditoría). Si trigger_reason == 'pre_decay_warning'
        además crea el pending_candidate.

        Returns:
            decision_id si hubo respuesta válida con new_ticker, None en otro caso.
        """
        sentinel_id = score["sentinel_id"]
        ticker      = score["ticker"]

        # Serializamos las llamadas a Claude para no exceder rate limits si
        # varios Sentinels tocan warning en el mismo ciclo.
        async with self._sem:
            try:
                macro = await self.historian.get_recent_macro_context(hours=6)
            except Exception as e:
                logger.warning(f"macro_context falló (usando defaults): {e}")
                macro = {"risk_score": 0.0, "circuit_breaker": False,
                         "vix_delta": None, "spy_delta": None, "recent_titles": []}

            try:
                failed = await self.historian.get_failed_tickers_for_sentinel(sentinel_id)
            except Exception as e:
                logger.warning(f"failed_tickers falló: {e}")
                failed = []

            # Composición del portafolio agregado (#UNIVERSE-FACTOR). Se aplana
            # un Sentinel con varios tickers en filas separadas para que el
            # resumen factorial cuente cada exposición. Reusa get_active_sentinels
            # (no requiere helper nuevo).
            portfolio_composition: list[dict] = []
            try:
                active = await self.historian.get_active_sentinels(self.owner_id)
                for s in active:
                    name = s.get("name") or "?"
                    strat = s.get("strategy_type") or "?"
                    tickers = s.get("tickers") or []
                    if not tickers:
                        portfolio_composition.append({
                            "sentinel_codename": name,
                            "current_ticker":    "(sin ticker)",
                            "strategy_type":     strat,
                        })
                        continue
                    for tk in tickers:
                        portfolio_composition.append({
                            "sentinel_codename": name,
                            "current_ticker":    tk,
                            "strategy_type":     strat,
                        })
            except Exception as e:
                logger.warning(f"get_active_sentinels falló (portafolio vacío): {e}")
                portfolio_composition = []

            user_prompt = build_user_prompt(
                sentinel={
                    "name":          score.get("sentinel_name") or "?",
                    "strategy_type": score.get("strategy_type") or "?",
                    "ticker":        ticker,
                    "win_rate":      score.get("win_rate"),
                    "sharpe_ratio":  score.get("sharpe_ratio"),
                    "total_trades":  score.get("total_trades"),
                },
                macro=macro,
                failed_tickers=failed,
                reason=trigger_reason,
                portfolio_composition=portfolio_composition,
            )

            result = await self.claude.call_json(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=user_prompt,
                response_schema=_RESPONSE_SCHEMA,
                max_tokens=2000,
            )

        # Aún si Claude falló, persistimos la decisión con status='failed'
        # para mantener registro completo (auditoría + métricas de costo).
        parsed = result.get("parsed") or {}
        new_ticker  = parsed.get("recommended_ticker") if result["success"] else None
        candidates  = parsed.get("candidates") if result["success"] else []
        reasoning   = parsed.get("reasoning") if result["success"] else None
        # factor_exposure_analysis es el campo nuevo del marco All Weather/AQR.
        # Lo concatenamos al claude_reasoning antes de persistir para no
        # requerir cambios de schema en rotation_decisions (la columna
        # claude_reasoning es TEXT y soporta payload extendido).
        factor_exposure = parsed.get("factor_exposure_analysis") if result["success"] else None
        if factor_exposure and reasoning:
            reasoning = f"{reasoning}\n\n[Factor exposure analysis]\n{factor_exposure}"
        elif factor_exposure and not reasoning:
            reasoning = f"[Factor exposure analysis]\n{factor_exposure}"
        confidence  = parsed.get("overall_confidence") if result["success"] else None
        status      = "pending" if (result["success"] and new_ticker) else "failed"
        notes       = result.get("error")

        try:
            decision_id = await self.historian.save_rotation_decision(
                sentinel_id          = sentinel_id,
                owner_id             = self.owner_id,
                trigger_reason       = trigger_reason,
                old_ticker           = ticker,
                old_win_rate         = score.get("win_rate"),
                old_sharpe_ratio     = score.get("sharpe_ratio"),
                old_total_trades     = score.get("total_trades"),
                new_ticker           = new_ticker,
                candidates_proposed  = candidates,
                claude_reasoning     = reasoning,
                claude_confidence    = confidence,
                claude_model         = result.get("model"),
                claude_input_tokens  = result.get("input_tokens", 0),
                claude_output_tokens = result.get("output_tokens", 0),
                claude_cost_usd      = result.get("cost_usd", 0.0),
                status               = status,
                notes                = notes,
            )
        except Exception as e:
            logger.error(f"save_rotation_decision falló: {e}")
            return None

        if not result["success"] or not new_ticker:
            logger.warning(
                f"Claude no produjo candidato válido para sentinel={sentinel_id}/{ticker} "
                f"(reason={trigger_reason}, error={notes})"
            )
            return None

        # Si es warning → guardar en watchlist
        if trigger_reason == "pre_decay_warning":
            try:
                await self.historian.save_pending_candidate(
                    sentinel_id     = sentinel_id,
                    proposed_ticker = new_ticker,
                    decision_id     = decision_id,
                    ttl_days        = UNIVERSE_SELECTION_CANDIDATE_TTL_DAYS,
                )
            except Exception as e:
                # Posible UNIQUE violation si race condition — descartamos.
                logger.warning(f"save_pending_candidate falló: {e}")

        return decision_id

    # ---------------------------------------------------------------------
    # Rollback (llamado desde endpoint admin)
    # ---------------------------------------------------------------------
    async def rollback_rotation(self, decision_id: UUID, admin_email: str) -> bool:
        """Wrapper sobre historian.rollback_rotation_in_db con email logging."""
        try:
            return await self.historian.rollback_rotation_in_db(decision_id, admin_email)
        except Exception as e:
            logger.error(f"rollback_rotation falló: {e}")
            return False
