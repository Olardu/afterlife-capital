# Tests TDD para simulated_costs.calculate_fees (#CR-3).
# Función pura → sin DB, sin mocks. Valida que los fees solo apliquen a SELL,
# el tope de FINRA TAF, y la consistencia total == suma de componentes.

import os
import sys
from decimal import Decimal

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from simulated_costs import (  # noqa: E402
    calculate_fees,
    FINRA_TAF_MAX_PER_TRADE,
)


def test_buy_no_paga_fees():
    # Las compras no pagan ninguno de los 3 cargos.
    fees = calculate_fees("BUY", Decimal("100"), Decimal("50"))
    assert fees == {
        "sec_fee": Decimal("0.0000"),
        "finra_taf": Decimal("0.0000"),
        "exchange_fee": Decimal("0.0000"),
        "total": Decimal("0.0000"),
    }


def test_sell_chica_sin_tope_finra():
    # qty=100 @ $50 → notional 5000.
    #   sec   = 5000/1000 * 0.0278 = 0.1390
    #   finra = 100 * 0.000166     = 0.0166  (bajo el tope 8.30)
    #   exch  = 100 * 0.0001       = 0.0100
    #   total = 0.1656
    fees = calculate_fees("SELL", Decimal("100"), Decimal("50"))
    assert fees["sec_fee"] == Decimal("0.1390")
    assert fees["finra_taf"] == Decimal("0.0166")
    assert fees["exchange_fee"] == Decimal("0.0100")
    assert fees["total"] == Decimal("0.1656")


def test_sell_grande_aplica_tope_finra():
    # qty=100000 @ $10 → notional 1,000,000.
    #   sec   = 1_000_000/1000 * 0.0278 = 27.8000
    #   finra = 100000 * 0.000166 = 16.6 → CAP 8.3000
    #   exch  = 100000 * 0.0001         = 10.0000
    #   total = 46.1000
    fees = calculate_fees("SELL", Decimal("100000"), Decimal("10"))
    assert fees["sec_fee"] == Decimal("27.8000")
    assert fees["finra_taf"] == FINRA_TAF_MAX_PER_TRADE.quantize(Decimal("0.0001"))
    assert fees["finra_taf"] == Decimal("8.3000")
    assert fees["exchange_fee"] == Decimal("10.0000")
    assert fees["total"] == Decimal("46.1000")


def test_total_es_suma_de_componentes():
    # El total debe ser exactamente la suma de los 3 componentes cuantizados.
    fees = calculate_fees("SELL", Decimal("777"), Decimal("33.33"))
    assert fees["total"] == fees["sec_fee"] + fees["finra_taf"] + fees["exchange_fee"]


@pytest.mark.parametrize(
    "side,qty,price",
    [
        ("SELL", None, Decimal("50")),       # qty faltante
        ("SELL", Decimal("100"), None),      # price faltante
        ("SELL", Decimal("0"), Decimal("50")),    # qty 0
        ("SELL", Decimal("-5"), Decimal("50")),   # qty negativa
        ("SELL", Decimal("100"), Decimal("0")),   # price 0
        ("HOLD", Decimal("100"), Decimal("50")),  # side desconocido
    ],
)
def test_edge_cases_devuelven_cero(side, qty, price):
    fees = calculate_fees(side, qty, price)
    assert fees["total"] == Decimal("0.0000")
    assert all(v == Decimal("0.0000") for v in fees.values())


def test_acepta_float_y_str_via_decimal_str():
    # qty/price pueden venir como float o str (asyncpg/Alpaca); se normalizan.
    f_dec = calculate_fees("SELL", Decimal("100"), Decimal("50"))
    f_flt = calculate_fees("SELL", 100, 50.0)
    f_str = calculate_fees("SELL", "100", "50")
    assert f_dec == f_flt == f_str
