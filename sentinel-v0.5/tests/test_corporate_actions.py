# Tests TDD para corporate_actions.py (#CR-2 splits/dividendos).
from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace

import corporate_actions as ca
from tax_lots import compute_tax_report


def _t(ticker, side, qty, price, dt):
    """Helper: trade FILLED con dt datetime."""
    return {"ticker": ticker, "side": side, "qty": qty, "price": price, "dt": dt}


# --------------------------------------------------------------------------
# normalize_alpaca_ca
# --------------------------------------------------------------------------
def test_normalize_forward_split_ratio():
    raw = {"forward_splits": [SimpleNamespace(
        symbol="XLU", ex_date=date(2025, 12, 5), new_rate=2.0, old_rate=1.0)]}
    out = ca.normalize_alpaca_ca(raw)
    assert out["splits"] == [{"symbol": "XLU", "ex_date": date(2025, 12, 5), "ratio": Decimal("2")}]
    assert out["dividends"] == []


def test_normalize_reverse_split_ratio_below_one():
    raw = {"reverse_splits": [SimpleNamespace(
        symbol="ABC", ex_date=date(2025, 6, 1), new_rate=1.0, old_rate=2.0)]}
    out = ca.normalize_alpaca_ca(raw)
    assert out["splits"][0]["ratio"] == Decimal("0.5")


def test_normalize_cash_dividend_fields():
    raw = {"cash_dividends": [SimpleNamespace(
        symbol="AAPL", ex_date=date(2026, 5, 11), rate=0.27, special=False)]}
    out = ca.normalize_alpaca_ca(raw)
    assert out["dividends"] == [
        {"symbol": "AAPL", "ex_date": date(2026, 5, 11), "rate": Decimal("0.27"), "special": False}
    ]


def test_normalize_accepts_dicts_and_datetime():
    raw = {"cash_dividends": [
        {"symbol": "X", "ex_date": datetime(2026, 1, 2, 9, 30), "rate": 1.5, "special": True}]}
    out = ca.normalize_alpaca_ca(raw)
    assert out["dividends"][0]["ex_date"] == date(2026, 1, 2)
    assert out["dividends"][0]["special"] is True


def test_normalize_discards_invalid_and_empty():
    assert ca.normalize_alpaca_ca(None) == {"splits": [], "dividends": []}
    raw = {
        "forward_splits": [SimpleNamespace(symbol="X", ex_date=date(2025, 1, 1), new_rate=2.0, old_rate=0.0)],
        "cash_dividends": [SimpleNamespace(symbol=None, ex_date=date(2025, 1, 1), rate=1.0, special=False)],
    }
    out = ca.normalize_alpaca_ca(raw)
    assert out == {"splits": [], "dividends": []}


def test_normalize_ignores_unsupported_ca_types():
    raw = {"spin_offs": [SimpleNamespace(source_symbol="X")],
           "name_changes": [SimpleNamespace(old_symbol="X")]}
    assert ca.normalize_alpaca_ca(raw) == {"splits": [], "dividends": []}


# --------------------------------------------------------------------------
# adjust_trades_for_splits
# --------------------------------------------------------------------------
def test_adjust_forward_split_pre_split_trade():
    trades = [_t("NVDA", "BUY", 1, 1200, datetime(2024, 6, 1))]
    splits = [{"symbol": "NVDA", "ex_date": date(2024, 6, 10), "ratio": Decimal("10")}]
    out = ca.adjust_trades_for_splits(trades, splits)
    assert out[0]["qty"] == Decimal("10")
    assert out[0]["price"] == Decimal("120")
    # cost_basis se conserva
    assert out[0]["qty"] * out[0]["price"] == Decimal("1200")


def test_adjust_does_not_touch_post_split_trade():
    trades = [_t("NVDA", "SELL", 10, 120, datetime(2024, 6, 15))]
    splits = [{"symbol": "NVDA", "ex_date": date(2024, 6, 10), "ratio": Decimal("10")}]
    out = ca.adjust_trades_for_splits(trades, splits)
    assert out[0]["qty"] == Decimal("10") and out[0]["price"] == Decimal("120")


def test_adjust_trade_on_ex_date_is_post_split():
    trades = [_t("X", "BUY", 2, 50, datetime(2025, 3, 10))]
    splits = [{"symbol": "X", "ex_date": date(2025, 3, 10), "ratio": Decimal("2")}]
    out = ca.adjust_trades_for_splits(trades, splits)
    assert out[0]["qty"] == Decimal("2")  # ex_date == trade date ⇒ no ajusta


def test_adjust_reverse_split():
    trades = [_t("X", "BUY", 10, 5, datetime(2025, 1, 1))]
    splits = [{"symbol": "X", "ex_date": date(2025, 6, 1), "ratio": Decimal("0.5")}]
    out = ca.adjust_trades_for_splits(trades, splits)
    assert out[0]["qty"] == Decimal("5") and out[0]["price"] == Decimal("10")


def test_adjust_no_splits_is_passthrough_values():
    trades = [_t("X", "BUY", 3, 10, datetime(2025, 1, 1))]
    out = ca.adjust_trades_for_splits(trades, [])
    assert out[0]["qty"] == Decimal("3") and out[0]["price"] == Decimal("10")


def test_adjust_does_not_mutate_input():
    trades = [_t("X", "BUY", 1, 100, datetime(2025, 1, 1))]
    splits = [{"symbol": "X", "ex_date": date(2025, 6, 1), "ratio": Decimal("2")}]
    ca.adjust_trades_for_splits(trades, splits)
    assert trades[0]["qty"] == 1  # original intacto


def test_adjust_other_ticker_unaffected():
    trades = [_t("AAA", "BUY", 1, 100, datetime(2025, 1, 1))]
    splits = [{"symbol": "BBB", "ex_date": date(2025, 6, 1), "ratio": Decimal("2")}]
    out = ca.adjust_trades_for_splits(trades, splits)
    assert out[0]["qty"] == Decimal("1")


# --------------------------------------------------------------------------
# compute_dividend_income
# --------------------------------------------------------------------------
def test_dividend_long_position_earns_income():
    trades = [_t("AAPL", "BUY", 1, 200, datetime(2026, 4, 28))]  # nunca vendió ⇒ 1 long
    divs = [{"symbol": "AAPL", "ex_date": date(2026, 5, 11), "rate": Decimal("0.27"), "special": False}]
    out = ca.compute_dividend_income(trades, divs)
    assert out["n_events"] == 1
    assert out["total_income"] == 0.27
    assert out["items"][0]["shares"] == 1.0


def test_dividend_flat_position_omitted():
    trades = [
        _t("X", "BUY", 1, 10, datetime(2026, 1, 1)),
        _t("X", "SELL", 1, 11, datetime(2026, 1, 5)),
    ]
    divs = [{"symbol": "X", "ex_date": date(2026, 2, 1), "rate": Decimal("0.5"), "special": False}]
    out = ca.compute_dividend_income(trades, divs)
    assert out["n_events"] == 0 and out["total_income"] == 0.0


def test_dividend_short_position_pays_in_lieu():
    trades = [_t("X", "SELL", 2, 10, datetime(2026, 1, 1))]  # short 2
    divs = [{"symbol": "X", "ex_date": date(2026, 2, 1), "rate": Decimal("0.5"), "special": False}]
    out = ca.compute_dividend_income(trades, divs)
    assert out["total_income"] == -1.0  # paga 2 * 0.5
    assert out["items"][0]["shares"] == -2.0


def test_dividend_position_opened_after_ex_date_ignored():
    trades = [_t("TLT", "BUY", 1, 90, datetime(2026, 5, 11))]
    divs = [{"symbol": "TLT", "ex_date": date(2026, 5, 1), "rate": Decimal("0.31"), "special": False}]
    out = ca.compute_dividend_income(trades, divs)
    assert out["n_events"] == 0


def test_dividend_no_dividends():
    out = ca.compute_dividend_income([_t("X", "BUY", 1, 1, datetime(2026, 1, 1))], [])
    assert out == {"items": [], "n_events": 0, "total_income": 0.0}


def test_dividend_ignores_other_tickers_and_none_qty():
    # cubre el skip de ticker distinto y el skip de qty None en _net_long_before
    trades = [
        _t("OTHER", "BUY", 5, 10, datetime(2026, 1, 1)),     # otro ticker → skip
        _t("AAPL", "BUY", None, 200, datetime(2026, 4, 1)),  # qty None → skip
        _t("AAPL", "BUY", 1, 200, datetime(2026, 4, 28)),
    ]
    divs = [{"symbol": "AAPL", "ex_date": date(2026, 5, 11), "rate": Decimal("0.27"), "special": False}]
    out = ca.compute_dividend_income(trades, divs)
    assert out["items"][0]["shares"] == 1.0
    assert out["total_income"] == 0.27


# --------------------------------------------------------------------------
# helpers privados (ramas defensivas)
# --------------------------------------------------------------------------
def test_to_decimal_none():
    assert ca._to_decimal(None) is None


def test_as_date_none():
    assert ca._as_date(None) is None


def test_normalize_discards_non_positive_ratio():
    raw = {"forward_splits": [SimpleNamespace(
        symbol="X", ex_date=date(2025, 1, 1), new_rate=-1.0, old_rate=1.0)]}
    assert ca.normalize_alpaca_ca(raw)["splits"] == []


# --------------------------------------------------------------------------
# build_corporate_actions_report
# --------------------------------------------------------------------------
def test_build_no_ca_matches_plain_tax_report():
    trades = [
        _t("X", "BUY", 1, 100, datetime(2026, 1, 1)),
        _t("X", "SELL", 1, 90, datetime(2026, 1, 10)),
    ]
    out = ca.build_corporate_actions_report(trades, {"splits": [], "dividends": []})
    # no-regresión: sin CA, el tax report == el de #CR-1 sobre los mismos trades
    assert out["tax_report"] == compute_tax_report(trades)
    assert out["dividends"]["total_income"] == 0.0
    assert out["splits"] == []


def test_build_split_makes_fifo_balance():
    # compró 1 pre-split 2:1, vendió 2 post-split ⇒ sin ajuste quedaría
    # desbalanceado; con ajuste, cierra 2 vs 2.
    trades = [
        _t("X", "BUY", 1, 100, datetime(2025, 1, 1)),
        _t("X", "SELL", 2, 60, datetime(2025, 7, 1)),
    ]
    splits = [{"symbol": "X", "ex_date": date(2025, 6, 1), "ratio": Decimal("2")}]
    out = ca.build_corporate_actions_report(trades, {"splits": splits, "dividends": []})
    summ = out["tax_report"]["summary"]
    # gain = proceeds(2*60=120) - cost(2*50=100) = 20, todo pareado (net qty 0)
    assert summ["realized_gain"] == 20.0
    assert summ["n_disposals"] == 1
    assert out["splits"][0]["affected_trades"] is True


def test_build_none_ca_safe():
    out = ca.build_corporate_actions_report([], None)
    assert out["dividends"]["total_income"] == 0.0
    assert out["tax_report"]["summary"]["n_disposals"] == 0


def test_build_splits_applied_flag_false_when_no_pre_split_trades():
    trades = [_t("XLU", "BUY", 1, 80, datetime(2026, 5, 11))]  # post-split (XLU 2:1 fue 2025-12-05)
    splits = [{"symbol": "XLU", "ex_date": date(2025, 12, 5), "ratio": Decimal("2")}]
    out = ca.build_corporate_actions_report(trades, {"splits": splits, "dividends": []})
    assert out["splits"][0]["affected_trades"] is False
