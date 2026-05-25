# Tests TDD para investment_thesis.py (#HE-2 Investment Thesis Tracking).
#
# Módulo PURO: state machine + MAE/MFE + outcome + dataset de feedback.
# Sin DB, sin red → 100% cobertura (§8.6, path de métricas financieras).

import pytest

import investment_thesis as it


# --- State machine -----------------------------------------------------------

def test_states_constants_and_set():
    assert it.STATES == frozenset(
        {it.STATE_IDEA, it.STATE_ENTRY_READY, it.STATE_ACTIVE, it.STATE_CLOSED}
    )
    assert it.STATE_CLOSED in it.TERMINAL_STATES


def test_can_transition_valid_path():
    assert it.can_transition(it.STATE_IDEA, it.STATE_ENTRY_READY)
    assert it.can_transition(it.STATE_ENTRY_READY, it.STATE_ACTIVE)
    assert it.can_transition(it.STATE_ACTIVE, it.STATE_CLOSED)
    # Descarte temprano (recovery del Sentinel / candidato no ejecutado).
    assert it.can_transition(it.STATE_IDEA, it.STATE_CLOSED)
    assert it.can_transition(it.STATE_ENTRY_READY, it.STATE_CLOSED)


def test_can_transition_invalid():
    assert not it.can_transition(it.STATE_IDEA, it.STATE_ACTIVE)      # salta ENTRY_READY
    assert not it.can_transition(it.STATE_ACTIVE, it.STATE_IDEA)      # no retrocede
    assert not it.can_transition(it.STATE_CLOSED, it.STATE_ACTIVE)    # terminal
    assert not it.can_transition(it.STATE_IDEA, it.STATE_IDEA)        # no self-loop


def test_validate_transition_returns_target():
    assert it.validate_transition(it.STATE_ACTIVE, it.STATE_CLOSED) == it.STATE_CLOSED


def test_validate_transition_raises_on_invalid():
    with pytest.raises(ValueError):
        it.validate_transition(it.STATE_IDEA, it.STATE_ACTIVE)


def test_validate_transition_raises_on_unknown_state():
    with pytest.raises(ValueError):
        it.validate_transition("FOO", it.STATE_CLOSED)
    with pytest.raises(ValueError):
        it.validate_transition(it.STATE_IDEA, "BAR")


# --- MAE / MFE (Maximum Adverse / Favorable Excursion) -----------------------

def _bar(high, low):
    return {"high": high, "low": low}


def test_excursions_long_both_sides():
    bars = [_bar(105, 98), _bar(110, 95)]
    out = it.compute_excursions("LONG", 100, bars)
    assert out["mae"] == 5.0       # entry 100 - min_low 95
    assert out["mfe"] == 10.0      # max_high 110 - entry 100
    assert out["mae_pct"] == 5.0
    assert out["mfe_pct"] == 10.0


def test_excursions_short_both_sides():
    bars = [_bar(105, 98), _bar(110, 95)]
    out = it.compute_excursions("SHORT", 100, bars)
    assert out["mae"] == 10.0      # max_high 110 - entry 100 (sube = adverso para short)
    assert out["mfe"] == 5.0       # entry 100 - min_low 95 (baja = favorable)
    assert out["mae_pct"] == 10.0
    assert out["mfe_pct"] == 5.0


def test_excursions_long_favorable_only_clamps_mae_to_zero():
    # El precio nunca cayó bajo el entry → MAE = 0 (no negativo).
    bars = [_bar(103, 101), _bar(108, 102)]
    out = it.compute_excursions("LONG", 100, bars)
    assert out["mae"] == 0.0
    assert out["mfe"] == 8.0


def test_excursions_accepts_close_only_bars():
    bars = [{"close": 102}, {"close": 104}]
    out = it.compute_excursions("LONG", 100, bars)
    assert out["mae"] == 0.0
    assert out["mfe"] == 4.0


def test_excursions_normalizes_buy_sell_direction():
    bars = [_bar(110, 95)]
    assert it.compute_excursions("BUY", 100, bars) == it.compute_excursions("LONG", 100, bars)
    assert it.compute_excursions("SELL", 100, bars) == it.compute_excursions("SHORT", 100, bars)


def test_excursions_empty_bars_returns_zeros():
    out = it.compute_excursions("LONG", 100, [])
    assert out == {"mae": 0.0, "mfe": 0.0, "mae_pct": 0.0, "mfe_pct": 0.0}


def test_excursions_invalid_entry_returns_zeros():
    assert it.compute_excursions("LONG", 0, [_bar(110, 95)])["mae_pct"] == 0.0
    assert it.compute_excursions("LONG", None, [_bar(110, 95)])["mfe"] == 0.0


def test_excursions_invalid_direction_returns_zeros():
    out = it.compute_excursions("WAT", 100, [_bar(110, 95)])
    assert out == {"mae": 0.0, "mfe": 0.0, "mae_pct": 0.0, "mfe_pct": 0.0}


def test_excursions_skips_malformed_bars():
    bars = [{"foo": 1}, _bar(110, 95), {"high": None, "low": None}]
    out = it.compute_excursions("LONG", 100, bars)
    assert out["mfe"] == 10.0


def test_excursions_skips_non_dict_bars():
    bars = ["nope", 42, _bar(110, 95)]
    out = it.compute_excursions("LONG", 100, bars)
    assert out["mfe"] == 10.0


def test_excursions_non_numeric_entry_returns_zeros():
    # Dispara la rama de excepción de _to_decimal (Decimal("abc") → InvalidOperation).
    assert it.compute_excursions("LONG", "abc", [_bar(110, 95)]) == it._ZERO_EXCURSION


def test_excursions_non_string_direction_returns_zeros():
    assert it.compute_excursions(123, 100, [_bar(110, 95)]) == it._ZERO_EXCURSION


# --- Outcome -----------------------------------------------------------------

def test_outcome_long_win_loss_breakeven():
    assert it.compute_outcome("LONG", 100, 110) == {"gain": 10.0, "gain_pct": 10.0, "outcome": "win"}
    assert it.compute_outcome("LONG", 100, 90)["outcome"] == "loss"
    assert it.compute_outcome("LONG", 100, 100)["outcome"] == "breakeven"


def test_outcome_short_inverts_sign():
    assert it.compute_outcome("SHORT", 100, 90) == {"gain": 10.0, "gain_pct": 10.0, "outcome": "win"}
    assert it.compute_outcome("SHORT", 100, 110)["outcome"] == "loss"


def test_outcome_invalid_entry():
    out = it.compute_outcome("LONG", 0, 100)
    assert out["outcome"] == "breakeven"
    assert out["gain_pct"] == 0.0


# --- Summary / feedback dataset ----------------------------------------------

def _closed(ticker, direction, outcome, gain_pct, mae_pct, mfe_pct, holding_days):
    return {
        "ticker": ticker, "direction": direction, "outcome": outcome,
        "gain_pct": gain_pct, "mae_pct": mae_pct, "mfe_pct": mfe_pct,
        "holding_days": holding_days,
    }


def test_summarize_theses_aggregates():
    theses = [
        _closed("AAPL", "LONG", "win", 10.0, 5.0, 10.0, 3),
        _closed("MSFT", "LONG", "loss", -4.0, 8.0, 2.0, 1),
    ]
    s = it.summarize_theses(theses)
    assert s["n"] == 2
    assert s["n_wins"] == 1
    assert s["n_losses"] == 1
    assert s["win_rate"] == 50.0
    assert s["avg_gain_pct"] == 3.0
    assert s["avg_mae_pct"] == 6.5
    assert s["avg_mfe_pct"] == 6.0
    assert s["avg_holding_days"] == 2.0


def test_summarize_theses_empty():
    s = it.summarize_theses([])
    assert s["n"] == 0
    assert s["win_rate"] == 0.0
    assert s["avg_gain_pct"] == 0.0


def test_build_feedback_block_has_content():
    theses = [
        _closed("AAPL", "LONG", "win", 10.0, 5.0, 10.0, 3),
        _closed("MSFT", "LONG", "loss", -4.0, 8.0, 2.0, 1),
    ]
    block = it.build_feedback_block(theses)
    assert "AAPL" in block
    assert "50" in block          # win rate 50%
    assert block.strip() != ""


def test_build_feedback_block_empty_returns_empty_string():
    assert it.build_feedback_block([]) == ""


def test_build_feedback_block_respects_max_examples():
    theses = [_closed(f"T{i}", "LONG", "win", 1.0, 1.0, 1.0, 1) for i in range(20)]
    block = it.build_feedback_block(theses, max_examples=3)
    # El bloque resume 20 pero solo lista 3 ejemplos individuales.
    assert block.count("T") >= 3
    assert "20" in block          # el agregado cuenta los 20
