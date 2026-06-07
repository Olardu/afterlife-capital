# tests/test_alc_g_rebalance.py
# TDD de la EJECUCIÓN del rebalanceo ALC-G ("que la barra ejecute"):
#   - capa pura: plan_rebalance_orders + sell_qty_from_position (core.py)
#   - broker real submit_rebalance con TradingClient FAKE (sin red)
#   - runner.execute_rebalance + endpoint POST /api/alcg/rebalance
# Path financiero crítico -> cobertura de cada rama (BUY/SELL/close/skip/gate).

from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from alc_g.alcg_api import create_app
from alc_g.alcg_client import AlpacaAlcgBroker
from alc_g.config_alc_g import AlcgParams
from alc_g.core import (
    AccountSnapshot,
    plan_rebalance_orders,
    sell_qty_from_position,
)
from alc_g.core_runner import AlcgRunner

D = Decimal


# --- helpers -----------------------------------------------------------------

def _order(ticker, side, delta):
    return {"ticker": ticker, "side": side, "delta_value": str(delta),
            "target_value": "0", "current_value": "0"}


# === capa PURA: plan_rebalance_orders ========================================

def test_plan_filtra_hold_y_banda_muerta():
    plan = plan_rebalance_orders(
        [_order("SPY", "BUY", 5000), _order("QQQ", "HOLD", 0),
         _order("IWM", "SELL", 50)],  # 50 < min 100 -> se omite
        min_order_usd=D("100"),
    )
    assert [(o.ticker, o.side, o.notional) for o in plan] == [("SPY", "BUY", D("5000"))]


def test_plan_sell_usa_valor_absoluto_del_delta():
    plan = plan_rebalance_orders([_order("SPY", "SELL", -3000)], min_order_usd=D("100"))
    assert plan[0].side == "SELL"
    assert plan[0].notional == D("3000")


def test_plan_delta_justo_en_el_umbral_pasa():
    # delta == min_order_usd no es "< min" -> se incluye
    plan = plan_rebalance_orders([_order("SPY", "BUY", 100)], min_order_usd=D("100"))
    assert len(plan) == 1


def test_plan_ignora_side_desconocido():
    plan = plan_rebalance_orders([_order("SPY", "WAT", 5000)], min_order_usd=D("100"))
    assert plan == []


# === capa PURA: sell_qty_from_position =======================================

def test_sell_qty_posicion_vacia():
    assert sell_qty_from_position(1000, 0, 0) == (D("0"), False)


def test_sell_qty_cierra_todo_si_tapa_la_posicion():
    # monto >= valor de mercado -> cerrar por qty total (close_all)
    assert sell_qty_from_position(60000, 100, 60000) == (D("100"), True)
    assert sell_qty_from_position(70000, 100, 60000) == (D("100"), True)


def test_sell_qty_parcial_trunca_a_enteras():
    # mv 60000 / 100 acc = $600/acc ; vender $5000 -> floor(8.33) = 8
    assert sell_qty_from_position(5000, 100, 60000) == (D("8"), False)


def test_sell_qty_menos_de_una_accion_es_cero():
    # $300 a $600/acc -> 0.5 -> 0 (no se manda)
    assert sell_qty_from_position(300, 100, 60000) == (D("0"), False)


def test_sell_qty_notional_no_positivo():
    assert sell_qty_from_position(0, 100, 60000) == (D("0"), False)


# === broker real con TradingClient FAKE ======================================

class _FakeOrder:
    def __init__(self, oid="o1", status="accepted", filled=None):
        self.id = oid
        self.status = SimpleNamespace(value=status)
        self.filled_avg_price = filled


class _FakePosition:
    def __init__(self, qty, market_value):
        self.qty = qty
        self.market_value = market_value


class _FakeTradingClient:
    """TradingClient en memoria: registra órdenes/cierres, sin tocar Alpaca."""

    def __init__(self, positions=None):
        self.positions = positions or {}
        self.submitted = []
        self.closed = []

    def submit_order(self, req):
        self.submitted.append(req)
        return _FakeOrder(oid="sub-" + req.symbol)

    def get_open_position(self, symbol):
        if symbol not in self.positions:
            raise Exception("position does not exist")
        return self.positions[symbol]

    def close_position(self, symbol):
        self.closed.append(symbol)
        return _FakeOrder(oid="close-" + symbol)


def _broker(fake, allow=True):
    return AlpacaAlcgBroker("", "", allow_execute=allow, client=fake)


def test_broker_bloquea_si_allow_execute_false():
    b = _broker(_FakeTradingClient(), allow=False)
    with pytest.raises(PermissionError):
        b.submit_rebalance([_order("SPY", "BUY", 5000)], min_order_usd=D("100"))


def test_broker_buy_manda_orden_por_notional():
    fake = _FakeTradingClient()
    res = _broker(fake).submit_rebalance([_order("SPY", "BUY", 5000)], min_order_usd=D("100"))
    assert len(fake.submitted) == 1
    req = fake.submitted[0]
    assert req.symbol == "SPY" and float(req.notional) == 5000 and req.qty is None
    assert res[0]["side"] == "BUY" and res[0]["status"] == "ACCEPTED"
    assert res[0]["order_id"] == "sub-SPY" and res[0]["skipped"] is False


def test_broker_sell_parcial_manda_qty_entera():
    fake = _FakeTradingClient({"SPY": _FakePosition(qty="100", market_value="60000")})
    res = _broker(fake).submit_rebalance([_order("SPY", "SELL", -5000)], min_order_usd=D("100"))
    req = fake.submitted[0]
    assert req.symbol == "SPY" and float(req.qty) == 8 and req.notional is None
    assert res[0]["side"] == "SELL" and res[0]["qty"] == "8"


def test_broker_sell_que_tapa_la_posicion_cierra_total():
    fake = _FakeTradingClient({"TLT": _FakePosition(qty="50", market_value="4000")})
    res = _broker(fake).submit_rebalance([_order("TLT", "SELL", -9000)], min_order_usd=D("100"))
    assert fake.closed == ["TLT"]
    assert fake.submitted == []  # se cerró con close_position, no submit_order
    assert res[0]["qty"] == "50" and res[0]["order_id"] == "close-TLT"


def test_broker_sell_sin_posicion_se_omite():
    fake = _FakeTradingClient()  # no hay posición de SPY
    res = _broker(fake).submit_rebalance([_order("SPY", "SELL", -5000)], min_order_usd=D("100"))
    assert fake.submitted == [] and fake.closed == []
    assert res[0]["skipped"] is True and "sin posición" in res[0]["reason"]


def test_broker_sell_menos_de_una_accion_se_omite():
    fake = _FakeTradingClient({"SPY": _FakePosition(qty="100", market_value="60000")})
    # $150 a $600/acc -> 0 acciones (pero pasa la banda muerta de $100)
    res = _broker(fake).submit_rebalance([_order("SPY", "SELL", -150)], min_order_usd=D("100"))
    assert fake.submitted == [] and fake.closed == []
    assert res[0]["skipped"] is True and "1 acción" in res[0]["reason"]


def test_broker_buy_con_fill_reporta_precio():
    class _C(_FakeTradingClient):
        def submit_order(self, req):
            self.submitted.append(req)
            return _FakeOrder(oid="x", status="filled", filled="601.25")
    fake = _C()
    res = _broker(fake).submit_rebalance([_order("SPY", "BUY", 5000)], min_order_usd=D("100"))
    assert res[0]["status"] == "FILLED" and res[0]["filled_avg_price"] == "601.25"


# === runner.execute_rebalance ================================================

class _FakeBroker:
    def __init__(self, snap, vix=None):
        self._snap = snap
        self._vix = vix
        self.calls = []

    def get_snapshot(self):
        return self._snap

    def get_vix_close(self):
        return self._vix

    def submit_rebalance(self, orders, *, min_order_usd, p=None):
        self.calls.append((orders, min_order_usd))
        return [{"ticker": "SPY", "side": "BUY", "skipped": False, "status": "ACCEPTED"}]


def test_runner_execute_rebalance_llama_al_broker():
    snap = AccountSnapshot(equity=D("100000"), long_value=D("0"), positions={})
    broker = _FakeBroker(snap)
    runner = AlcgRunner(broker, AlcgParams())
    out = runner.execute_rebalance()
    assert len(broker.calls) == 1
    assert broker.calls[0][1] == D("100")  # min_order_usd default
    assert out["sent_count"] == 1
    assert out["min_order_usd"] == "100"
    assert any(o["ticker"] == "SPY" for o in out["planned_orders"])


# === endpoint POST /api/alcg/rebalance =======================================

def _client(broker):
    return TestClient(create_app(AlcgRunner(broker, AlcgParams())))


def test_endpoint_sin_confirmar_rechaza():
    snap = AccountSnapshot(equity=D("100000"), long_value=D("0"), positions={})
    r = _client(_FakeBroker(snap)).post("/api/alcg/rebalance", json={"confirm": False})
    assert r.status_code == 400 and r.json()["codigo"] == "not_confirmed"


def test_endpoint_confirmado_ejecuta():
    snap = AccountSnapshot(equity=D("100000"), long_value=D("0"), positions={})
    r = _client(_FakeBroker(snap)).post("/api/alcg/rebalance", json={"confirm": True})
    assert r.status_code == 200
    assert r.json()["data"]["sent_count"] == 1


def test_endpoint_ejecucion_deshabilitada_403():
    snap = AccountSnapshot(equity=D("100000"), long_value=D("0"), positions={})

    class _Blocked(_FakeBroker):
        def submit_rebalance(self, orders, *, min_order_usd, p=None):
            raise PermissionError("ejecución deshabilitada")

    r = _client(_Blocked(snap)).post("/api/alcg/rebalance", json={"confirm": True})
    assert r.status_code == 403 and r.json()["codigo"] == "execution_disabled"


def test_endpoint_error_de_cuenta_502():
    snap = AccountSnapshot(equity=D("100000"), long_value=D("0"), positions={})

    class _Boom(_FakeBroker):
        def submit_rebalance(self, orders, *, min_order_usd, p=None):
            raise RuntimeError("Alpaca caído")

    r = _client(_Boom(snap)).post("/api/alcg/rebalance", json={"confirm": True})
    assert r.status_code == 502 and r.json()["codigo"] == "rebalance_error"
