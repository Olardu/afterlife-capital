# corporate_actions.py
# #CR-2 (T-S) — Splits y dividendos para el reporte fiscal simulado.
#
# Capa de corporate actions sobre el motor fiscal de #CR-1 (tax_lots). Dos
# efectos sobre el reporte fiscal de paper trading:
#
#   1. SPLITS — un forward/reverse split ajusta los lotes ABIERTOS antes de su
#      ex_date: forward 2:1 duplica las acciones y parte el precio a la mitad
#      (el cost_basis total NO cambia). Sin este ajuste, el FIFO de tax_lots
#      desempareja cantidades (vendés 10 lo que compraste como 1) y abre lotes
#      fantasma. Trato forward y reverse igual: ratio = new_rate / old_rate.
#
#   2. DIVIDENDOS EN EFECTIVO — income fiscal por las acciones long que el bot
#      tenía en la ex_date. Posición SHORT en ex_date ⇒ el bot PAGA el dividendo
#      (payment in lieu) ⇒ se registra como income negativo.
#
# Función PURA (sin DB, sin red) → 100% testeable. Mismo patrón que tax_lots
# (#CR-1) y simulated_costs (#CR-3): el caller (historian/api) trae los datos
# crudos —trades de la DB, corporate actions de la API de Alpaca— y se los pasa
# ya normalizados. NO toca DB ni schema (on-the-fly, decisión Roman 2026-05-25).
#
# Alcance v1 (documentado, ampliable):
#   - normalize_alpaca_ca acepta objetos del SDK alpaca-py (ForwardSplit,
#     ReverseSplit, CashDividend) o dicts equivalentes.
#   - Dividendos: se cuenta la posición neta sobre los trades TAL CUAL (sin
#     ajustar por un split intermedio entre la compra y la ex_date — caso que
#     no ocurre en los datos del período). qualified vs ordinary NO se separa:
#     se reporta el income total como ordinary (el bot opera mean-reversion con
#     holding corto ⇒ casi todo sería ordinary igual). Refinable luego.
#   - El reporte fiscal (tax_report) se calcula sobre los trades YA ajustados
#     por splits, de modo que cierra correcto incluso post-split.

from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP

from tax_lots import compute_tax_report

_ZERO = Decimal("0")
_CENT = Decimal("0.01")


def _attr(item, key):
    """Lee `key` de un objeto (getattr) o de un dict (get). None si no está."""
    if isinstance(item, dict):
        return item.get(key)
    return getattr(item, key, None)


def _to_decimal(x):
    """Normaliza a Decimal; None si no es convertible."""
    if x is None:
        return None
    return Decimal(str(x))


def _as_date(x):
    """Normaliza a date: datetime → su .date(); date → tal cual; None si no aplica."""
    if x is None:
        return None
    return x.date() if hasattr(x, "date") else x


# Tipos de CA del SDK alpaca-py que este módulo consume (el resto se ignora en v1).
_SPLIT_TYPES = ("forward_splits", "reverse_splits")
_DIVIDEND_TYPES = ("cash_dividends",)


def normalize_alpaca_ca(ca_data: dict) -> dict:
    """
    Convierte el `.data` de un CorporateActionsSet de alpaca-py —dict
    {ca_type: [item, ...]}— a la forma simple que consume este módulo:

        {"splits":    [{"symbol", "ex_date", "ratio"}],
         "dividends": [{"symbol", "ex_date", "rate", "special"}]}

    `ratio = new_rate / old_rate` (forward 2:1 → 2.0; reverse 1:2 → 0.5). Cada
    item puede ser un objeto del SDK (atributos) o un dict equivalente. Entradas
    sin los campos mínimos o con ratio no positivo se descartan.
    """
    splits, dividends = [], []
    ca_data = ca_data or {}

    for ca_type in _SPLIT_TYPES:
        for it in ca_data.get(ca_type, []):
            symbol = _attr(it, "symbol")
            ex_date = _as_date(_attr(it, "ex_date"))
            new_rate = _to_decimal(_attr(it, "new_rate"))
            old_rate = _to_decimal(_attr(it, "old_rate"))
            if not symbol or ex_date is None or not new_rate or not old_rate or old_rate <= 0:
                continue
            ratio = new_rate / old_rate
            if ratio <= 0:
                continue
            splits.append({"symbol": symbol, "ex_date": ex_date, "ratio": ratio})

    for ca_type in _DIVIDEND_TYPES:
        for it in ca_data.get(ca_type, []):
            symbol = _attr(it, "symbol")
            ex_date = _as_date(_attr(it, "ex_date"))
            rate = _to_decimal(_attr(it, "rate"))
            if not symbol or ex_date is None or rate is None:
                continue
            dividends.append({
                "symbol": symbol,
                "ex_date": ex_date,
                "rate": rate,
                "special": bool(_attr(it, "special")),
            })

    return {"splits": splits, "dividends": dividends}


def adjust_trades_for_splits(trades, splits) -> list:
    """
    Devuelve una NUEVA lista de trades con qty/price ajustados por los splits
    cuyo ex_date es POSTERIOR al trade (el trade es pre-split, hay que llevarlo a
    unidades post-split). Para un forward 2:1 (ratio 2): qty *= 2, price /= 2 →
    el cost_basis del lote (qty*price) se mantiene. No muta la entrada.

    Cada trade es {ticker, side, qty, price, dt}. Se comparan fechas: un trade
    con `dt` estrictamente anterior al ex_date del split se ajusta; en o después
    del ex_date ya cotiza post-split.
    """
    by_ticker = defaultdict(list)
    for s in splits:
        by_ticker[s["symbol"]].append(s)

    adjusted = []
    for t in trades:
        qty = _to_decimal(t.get("qty"))
        price = _to_decimal(t.get("price"))
        new_t = dict(t)
        if qty is not None and price is not None:
            t_date = _as_date(t.get("dt"))
            for s in by_ticker.get(t.get("ticker"), ()):
                if t_date is not None and t_date < s["ex_date"]:
                    qty = qty * s["ratio"]
                    price = price / s["ratio"]
            new_t["qty"] = qty
            new_t["price"] = price
        adjusted.append(new_t)

    return adjusted


def _net_long_before(trades, ticker, ex_date) -> Decimal:
    """
    Posición neta (BUY - SELL, en acciones) de `ticker` ANTES de `ex_date`.
    Positiva = long (cobra dividendo), negativa = short (lo paga en lieu).
    """
    net = _ZERO
    for t in trades:
        if t.get("ticker") != ticker:
            continue
        t_date = _as_date(t.get("dt"))
        if t_date is None or t_date >= ex_date:
            continue
        qty = _to_decimal(t.get("qty"))
        if qty is None:
            continue
        net += qty if t.get("side") == "BUY" else -qty
    return net


def compute_dividend_income(trades, dividends) -> dict:
    """
    Income por dividendos en efectivo: para cada dividendo, cuenta la posición
    neta del ticker en la ex_date. Long (>0) ⇒ income = shares * rate; short
    (<0) ⇒ income negativo (el bot paga el dividendo, "in lieu"); flat ⇒ se
    omite. Montos en Decimal exacto, redondeo único a centavos en el total.

    Returns {"items": [{symbol, ex_date(ISO), rate, shares, amount, special}],
             "total_income": float, "n_events": int}.
    """
    items = []
    total = _ZERO
    for d in dividends:
        shares = _net_long_before(trades, d["symbol"], d["ex_date"])
        if shares == 0:
            continue
        amount = shares * d["rate"]
        total += amount
        items.append({
            "symbol": d["symbol"],
            "ex_date": d["ex_date"].isoformat(),
            "rate": float(d["rate"]),
            "shares": float(shares),
            "amount": float(amount.quantize(_CENT, rounding=ROUND_HALF_UP)),
            "special": d.get("special", False),
        })

    return {
        "items": items,
        "n_events": len(items),
        "total_income": float(total.quantize(_CENT, rounding=ROUND_HALF_UP)),
    }


def _splits_applied(trades, splits) -> list:
    """Splits que efectivamente ajustan algún lote (hay trades pre-ex_date)."""
    applied = []
    for s in splits:
        affects = any(
            t.get("ticker") == s["symbol"]
            and _as_date(t.get("dt")) is not None
            and _as_date(t.get("dt")) < s["ex_date"]
            for t in trades
        )
        applied.append({
            "symbol": s["symbol"],
            "ex_date": s["ex_date"].isoformat(),
            "ratio": float(s["ratio"]),
            "affected_trades": affects,
        })
    return applied


def build_corporate_actions_report(trades, ca) -> dict:
    """
    Reporte de corporate actions sobre los trades FILLED de un owner.

    `ca` es la salida de normalize_alpaca_ca: {"splits": [...], "dividends": [...]}.
    Ajusta los trades por splits, recalcula el reporte fiscal (tax_lots) sobre los
    trades ajustados —correcto post-split—, y computa el income por dividendos
    sobre la posición real del bot en cada ex_date.

    Returns {"dividends": {...}, "splits": [...], "tax_report": {...}}.
    """
    ca = ca or {"splits": [], "dividends": []}
    splits = ca.get("splits", [])
    dividends = ca.get("dividends", [])

    adjusted = adjust_trades_for_splits(trades, splits)
    return {
        "dividends": compute_dividend_income(trades, dividends),
        "splits": _splits_applied(trades, splits),
        "tax_report": compute_tax_report(adjusted),
    }
