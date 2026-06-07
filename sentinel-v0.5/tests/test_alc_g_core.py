# tests/test_alc_g_core.py
# TDD del runtime ALC-G Fase 0 (alc_g/core.py + config). Path financiero crítico
# (§8.6): sizing/allocation + controles de riesgo -> cobertura objetivo 100%.

from decimal import Decimal

import pytest

from alc_g.config_alc_g import AlcgParams, load_params_from_env, PRESETS
from alc_g.core import (
    AccountSnapshot,
    VixState,
    build_cycle_report,
    calc_real_leverage,
    component_drifts,
    dca_floor_deposit,
    drifted_tickers,
    effective_leverage,
    leverage_gap,
    max_leverage_for_equity,
    needs_leverage_rebalance,
    step_vix_auto,
    target_exposure_by_ticker,
)

D = Decimal


# --- calc_real_leverage ------------------------------------------------------

def test_real_leverage_normal():
    assert calc_real_leverage(150_000, 100_000) == D("1.5")


def test_real_leverage_equity_cero_no_divide():
    assert calc_real_leverage(150_000, 0) == D("0")


def test_real_leverage_equity_negativa():
    assert calc_real_leverage(50_000, -10_000) == D("0")


def test_real_leverage_acepta_strings_y_floats():
    assert calc_real_leverage("98000", 98_000.0) == D("1")


# --- max_leverage_for_equity (glide-path escalonado, spec §4) ----------------

def test_glide_seed_debajo_t1():
    assert max_leverage_for_equity(100_000) == D("1.5")
    assert max_leverage_for_equity(249_999) == D("1.5")


def test_glide_t1_entre_250_y_350():
    assert max_leverage_for_equity(250_000) == D("1.35")
    assert max_leverage_for_equity(349_999) == D("1.35")


def test_glide_t2_entre_350_y_500():
    assert max_leverage_for_equity(350_000) == D("1.2")
    assert max_leverage_for_equity(499_999) == D("1.2")


def test_glide_floor_desde_500():
    assert max_leverage_for_equity(500_000) == D("1.0")
    assert max_leverage_for_equity(2_000_000) == D("1.0")


def test_glide_es_monotono_decreciente():
    eqs = [100_000, 250_000, 350_000, 500_000, 900_000]
    levs = [max_leverage_for_equity(e) for e in eqs]
    assert all(levs[i] >= levs[i + 1] for i in range(len(levs) - 1))


# --- effective_leverage: el slider NUNCA supera el techo ---------------------

def test_effective_slider_bajo_el_techo_se_respeta():
    p = AlcgParams(leverage_target=D("1.2"))
    assert effective_leverage(100_000, p) == D("1.2")  # techo 1.5, slider 1.2


def test_slider_no_supera_techo_glide():
    p = AlcgParams(leverage_target=D("1.5"))
    # equity 400k -> techo glide 1.2 -> aunque el slider pida 1.5, opera 1.2
    assert effective_leverage(400_000, p) == D("1.2")


def test_effective_vix_capped_recorta_a_1():
    p = AlcgParams(leverage_target=D("1.5"))
    assert effective_leverage(100_000, p, vix_capped=True) == D("1.0")


def test_effective_vix_cap_no_sube_si_ya_estaba_bajo():
    p = AlcgParams(leverage_target=D("0.9"))
    # slider 0.9 < cap VIX 1.0 -> sigue 0.9 (el cap es techo, no piso)
    assert effective_leverage(100_000, p, vix_capped=True) == D("0.9")


# --- target_exposure_by_ticker -----------------------------------------------

def test_target_turbo_sin_lastre():
    # equity 100k, leverage 1.5, turbo (0% lastre) -> 150k repartido 40/30/30
    t = target_exposure_by_ticker(100_000, D("1.5"))
    assert t["SPY"] == D("60000.0")   # 150k * 0.40
    assert t["QQQ"] == D("45000.0")   # 150k * 0.30
    assert t["IWM"] == D("45000.0")
    assert "TLT" not in t and "GLD" not in t


def test_target_suma_igual_equity_por_leverage():
    t = target_exposure_by_ticker(100_000, D("1.5"))
    assert sum(t.values()) == D("150000.0")


def test_target_con_lastre_pasivo():
    # pasivo: leverage 1.0, ballast 50% (TLT30/GLD20 dentro del lastre)
    p = AlcgParams(preset="pasivo")
    t = target_exposure_by_ticker(100_000, D("1.0"), p)
    # core 50% * 1.0 = 50k -> 40/30/30 ; lastre 50% * 1.0 = 50k -> TLT60/GLD40
    assert t["SPY"] == D("20000.00")   # 50k*0.40
    assert t["TLT"] == D("30000.0000") # 50k*0.60
    assert t["GLD"] == D("20000.0000") # 50k*0.40


# --- leverage_gap + needs_leverage_rebalance ---------------------------------

def test_gap_sobreapalancado_positivo():
    assert leverage_gap(D("1.5"), D("1.55")) == D("0.05")


def test_gap_subinvertido_negativo():
    assert leverage_gap(D("1.5"), D("1.40")) == D("-0.10")


def test_needs_rebalance_supera_umbral():
    assert needs_leverage_rebalance(D("0.06")) is True
    assert needs_leverage_rebalance(D("-0.06")) is True


def test_no_rebalance_dentro_de_umbral():
    assert needs_leverage_rebalance(D("0.05")) is False
    assert needs_leverage_rebalance(D("0.02")) is False


# --- component_drifts + drifted_tickers --------------------------------------

def test_drift_componente_sobre_objetivo():
    target = {"SPY": D("100"), "QQQ": D("100")}
    pos = {"SPY": D("110"), "QQQ": D("100")}
    d = component_drifts(pos, target)
    assert d["SPY"] == D("0.10")
    assert d["QQQ"] == D("0")


def test_drift_objetivo_cero_con_posicion_es_uno():
    target = {"SPY": D("0")}
    assert component_drifts({"SPY": D("50")}, target)["SPY"] == D("1")
    assert component_drifts({"SPY": D("0")}, target)["SPY"] == D("0")


def test_drift_ticker_fuera_del_target():
    target = {"SPY": D("100")}
    d = component_drifts({"SPY": D("100"), "TSLA": D("30")}, target)
    assert d["TSLA"] == D("1")


def test_drifted_tickers_supera_banda():
    target = {"SPY": D("100"), "QQQ": D("100")}
    pos = {"SPY": D("106"), "QQQ": D("103")}  # 6% drift vs 3%
    assert drifted_tickers(pos, target) == ["SPY"]


# --- step_vix_auto (modo auto, histéresis) -----------------------------------

def test_vix_entra_al_cap_sobre_40():
    s = step_vix_auto(VixState(), D("41"))
    assert s.capped is True and s.release_streak == 0


def test_vix_no_capea_en_40_exacto():
    s = step_vix_auto(VixState(), D("40"))
    assert s.capped is False


def test_vix_mantiene_cap_mientras_no_recupera():
    s = VixState(capped=True, release_streak=0)
    s2 = step_vix_auto(s, D("38"))  # 38 no < 35 -> no cuenta
    assert s2.capped is True and s2.release_streak == 0


def test_vix_cuenta_racha_de_recuperacion():
    s = VixState(capped=True, release_streak=0)
    s1 = step_vix_auto(s, D("34"))
    assert s1.capped is True and s1.release_streak == 1
    s2 = step_vix_auto(s1, D("30"))
    assert s2.capped is True and s2.release_streak == 2
    s3 = step_vix_auto(s2, D("30"))  # 3er día seguido -> libera
    assert s3.capped is False and s3.release_streak == 0


def test_vix_racha_se_interrumpe_si_vuelve_a_subir():
    s = VixState(capped=True, release_streak=2)
    s2 = step_vix_auto(s, D("36"))  # 36 no < 35 -> resetea racha, sigue capped
    assert s2.capped is True and s2.release_streak == 0


def test_vix_capped_se_mantiene_sin_subir_solo():
    # estando NO capped y vix bajo, nunca entra a capped ni cuenta racha
    s = step_vix_auto(VixState(), D("20"))
    assert s.capped is False and s.release_streak == 0


# --- dca_floor_deposit -------------------------------------------------------

def test_floor_deposita_bajo_el_piso():
    assert dca_floor_deposit(90_000) == D("500")


def test_floor_pausa_sobre_el_piso():
    assert dca_floor_deposit(100_000) == D("0")
    assert dca_floor_deposit(150_000) == D("0")


def test_floor_desactivado():
    p = AlcgParams(floor_enabled=False)
    assert dca_floor_deposit(50_000, p) == D("0")


# --- build_cycle_report ------------------------------------------------------

def test_cycle_report_turbo_subinvertido():
    acc = AccountSnapshot(equity=D("100000"), long_value=D("130000"),
                          positions={"SPY": D("60000"), "QQQ": D("40000"),
                                     "IWM": D("30000")})
    r = build_cycle_report(acc, VixState())
    assert r.effective_leverage == D("1.5")
    assert r.real_leverage == D("1.3")
    assert r.gap == D("-0.2")              # subinvertido
    assert r.needs_rebalance is True
    assert r.glide_ceiling == D("1.5")
    assert r.vix_capped is False


def test_cycle_report_vix_capped_baja_target():
    acc = AccountSnapshot(equity=D("100000"), long_value=D("100000"), positions={})
    r = build_cycle_report(acc, VixState(capped=True))
    assert r.effective_leverage == D("1.0")
    assert r.vix_capped is True


def test_cycle_report_detecta_drift():
    acc = AccountSnapshot(equity=D("100000"), long_value=D("150000"),
                          positions={"SPY": D("70000"), "QQQ": D("45000"),
                                     "IWM": D("45000")})  # SPY sobra vs 60k target
    r = build_cycle_report(acc, VixState())
    assert "SPY" in r.drifted


# --- config: presets y carga de env ------------------------------------------

def test_preset_cfg_valido():
    p = AlcgParams(preset="rendimiento")
    assert p.preset_cfg().leverage == D("1.25")
    assert p.preset_cfg().ballast_pct == D("0.20")


def test_preset_cfg_invalido_lanza():
    with pytest.raises(ValueError):
        AlcgParams(preset="inexistente").preset_cfg()


def test_with_rechaza_campo_desconocido():
    with pytest.raises(TypeError):
        AlcgParams().with_(no_existe=1)


def test_load_params_from_env_pisa_solo_lo_presente():
    env = {"ALCG_LEVERAGE_TARGET": "1.25", "ALCG_PRESET": "normal",
           "ALCG_MODE": "ejecutar"}
    p = load_params_from_env(env)
    assert p.leverage_target == D("1.25")
    assert p.preset == "normal"
    assert p.mode == "ejecutar"


def test_load_params_from_env_vacio_deja_defaults():
    p = load_params_from_env({})
    assert p.leverage_target == D("1.5")
    assert p.preset == "turbo"
    assert p.mode == "informe"


def test_todos_los_presets_tienen_leverage_y_ballast():
    for name, preset in PRESETS.items():
        assert preset.name == name
        assert isinstance(preset.leverage, Decimal)
        assert isinstance(preset.ballast_pct, Decimal)
