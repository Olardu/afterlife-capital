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
#
# Índice de secciones (§) — buscables con "§ N":
#   § 1 — Imports y configuración (arriba de este bloque)
#   § 2 — Prompts (system/user) + helpers de formato
#   § 3 — Filtro técnico de elegibilidad (defensa post-Claude)
#   § 4 — Universe Selector (clase UniverseSelector)

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from claude_client import ClaudeClient
from config import (
    DECAY_THRESHOLD_SHARPE,
    DECAY_THRESHOLD_WIN_RATE,
    THESIS_FEEDBACK_LIMIT,
    THESIS_TRACKING_ENABLED,
    UNIVERSE_SELECTION_CANDIDATE_TTL_DAYS,
    WARNING_THRESHOLD_SHARPE,
    WARNING_THRESHOLD_WIN_RATE,
    WARMUP_TRADES_REQUIRED,
)
from investment_thesis import build_feedback_block


logger = logging.getLogger("sentinel.universe_selector")


# Lista negra de productos prohibidos para rotación (defensa en código).
# Espejo de la sección "PROHIBIDO PROPONER" del SYSTEM_PROMPT: el prompt es
# prevención (guía a Claude), este set es enforcement. Si Claude propone uno
# a pesar del prompt, `_request_candidate` lo bloquea (fail-cerrada) y deja el
# motivo en rotation_decisions.claude_reasoning para auditoría.
_BLACKLIST = frozenset({
    # Leveraged inverse ETFs
    "SQQQ", "SOXS", "TZA", "SDS", "FAZ",
    # Leveraged long ETFs
    "TQQQ", "UPRO", "SPXL", "TNA", "FAS",
    # Volatility ETFs/ETNs
    "UVXY", "VIXY", "VXX", "SVXY",
    # Commodity futures con contango/decay
    "USO", "UNG", "DBA",
    # Inverse single-stock
    "BITI", "ETHU",
})


# Trigger idle_timeout (#UNIVERSE-IDLE, v0.6): un ticker asignado que no opera
# hace tiempo es un "zombie inverso" (asignado pero silencioso) — los 3 triggers
# previos (warning/decay/recovery) solo ven tickers que SÍ operaron. El umbral
# de inactividad se calibra por la frecuencia natural de cada estrategia.
_IDLE_TIMEOUT_DAYS: dict[str, int] = {
    "rsi_short":         5,   # mean-reversion alta frecuencia
    "rsi_divergence":    7,   # mean-reversion media frecuencia
    "bollinger_bounce":  5,   # mean-reversion alta frecuencia
    "vwap_reversion":    5,   # intraday, debería operar a diario
    "macd_volume":      10,   # mixto
    "sma_crossover":    14,   # trend-following baja frecuencia natural
    "ema_triple":       14,   # trend-following
    "orb_breakout":     10,   # máx 1 setup/día por diseño
    "bollinger_squeeze": 14,  # squeeze events raros, frecuencia muy baja
}
_IDLE_TIMEOUT_DEFAULT_DAYS = 10  # estrategias fuera de la tabla

# Guard de mercado plano: si el VIX promedio reciente está muy bajo, todos los
# tickers están callados — no es problema del ticker individual, no se rota.
_IDLE_VIX_GUARD_THRESHOLD = 14.0
_IDLE_VIX_GUARD_DAYS = 5

# Ventana de recovery antes de ejecutar la rotación idle: el candidato queda en
# watchlist y solo se ejecuta si el ticker SIGUE idle pasados estos días (da
# chance a que rompa el silencio). El TTL del pending idle es más largo que esta
# ventana para que no expire antes de poder ejecutarse (el pending de warning/
# decay usa el TTL corto estándar; idle necesita sobrevivir hasta la ejecución).
_IDLE_EXECUTE_AFTER_DAYS = 7
_IDLE_PENDING_TTL_DAYS = 14


# =============================================================================
# § 2 — PROMPTS
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

## Análisis fundamental (Equity Research)

Además de la compatibilidad técnica y la diversificación factorial, evalúa la **calidad y el riesgo fundamental** del candidato. El horizonte del sistema es corto (días a semanas, mean-reversion / trend técnico): el análisis fundamental NO busca una tesis de valor de largo plazo, se usa como **filtro de calidad y de riesgo de evento** para evitar activos con deterioro estructural o gap risk inminente.

**Para acciones individuales** (NVDA, AAPL, JPM, etc.), considera con tu conocimiento del mercado:
- **Salud financiera** (señales tipo 10-K/10-Q): tendencia de revenue y earnings, márgenes, nivel de deuda/leverage, generación de caja. Evita nombres con deterioro severo, dilución agresiva o riesgo de going-concern/delisting.
- **Valuación relativa**: múltiplos (P/E, EV/EBITDA, P/S) frente a comparables del sector. Sobrevaluación extrema agrega riesgo de reversión brusca; infravaloración con fundamentales sanos favorece estrategias de reversión.
- **Riesgo de evento**: earnings/guidance inminentes, litigios, eventos regulatorios. Un reporte de resultados dentro del horizonte agrega gap risk que penaliza estrategias intradía/mean-reversion.

**Para ETFs, sectoriales y commodities** (SPY, GLD, XLV, TLT, etc.): NO apliques DCF ni múltiplos de acción individual. El "fundamental" relevante acá es composición/concentración del fondo, expense ratio, liquidez (AUM/volumen) y rol macro (ya cubierto por el marco factorial de arriba).

Documenta este análisis en el campo `fundamental_analysis` del JSON. Si no tenés información fundamental reciente y confiable sobre el candidato (o es un ETF), dilo explícitamente en ese campo en vez de inventar cifras — la honestidad sobre incertidumbre aplica igual acá.

## Restricciones operativas (Alpaca paper trading)

- Universo permitido: US stocks, ETFs (incluyendo GLD, TLT, IEF, sectoriales XL*, commodities ETFs no apalancados), crypto (BTC/USD, ETH/USD, etc.).
- NUNCA propongas el mismo ticker que el actual a menos que sea explícitamente solicitado.
- Si el Sentinel ya falló en tickers correlacionados, propón algo descorrelacionado por construcción, no solo "otro tech que esté funcionando".

### PROHIBIDO PROPONER — lista negra explícita de productos

Estos productos erosionan su valor de forma estructural, independiente de la dirección del subyacente, por lo que NO sirven para estrategias mean-reversion ni trend-following de varios días/semanas:

- **Leveraged inverse ETFs:** SQQQ, SOXS, TZA, SDS, FAZ (decay diario sostenido por reseteo apalancado).
- **Leveraged long ETFs:** TQQQ, UPRO, SPXL, TNA, FAS (mismo decay por reseteo diario).
- **Volatility ETFs/ETNs:** UVXY, VIXY, VXX, SVXY (estructura de futuros con contango drag). Nota: VIXY se usa como señal macro del sistema (cambio %), NUNCA como ticker a operar.
- **Commodity futures funds con decay:** USO, UNG (contango); DBA en menor medida.
- **Inverse single-stock ETFs:** BITI, ETHU y similares (1x/2x inverse de cripto o acción).

### PROHIBIDO PROPONER — por tipo

- **Penny stocks (precio < $10 USD):** liquidez baja, spread alto, riesgo de pump-and-dump.
- **OTC / Pink sheets:** no listados en NYSE/NASDAQ, sin reportes regulares.
- **Baja liquidez:** volumen diario promedio insuficiente para entrada/salida limpia (referencia: < 1M shares, o equivalente en crypto).

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
  "fundamental_analysis": "Para acciones individuales: salud financiera (10-K/10-Q), valuación relativa vs comparables del sector, riesgo de earnings/eventos. Para ETFs/commodities: composición, expense ratio, liquidez (NO DCF). Sé honesto si no hay datos fundamentales confiables.",
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
        # Campo nuevo de la integración Equity Research (T-T Sub-3): análisis
        # fundamental del candidato (salud financiera, valuación relativa,
        # riesgo de evento). Opcional — vacío/honesto para ETFs o sin datos.
        # Persistido concatenado al claude_reasoning (sin cambios de schema DB).
        "fundamental_analysis": {"type": "string"},
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


def _format_pending_watchlist(pending: list[dict]) -> str:
    """
    Renderiza el bloque de coordinación entre Sentinels (#UNIVERSE-COORD).
    Si pending está vacío retorna "" — sin overhead en el prompt.
    """
    if not pending:
        return ""
    header = (
        "\n\n[!] TICKERS PENDIENTES EN WATCHLIST "
        "(reclamados por otros Sentinels en barridos recientes, aún no rotados):\n"
    )
    body = "\n".join(
        f"- {p.get('sentinel_codename','?')} reclamó "
        f"{p.get('proposed_ticker','?')} ({p.get('trigger_reason') or 'pre_decay_warning'})"
        for p in pending
    )
    footer = (
        "\n\nIMPORTANTE: si propones uno de estos tickers, varios Sentinels "
        "terminarán rotando al mismo activo y se anula el beneficio de la "
        "diversificación factorial. Considera alternativas que cubran "
        "ambientes económicos similares pero con tickers distintos. Ejemplos: "
        "si GLD ya está reclamado, GDX (gold miners) o SLV (silver) cubren "
        "Ambientes 1+3; si TLT ya está reclamado, IEF (bonos intermedios) "
        "cubre Ambiente 4 con menor duration; si XLP ya está reclamado, XLV "
        "(healthcare) cubre Ambiente 3 defensivo."
    )
    return header + body + footer


# =============================================================================
# § 3 — FILTRO TÉCNICO DE ELEGIBILIDAD (defensa post-Claude, #UNIVERSE-FILTER)
# =============================================================================

async def _filter_candidate_eligibility(ticker: str, client) -> dict:
    """
    Valida que un ticker pase filtros técnicos básicos antes de proponerlo o
    confirmarlo como rotación: asset existente, ACTIVE, tradable y fractionable
    (Sentinel opera fraccional long-only).

    NO consulta la lista negra de productos exóticos — esa vive en el
    SYSTEM_PROMPT como guía a Claude. Este filtro es la defensa técnica
    complementaria vía Alpaca Assets API (caso defensivo: si Claude propone un
    ticker no operable a pesar del prompt, lo cazamos acá).

    Args:
        ticker: símbolo a verificar (ej. "NVDA").
        client: TradingClient de Alpaca. `get_asset` es síncrono y se corre en
                un thread aparte para no bloquear el loop.

    Returns:
        dict {eligible: bool, reason: str | None, asset: Asset | None}.
    """
    from alpaca.trading.enums import AssetStatus

    try:
        asset = await asyncio.to_thread(client.get_asset, ticker)
    except Exception as e:
        return {"eligible": False, "reason": f"asset_lookup_failed: {e}", "asset": None}

    if asset.status != AssetStatus.ACTIVE:
        return {"eligible": False, "reason": f"not_active: {asset.status}", "asset": asset}
    if not asset.tradable:
        return {"eligible": False, "reason": "not_tradable", "asset": asset}
    if not asset.fractionable:
        return {"eligible": False, "reason": "not_fractionable", "asset": asset}

    # marginable/shortable no son obligatorios hoy (long-only sin margin) — se
    # loguean a debug si faltan, sin bloquear la elegibilidad.
    if not asset.marginable:
        logger.debug(f"{ticker} not_marginable — OK por ahora (long-only sin margin)")
    if not asset.shortable:
        logger.debug(f"{ticker} not_shortable — OK por ahora (long-only)")

    return {"eligible": True, "reason": None, "asset": asset}


# Estrategias que operan en CORTO (#HE-2: la dirección de la tesis condiciona el
# cálculo de MAE/MFE y outcome). El resto del universo de Sentinels es long.
_SHORT_STRATEGY_TYPES = frozenset({"rsi_short", "rsi_divergence"})


def _thesis_direction(strategy_type: Optional[str]) -> str:
    """Dirección de la tesis ('LONG'/'SHORT') según el tipo de estrategia del Sentinel."""
    return "SHORT" if strategy_type in _SHORT_STRATEGY_TYPES else "LONG"


def build_user_prompt(
    *,
    sentinel: dict,
    macro: dict,
    failed_tickers: list[str],
    reason: str,
    portfolio_composition: Optional[list[dict]] = None,
    pending_tickers_in_watchlist: Optional[list[dict]] = None,
    thesis_feedback: str = "",
) -> str:
    win_rate = sentinel.get("win_rate") or 0.0
    sharpe   = sentinel.get("sharpe_ratio") or 0.0
    trades   = sentinel.get("total_trades") or 0
    vix      = macro.get("vix_delta")
    spy      = macro.get("spy_delta")

    portfolio_section = _format_portfolio_composition(portfolio_composition or [])
    pending_section   = _format_pending_watchlist(pending_tickers_in_watchlist or [])
    # Feedback de tesis cerradas (#HE-2 / #ME-2): historial de cómo resultaron las
    # rotaciones previas. Sección vacía si no hay historial o el flag está off.
    feedback_section = f"\n\n{thesis_feedback}" if thesis_feedback else ""

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
{portfolio_section}{pending_section}

TICKERS YA ROTADOS POR ESTE SENTINEL (sin éxito):
{_format_failed(failed_tickers)}{feedback_section}

Propón el mejor ticker de reemplazo siguiendo el schema. Considera explícitamente la diversificación factorial del portafolio agregado (poblá factor_exposure_analysis) y el análisis fundamental del candidato (poblá fundamental_analysis, respetando la distinción acciones individuales vs ETFs/commodities del system prompt) en tu reasoning."""


# =============================================================================
# § 4 — UNIVERSE SELECTOR
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
            "idle":       0,
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

        # 3. Trigger idle_timeout (#UNIVERSE-IDLE): los zombies inversos no
        #    aparecen en performance_scores (nunca operaron), así que se
        #    evalúan recorriendo los Sentinels activos. Mismo flujo que warning:
        #    se pide candidato y queda en watchlist (TTL 7d).
        await self._evaluate_idle_timeout(stats)

        logger.info(
            f"Universe Selection ciclo: evaluated={stats['evaluated']} "
            f"warnings={stats['warning']} rotations={stats['rotations']} "
            f"new_candidates={stats['candidates']} idle={stats['idle']} "
            f"errors={stats['errors']}"
        )
        return stats

    async def _evaluate_idle_timeout(self, stats: dict) -> None:
        """
        Recorre los Sentinels activos buscando tickers idle y, por cada uno sin
        candidato pendiente, pide uno a Claude (trigger_reason='idle_timeout').
        Errores aislados por Sentinel: una falla no detiene a los demás. Muta
        `stats` in-place (idle, candidates, errors).
        """
        try:
            active = await self.historian.get_active_sentinels(self.owner_id)
        except Exception as e:
            logger.warning(f"idle_timeout: get_active_sentinels falló: {e}")
            return

        for s in active:
            sid   = s.get("sentinel_id")
            strat = s.get("strategy_type") or ""
            name  = s.get("name") or "?"
            try:
                idle = await self._check_idle_tickers(sid, strat)
            except Exception as e:
                logger.warning(f"idle_timeout check falló (sentinel={sid}): {e}")
                stats["errors"] += 1
                continue

            idle_set = set(idle)
            stats["idle"] += len(idle)

            # 1. ¿Ya hay un candidato idle pendiente para este Sentinel? Entonces
            #    resolverlo (ejecutar si cumplió la ventana y sigue idle, o
            #    descartar si el ticker recuperó) — no se pide otro (UNIQUE
            #    parcial: un solo 'watching' por Sentinel).
            try:
                idle_pending = await self.historian.get_idle_pending_candidate(sid)
            except Exception as e:
                logger.warning(f"idle_timeout get_idle_pending falló (sentinel={sid}): {e}")
                idle_pending = None

            if idle_pending is not None:
                try:
                    await self._resolve_idle_pending(idle_pending, idle_set, stats)
                except Exception as e:
                    logger.exception(f"idle_timeout resolve falló (sentinel={sid}): {e}")
                    stats["errors"] += 1
                continue

            # 2. Sin pending idle → pedir candidato para el primer ticker idle
            #    (solo uno: el índice UNIQUE permite un 'watching' por Sentinel).
            for ticker in idle:
                try:
                    # No pisar un pending vivo de otro trigger (warning/decay).
                    if await self.historian.get_pending_candidate(sid) is not None:
                        break
                    score = {
                        "sentinel_id":   sid,
                        "ticker":        ticker,
                        "sentinel_name": name,
                        "strategy_type": strat,
                        "win_rate":      None,
                        "sharpe_ratio":  None,
                        "total_trades":  0,
                    }
                    decision_id = await self._request_candidate(
                        score, trigger_reason="idle_timeout",
                    )
                    if decision_id is not None:
                        stats["candidates"] += 1
                except Exception as e:
                    logger.exception(
                        f"idle_timeout _request_candidate falló "
                        f"(sentinel={sid}/{ticker}): {e}"
                    )
                    stats["errors"] += 1
                break  # un solo pending por Sentinel

    async def _resolve_idle_pending(
        self, pending: dict, idle_set: set, stats: dict,
    ) -> None:
        """
        Resuelve un candidato idle pendiente (#UNIVERSE-IDLE):

        - Si el ticker que iba a reemplazar YA NO está idle (rompió el silencio
          dentro de la ventana) → descartar el candidato (recovery).
        - Si SIGUE idle y el pending ya cumplió `_IDLE_EXECUTE_AFTER_DAYS` →
          ejecutar la rotación (un ticker idle nunca cruza decay, así que esta
          es la única vía de ejecución) y descartar el pending ya consumido.
        - Si sigue idle pero el pending es reciente → esperar (no hace nada).

        Muta `stats` in-place (rotations).
        """
        old_ticker   = pending["old_ticker"]
        candidate_id = pending["candidate_id"]
        proposed     = pending["proposed_ticker"]

        if old_ticker not in idle_set:
            await self.historian.discard_pending_candidate(
                candidate_id, reason="idle_recovered",
            )
            logger.info(
                f"idle_timeout recovery: {old_ticker} volvió a operar — "
                f"candidato {proposed} descartado"
            )
            return

        cutoff = datetime.now() - timedelta(days=_IDLE_EXECUTE_AFTER_DAYS)
        if pending["proposed_at"] < cutoff:
            ok = await self.historian.execute_rotation_in_db(pending["decision_id"])
            if ok:
                stats["rotations"] += 1
                await self.historian.discard_pending_candidate(
                    candidate_id, reason="idle_rotation_executed",
                )
                logger.info(
                    f"idle_timeout ejecutado: {old_ticker} → {proposed} "
                    f"(pending {_IDLE_EXECUTE_AFTER_DAYS}d+, sigue idle)"
                )
            else:
                logger.warning(
                    f"idle_timeout: execute_rotation_in_db devolvió False "
                    f"(decision={pending['decision_id']})"
                )

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

        # #HE-2: tesis nueva → ENTRY_READY; tesis del ticker saliente → CLOSED.
        await self._track_rotation_executed(decision_id=decision_id, score=score)

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
    # Trigger idle_timeout (#UNIVERSE-IDLE)
    # ---------------------------------------------------------------------
    async def _check_idle_tickers(
        self,
        sentinel_id: UUID,
        strategy_type: str,
    ) -> list[str]:
        """
        Detecta tickers asignados al Sentinel que no operan hace N días
        (zombies inversos: asignados pero silenciosos). N depende de la
        frecuencia natural de la estrategia (`_IDLE_TIMEOUT_DAYS`).

        Returns:
            Lista de tickers idle. Vacía si: VIX promedio < guard (mercado
            plano), ningún ticker excede su umbral, o el ticker se agregó al
            universo hace menos que el umbral (aún sin tiempo de operar).

        Nota de zona horaria: los timestamps de la DB son naive en hora local
        del server (mismo host que este proceso), así que el cutoff se calcula
        con `datetime.now()` naive — NO UTC-aware — para comparar consistente.
        """
        timeout_days = _IDLE_TIMEOUT_DAYS.get(strategy_type, _IDLE_TIMEOUT_DEFAULT_DAYS)

        # Guard de mercado plano.
        avg_vix = await self.historian.get_avg_vix(days=_IDLE_VIX_GUARD_DAYS)
        if avg_vix is not None and avg_vix < _IDLE_VIX_GUARD_THRESHOLD:
            logger.debug(
                f"idle_timeout suspendido ({strategy_type}): VIX promedio "
                f"{avg_vix:.2f} < {_IDLE_VIX_GUARD_THRESHOLD} (mercado plano)"
            )
            return []

        tickers = await self.historian.get_sentinel_tickers(sentinel_id)
        cutoff = datetime.now() - timedelta(days=timeout_days)
        idle_tickers: list[str] = []

        for ticker in tickers:
            last_trade_at = await self.historian.get_last_trade_timestamp(sentinel_id, ticker)
            if last_trade_at is None:
                # Nunca operó: solo es idle si lleva en el universo más que el
                # umbral (un ticker recién agregado aún no tuvo tiempo).
                added_at = await self.historian.get_ticker_added_at(sentinel_id, ticker)
                if added_at is None or added_at > cutoff:
                    continue
                idle_tickers.append(ticker)
            elif last_trade_at < cutoff:
                idle_tickers.append(ticker)

        if idle_tickers:
            logger.info(
                f"idle_timeout: tickers inactivos en Sentinel {sentinel_id} "
                f"({strategy_type}, umbral {timeout_days}d): {idle_tickers}"
            )
        return idle_tickers

    # ---------------------------------------------------------------------
    # Defensa doble POST-Claude (#UNIVERSE-FILTER)
    # ---------------------------------------------------------------------
    async def _screen_candidate(self, ticker: str) -> Optional[str]:
        """
        Valida un ticker propuesto por Claude antes de aceptarlo como rotación.
        Defensa en dos capas, fail-cerrada:

            1. Lista negra en código (`_BLACKLIST`) — enforcement del prompt.
            2. Elegibilidad técnica vía Alpaca (`_filter_candidate_eligibility`).

        Returns:
            None si el ticker pasa (se puede rotar), o un str con el motivo de
            bloqueo (prefijo `blocked_blacklist` / `blocked_eligibility`) que
            queda registrado para auditoría.
        """
        if ticker.upper() in _BLACKLIST:
            return (
                f"blocked_blacklist: {ticker} está en lista negra "
                f"(leveraged/decay/inverse); Claude lo propuso a pesar del prompt"
            )

        # Cliente Alpaca local por función (patrón del codebase: api.py,
        # dispatcher.py, reconcile_pending_trades). No se inyecta en __init__.
        from alpaca.trading.client import TradingClient
        from config import ALPACA_API_KEY, ALPACA_SECRET_KEY

        client = TradingClient(ALPACA_API_KEY, ALPACA_SECRET_KEY, paper=True)
        eligibility = await _filter_candidate_eligibility(ticker, client)
        if not eligibility["eligible"]:
            return f"blocked_eligibility: {ticker} — {eligibility['reason']}"

        return None

    # ---------------------------------------------------------------------
    # Llamada a Claude
    # ---------------------------------------------------------------------
    # ---------------------------------------------------------------------
    # Investment Thesis Tracking (#HE-2) — flag-gated, error-isolado.
    # Una falla en el tracking NUNCA debe abortar la rotación ni el ciclo.
    # ---------------------------------------------------------------------
    async def _fetch_thesis_feedback(self, sentinel_id: UUID) -> str:
        """
        Bloque de feedback de tesis cerradas para el system prompt (#ME-2).
        '' si el flag está off, no hay historial o falla la consulta.
        """
        if not THESIS_TRACKING_ENABLED:
            return ""
        try:
            closed = await self.historian.get_closed_theses_feedback(
                self.owner_id, sentinel_id=sentinel_id, limit=THESIS_FEEDBACK_LIMIT,
            )
            return build_feedback_block(closed)
        except Exception as e:
            logger.warning(f"thesis feedback falló (prompt sin bloque): {e}")
            return ""

    async def _track_thesis_idea(
        self, *, decision_id: UUID, score: dict, new_ticker: str,
        reasoning: Optional[str], trigger_reason: str,
    ) -> None:
        """Registra la rotación propuesta como tesis IDEA. No bloquea si falla."""
        if not THESIS_TRACKING_ENABLED:
            return
        try:
            await self.historian.save_investment_thesis(
                sentinel_id      = score["sentinel_id"],
                owner_id         = self.owner_id,
                ticker           = new_ticker,
                direction        = _thesis_direction(score.get("strategy_type")),
                decision_id      = decision_id,
                rationale_text   = f"Rotación {score.get('ticker')} → {new_ticker} ({trigger_reason})",
                claude_reasoning = reasoning,
                state            = "IDEA",
            )
        except Exception as e:
            logger.warning(f"track_thesis_idea falló (no bloquea): {e}")

    async def _track_rotation_executed(self, *, decision_id: UUID, score: dict) -> None:
        """
        Al ejecutarse la rotación: la tesis nueva pasa IDEA→ENTRY_READY (ticker ya
        asignado, listo para operar) y la tesis abierta del ticker saliente se
        cierra (postmortem). El new_ticker se lee de la decisión ejecutada (cubre
        candidato pre-aprobado y urgente). El outcome coarse sale del win_rate del
        score; el outcome fino + MAE/MFE quedan para el backfill (#HE-2b). No
        bloquea si falla.
        """
        if not THESIS_TRACKING_ENABLED:
            return
        sentinel_id = score["sentinel_id"]
        old_ticker  = score.get("ticker")
        new_ticker = None
        try:
            full = await self.historian.get_rotation_decision(decision_id)
            if full:
                new_ticker = full.get("new_ticker")
        except Exception as e:
            logger.warning(f"track: get_rotation_decision falló: {e}")

        if new_ticker:
            try:
                new_thesis = await self.historian.find_open_thesis(
                    self.owner_id, sentinel_id, new_ticker)
                if new_thesis is not None:
                    await self.historian.update_thesis_state(
                        UUID(new_thesis["thesis_id"]), "ENTRY_READY")
            except Exception as e:
                logger.warning(f"track ENTRY_READY falló (no bloquea): {e}")
        try:
            old_thesis = await self.historian.find_open_thesis(
                self.owner_id, sentinel_id, old_ticker)
            if old_thesis is not None:
                wr = score.get("win_rate")
                outcome = "win" if (wr is not None and wr >= 0.5) else "loss"
                await self.historian.update_thesis_state(
                    UUID(old_thesis["thesis_id"]), "CLOSED",
                    closed_at=datetime.now(),
                    outcome=outcome,
                    notes=f"Cerrada por rotación → {new_ticker} | win_rate={wr}",
                )
        except Exception as e:
            logger.warning(f"track CLOSE old falló (no bloquea): {e}")

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

            # Coordinación entre Sentinels (#UNIVERSE-COORD). Listamos los
            # pending_candidates 'watching' del owner para que Claude vea
            # qué tickers ya reclamaron otros Sentinels en barridos
            # recientes (incluyendo el actual: si MORPHEUS ya pasó por aquí
            # 30s antes y reclamó GLD, NETRUNNER ahora lo ve). Filtramos
            # el candidato del propio Sentinel para evitar autoreferencia
            # (si ya tenía pending lo descarta el caller antes de llegar acá).
            pending_tickers_in_watchlist: list[dict] = []
            try:
                pending = await self.historian.get_active_pending_candidates(self.owner_id)
                self_name = score.get("sentinel_name") or ""
                for p in pending:
                    if p.get("sentinel_name") == self_name:
                        continue
                    pending_tickers_in_watchlist.append({
                        "sentinel_codename": p.get("sentinel_name"),
                        "proposed_ticker":   p.get("proposed_ticker"),
                        "trigger_reason":    p.get("trigger_reason"),
                    })
            except Exception as e:
                logger.warning(f"get_active_pending_candidates falló: {e}")
                pending_tickers_in_watchlist = []

            # Feedback loop (#HE-2 / #ME-2): historial de tesis cerradas de este
            # Sentinel como contexto para la próxima decisión. '' si flag off.
            thesis_feedback = await self._fetch_thesis_feedback(sentinel_id)

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
                pending_tickers_in_watchlist=pending_tickers_in_watchlist,
                thesis_feedback=thesis_feedback,
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

        # fundamental_analysis es el campo nuevo de la integración Equity
        # Research (T-T Sub-3). Mismo patrón que factor_exposure: lo
        # concatenamos al claude_reasoning (TEXT) para auditar el razonamiento
        # fundamental sin tocar el schema de rotation_decisions.
        fundamental = parsed.get("fundamental_analysis") if result["success"] else None
        if fundamental and reasoning:
            reasoning = f"{reasoning}\n\n[Fundamental analysis]\n{fundamental}"
        elif fundamental and not reasoning:
            reasoning = f"[Fundamental analysis]\n{fundamental}"

        # Defensa doble POST-Claude (#UNIVERSE-FILTER, fail-cerrada): si Claude
        # propuso un ticker pese al prompt, lo bloqueamos en código. El bloqueo
        # se persiste como decisión 'failed' (new_ticker → None) con el motivo
        # en claude_reasoning para auditoría; no se crea pending ni se rota,
        # se reintenta el próximo ciclo.
        block_reason = await self._screen_candidate(new_ticker) if new_ticker else None
        if block_reason is not None:
            logger.error(
                f"Universe Selection: candidato '{new_ticker}' bloqueado "
                f"(sentinel={sentinel_id}/{ticker}) — {block_reason}"
            )
            reasoning = (
                f"[BLOQUEADO POST-Claude: {block_reason}]\n\n{reasoning}"
                if reasoning else f"[BLOQUEADO POST-Claude: {block_reason}]"
            )
            new_ticker = None

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

        # #HE-2: registrar la rotación propuesta como tesis IDEA (flag-gated).
        await self._track_thesis_idea(
            decision_id=decision_id, score=score, new_ticker=new_ticker,
            reasoning=reasoning, trigger_reason=trigger_reason,
        )

        # Si es warning o idle → guardar en watchlist. idle_timeout sigue el
        # mismo flujo que pre_decay_warning, pero con TTL más largo: su
        # ejecución ocurre recién a los _IDLE_EXECUTE_AFTER_DAYS, así que el
        # pending debe sobrevivir esa ventana (con el TTL corto expiraría justo
        # al querer ejecutarlo).
        if trigger_reason in ("pre_decay_warning", "idle_timeout"):
            ttl = (
                _IDLE_PENDING_TTL_DAYS if trigger_reason == "idle_timeout"
                else UNIVERSE_SELECTION_CANDIDATE_TTL_DAYS
            )
            try:
                await self.historian.save_pending_candidate(
                    sentinel_id     = sentinel_id,
                    proposed_ticker = new_ticker,
                    decision_id     = decision_id,
                    ttl_days        = ttl,
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
