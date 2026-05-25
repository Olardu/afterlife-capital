# Tests TDD para tax_lots (#CR-1 fiscal).
# Motor PURO (sin DB, sin mocks): FIFO firmado (long + short), holding period,
# term short/long, wash-sale (pérdida + recompra ±30d) y resumen.
# Cierra de paso #TD-1 (el pairing ingenuo zip(buys,sells) de calculate_performance).

import os
import sys
from datetime import datetime
from decimal import Decimal

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tax_lots import (  # noqa: E402
    match_fifo,
    apply_wash_sales,
    summarize,
    compute_tax_report,
)


def _t(side, qty, price, dt, ticker="AAA"):
    """Construye un trade de entrada como lo entrega historian (Decimal + datetime)."""
    return {
        "ticker": ticker,
        "side": side,
        "qty": Decimal(str(qty)),
        "price": Decimal(str(price)),
        "dt": dt,
    }


def _d(y, m, d):
    return datetime(y, m, d)


# ───────────────────────── match_fifo: long ─────────────────────────

def test_long_simple_ganancia_short_term():
    trades = [
        _t("BUY", 10, 100, _d(2026, 1, 1)),
        _t("SELL", 10, 120, _d(2026, 2, 1)),  # 31 días → short
    ]
    disp = match_fifo(trades)
    assert len(disp) == 1
    d = disp[0]
    assert d["direction"] == "LONG"
    assert d["qty"] == Decimal("10")
    assert d["proceeds"] == Decimal("1200")
    assert d["cost_basis"] == Decimal("1000")
    assert d["gain"] == Decimal("200")
    assert d["holding_days"] == 31
    assert d["term"] == "short"


def test_long_fifo_consume_dos_lotes_y_deja_remanente():
    # Vende 15 contra dos compras (10@100 + 10@110) → 2 disposals, 5 quedan abiertas.
    trades = [
        _t("BUY", 10, 100, _d(2026, 1, 1)),
        _t("BUY", 10, 110, _d(2026, 1, 2)),
        _t("SELL", 15, 120, _d(2026, 1, 10)),
    ]
    disp = match_fifo(trades)
    assert len(disp) == 2
    assert disp[0]["qty"] == Decimal("10")
    assert disp[0]["cost_basis"] == Decimal("1000")  # lote FIFO @100
    assert disp[0]["gain"] == Decimal("200")
    assert disp[1]["qty"] == Decimal("5")
    assert disp[1]["cost_basis"] == Decimal("550")   # lote @110
    assert disp[1]["gain"] == Decimal("50")


def test_long_term_supera_365_dias():
    trades = [
        _t("BUY", 10, 100, _d(2025, 1, 1)),
        _t("SELL", 10, 130, _d(2026, 6, 1)),  # > 365 días
    ]
    disp = match_fifo(trades)
    assert disp[0]["term"] == "long"
    assert disp[0]["holding_days"] > 365


def test_term_frontera_365_es_short_y_366_es_long():
    # 2025 no bisiesto: 2025-01-01 → 2026-01-01 = 365 días exactos = short.
    short = match_fifo([
        _t("BUY", 1, 10, _d(2025, 1, 1)),
        _t("SELL", 1, 11, _d(2026, 1, 1)),
    ])
    assert short[0]["holding_days"] == 365
    assert short[0]["term"] == "short"
    longt = match_fifo([
        _t("BUY", 1, 10, _d(2025, 1, 1)),
        _t("SELL", 1, 11, _d(2026, 1, 2)),
    ])
    assert longt[0]["holding_days"] == 366
    assert longt[0]["term"] == "long"


# ───────────────────────── match_fifo: short ────────────────────────

def test_short_sell_abre_buy_cierra():
    # SELL abre corto @100, BUY cubre @90 → ganancia 100 (el corto gana al bajar).
    trades = [
        _t("SELL", 10, 100, _d(2026, 1, 1)),
        _t("BUY", 10, 90, _d(2026, 1, 10)),
    ]
    disp = match_fifo(trades)
    assert len(disp) == 1
    d = disp[0]
    assert d["direction"] == "SHORT"
    assert d["proceeds"] == Decimal("1000")   # venta del corto
    assert d["cost_basis"] == Decimal("900")  # costo de cubrir
    assert d["gain"] == Decimal("100")
    assert d["holding_days"] == 9
    assert d["term"] == "short"


def test_sin_trades_devuelve_vacio():
    assert match_fifo([]) == []


def test_ignora_qty_o_price_no_computable():
    trades = [
        _t("BUY", 0, 100, _d(2026, 1, 1)),     # qty 0 → ignorado
        _t("BUY", 10, 0, _d(2026, 1, 2)),      # price 0 → ignorado
        {"ticker": "AAA", "side": "BUY", "qty": None, "price": Decimal("5"), "dt": _d(2026, 1, 3)},
        _t("BUY", 10, 100, _d(2026, 1, 4)),
        _t("SELL", 10, 110, _d(2026, 1, 20)),
    ]
    disp = match_fifo(trades)
    assert len(disp) == 1
    assert disp[0]["cost_basis"] == Decimal("1000")  # solo el BUY válido @100


# ───────────────────────── wash sale ────────────────────────────────

def test_wash_sale_recompra_dentro_de_ventana():
    trades = [
        _t("BUY", 10, 100, _d(2026, 1, 1)),
        _t("SELL", 10, 90, _d(2026, 1, 11)),   # pérdida -100
        _t("BUY", 10, 92, _d(2026, 1, 21)),    # recompra 10 días después → wash
    ]
    disp = apply_wash_sales(match_fifo(trades), trades)
    loss = disp[0]
    assert loss["gain"] == Decimal("-100")
    assert loss["wash_sale"] is True
    assert loss["disallowed_loss"] == Decimal("100")  # positivo, diferido


def test_sin_wash_sale_si_solo_existe_la_compra_original():
    # La compra que abrió el lote NO cuenta como recompra (se excluye opened_at).
    trades = [
        _t("BUY", 10, 100, _d(2026, 1, 1)),
        _t("SELL", 10, 90, _d(2026, 1, 11)),   # pérdida, sin recompra posterior
    ]
    disp = apply_wash_sales(match_fifo(trades), trades)
    assert disp[0]["wash_sale"] is False
    assert disp[0]["disallowed_loss"] == Decimal("0")


def test_ganancia_nunca_es_wash_sale():
    trades = [
        _t("BUY", 10, 100, _d(2026, 1, 1)),
        _t("SELL", 10, 120, _d(2026, 1, 11)),  # ganancia
        _t("BUY", 10, 121, _d(2026, 1, 15)),   # recompra, pero no hubo pérdida
    ]
    disp = apply_wash_sales(match_fifo(trades), trades)
    assert disp[0]["wash_sale"] is False


# ───────────────────────── summarize ────────────────────────────────

def test_summarize_separa_corto_y_largo_y_neto():
    trades = [
        _t("BUY", 10, 100, _d(2025, 1, 1)),
        _t("SELL", 10, 130, _d(2026, 6, 1)),   # +300 long
        _t("BUY", 10, 50, _d(2026, 6, 1)),
        _t("SELL", 10, 40, _d(2026, 6, 20)),   # -100 short, sin recompra
    ]
    report = compute_tax_report(trades)
    s = report["summary"]
    assert s["n_disposals"] == 2
    assert s["realized_gain"] == 200.0          # 300 - 100
    assert s["long_term_gain"] == 300.0
    assert s["short_term_gain"] == -100.0
    assert s["wash_sale_count"] == 0
    assert s["net_realized_gain"] == 200.0      # sin wash sales, neto == realizado


def test_summarize_vacio_es_cero():
    s = summarize([])
    assert s["n_disposals"] == 0
    assert s["realized_gain"] == 0.0
    assert s["net_realized_gain"] == 0.0


def test_net_realized_suma_perdida_diferida():
    # Pérdida -100 con wash sale → realizado -100, pero neto 0 (se difiere).
    trades = [
        _t("BUY", 10, 100, _d(2026, 1, 1)),
        _t("SELL", 10, 90, _d(2026, 1, 11)),
        _t("BUY", 10, 92, _d(2026, 1, 21)),
    ]
    report = compute_tax_report(trades)
    s = report["summary"]
    assert s["realized_gain"] == -100.0
    assert s["wash_sale_count"] == 1
    assert s["disallowed_loss_total"] == 100.0
    assert s["net_realized_gain"] == 0.0


# ───────────────────────── compute_tax_report multi-ticker ──────────

def test_compute_agrupa_por_ticker():
    trades = [
        _t("BUY", 10, 100, _d(2026, 1, 1), ticker="AAA"),
        _t("SELL", 10, 120, _d(2026, 1, 10), ticker="AAA"),  # +200
        _t("BUY", 5, 200, _d(2026, 1, 2), ticker="BBB"),
        _t("SELL", 5, 180, _d(2026, 1, 12), ticker="BBB"),   # -100
    ]
    report = compute_tax_report(trades)
    assert report["summary"]["n_disposals"] == 2
    assert report["summary"]["realized_gain"] == 100.0
    tickers = {d["ticker"] for d in report["disposals"]}
    assert tickers == {"AAA", "BBB"}
