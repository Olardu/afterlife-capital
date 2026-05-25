# simulated_costs.py
# #CR-3 (T-S) — Fees realistas simulados para paper trading.
#
# Alpaca paper NO cobra comisiones ni fees regulatorios. Sin simularlos, el
# Sharpe y el P&L de paper son sistemáticamente mejores que los de live, lo que
# distorsiona la evaluación de cara a la Fase 5 (live conservador). Este módulo
# estima los 3 cargos de US equities que se pagan al VENDER, para que el reporte
# pueda mostrar P&L bruto vs P&L neto de fees.
#
# Función PURA (sin DB, sin red) → 100% testeable. Mismo patrón que
# historian._slippage_to_bps (#ME-1).
#
# Tasas (revisar — cambian con el tiempo; centralizadas como constantes abajo):
#   - SEC fee (Section 31): sobre el notional vendido. La SEC la ajusta ~cada
#     trimestre.
#   - FINRA TAF: por acción vendida, con tope por trade.
#   - Exchange/venue fee: promedio estimado por acción.
# Los 3 aplican SOLO a SELL — las compras no pagan ninguno de estos cargos.

from decimal import Decimal, ROUND_HALF_UP

# --- Tasas ajustables --------------------------------------------------------
# SEC §31 fee. Spec T-S: $0.00278 por cada $1000 de notional vendido.
# ⚠️ NOTA: la tasa SEC real fluctúa trimestralmente; en 2024 rondó los
#    $27.80 por millón vendido ( = $0.0278 / $1000, ~10x este valor). Se deja el
#    número de la spec; ajustar SEC_FEE_PER_1000_USD a la tasa vigente cuando
#    Roman/Cowork confirmen cuál usar.
SEC_FEE_PER_1000_USD    = Decimal("0.00278")

# FINRA Trading Activity Fee: por acción vendida, con tope por trade.
FINRA_TAF_PER_SHARE_USD = Decimal("0.000166")
FINRA_TAF_MAX_PER_TRADE = Decimal("8.30")

# Exchange / venue fee promedio por acción (estimación; varía por venue).
EXCHANGE_FEE_PER_SHARE  = Decimal("0.0001")

# Precisión de almacenamiento/reporte: 4 decimales (DECIMAL(10,4) de la columna
# trades.simulated_fees que agrega la migración 017).
_QUANT = Decimal("0.0001")
_ZERO  = Decimal("0.0000")


def _q(value: Decimal) -> Decimal:
    """Cuantiza a 4 decimales (ROUND_HALF_UP) — la precisión de la columna."""
    return value.quantize(_QUANT, rounding=ROUND_HALF_UP)


def _zero_breakdown() -> dict:
    """Desglose en cero (BUY, side desconocido o input no computable)."""
    return {
        "sec_fee": _ZERO,
        "finra_taf": _ZERO,
        "exchange_fee": _ZERO,
        "total": _ZERO,
    }


def calculate_fees(side, qty, filled_price) -> dict:
    """
    Fees simulados de un trade (#CR-3). Retorna el desglose
    {sec_fee, finra_taf, exchange_fee, total} en Decimal cuantizado a 4
    decimales (USD). El total es la suma de los 3 componentes YA cuantizados,
    así total == sec_fee + finra_taf + exchange_fee exacto (sin sorpresas de
    redondeo al persistir/sumar).

    Reglas:
      - Solo SELL paga fees. BUY o side desconocido → todo 0.
      - qty / filled_price None o <= 0 → todo 0 (no computable).
      - sec_fee   = notional / 1000 * SEC_FEE_PER_1000_USD   (notional = qty*price)
      - finra_taf = min(qty * FINRA_TAF_PER_SHARE_USD, FINRA_TAF_MAX_PER_TRADE)
      - exchange  = qty * EXCHANGE_FEE_PER_SHARE
    """
    if side != "SELL":
        return _zero_breakdown()
    if qty is None or filled_price is None:
        return _zero_breakdown()

    qty = Decimal(str(qty))
    price = Decimal(str(filled_price))
    if qty <= 0 or price <= 0:
        return _zero_breakdown()

    notional = qty * price
    sec_fee = _q(notional / Decimal("1000") * SEC_FEE_PER_1000_USD)
    finra_taf = _q(min(qty * FINRA_TAF_PER_SHARE_USD, FINRA_TAF_MAX_PER_TRADE))
    exchange_fee = _q(qty * EXCHANGE_FEE_PER_SHARE)
    total = _q(sec_fee + finra_taf + exchange_fee)
    return {
        "sec_fee": sec_fee,
        "finra_taf": finra_taf,
        "exchange_fee": exchange_fee,
        "total": total,
    }
