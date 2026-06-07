# tests/test_alc_g_runner.py
# TDD del runtime ALC-G (core_runner) + API (alcg_api). Broker FAKE (sin red).
# El runner orquesta lógica financiera -> se testea el ciclo completo.

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from alc_g.alcg_api import create_app
from alc_g.config_alc_g import AlcgParams
from alc_g.core import AccountSnapshot
from alc_g.core_runner import AlcgRunner

D = Decimal


class FakeBroker:
    """Broker en memoria: devuelve un snapshot fijo y un VIX configurable."""

    def __init__(self, snapshot: AccountSnapshot, vix=None):
        self._snap = snapshot
        self._vix = vix

    def get_snapshot(self) -> AccountSnapshot:
        return self._snap

    def get_vix_close(self):
        return self._vix


def _snap(equity="100000", long_value="130000", positions=None):
    return AccountSnapshot(equity=D(equity), long_value=D(long_value),
                           positions=positions or {})


# --- runner.run_once ---------------------------------------------------------

def test_run_once_modo_informe_no_ejecuta():
    runner = AlcgRunner(FakeBroker(_snap()), AlcgParams())
    out = runner.run_once()
    assert out["mode"] == "informe"
    assert out["report"]["effective_leverage"] == "1.5"
    assert out["report"]["real_leverage"] == "1.3"
    assert out["report"]["needs_rebalance"] is True


def test_run_once_planned_orders_cubren_el_nucleo():
    runner = AlcgRunner(FakeBroker(_snap(positions={"SPY": D("60000")})), AlcgParams())
    out = runner.run_once()
    tickers = {o["ticker"] for o in out["planned_orders"]}
    assert {"SPY", "QQQ", "IWM"} <= tickers
    spy = next(o for o in out["planned_orders"] if o["ticker"] == "SPY")
    assert spy["side"] == "HOLD"  # 60k actual == 60k target (100k*1.5*0.40)


def test_run_once_floor_deposit_bajo_piso():
    runner = AlcgRunner(FakeBroker(_snap(equity="90000", long_value="0")), AlcgParams())
    out = runner.run_once()
    assert out["floor_deposit"] == "500"


def test_evaluate_vix_alto_capea_leverage():
    runner = AlcgRunner(FakeBroker(_snap()), AlcgParams())
    runner.evaluate(_snap(), D("45"))            # VIX>40 -> capped
    assert runner.vix_state.capped is True
    assert runner.last_report.effective_leverage == D("1.0")


def test_evaluate_sin_vix_no_toca_modo_auto():
    runner = AlcgRunner(FakeBroker(_snap()), AlcgParams())
    runner.evaluate(_snap(), None)
    assert runner.vix_state.capped is False


def test_run_once_modo_ejecutar_avisa_pero_no_ejecuta():
    # mode=ejecutar en Fase 0: el runner advierte pero NO manda órdenes.
    runner = AlcgRunner(FakeBroker(_snap()), AlcgParams(mode="ejecutar"))
    out = runner.run_once()
    assert out["mode"] == "ejecutar"
    assert "planned_orders" in out  # se calculan, no se envían


# --- API ---------------------------------------------------------------------

@pytest.fixture
def client():
    runner = AlcgRunner(FakeBroker(_snap()), AlcgParams())
    return TestClient(create_app(runner))


def test_api_status_ok(client):
    r = client.get("/api/alcg/status")
    assert r.status_code == 200
    body = r.json()
    assert body["meta"]["ok"] is True
    assert body["data"]["report"]["target_leverage"] == "1.5"


def test_api_presets(client):
    r = client.get("/api/alcg/presets")
    assert r.status_code == 200
    assert "turbo" in r.json()["data"]


def test_api_set_leverage_valido(client):
    r = client.post("/api/alcg/leverage", json={"target": 1.25})
    assert r.status_code == 200
    assert r.json()["data"]["leverage_target"] == "1.25"


def test_api_set_leverage_fuera_de_rango(client):
    r = client.post("/api/alcg/leverage", json={"target": 2.5})
    assert r.status_code == 400
    assert r.json()["codigo"] == "out_of_range"


def test_api_set_preset_valido(client):
    r = client.post("/api/alcg/preset", json={"preset": "pasivo"})
    assert r.status_code == 200
    assert r.json()["data"]["leverage_target"] == "1.0"


def test_api_set_preset_desconocido(client):
    r = client.post("/api/alcg/preset", json={"preset": "nope"})
    assert r.status_code == 400
    assert r.json()["codigo"] == "unknown_preset"


def test_api_status_broker_error_502():
    class BoomBroker:
        def get_snapshot(self):
            raise RuntimeError("sin conexión")

        def get_vix_close(self):
            return None

    c = TestClient(create_app(AlcgRunner(BoomBroker(), AlcgParams())))
    r = c.get("/api/alcg/status")
    assert r.status_code == 502
    assert r.json()["codigo"] == "broker_error"
