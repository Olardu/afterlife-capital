# investment_thesis.py
# #HE-2 (T-T) — Investment Thesis Tracking.
#
# Tracking estructurado de tesis de inversión del bot: cada propuesta del
# Universe Selector (rotación) nace como una "tesis" que avanza por una state
# machine (IDEA → ENTRY_READY → ACTIVE → CLOSED) y, al cerrar, se evalúa con
# MAE/MFE (Maximum Adverse / Favorable Excursion) y outcome. El conjunto de
# tesis cerradas alimenta el system prompt del Universe Selector como contexto
# histórico (feedback loop, #ME-2).
#
# Función PURA (sin DB, sin red) → 100% testeable (§8.6). Mismo patrón que
# tax_lots.py (#CR-1) y corporate_actions.py (#CR-2): historian/endpoint
# extraen e inyectan las filas ya tipadas (DIP); este módulo no toca DB,
# schema ni Alpaca. Montos/precios en Decimal EXACTO, redondeo único al
# serializar (mismo criterio que tax_lots.summarize).
#
# Adaptado del enfoque de tradermonty/claude-trading-skills (thesis tracking +
# MAE/MFE como postmortem cuantitativo), simplificado al dominio Sentinel.

from decimal import Decimal, ROUND_HALF_UP

# --- State machine -----------------------------------------------------------
STATE_IDEA = "IDEA"                # propuesta del Universe Selector, sin ejecutar
STATE_ENTRY_READY = "ENTRY_READY"  # candidato listo para entrar (watchlist activada)
STATE_ACTIVE = "ACTIVE"            # posición abierta (fill ejecutado)
STATE_CLOSED = "CLOSED"            # posición cerrada o tesis descartada → postmortem

STATES = frozenset({STATE_IDEA, STATE_ENTRY_READY, STATE_ACTIVE, STATE_CLOSED})
TERMINAL_STATES = frozenset({STATE_CLOSED})

# Transiciones permitidas. Una tesis puede descartarse desde IDEA o ENTRY_READY
# (el Sentinel se recupera o el candidato nunca se ejecuta) → va directo a CLOSED.
VALID_TRANSITIONS = {
    STATE_IDEA: frozenset({STATE_ENTRY_READY, STATE_CLOSED}),
    STATE_ENTRY_READY: frozenset({STATE_ACTIVE, STATE_CLOSED}),
    STATE_ACTIVE: frozenset({STATE_CLOSED}),
    STATE_CLOSED: frozenset(),
}

_QUANT = Decimal("0.0001")  # 4 decimales para precio y %
_ZERO = Decimal("0")
_HUNDRED = Decimal("100")


def can_transition(from_state: str, to_state: str) -> bool:
    """True si la transición from_state → to_state es válida en la state machine."""
    return to_state in VALID_TRANSITIONS.get(from_state, frozenset())


def validate_transition(from_state: str, to_state: str) -> str:
    """
    Valida la transición y devuelve `to_state` si es válida. Lanza ValueError si
    algún estado es desconocido o la transición no está permitida. Usar en el
    wire-up del historian antes de un UPDATE de estado.
    """
    if from_state not in STATES:
        raise ValueError(f"Estado origen desconocido: {from_state!r}")
    if to_state not in STATES:
        raise ValueError(f"Estado destino desconocido: {to_state!r}")
    if not can_transition(from_state, to_state):
        raise ValueError(f"Transición inválida: {from_state} → {to_state}")
    return to_state


# --- MAE / MFE ---------------------------------------------------------------

def _to_decimal(value):
    """Convierte a Decimal vía str (evita ruido binario de float). None si no es computable."""
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (ValueError, ArithmeticError):
        return None


def _normalize_direction(direction):
    """LONG/BUY → 'LONG'; SHORT/SELL → 'SHORT'; cualquier otra cosa → None."""
    if not isinstance(direction, str):
        return None
    d = direction.strip().upper()
    if d in ("LONG", "BUY"):
        return "LONG"
    if d in ("SHORT", "SELL"):
        return "SHORT"
    return None


def _bar_high_low(bar):
    """
    Extrae (high, low) Decimal de una barra. Acepta {high, low} o, si faltan,
    un único precio en {close} / {price} (punto sin rango). None si no hay dato.
    """
    if not isinstance(bar, dict):
        return None
    high = _to_decimal(bar.get("high"))
    low = _to_decimal(bar.get("low"))
    if high is not None and low is not None:
        return high, low
    point = _to_decimal(bar.get("close"))
    if point is None:
        point = _to_decimal(bar.get("price"))
    if point is None:
        return None
    return point, point


def _q(value: Decimal) -> float:
    """Redondea a 4 decimales (ROUND_HALF_UP) y devuelve float JSON-safe."""
    return float(value.quantize(_QUANT, rounding=ROUND_HALF_UP))


_ZERO_EXCURSION = {"mae": 0.0, "mfe": 0.0, "mae_pct": 0.0, "mfe_pct": 0.0}


def compute_excursions(direction, entry_price, bars) -> dict:
    """
    Maximum Adverse Excursion (MAE) y Maximum Favorable Excursion (MFE) de una
    tesis durante su holding, a partir de las barras OHLC del período.

    - MAE: peor movimiento EN CONTRA de la posición (magnitud >= 0).
    - MFE: mejor movimiento A FAVOR de la posición (magnitud >= 0).

    LONG: adverso = entry − min(low); favorable = max(high) − entry.
    SHORT: adverso = max(high) − entry; favorable = entry − min(low).
    Ambos se truncan a >= 0 (si el precio nunca fue en contra, MAE = 0).

    Devuelve {mae, mfe, mae_pct, mfe_pct} (precio y % vs entry, 4 decimales).
    Entrada inválida, dirección desconocida o sin barras → todo 0.0 (seguro:
    los errores en runtime nunca deben crashear el bot).
    """
    side = _normalize_direction(direction)
    entry = _to_decimal(entry_price)
    if side is None or entry is None or entry <= 0:
        return dict(_ZERO_EXCURSION)

    highs, lows = [], []
    for bar in bars or ():
        hl = _bar_high_low(bar)
        if hl is None:
            continue
        highs.append(hl[0])
        lows.append(hl[1])
    if not highs:
        return dict(_ZERO_EXCURSION)

    max_high = max(highs)
    min_low = min(lows)
    if side == "LONG":
        adverse = entry - min_low
        favorable = max_high - entry
    else:  # SHORT
        adverse = max_high - entry
        favorable = entry - min_low

    mae = adverse if adverse > _ZERO else _ZERO
    mfe = favorable if favorable > _ZERO else _ZERO
    return {
        "mae": _q(mae),
        "mfe": _q(mfe),
        "mae_pct": _q(mae / entry * _HUNDRED),
        "mfe_pct": _q(mfe / entry * _HUNDRED),
    }


# --- Outcome -----------------------------------------------------------------

def compute_outcome(direction, entry_price, exit_price) -> dict:
    """
    Resultado realizado de una tesis cerrada (por acción, en precio):
    LONG → gain = exit − entry; SHORT → gain = entry − exit.
    Devuelve {gain, gain_pct, outcome} con outcome ∈ {win, loss, breakeven}.
    Entrada inválida → gain 0 / breakeven (seguro).
    """
    side = _normalize_direction(direction)
    entry = _to_decimal(entry_price)
    exit_ = _to_decimal(exit_price)
    if side is None or entry is None or exit_ is None or entry <= 0:
        return {"gain": 0.0, "gain_pct": 0.0, "outcome": "breakeven"}

    gain = (exit_ - entry) if side == "LONG" else (entry - exit_)
    if gain > _ZERO:
        outcome = "win"
    elif gain < _ZERO:
        outcome = "loss"
    else:
        outcome = "breakeven"
    return {"gain": _q(gain), "gain_pct": _q(gain / entry * _HUNDRED), "outcome": outcome}


# --- Summary / feedback dataset ----------------------------------------------

def _avg(values) -> float:
    return _q(sum(_to_decimal(v) or _ZERO for v in values) / Decimal(len(values))) if values else 0.0


def summarize_theses(closed_theses) -> dict:
    """
    Agrega una lista de tesis cerradas (cada una con outcome/gain_pct/mae_pct/
    mfe_pct/holding_days) en métricas para el feedback loop. Lista vacía → ceros.
    """
    n = len(closed_theses)
    if n == 0:
        return {
            "n": 0, "n_wins": 0, "n_losses": 0, "win_rate": 0.0,
            "avg_gain_pct": 0.0, "avg_mae_pct": 0.0, "avg_mfe_pct": 0.0,
            "avg_holding_days": 0.0,
        }
    wins = sum(1 for t in closed_theses if t.get("outcome") == "win")
    losses = sum(1 for t in closed_theses if t.get("outcome") == "loss")
    return {
        "n": n,
        "n_wins": wins,
        "n_losses": losses,
        "win_rate": _q(Decimal(wins) / Decimal(n) * _HUNDRED),
        "avg_gain_pct": _avg([t.get("gain_pct") for t in closed_theses]),
        "avg_mae_pct": _avg([t.get("mae_pct") for t in closed_theses]),
        "avg_mfe_pct": _avg([t.get("mfe_pct") for t in closed_theses]),
        "avg_holding_days": _avg([t.get("holding_days") for t in closed_theses]),
    }


def build_feedback_block(closed_theses, max_examples: int = 5) -> str:
    """
    Construye el bloque de texto (español) que se inyecta al system prompt del
    Universe Selector con el historial de tesis cerradas: agregados + los
    `max_examples` ejemplos más recientes (asume orden cronológico, toma la cola).
    Lista vacía → "" (el caller omite la sección). Pensado para gastar pocos
    tokens: una línea de agregado + una línea por ejemplo.
    """
    if not closed_theses:
        return ""
    s = summarize_theses(closed_theses)
    lines = [
        "## Historial de tesis cerradas (feedback)",
        (
            f"{s['n']} tesis cerradas · win rate {s['win_rate']}% "
            f"({s['n_wins']}W/{s['n_losses']}L) · retorno medio {s['avg_gain_pct']}% · "
            f"MAE medio {s['avg_mae_pct']}% · MFE medio {s['avg_mfe_pct']}% · "
            f"holding medio {s['avg_holding_days']}d."
        ),
        "Ejemplos recientes (ticker · dirección · resultado · retorno% · MAE%/MFE% · días):",
    ]
    for t in list(closed_theses)[-max_examples:]:
        lines.append(
            f"- {t.get('ticker', '?')} · {t.get('direction', '?')} · "
            f"{t.get('outcome', '?')} · {t.get('gain_pct', 0)}% · "
            f"{t.get('mae_pct', 0)}%/{t.get('mfe_pct', 0)}% · {t.get('holding_days', 0)}d"
        )
    return "\n".join(lines)
