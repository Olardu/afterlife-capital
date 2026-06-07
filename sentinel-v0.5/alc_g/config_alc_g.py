# alc_g/config_alc_g.py
# Perillas del runtime ALC-G Fase 0. Inmutables (una estructura por corrida).
# Spec: teamwork/alc-g-phase0-runtime-spec.md (Deep handoff #105).
#
# §8.6: todo lo que toca dinero (pesos, leverage, umbrales de capital, piso) es
# Decimal. Días/ventanas son int. VIX es Decimal (se compara con umbrales).

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal

# --- Núcleo apalancado: pesos del core-blend (suman 1) -----------------------
# Mismo blend que el research ALC-G (params.CORE_WEIGHTS).
CORE_WEIGHTS: dict[str, Decimal] = {
    "SPY": Decimal("0.40"),
    "QQQ": Decimal("0.30"),
    "IWM": Decimal("0.30"),
}

# --- Lastre (ballast) por preset --------------------------------------------
# Split DENTRO del sleeve de lastre (suman 1). Turbo no usa lastre.
BALLAST_SPLIT: dict[str, Decimal] = {
    "TLT": Decimal("0.60"),
    "GLD": Decimal("0.40"),
}


@dataclass(frozen=True)
class Preset:
    """Composición de un preset: leverage del core + % de lastre (spec §3)."""
    name: str
    leverage: Decimal
    ballast_pct: Decimal


# Tabla de presets (spec §3). Fase 0 arranca en Turbo (0% lastre).
PRESETS: dict[str, Preset] = {
    "turbo":       Preset("turbo",       Decimal("1.5"),  Decimal("0.00")),
    "rendimiento": Preset("rendimiento", Decimal("1.25"), Decimal("0.20")),
    "normal":      Preset("normal",      Decimal("1.15"), Decimal("0.30")),
    "pasivo":      Preset("pasivo",      Decimal("1.0"),  Decimal("0.50")),
}


@dataclass(frozen=True)
class AlcgParams:
    """Config inmutable del runtime ALC-G Fase 0. Defaults = GATE de Roman
    (Turbo 1.5×, glide-path semilla, piso $100K, modo informe)."""

    # --- Slider de leverage (humano-en-el-loop) -----------------------------
    leverage_target: Decimal = Decimal("1.5")
    preset: str = "turbo"

    # --- Glide-path: techo de leverage por capital (spec §4) ----------------
    # Escalonado simple (no vol-scaling): a más capital, menos techo.
    glide_t1_equity: Decimal = Decimal("250000")   # < t1 -> lev_seed
    glide_t2_equity: Decimal = Decimal("350000")   # < t2 -> lev_t1
    glide_t3_equity: Decimal = Decimal("500000")   # < t3 -> lev_t2 ; >= t3 -> lev_floor
    glide_lev_seed: Decimal = Decimal("1.5")
    glide_lev_t1: Decimal = Decimal("1.35")
    glide_lev_t2: Decimal = Decimal("1.2")
    glide_lev_floor: Decimal = Decimal("1.0")

    # --- Rebalanceo (spec §7) -----------------------------------------------
    rebalance_gap: Decimal = Decimal("0.05")       # |target-real| > esto -> rebalancea
    drift_band: Decimal = Decimal("0.05")          # componente ±5% de su peso -> rebalancea
    cost_bps: Decimal = Decimal("10")              # 10 bps por trade (slippage+comisión)
    min_order_usd: Decimal = Decimal("100")        # banda muerta: deltas < esto se omiten

    # --- Modo auto: solo des-arriesga por VIX (spec §5) ---------------------
    vix_cap_threshold: Decimal = Decimal("40")     # VIX close > 40 -> cap 1.0×
    vix_release_threshold: Decimal = Decimal("35") # VIX < 35 ...
    vix_release_days: int = 3                      # ... por 3 días seguidos -> libera
    vix_capped_leverage: Decimal = Decimal("1.0")

    # --- Piso de aportes $100K (DCA contracíclico, spec §6) -----------------
    floor_enabled: bool = True
    floor_equity: Decimal = Decimal("100000")
    floor_weekly_deposit: Decimal = Decimal("500")

    # --- Ejecución ----------------------------------------------------------
    mode: str = "informe"   # informe (no manda órdenes) | ejecutar (GO Roman)

    def preset_cfg(self) -> Preset:
        if self.preset not in PRESETS:
            raise ValueError(f"preset desconocido: {self.preset!r} (válidos: {sorted(PRESETS)})")
        return PRESETS[self.preset]

    def with_(self, **overrides) -> "AlcgParams":
        unknown = set(overrides) - {f.name for f in self.__dataclass_fields__.values()}
        if unknown:
            raise TypeError(f"AlcgParams.with_: campos desconocidos {sorted(unknown)}")
        return replace(self, **overrides)


def _D(x) -> Decimal:
    return x if isinstance(x, Decimal) else Decimal(str(x))


def load_params_from_env(env: dict[str, str], base: AlcgParams | None = None) -> AlcgParams:
    """Construye AlcgParams desde un dict de entorno (.env.alc-g). Solo pisa los
    campos presentes; el resto queda en defaults (o en `base`)."""
    p = base or AlcgParams()
    overrides: dict = {}
    if env.get("ALCG_LEVERAGE_TARGET"):
        overrides["leverage_target"] = _D(env["ALCG_LEVERAGE_TARGET"])
    if env.get("ALCG_PRESET"):
        overrides["preset"] = env["ALCG_PRESET"].strip().lower()
    if env.get("ALCG_MODE"):
        overrides["mode"] = env["ALCG_MODE"].strip().lower()
    if env.get("ALCG_MIN_ORDER_USD"):
        overrides["min_order_usd"] = _D(env["ALCG_MIN_ORDER_USD"])
    return p.with_(**overrides) if overrides else p
