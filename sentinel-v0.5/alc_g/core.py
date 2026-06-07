# alc_g/core.py
# Lógica PURA del runtime ALC-G Fase 0 (sin Alpaca, sin DB, sin red — testeable
# 100%). El core_runner inyecta los datos (equity, posiciones, VIX) y orquesta.
# Spec: teamwork/alc-g-phase0-runtime-spec.md (Deep handoff #105).
#
# §8.6 Decimal exacto en todo lo que toca dinero. Las funciones devuelven Decimal.

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from alc_g.config_alc_g import CORE_WEIGHTS, BALLAST_SPLIT, AlcgParams


def _D(x) -> Decimal:
    return x if isinstance(x, Decimal) else Decimal(str(x))


# --- Leverage real y techo por glide-path ------------------------------------

def calc_real_leverage(long_value, equity) -> Decimal:
    """Leverage real = valor long de mercado / equity. equity<=0 -> 0
    (cuenta liquidada/sin equity; evita división por cero)."""
    long_value, equity = _D(long_value), _D(equity)
    if equity <= 0:
        return Decimal("0")
    return long_value / equity


def max_leverage_for_equity(equity, p: AlcgParams | None = None) -> Decimal:
    """Techo de leverage por capital (glide-path escalonado, spec §4). A más
    capital, menos techo: preserva ganancias ex-ante (no es escudo de crash)."""
    p = p or AlcgParams()
    equity = _D(equity)
    if equity < p.glide_t1_equity:
        return p.glide_lev_seed
    if equity < p.glide_t2_equity:
        return p.glide_lev_t1
    if equity < p.glide_t3_equity:
        return p.glide_lev_t2
    return p.glide_lev_floor


def effective_leverage(equity, p: AlcgParams | None = None,
                       vix_capped: bool = False) -> Decimal:
    """Leverage que se opera = min(slider, techo glide-path). Si el modo auto
    cappeó por VIX, el techo adicional es vix_capped_leverage. El slider NUNCA
    supera ningún techo (spec §2.1, §4, §5)."""
    p = p or AlcgParams()
    ceil_glide = max_leverage_for_equity(equity, p)
    eff = min(_D(p.leverage_target), ceil_glide)
    if vix_capped:
        eff = min(eff, _D(p.vix_capped_leverage))
    return eff


# --- Pesos objetivo (núcleo apalancado + lastre) -----------------------------

def target_exposure_by_ticker(equity, leverage, p: AlcgParams | None = None) -> dict[str, Decimal]:
    """Valor objetivo ($) por ticker para una equity y leverage dados.

    Núcleo (SPY/QQQ/IWM): apalancado al `leverage`. Lastre (TLT/GLD, si el preset
    lo usa): a 1.0× (sin leverage), spec §3. Turbo => ballast_pct=0 => 100% núcleo.

      core_pct      = 1 - ballast_pct
      core_total    = equity * core_pct * leverage
      ballast_total = equity * ballast_pct * 1.0
    """
    p = p or AlcgParams()
    equity, leverage = _D(equity), _D(leverage)
    ballast_pct = p.preset_cfg().ballast_pct
    core_pct = Decimal("1") - ballast_pct

    out: dict[str, Decimal] = {}
    core_total = equity * core_pct * leverage
    for tk, w in CORE_WEIGHTS.items():
        out[tk] = core_total * w
    if ballast_pct > 0:
        ballast_total = equity * ballast_pct  # 1.0× (sin leverage)
        for tk, w in BALLAST_SPLIT.items():
            out[tk] = out.get(tk, Decimal("0")) + ballast_total * w
    return out


# --- Gap y decisión de rebalanceo --------------------------------------------

def leverage_gap(target_lev, real_lev) -> Decimal:
    """Gap = real - target. Positivo = sobre-apalancado (vender); negativo =
    sub-invertido (comprar). Se reporta cada ciclo (spec §2.3)."""
    return _D(real_lev) - _D(target_lev)


def needs_leverage_rebalance(gap, p: AlcgParams | None = None) -> bool:
    """True si |gap| supera el umbral de rebalanceo (spec §2.3)."""
    p = p or AlcgParams()
    return abs(_D(gap)) > p.rebalance_gap


def component_drifts(positions: dict, target: dict[str, Decimal]) -> dict[str, Decimal]:
    """Drift relativo por ticker = (valor_real - valor_objetivo) / valor_objetivo.
    `positions` = {ticker: market_value}. Ticker con objetivo 0 y valor>0 -> drift
    'infinito' representado como 1 (sobra algo que no debería estar)."""
    out: dict[str, Decimal] = {}
    for tk, tgt in target.items():
        tgt = _D(tgt)
        real = _D(positions.get(tk, 0))
        if tgt <= 0:
            out[tk] = Decimal("1") if real > 0 else Decimal("0")
        else:
            out[tk] = (real - tgt) / tgt
    # tickers que están en cartera pero NO en el target (no deberían existir)
    for tk, real in positions.items():
        if tk not in target and _D(real) > 0:
            out[tk] = Decimal("1")
    return out


def drifted_tickers(positions: dict, target: dict[str, Decimal],
                    p: AlcgParams | None = None) -> list[str]:
    """Tickers cuyo drift supera la banda ±drift_band (spec §7)."""
    p = p or AlcgParams()
    drifts = component_drifts(positions, target)
    return sorted(tk for tk, d in drifts.items() if abs(d) > p.drift_band)


# --- Modo auto VIX (des-arriesga; estado de la racha de liberación) ----------

@dataclass(frozen=True)
class VixState:
    """Estado del modo auto por VIX. `capped`=True mientras se mantiene el cap a
    1.0×. `release_streak`=días consecutivos con VIX < release_threshold."""
    capped: bool = False
    release_streak: int = 0


def step_vix_auto(state: VixState, vix_close, p: AlcgParams | None = None) -> VixState:
    """Avanza un día el modo auto (spec §5). NUNCA sube leverage por sí solo:
    solo entra al cap (VIX>40) o lo libera tras `vix_release_days` seguidos <35.
    Devuelve el nuevo estado (puro, sin efectos)."""
    p = p or AlcgParams()
    vix = _D(vix_close)
    if not state.capped:
        if vix > p.vix_cap_threshold:
            return VixState(capped=True, release_streak=0)
        return VixState(capped=False, release_streak=0)
    # ya cappeado: contar racha de recuperación
    if vix < p.vix_release_threshold:
        streak = state.release_streak + 1
        if streak >= p.vix_release_days:
            return VixState(capped=False, release_streak=0)  # libera
        return VixState(capped=True, release_streak=streak)
    return VixState(capped=True, release_streak=0)  # se interrumpe la racha


# --- Piso de aportes $100K (DCA contracíclico) -------------------------------

def dca_floor_deposit(equity, p: AlcgParams | None = None) -> Decimal:
    """Aporte semanal a depositar (spec §6). $deposit si equity < piso y el piso
    está activo; 0 si no. Se reactiva solo cuando la equity vuelve a caer bajo el
    piso (la decisión es sin estado: depende solo de la equity actual)."""
    p = p or AlcgParams()
    if not p.floor_enabled:
        return Decimal("0")
    return p.floor_weekly_deposit if _D(equity) < p.floor_equity else Decimal("0")


# --- Snapshot del runtime (lo que el runner reporta cada ciclo) --------------

@dataclass(frozen=True)
class AccountSnapshot:
    """Foto de la cuenta #2 inyectada por el runner (DIP): equity, valor long de
    mercado y posiciones {ticker: market_value}. Agrupa los 3 datos de cuenta en
    un solo parámetro (§14.2: funciones ≤4 params)."""
    equity: Decimal
    long_value: Decimal
    positions: dict


@dataclass(frozen=True)
class CycleReport:
    target_leverage: Decimal
    effective_leverage: Decimal
    real_leverage: Decimal
    gap: Decimal
    needs_rebalance: bool
    glide_ceiling: Decimal
    vix_capped: bool
    equity: Decimal
    long_value: Decimal
    drifted: tuple[str, ...]


def build_cycle_report(account: AccountSnapshot, vix_state: VixState,
                       p: AlcgParams | None = None) -> CycleReport:
    """Arma el reporte de un ciclo (modo informe): qué leverage se quiere, qué
    techo aplica, leverage real y si haría falta rebalancear. No ejecuta nada."""
    p = p or AlcgParams()
    equity, long_value = _D(account.equity), _D(account.long_value)
    eff = effective_leverage(equity, p, vix_capped=vix_state.capped)
    real = calc_real_leverage(long_value, equity)
    gap = leverage_gap(eff, real)
    target = target_exposure_by_ticker(equity, eff, p)
    return CycleReport(
        target_leverage=_D(p.leverage_target),
        effective_leverage=eff,
        real_leverage=real,
        gap=gap,
        needs_rebalance=needs_leverage_rebalance(gap, p),
        glide_ceiling=max_leverage_for_equity(equity, p),
        vix_capped=vix_state.capped,
        equity=equity,
        long_value=long_value,
        drifted=tuple(drifted_tickers(account.positions, target, p)),
    )
