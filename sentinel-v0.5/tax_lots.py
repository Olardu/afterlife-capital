# tax_lots.py
# #CR-1 (T-S) — Reporte fiscal simulado para paper trading.
#
# Calcula ganancias/pérdidas realizadas a partir de los fills de `trades`,
# pareando posiciones por FIFO (First-In-First-Out, decisión de Roman 2026-05-25:
# default IRS, simple y auditable). Deriva holding period (short/long-term),
# detecta wash sales (pérdida + recompra dentro de ±30 días) y resume el resultado.
#
# Función PURA (sin DB, sin red) → 100% testeable. Mismo patrón que
# simulated_costs.calculate_fees (#CR-3) y historian._slippage_to_bps (#ME-1):
# historian extrae las filas y se las pasa ya tipadas. NO toca DB ni schema.
#
# Cierra de paso #TD-1: el pareo ingenuo zip(buys, sells) de
# historian.calculate_performance asume ciclos 1:1 alternados y desempareja
# compras parciales. El motor FIFO de acá consume por cantidad exacta.
#
# Alcance v1 (documentado, ampliable):
#   - FIFO firmado: maneja LONG (BUY abre → SELL cierra) y SHORT (SELL abre →
#     BUY cubre); ambos usan gain = proceeds - cost_basis. Los Sentinels S-2 y
#     S-8 operan en corto, así que el caso short es real.
#   - Long-term si holding_days > 365 (aprox. de "más de un año"; no ajusta por
#     la regla IRS de "día siguiente a la adquisición").
#   - Wash sale: se aplica a disposals LONG con pérdida cuando hay una recompra
#     (BUY) del mismo ticker en ±30 días, EXCLUYENDO la compra que abrió el
#     lote. Simplificación: difiere la pérdida COMPLETA (no la prorratea al
#     número de acciones de reemplazo). Wash sale del lado short queda fuera de v1.

from collections import deque
from decimal import Decimal, ROUND_HALF_UP

WASH_SALE_WINDOW_DAYS = 30
LONG_TERM_DAYS = 365  # holding > 365 días → long-term

_ZERO = Decimal("0")
_CENT = Decimal("0.01")


def _norm(qty, price):
    """Normaliza (qty, price) a Decimal. Retorna None si no es computable."""
    if qty is None or price is None:
        return None
    q = Decimal(str(qty))
    p = Decimal(str(price))
    if q <= 0 or p <= 0:
        return None
    return q, p


def match_fifo(trades) -> list:
    """
    Parea los trades FILLED de UN ticker por FIFO firmado y devuelve la lista de
    disposals (cierres de posición). Cada trade es un dict
    {ticker, side, qty, price, dt}; se ordena por `dt` ascendente.

    Inventario FIFO de lotes abiertos (deque): un trade en la misma dirección que
    el inventario abre lote; en dirección opuesta cierra lotes desde el frente
    (FIFO) y, si sobra, abre lote nuevo. LONG = abierto por BUY, SHORT por SELL.

    Disposal: {ticker, direction, qty, proceeds, cost_basis, gain, opened_at,
    closed_at, holding_days, term}. proceeds/cost_basis en Decimal EXACTO (sin
    redondear; el redondeo a centavos se hace recién en summarize). Para un LONG,
    proceeds = qty*precio_venta y cost_basis = qty*precio_compra; para un SHORT,
    proceeds = qty*precio_venta_en_corto y cost_basis = qty*precio_de_cobertura.
    En ambos, gain = proceeds - cost_basis.
    """
    lots = deque()  # cada lote: {direction, qty, price, dt}
    disposals = []

    for t in sorted(trades, key=lambda x: x["dt"]):
        norm = _norm(t.get("qty"), t.get("price"))
        if norm is None:
            continue
        qty, price = norm
        dt = t["dt"]
        ticker = t.get("ticker")
        incoming = "LONG" if t["side"] == "BUY" else "SHORT"

        remaining = qty
        # Cierra lotes de dirección OPUESTA desde el frente (FIFO).
        while remaining > 0 and lots and lots[0]["direction"] != incoming:
            lot = lots[0]
            matched = min(remaining, lot["qty"])
            if lot["direction"] == "LONG":          # SELL cierra un LONG
                sell_price, buy_price = price, lot["price"]
            else:                                   # BUY cubre un SHORT
                sell_price, buy_price = lot["price"], price
            proceeds = matched * sell_price
            cost_basis = matched * buy_price
            opened_at = lot["dt"]
            holding_days = (dt - opened_at).days
            disposals.append({
                "ticker": ticker,
                "direction": lot["direction"],
                "qty": matched,
                "proceeds": proceeds,
                "cost_basis": cost_basis,
                "gain": proceeds - cost_basis,
                "opened_at": opened_at,
                "closed_at": dt,
                "holding_days": holding_days,
                "term": "long" if holding_days > LONG_TERM_DAYS else "short",
            })
            lot["qty"] -= matched
            remaining -= matched
            if lot["qty"] == 0:
                lots.popleft()

        # Lo que sobra abre lote nuevo en la dirección entrante.
        if remaining > 0:
            lots.append({"direction": incoming, "qty": remaining, "price": price, "dt": dt})

    return disposals


def apply_wash_sales(disposals, trades, window_days: int = WASH_SALE_WINDOW_DAYS) -> list:
    """
    Marca wash sales sobre los disposals (muta in-place y los devuelve). Regla:
    un disposal LONG con pérdida (gain < 0) es wash sale si existe una recompra
    (BUY del mismo ticker) dentro de ±window_days de la fecha de cierre,
    EXCLUYENDO la compra que abrió ese mismo lote (no es "reemplazo").

    Agrega a cada disposal: `wash_sale` (bool) y `disallowed_loss` (Decimal >= 0,
    la pérdida diferida — simplificación: la pérdida completa, no prorrateada).
    Los disposals sin pérdida o SHORT quedan wash_sale=False / disallowed_loss=0.
    """
    buys_by_ticker = {}
    for t in trades:
        if t["side"] == "BUY" and _norm(t.get("qty"), t.get("price")) is not None:
            buys_by_ticker.setdefault(t["ticker"], []).append(t["dt"])

    for d in disposals:
        d["wash_sale"] = False
        d["disallowed_loss"] = _ZERO
        if d["direction"] != "LONG" or d["gain"] >= 0:
            continue
        closed = d["closed_at"]
        for buy_dt in buys_by_ticker.get(d["ticker"], ()):
            if buy_dt == d["opened_at"]:          # la compra original no es reemplazo
                continue
            if abs((buy_dt - closed).days) <= window_days:
                d["wash_sale"] = True
                d["disallowed_loss"] = -d["gain"]  # pérdida diferida (positiva)
                break

    return disposals


def summarize(disposals) -> dict:
    """
    Agrega los disposals en un resumen fiscal. Montos en float USD redondeados a
    centavos (ROUND_HALF_UP) — se suma EXACTO en Decimal y se redondea al final
    (mismo criterio que simulated_costs). `net_realized_gain` suma de vuelta las
    pérdidas diferidas por wash sale (no son deducibles en el período).
    """
    realized = short_term = long_term = proceeds = cost_basis = _ZERO
    disallowed = _ZERO
    wash_count = 0
    for d in disposals:
        realized += d["gain"]
        proceeds += d["proceeds"]
        cost_basis += d["cost_basis"]
        if d["term"] == "long":
            long_term += d["gain"]
        else:
            short_term += d["gain"]
        if d.get("wash_sale"):
            wash_count += 1
            disallowed += d.get("disallowed_loss", _ZERO)

    def _usd(x):
        return float(x.quantize(_CENT, rounding=ROUND_HALF_UP))

    return {
        "n_disposals": len(disposals),
        "realized_gain": _usd(realized),
        "short_term_gain": _usd(short_term),
        "long_term_gain": _usd(long_term),
        "total_proceeds": _usd(proceeds),
        "total_cost_basis": _usd(cost_basis),
        "wash_sale_count": wash_count,
        "disallowed_loss_total": _usd(disallowed),
        "net_realized_gain": _usd(realized + disallowed),
    }


def compute_tax_report(trades, window_days: int = WASH_SALE_WINDOW_DAYS) -> dict:
    """
    Reporte fiscal completo sobre una lista de trades FILLED de cualquier ticker.
    Agrupa por ticker (el pareo FIFO y el wash sale son por security), corre el
    motor por grupo y agrega el resumen global.

    Returns {"disposals": [...], "summary": {...}}.
    """
    by_ticker = {}
    for t in trades:
        by_ticker.setdefault(t["ticker"], []).append(t)

    all_disposals = []
    for ticker_trades in by_ticker.values():
        disp = match_fifo(ticker_trades)
        apply_wash_sales(disp, ticker_trades, window_days)
        all_disposals.extend(disp)

    return {"disposals": all_disposals, "summary": summarize(all_disposals)}
