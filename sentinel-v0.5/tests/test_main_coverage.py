"""Tests T-P Sub-objetivo 9 — cobertura de main.py (entry point + wiring).

main.py es wiring asyncio: helpers de horario, initialize() (instancia todos los
agentes), main_loop() (ciclo de 15 min), 4 pollers de background + sus callbacks
done, y main() (orquestación). Todo se mockea — sin DB, sin red, sin Alpaca.

_send_heartbeat ya está cubierto por test_heartbeat.py (no se duplica aquí).

Correr:
  venv\\Scripts\\python.exe -m pytest tests/test_main_coverage.py -v
"""
import asyncio
import os
import sys
import uuid
from contextlib import contextmanager
from datetime import datetime
from zoneinfo import ZoneInfo
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main


def _run(coro):
    return asyncio.run(coro)


_ET = ZoneInfo("America/New_York")


class _AsyncCM:
    """Async context manager falso: `async with` devuelve el valor dado."""

    def __init__(self, value):
        self._value = value

    async def __aenter__(self):
        return self._value

    async def __aexit__(self, *a):
        return False


class _StopLoop(Exception):
    """Centinela para romper un `while True` desde un mock de asyncio.sleep."""


# =============================================================================
# § 1 — LOGGING (_setup_logging)
# =============================================================================

def test_setup_logging_configura_cuando_root_vacio():
    """Con root sin handlers, agrega console + file handler y setea nivel."""
    fake_root = MagicMock()
    fake_root.handlers = []  # falsy → no retorna temprano
    with patch.object(main.logging, "getLogger", return_value=fake_root), \
         patch.object(main.logging, "StreamHandler") as mock_stream, \
         patch.object(main, "TimedRotatingFileHandler") as mock_file:
        main._setup_logging()
    assert fake_root.setLevel.called
    assert fake_root.addHandler.call_count == 2
    mock_stream.assert_called_once()
    mock_file.assert_called_once()


def test_setup_logging_noop_cuando_root_ya_tiene_handlers():
    """Con handlers preexistentes, retorna sin tocar nada (evita duplicados)."""
    fake_root = MagicMock()
    fake_root.handlers = [MagicMock()]  # truthy → return temprano
    with patch.object(main.logging, "getLogger", return_value=fake_root):
        main._setup_logging()
    fake_root.setLevel.assert_not_called()
    fake_root.addHandler.assert_not_called()


# =============================================================================
# § 2 — HELPERS DE HORARIO
# =============================================================================

def test_is_market_open_lunes_horario():
    # 2026-05-25 es lunes; 10:00 ET está entre 09:30 y 16:00.
    fake = datetime(2026, 5, 25, 10, 0, tzinfo=_ET)
    with patch.object(main, "datetime") as md:
        md.now.return_value = fake
        assert main._is_market_open() is True


def test_is_market_open_lunes_pre_apertura():
    fake = datetime(2026, 5, 25, 8, 0, tzinfo=_ET)  # antes de 09:30
    with patch.object(main, "datetime") as md:
        md.now.return_value = fake
        assert main._is_market_open() is False


def test_is_market_open_fin_de_semana():
    fake = datetime(2026, 5, 24, 12, 0, tzinfo=_ET)  # domingo
    with patch.object(main, "datetime") as md:
        md.now.return_value = fake
        assert main._is_market_open() is False


def test_seconds_to_next_candle_alineado():
    fake = datetime(2026, 5, 25, 10, 7, 0, tzinfo=_ET)  # min 7 → faltan 8 min
    with patch.object(main, "datetime") as md:
        md.now.return_value = fake
        assert main._seconds_to_next_candle() == (15 - 7) * 60 - 0


def test_seconds_to_next_candle_clamp_minimo():
    fake = datetime(2026, 5, 25, 10, 14, 59, tzinfo=_ET)  # casi en el borde
    with patch.object(main, "datetime") as md:
        md.now.return_value = fake
        assert main._seconds_to_next_candle() == 1.0


# =============================================================================
# § 3 — _get_owner_id
# =============================================================================

def test_get_owner_id_encontrado():
    oid = uuid.uuid4()
    conn = MagicMock()
    conn.fetchrow = AsyncMock(return_value={"user_id": oid})
    hist = MagicMock()
    hist.pool.acquire = lambda: _AsyncCM(conn)
    assert _run(main._get_owner_id(hist)) == oid


def test_get_owner_id_no_encontrado_levanta():
    conn = MagicMock()
    conn.fetchrow = AsyncMock(return_value=None)
    hist = MagicMock()
    hist.pool.acquire = lambda: _AsyncCM(conn)
    with pytest.raises(RuntimeError, match="no encontrado"):
        _run(main._get_owner_id(hist))


# =============================================================================
# § 5 — CALLBACKS DONE de los pollers
# =============================================================================

def _task_with_exception(exc):
    t = MagicMock()
    t.exception.return_value = exc
    return t


def _task_cancelled_exc():
    t = MagicMock()
    t.exception.side_effect = asyncio.CancelledError()
    return t


# --- _ear_task_done (usa task.exception(), captura CancelledError) -----------
def test_ear_task_done_cancelado():
    with patch.object(main, "logger") as lg:
        main._ear_task_done(_task_cancelled_exc())
        assert lg.info.called


def test_ear_task_done_con_excepcion():
    with patch.object(main, "logger") as lg:
        main._ear_task_done(_task_with_exception(ValueError("boom")))
        assert lg.critical.called


def test_ear_task_done_sin_excepcion():
    with patch.object(main, "logger") as lg:
        main._ear_task_done(_task_with_exception(None))
        assert lg.warning.called


# --- _ks_task_done (mismo patrón que ear) ------------------------------------
def test_ks_task_done_cancelado():
    with patch.object(main, "logger") as lg:
        main._ks_task_done(_task_cancelled_exc())
        assert lg.info.called


def test_ks_task_done_con_excepcion():
    with patch.object(main, "logger") as lg:
        main._ks_task_done(_task_with_exception(RuntimeError("x")))
        assert lg.critical.called


def test_ks_task_done_sin_excepcion():
    with patch.object(main, "logger") as lg:
        main._ks_task_done(_task_with_exception(None))
        assert lg.warning.called


# --- _reconcile_task_done (usa task.cancelled() + task.exception()) ----------
def _task_cancelled_flag(cancelled, exc=None):
    t = MagicMock()
    t.cancelled.return_value = cancelled
    t.exception.return_value = exc
    return t


def test_reconcile_task_done_cancelado():
    with patch.object(main, "logger") as lg:
        main._reconcile_task_done(_task_cancelled_flag(True))
        assert lg.info.called


def test_reconcile_task_done_con_excepcion():
    with patch.object(main, "logger") as lg:
        main._reconcile_task_done(_task_cancelled_flag(False, RuntimeError("x")))
        assert lg.error.called


def test_reconcile_task_done_limpio():
    with patch.object(main, "logger") as lg:
        main._reconcile_task_done(_task_cancelled_flag(False, None))
        assert not lg.error.called


# --- _equity_snapshot_task_done (mismo patrón que reconcile) -----------------
def test_equity_snapshot_task_done_cancelado():
    with patch.object(main, "logger") as lg:
        main._equity_snapshot_task_done(_task_cancelled_flag(True))
        assert lg.info.called


def test_equity_snapshot_task_done_con_excepcion():
    with patch.object(main, "logger") as lg:
        main._equity_snapshot_task_done(_task_cancelled_flag(False, RuntimeError("x")))
        assert lg.error.called


def test_equity_snapshot_task_done_limpio():
    with patch.object(main, "logger") as lg:
        main._equity_snapshot_task_done(_task_cancelled_flag(False, None))
        assert not lg.error.called


# =============================================================================
# § 3 — initialize() (wiring de todos los agentes)
# =============================================================================

class _FakeSentinel:
    """Sustituye a las clases reales de SENTINEL_REGISTRY / SentinelSMACrossover."""

    def __init__(self, sentinel_id, owner_id, tickers):
        self.sentinel_id = sentinel_id
        self.owner_id = owner_id
        self.tickers = tickers
        self.name = f"FakeSentinel({','.join(tickers)})"


def _row(strategy_type, name, tickers, sid=None):
    return {
        "strategy_type": strategy_type,
        "name": name,
        "tickers": tickers,
        "sentinel_id": sid or uuid.uuid4(),
    }


def _make_historian(active_rows, *, get_active_raises=False,
                    insert_raises=False, owner_email="owner@example.com"):
    """Historian mock con pool/conn que soportan los async-with de initialize()."""
    conn = MagicMock()
    conn.fetchval = AsyncMock(return_value=owner_email)
    conn.transaction = lambda: _AsyncCM(None)
    conn.execute = AsyncMock(side_effect=RuntimeError("insert fail")) if insert_raises \
        else AsyncMock()
    hist = MagicMock()
    hist.connect = AsyncMock()
    hist.close = AsyncMock()
    hist.pool.acquire = lambda: _AsyncCM(conn)
    if get_active_raises:
        hist.get_active_sentinels = AsyncMock(side_effect=RuntimeError("db down"))
    else:
        hist.get_active_sentinels = AsyncMock(return_value=active_rows)
    return hist


@contextmanager
def _init_env(hist, registry=None, us_enabled=False):
    registry = registry if registry is not None else {"sma_crossover": _FakeSentinel}
    with patch.object(main, "validate_config"), \
         patch.object(main, "Historian", return_value=hist), \
         patch.object(main, "RegimeClassifier",
                      return_value=MagicMock(initialize=AsyncMock())), \
         patch.object(main, "TheEar", return_value=MagicMock()), \
         patch.object(main, "CorrelationGuard", return_value=MagicMock()), \
         patch.object(main, "Dispatcher", return_value=MagicMock()), \
         patch.object(main, "SENTINEL_REGISTRY", registry), \
         patch.object(main, "SentinelSMACrossover", _FakeSentinel), \
         patch.object(main, "_get_owner_id", new=AsyncMock(return_value=uuid.uuid4())), \
         patch.object(main, "UNIVERSE_SELECTION_ENABLED", us_enabled), \
         patch.object(main, "logger"):
        yield


def test_initialize_sentinels_desde_db_filtra_invalidos():
    """1 row válido + 1 strategy desconocido + 1 sin tickers → 1 sentinel cargado."""
    hist = _make_historian([
        _row("sma_crossover", "S-A", ["SPY"]),
        _row("desconocido",  "S-B", ["QQQ"]),  # no en registry → skip
        _row("sma_crossover", "S-C", []),       # sin tickers → skip
    ])
    with _init_env(hist):
        system = _run(main.initialize())
    assert len(system["sentinels"]) == 1
    assert system["universe_selector"] is None
    for k in ("historian", "dispatcher", "the_ear", "correlation_guard", "owner_id"):
        assert k in system
    hist.connect.assert_awaited()


def test_initialize_finbert_flag_on_construye_analyzer():
    """#FEAT-007: con THE_EAR_SENTIMENT_ENABLED=true, initialize construye el
    SentimentAnalyzer y lo inyecta (rama if del wire-up)."""
    hist = _make_historian([_row("sma_crossover", "S-A", ["SPY"])])
    with _init_env(hist), \
         patch.object(main, "THE_EAR_SENTIMENT_ENABLED", True), \
         patch("sentiment_analyzer.SentimentAnalyzer", return_value=MagicMock()) as MSA:
        system = _run(main.initialize())
    MSA.assert_called_once()
    assert "the_ear" in system


def test_initialize_fallback_cuando_get_active_falla():
    """get_active_sentinels lanza → active=[] → inserta S-1 fallback en DB."""
    hist = _make_historian([], get_active_raises=True)
    with _init_env(hist):
        system = _run(main.initialize())
    assert len(system["sentinels"]) == 1  # el fallback S-1


def test_initialize_fallback_con_insert_fallido():
    """Sin sentinels y el INSERT del fallback lanza → igual se agrega el Sentinel."""
    hist = _make_historian([], insert_raises=True)
    with _init_env(hist):
        system = _run(main.initialize())
    assert len(system["sentinels"]) == 1


def test_initialize_universe_selection_exito_y_email_sender():
    hist = _make_historian([_row("sma_crossover", "S-A", ["SPY"])])
    fake_us = MagicMock()
    with _init_env(hist, us_enabled=True), \
         patch("claude_client.ClaudeClient", return_value=MagicMock()), \
         patch("universe_selector.UniverseSelector", return_value=fake_us) as MUS, \
         patch("email_service.send_rotation_email",
               new=AsyncMock(return_value=True)) as mock_send:
        system = _run(main.initialize())
        # cubrir el cuerpo del _email_sender anidado (owner_email presente)
        email_sender = MUS.call_args.kwargs["email_sender"]
        assert _run(email_sender({"x": 1})) is True
        mock_send.assert_awaited()
    assert system["universe_selector"] is fake_us


def test_initialize_email_sender_sin_owner_email():
    """owner_email None → _email_sender retorna False sin enviar."""
    hist = _make_historian([_row("sma_crossover", "S-A", ["SPY"])], owner_email=None)
    with _init_env(hist, us_enabled=True), \
         patch("claude_client.ClaudeClient", return_value=MagicMock()), \
         patch("universe_selector.UniverseSelector", return_value=MagicMock()) as MUS, \
         patch("email_service.send_rotation_email",
               new=AsyncMock(return_value=True)) as mock_send:
        _run(main.initialize())
        email_sender = MUS.call_args.kwargs["email_sender"]
        assert _run(email_sender({"x": 1})) is False
        mock_send.assert_not_awaited()


def test_initialize_universe_selection_runtime_error():
    hist = _make_historian([_row("sma_crossover", "S-A", ["SPY"])])
    with _init_env(hist, us_enabled=True), \
         patch("claude_client.ClaudeClient", side_effect=RuntimeError("no key")):
        system = _run(main.initialize())
    assert system["universe_selector"] is None


def test_initialize_universe_selection_error_generico():
    hist = _make_historian([_row("sma_crossover", "S-A", ["SPY"])])
    with _init_env(hist, us_enabled=True), \
         patch("claude_client.ClaudeClient", side_effect=ValueError("boom")):
        system = _run(main.initialize())
    assert system["universe_selector"] is None


# =============================================================================
# § 4 — main_loop() (ciclo de 15 min)
# =============================================================================

def test_main_loop_fuera_de_horario():
    """Mercado cerrado → duerme 60s (el sleep mockeado rompe el while)."""
    system = {"dispatcher": MagicMock(), "sentinels": [], "universe_selector": None}
    # 1er sleep retorna (ejecuta el `continue`), 2do rompe el while.
    with patch.object(main, "_is_market_open", return_value=False), \
         patch.object(main.asyncio, "sleep", new=AsyncMock(side_effect=[None, _StopLoop])), \
         patch.object(main, "logger"), \
         pytest.raises(_StopLoop):
        _run(main.main_loop(system))


def test_main_loop_ciclo_completo_con_universe_ok():
    """Mercado abierto: 1 señal + 1 excepción + 1 vacío de Sentinels; US OK."""
    sig = MagicMock()
    dispatcher = MagicMock()
    dispatcher.run_cycle = AsyncMock()
    system = {
        "dispatcher": dispatcher,
        "sentinels": [MagicMock(), MagicMock(), MagicMock()],
        "universe_selector": MagicMock(),
    }
    with patch.object(main, "_is_market_open", return_value=True), \
         patch.object(main.asyncio, "gather",
                      new=AsyncMock(return_value=[[sig], RuntimeError("e"), None])), \
         patch.object(main.asyncio, "wait_for", new=AsyncMock()), \
         patch.object(main.asyncio, "sleep", new=AsyncMock(side_effect=_StopLoop)), \
         patch.object(main, "_send_heartbeat", new=AsyncMock()), \
         patch.object(main, "_seconds_to_next_candle", return_value=1.0), \
         patch.object(main, "logger"), \
         pytest.raises(_StopLoop):
        _run(main.main_loop(system))
    dispatcher.run_cycle.assert_awaited()


def test_main_loop_gather_y_run_cycle_lanzan():
    """asyncio.gather lanza (catch) + dispatcher.run_cycle lanza (catch); US None."""
    dispatcher = MagicMock()
    dispatcher.run_cycle = AsyncMock(side_effect=RuntimeError("cycle fail"))
    system = {"dispatcher": dispatcher, "sentinels": [MagicMock()],
              "universe_selector": None}
    with patch.object(main, "_is_market_open", return_value=True), \
         patch.object(main.asyncio, "gather",
                      new=AsyncMock(side_effect=RuntimeError("gather fail"))), \
         patch.object(main.asyncio, "sleep", new=AsyncMock(side_effect=_StopLoop)), \
         patch.object(main, "_send_heartbeat", new=AsyncMock()), \
         patch.object(main, "_seconds_to_next_candle", return_value=1.0), \
         patch.object(main, "logger"), \
         pytest.raises(_StopLoop):
        _run(main.main_loop(system))


def test_main_loop_universe_timeout():
    dispatcher = MagicMock()
    dispatcher.run_cycle = AsyncMock()
    system = {"dispatcher": dispatcher, "sentinels": [],
              "universe_selector": MagicMock()}
    with patch.object(main, "_is_market_open", return_value=True), \
         patch.object(main.asyncio, "gather", new=AsyncMock(return_value=[])), \
         patch.object(main.asyncio, "wait_for",
                      new=AsyncMock(side_effect=asyncio.TimeoutError())), \
         patch.object(main.asyncio, "sleep", new=AsyncMock(side_effect=_StopLoop)), \
         patch.object(main, "_send_heartbeat", new=AsyncMock()), \
         patch.object(main, "_seconds_to_next_candle", return_value=1.0), \
         patch.object(main, "logger"), \
         pytest.raises(_StopLoop):
        _run(main.main_loop(system))


def test_main_loop_universe_error_generico():
    dispatcher = MagicMock()
    dispatcher.run_cycle = AsyncMock()
    system = {"dispatcher": dispatcher, "sentinels": [],
              "universe_selector": MagicMock()}
    with patch.object(main, "_is_market_open", return_value=True), \
         patch.object(main.asyncio, "gather", new=AsyncMock(return_value=[])), \
         patch.object(main.asyncio, "wait_for",
                      new=AsyncMock(side_effect=ValueError("us boom"))), \
         patch.object(main.asyncio, "sleep", new=AsyncMock(side_effect=_StopLoop)), \
         patch.object(main, "_send_heartbeat", new=AsyncMock()), \
         patch.object(main, "_seconds_to_next_candle", return_value=1.0), \
         patch.object(main, "logger"), \
         pytest.raises(_StopLoop):
        _run(main.main_loop(system))


# =============================================================================
# § 5 — POLLERS de background
# =============================================================================

# --- _kill_switch_poller (sleep al final del loop) ---------------------------
def test_kill_switch_poller_halt():
    hist = MagicMock()
    hist.get_system_flag = AsyncMock(side_effect=["true", "true", "false"])
    hist.set_system_flag = AsyncMock()
    disp = MagicMock()
    disp.activate_kill_switch = AsyncMock()
    with patch.object(main.asyncio, "sleep", new=AsyncMock(side_effect=_StopLoop)), \
         patch.object(main, "logger"), \
         pytest.raises(_StopLoop):
        _run(main._kill_switch_poller(hist, disp))
    disp.activate_kill_switch.assert_awaited()


def test_kill_switch_poller_resume():
    hist = MagicMock()
    hist.get_system_flag = AsyncMock(side_effect=["false", "true", "true"])
    hist.set_system_flag = AsyncMock()
    disp = MagicMock()
    disp.deactivate_kill_switch = AsyncMock()
    with patch.object(main.asyncio, "sleep", new=AsyncMock(side_effect=_StopLoop)), \
         patch.object(main, "logger"), \
         pytest.raises(_StopLoop):
        _run(main._kill_switch_poller(hist, disp))
    disp.deactivate_kill_switch.assert_awaited()


def test_kill_switch_poller_excepcion_transitoria():
    hist = MagicMock()
    hist.get_system_flag = AsyncMock(side_effect=RuntimeError("db blip"))
    with patch.object(main.asyncio, "sleep", new=AsyncMock(side_effect=_StopLoop)), \
         patch.object(main, "logger") as lg, \
         pytest.raises(_StopLoop):
        _run(main._kill_switch_poller(hist, MagicMock()))
    assert lg.warning.called


# --- _reconciliation_poller (sleep al inicio del loop) -----------------------
def test_reconciliation_poller_con_actualizaciones():
    hist = MagicMock()
    with patch.object(main.asyncio, "sleep", new=AsyncMock(side_effect=[None, _StopLoop])), \
         patch.object(main, "reconcile_pending",
                      new=AsyncMock(return_value={"updates_applied": 2,
                                                  "filled": 1, "cancelled": 1})), \
         patch.object(main, "logger") as lg, \
         pytest.raises(_StopLoop):
        _run(main._reconciliation_poller(hist, interval_sec=1))
    assert lg.info.called


def test_reconciliation_poller_sin_actualizaciones():
    hist = MagicMock()
    with patch.object(main.asyncio, "sleep", new=AsyncMock(side_effect=[None, _StopLoop])), \
         patch.object(main, "reconcile_pending",
                      new=AsyncMock(return_value={"updates_applied": 0,
                                                  "filled": 0, "cancelled": 0})), \
         patch.object(main, "logger"), \
         pytest.raises(_StopLoop):
        _run(main._reconciliation_poller(hist, interval_sec=1))


def test_reconciliation_poller_cancelado():
    hist = MagicMock()
    with patch.object(main.asyncio, "sleep", new=AsyncMock(side_effect=[None])), \
         patch.object(main, "reconcile_pending",
                      new=AsyncMock(side_effect=asyncio.CancelledError())), \
         patch.object(main, "logger"), \
         pytest.raises(asyncio.CancelledError):
        _run(main._reconciliation_poller(hist, interval_sec=1))


def test_reconciliation_poller_excepcion():
    hist = MagicMock()
    with patch.object(main.asyncio, "sleep", new=AsyncMock(side_effect=[None, _StopLoop])), \
         patch.object(main, "reconcile_pending",
                      new=AsyncMock(side_effect=RuntimeError("boom"))), \
         patch.object(main, "logger") as lg, \
         pytest.raises(_StopLoop):
        _run(main._reconciliation_poller(hist, interval_sec=1))
    assert lg.error.called


# --- _daily_equity_snapshot_poller (sleep al inicio) -------------------------
def _et_dt(hour, minute=0):
    return datetime(2026, 5, 25, hour, minute, tzinfo=_ET)


def test_equity_snapshot_poller_antes_de_eod():
    hist = MagicMock()
    with patch.object(main.asyncio, "sleep", new=AsyncMock(side_effect=[None, _StopLoop])), \
         patch.object(main, "datetime") as md, \
         patch.object(main, "logger"), \
         pytest.raises(_StopLoop):
        md.now.return_value = _et_dt(9, 0)  # antes de 16:05
        _run(main._daily_equity_snapshot_poller(hist, MagicMock(), uuid.uuid4(),
                                                 interval_sec=1))


def test_equity_snapshot_poller_ya_registrado_hoy():
    hist = MagicMock()
    hist.has_equity_snapshot_today = AsyncMock(return_value=True)
    with patch.object(main.asyncio, "sleep", new=AsyncMock(side_effect=[None, _StopLoop])), \
         patch.object(main, "datetime") as md, \
         patch.object(main, "logger"), \
         pytest.raises(_StopLoop):
        md.now.return_value = _et_dt(16, 30)
        _run(main._daily_equity_snapshot_poller(hist, MagicMock(), uuid.uuid4(),
                                                 interval_sec=1))


def test_equity_snapshot_poller_registra():
    hist = MagicMock()
    hist.has_equity_snapshot_today = AsyncMock(return_value=False)
    hist.record_daily_equity_snapshot = AsyncMock()
    disp = MagicMock()
    with patch.object(main.asyncio, "sleep", new=AsyncMock(side_effect=[None, _StopLoop])), \
         patch.object(main.asyncio, "wait_for", new=AsyncMock(return_value=100000.0)), \
         patch.object(main.asyncio, "to_thread", new=MagicMock(return_value=MagicMock())), \
         patch.object(main, "datetime") as md, \
         patch.object(main, "logger"), \
         pytest.raises(_StopLoop):
        md.now.return_value = _et_dt(16, 30)
        _run(main._daily_equity_snapshot_poller(hist, disp, uuid.uuid4(),
                                                 interval_sec=1))
    hist.record_daily_equity_snapshot.assert_awaited()


def test_equity_snapshot_poller_cancelado():
    hist = MagicMock()
    hist.has_equity_snapshot_today = AsyncMock(side_effect=asyncio.CancelledError())
    with patch.object(main.asyncio, "sleep", new=AsyncMock(side_effect=[None])), \
         patch.object(main, "datetime") as md, \
         patch.object(main, "logger"), \
         pytest.raises(asyncio.CancelledError):
        md.now.return_value = _et_dt(16, 30)
        _run(main._daily_equity_snapshot_poller(hist, MagicMock(), uuid.uuid4(),
                                                 interval_sec=1))


def test_equity_snapshot_poller_excepcion():
    hist = MagicMock()
    hist.has_equity_snapshot_today = AsyncMock(side_effect=RuntimeError("blip"))
    with patch.object(main.asyncio, "sleep", new=AsyncMock(side_effect=[None, _StopLoop])), \
         patch.object(main, "datetime") as md, \
         patch.object(main, "logger") as lg, \
         pytest.raises(_StopLoop):
        md.now.return_value = _et_dt(16, 30)
        _run(main._daily_equity_snapshot_poller(hist, MagicMock(), uuid.uuid4(),
                                                 interval_sec=1))
    assert lg.error.called


# =============================================================================
# § 5 — main() (orquestación: crea tasks, corre loop, finally cancela)
# =============================================================================

class _FakeTask:
    """Task falsa: add_done_callback no-op, cancel marca, await lanza Cancelled."""

    def add_done_callback(self, cb):
        return None

    def cancel(self):
        return None

    def __await__(self):
        async def _c():
            raise asyncio.CancelledError()
        return _c().__await__()


def test_main_arranca_tasks_y_cierra_limpio():
    the_ear = MagicMock()
    the_ear.start_polling = MagicMock(return_value=MagicMock())
    hist = MagicMock()
    hist.close = AsyncMock()
    system = {"the_ear": the_ear, "historian": hist,
              "dispatcher": MagicMock(), "owner_id": uuid.uuid4()}
    with patch.object(main, "initialize", new=AsyncMock(return_value=system)), \
         patch.object(main, "main_loop", new=AsyncMock()), \
         patch.object(main, "_kill_switch_poller", new=MagicMock(return_value=MagicMock())), \
         patch.object(main, "_reconciliation_poller", new=MagicMock(return_value=MagicMock())), \
         patch.object(main, "_daily_equity_snapshot_poller",
                      new=MagicMock(return_value=MagicMock())), \
         patch.object(main.asyncio, "create_task",
                      new=lambda coro, name=None: _FakeTask()), \
         patch.object(main, "logger"):
        _run(main.main())
    hist.close.assert_awaited()


def test_main_finally_corre_si_loop_lanza():
    """Si main_loop lanza, el finally igual cancela tasks y cierra el historian."""
    the_ear = MagicMock()
    the_ear.start_polling = MagicMock(return_value=MagicMock())
    hist = MagicMock()
    hist.close = AsyncMock()
    system = {"the_ear": the_ear, "historian": hist,
              "dispatcher": MagicMock(), "owner_id": uuid.uuid4()}
    with patch.object(main, "initialize", new=AsyncMock(return_value=system)), \
         patch.object(main, "main_loop", new=AsyncMock(side_effect=RuntimeError("loop boom"))), \
         patch.object(main, "_kill_switch_poller", new=MagicMock(return_value=MagicMock())), \
         patch.object(main, "_reconciliation_poller", new=MagicMock(return_value=MagicMock())), \
         patch.object(main, "_daily_equity_snapshot_poller",
                      new=MagicMock(return_value=MagicMock())), \
         patch.object(main.asyncio, "create_task",
                      new=lambda coro, name=None: _FakeTask()), \
         patch.object(main, "logger"), \
         pytest.raises(RuntimeError, match="loop boom"):
        _run(main.main())
    hist.close.assert_awaited()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
