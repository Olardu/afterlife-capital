"""Tests T-P — cobertura de correlation_guard.py.

Complementa test_correlation_guard_decimal.py y _persistence.py (que mockean la
correlación) cubriendo lo que faltaba: calculate_correlation (matemática pura),
fetch_bars / _fetch_bars_sync (Alpaca mockeado), y las ramas de evaluate_signal
no ejercitadas (fetch_bars falla, incoming sin barras, posición==incoming,
posición sin barras, sin correlaciones, avg ≤ threshold).

Correr:
  venv\\Scripts\\python.exe -m pytest tests/test_correlation_guard_coverage.py -v
"""
import asyncio
import os
import sys
from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import correlation_guard
from correlation_guard import CorrelationGuard


def _run(coro):
    return asyncio.run(coro)


# =============================================================================
# calculate_correlation (Pearson puro)
# =============================================================================

def test_correlacion_perfecta_positiva():
    cg = CorrelationGuard()
    assert cg.calculate_correlation([1, 2, 3], [2, 4, 6]) == pytest.approx(1.0)


def test_correlacion_perfecta_negativa():
    cg = CorrelationGuard()
    assert cg.calculate_correlation([1, 2, 3], [6, 4, 2]) == pytest.approx(-1.0)


def test_correlacion_serie_constante_es_cero():
    cg = CorrelationGuard()
    # std_a = 0 → denominador 0 → 0.0
    assert cg.calculate_correlation([5, 5, 5], [1, 2, 3]) == 0.0


def test_correlacion_longitudes_distintas_es_cero():
    cg = CorrelationGuard()
    assert cg.calculate_correlation([1, 2], [1, 2, 3]) == 0.0


def test_correlacion_vacia_es_cero():
    cg = CorrelationGuard()
    assert cg.calculate_correlation([], []) == 0.0


# =============================================================================
# fetch_bars / _fetch_bars_sync
# =============================================================================

def test_fetch_bars_exito_delega_en_sync():
    cg = CorrelationGuard()
    with patch.object(cg, "_fetch_bars_sync", return_value={"SPY": [1.0, 2.0, 3.0]}):
        res = _run(cg.fetch_bars(["SPY"], 3))
    assert res == {"SPY": [1.0, 2.0, 3.0]}


def test_fetch_bars_timeout_se_convierte_en_runtimeerror():
    cg = CorrelationGuard()
    # to_thread mockeado a sync MagicMock para no dejar una corutina huérfana
    # (el arg de wait_for se evalúa aunque wic_for esté mockeado).
    with patch.object(correlation_guard.asyncio, "to_thread",
                      new=MagicMock(return_value=MagicMock())), \
         patch.object(correlation_guard.asyncio, "wait_for",
                      side_effect=asyncio.TimeoutError()), \
         pytest.raises(RuntimeError, match="timeout"):
        _run(cg.fetch_bars(["SPY"], 3))


# --- Fakes mínimos para el DataFrame de Alpaca (bars_df.loc[t]["close"].tolist())
class _Closes:
    def __init__(self, closes):
        self._c = closes

    def tolist(self):
        return self._c


class _TickerBars:
    def __init__(self, closes):
        self._c = closes

    def __getitem__(self, key):  # ["close"]
        return _Closes(self._c)


class _Loc:
    def __init__(self, data):
        self._d = data

    def __getitem__(self, ticker):
        if ticker not in self._d:
            raise KeyError(ticker)
        return _TickerBars(self._d[ticker])


class _FakeBarsDF:
    def __init__(self, data):
        self.loc = _Loc(data)


def _patch_alpaca(bars_data=None, get_raises=False):
    """Patchea StockHistoricalDataClient para devolver bars_data sin red."""
    client = MagicMock()
    if get_raises:
        client.get_stock_bars.side_effect = RuntimeError("alpaca down")
    else:
        client.get_stock_bars.return_value = MagicMock(df=_FakeBarsDF(bars_data or {}))
    return patch("alpaca.data.historical.StockHistoricalDataClient",
                 return_value=client)


def test_fetch_bars_sync_incluye_ticker_con_suficientes_barras():
    cg = CorrelationGuard()
    with _patch_alpaca({"SPY": [1.0, 2.0, 3.0]}):
        res = cg._fetch_bars_sync(["SPY"], window=3)
    assert res == {"SPY": [1.0, 2.0, 3.0]}


def test_fetch_bars_sync_excluye_ticker_sin_datos():
    cg = CorrelationGuard()
    with _patch_alpaca({"SPY": [1.0, 2.0, 3.0]}):  # QQQ ausente → KeyError → excluido
        res = cg._fetch_bars_sync(["SPY", "QQQ"], window=3)
    assert "QQQ" not in res and "SPY" in res


def test_fetch_bars_sync_excluye_ticker_con_pocas_barras():
    cg = CorrelationGuard()
    with _patch_alpaca({"SPY": [1.0, 2.0]}):  # solo 2 < window 3 → excluido
        res = cg._fetch_bars_sync(["SPY"], window=3)
    assert res == {}


def test_fetch_bars_sync_alpaca_falla_levanta_runtimeerror():
    cg = CorrelationGuard()
    with _patch_alpaca(get_raises=True), \
         pytest.raises(RuntimeError, match="fetch_bars"):
        cg._fetch_bars_sync(["SPY"], window=3)


def test_fetch_bars_sync_usa_ventana_10_dias():
    """Incidente día-1 período-2 (26-may): la ventana de fetch de 5 días calendario
    no garantizaba CORRELATION_ROLLING_WINDOW=60 barras IEX los lunes/post-feriado
    (IEX es feed disperso → devolvía 51-59/60 → ticker excluido → #TD-3 rechaza
    la señal como no_data). El fetch debe pedir 10 días de margen, no 5."""
    cg = CorrelationGuard()
    client = MagicMock()
    client.get_stock_bars.return_value = MagicMock(df=_FakeBarsDF({"SPY": [1.0, 2.0, 3.0]}))
    with patch("alpaca.data.historical.StockHistoricalDataClient", return_value=client):
        cg._fetch_bars_sync(["SPY"], window=3)
        now = datetime.now(tz=ZoneInfo("UTC"))
    request = client.get_stock_bars.call_args[0][0]   # StockBarsRequest posicional
    req_start = request.start
    if req_start.tzinfo is None:        # pydantic de alpaca-py puede normalizar a naive UTC
        req_start = req_start.replace(tzinfo=ZoneInfo("UTC"))
    delta_days = (now - req_start).total_seconds() / 86400.0
    # start ≈ now − 10 días (con holgura por el tiempo de ejecución del test)
    assert 10.0 <= delta_days <= 10.05, f"ventana de fetch = {delta_days:.3f} días (esperado ~10)"


# =============================================================================
# evaluate_signal — ramas no cubiertas por los tests _decimal
# =============================================================================

def test_evaluate_signal_fetch_bars_falla_aprueba_con_warning():
    cg = CorrelationGuard()
    with patch.object(cg, "fetch_bars", side_effect=RuntimeError("boom")):
        res = _run(cg.evaluate_signal(
            "SPY", Decimal("10"),
            open_positions=[{"ticker": "QQQ", "qty": 1}], performance_scores=[],
        ))
    assert res["approved"] is True and res["reason"] == "approved"
    assert res["adjusted_qty"] == Decimal("10")


def test_evaluate_signal_incoming_sin_barras_rechaza_no_data():
    """#TD-3: sin barras del ticker entrante → RECHAZA con reason='no_data' (antes aprobaba)."""
    cg = CorrelationGuard()
    with patch.object(cg, "fetch_bars", return_value={"QQQ": [1.0, 2.0]}):
        res = _run(cg.evaluate_signal(
            "SPY", Decimal("10"),
            open_positions=[{"ticker": "QQQ", "qty": 1}], performance_scores=[],
        ))
    assert res["approved"] is False and res["reason"] == "no_data"
    assert res["adjusted_qty"] == Decimal("0")


def test_evaluate_signal_ticker_duplicado_veta():
    """#TD-4: posición abierta del mismo ticker → VETO inmediato (antes contaba 1.0 y reducía)."""
    cg = CorrelationGuard()
    with patch.object(cg, "fetch_bars", return_value={"SPY": [1.0, 2.0, 3.0]}):
        res = _run(cg.evaluate_signal(
            "SPY", Decimal("10"),
            open_positions=[{"ticker": "SPY", "qty": 1}], performance_scores=[],
        ))
    assert res["reason"] == "duplicate_ticker"
    assert res["approved"] is False
    assert res["avg_correlation"] == pytest.approx(1.0)


def test_evaluate_signal_alta_correlacion_descarta():
    """Ticker DISTINTO con correlación alta → reducción → adjusted < MIN → descarta."""
    cg = CorrelationGuard()
    with patch.object(cg, "fetch_bars",
                      return_value={"SPY": [1.0, 2.0, 3.0], "QQQ": [1.0, 2.0, 3.0]}), \
         patch.object(cg, "calculate_correlation", return_value=1.0):
        res = _run(cg.evaluate_signal(
            "SPY", Decimal("10"),
            open_positions=[{"ticker": "QQQ", "qty": 1}], performance_scores=[],
        ))
    # avg_corr 1.0 > threshold → reduction_factor 0 → adjusted 0 < MIN → descarta
    assert res["reason"] == "discarded_high_correlation"
    assert res["approved"] is False


def test_evaluate_signal_posicion_sin_barras_se_omite_y_aprueba():
    """Posición abierta sin barras → omitida; sin correlaciones → avg 0 → aprueba."""
    cg = CorrelationGuard()
    with patch.object(cg, "fetch_bars", return_value={"SPY": [1.0, 2.0, 3.0]}):
        res = _run(cg.evaluate_signal(
            "SPY", Decimal("10"),
            open_positions=[{"ticker": "XLU", "qty": 1}],  # XLU no está en bars
            performance_scores=[],
        ))
    assert res["approved"] is True
    assert res["reason"] == "approved"
    assert res["avg_correlation"] == 0.0


def test_evaluate_signal_correlacion_baja_aprueba_sin_cambios():
    cg = CorrelationGuard()
    with patch.object(cg, "fetch_bars",
                      return_value={"SPY": [1.0, 2.0, 3.0], "TLT": [3.0, 2.0, 1.0]}), \
         patch.object(cg, "calculate_correlation", return_value=0.1):
        res = _run(cg.evaluate_signal(
            "SPY", Decimal("10"),
            open_positions=[{"ticker": "TLT", "qty": 1}], performance_scores=[],
        ))
    assert res["approved"] is True
    assert res["reason"] == "approved"
    assert res["adjusted_qty"] == Decimal("10")


# =============================================================================
# #BUG-CG-SELL — el SELL queda exento del CorrelationGuard (des-riesga)
# =============================================================================

def test_evaluate_signal_sell_en_cartera_aprueba():
    """#BUG-CG-SELL: un SELL sobre un ticker EN CARTERA es un cierre/reducción legítimo
    → aprobado con qty completa (antes lo vetaba duplicate_ticker e impedía des-riesgar,
    diagnóstico ALC-P 1-5 jun log #80). Short-circuit: ni siquiera consulta barras."""
    cg = CorrelationGuard()
    fetch = MagicMock()
    with patch.object(cg, "fetch_bars", fetch):
        res = _run(cg.evaluate_signal(
            "SPY", Decimal("10"),
            open_positions=[{"ticker": "SPY", "qty": 5}], performance_scores=[],
            signal_type="SELL",
        ))
    assert res["approved"] is True
    assert res["reason"] == "approved"
    assert res["adjusted_qty"] == Decimal("10")   # qty completa, no reducida
    fetch.assert_not_called()                      # exento antes de tocar Alpaca


def test_evaluate_signal_sell_no_se_reduce_por_correlacion():
    """El SELL queda EXENTO de la reducción por correlación: un cierre no debe encogerse
    aunque el resto de la cartera esté muy correlacionada. (Drift correcto sobre el
    snippet de Deep, que con `continue` dejaba correr la reducción sobre el SELL.)"""
    cg = CorrelationGuard()
    with patch.object(cg, "fetch_bars",
                      return_value={"SPY": [1.0, 2.0, 3.0], "QQQ": [1.0, 2.0, 3.0]}), \
         patch.object(cg, "calculate_correlation", return_value=1.0):
        res = _run(cg.evaluate_signal(
            "SPY", Decimal("10"),
            open_positions=[{"ticker": "QQQ", "qty": 1}], performance_scores=[],
            signal_type="SELL",
        ))
    assert res["approved"] is True
    assert res["adjusted_qty"] == Decimal("10")


def test_evaluate_signal_buy_default_sigue_vetando_duplicado():
    """Backward-compat: sin signal_type explícito (default BUY) el veto duplicate_ticker
    sigue activo — el fix NO afloja la anti-concentración de las compras."""
    cg = CorrelationGuard()
    with patch.object(cg, "fetch_bars", return_value={"SPY": [1.0, 2.0, 3.0]}):
        res = _run(cg.evaluate_signal(
            "SPY", Decimal("10"),
            open_positions=[{"ticker": "SPY", "qty": 1}], performance_scores=[],
            signal_type="BUY",
        ))
    assert res["approved"] is False and res["reason"] == "duplicate_ticker"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
