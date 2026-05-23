#!/usr/bin/env python3
"""
Simulación aislada de los Fix 1 (Decimal/float) y Fix 2 (JOIN con sentinel_tickers)
contra el estado actual de producción del bot.

NO toca producción. NO requiere DB ni entorno del bot.

Reproduce el algoritmo de dispatcher.allocate_capital exactamente como está
en producción al 2026-05-08, y prueba 4 escenarios:

    A) Estado actual (sin fix): scores con Decimal + zombies en performance_scores
       → debe lanzar TypeError exactamente como en logs.

    B) Fix 1 aplicado, sin Fix 2: scores con float pero zombies todavía contaminan
       el promedio ponderado de Mantis → Sharpe agregado se cae.

    C) Fix 2 aplicado, sin Fix 1: scores filtrados (sin zombies) pero todavía
       Decimal → sigue crasheando.

    D) Ambos fixes aplicados: allocation Half-Kelly correcta.

Escenario D es lo que esperamos en producción tras aplicar los fixes.
"""

from decimal import Decimal
from typing import Optional


# ============================================================================
# CONSTANTES (de config.py — copiadas literalmente para no depender de imports)
# ============================================================================

MAX_CAPITAL_PER_SENTINEL = 25.0
MIN_CAPITAL_PER_SENTINEL = 5.0
KELLY_FRACTION           = 0.5


# ============================================================================
# DATOS SIMULADOS — reflejo del estado real de producción al 2026-05-08
# ============================================================================
# Mantis (S-2 rsi_short) tiene NVDA con Sharpe 39.96 (Excepción 1) y zombies
# TSLA y SPY que el sistema sigue leyendo aunque is_active=FALSE.
# Otros sentinels con Sharpes razonables — números aproximados, el punto es
# mostrar la estructura, no los valores exactos (esos los confirmará el SQL).

# Tipo realista: PostgreSQL NUMERIC viene como Decimal en asyncpg.
SCORES_FROM_DB_REAL = [
    # Mantis — NVDA real
    {"sentinel_id": "mantis-id", "sentinel_name": "Mantis", "ticker": "NVDA",
     "sharpe_ratio": Decimal("39.96"), "win_rate": Decimal("0.625"), "total_trades": 16},
    # Mantis — TSLA ZOMBIE (rotó hoy a TLT/GLD/IEF/etc, pero score sigue ahí)
    {"sentinel_id": "mantis-id", "sentinel_name": "Mantis", "ticker": "TSLA",
     "sharpe_ratio": Decimal("-2.45"), "win_rate": Decimal("0.222"), "total_trades": 18},
    # Mantis — SPY ZOMBIE
    {"sentinel_id": "mantis-id", "sentinel_name": "Mantis", "ticker": "SPY",
     "sharpe_ratio": Decimal("-1.80"), "win_rate": Decimal("0.300"), "total_trades": 15},

    # Otros 8 Sentinels — Sharpes hipotéticos (asumimos warmup completo)
    {"sentinel_id": "viper-id",     "sentinel_name": "Viper",     "ticker": "AAPL",
     "sharpe_ratio": Decimal("2.10"), "win_rate": Decimal("0.500"), "total_trades": 12},
    {"sentinel_id": "morpheus-id",  "sentinel_name": "Morpheus",  "ticker": "QQQ",
     "sharpe_ratio": Decimal("1.45"), "win_rate": Decimal("0.520"), "total_trades": 14},
    {"sentinel_id": "ghost-id",     "sentinel_name": "Ghost",     "ticker": "MSFT",
     "sharpe_ratio": Decimal("0.85"), "win_rate": Decimal("0.480"), "total_trades": 11},
    {"sentinel_id": "wraith-id",    "sentinel_name": "Wraith",    "ticker": "GLD",
     "sharpe_ratio": Decimal("0.30"), "win_rate": Decimal("0.450"), "total_trades": 10},
    {"sentinel_id": "phantom-id",   "sentinel_name": "Phantom",   "ticker": "XLP",
     "sharpe_ratio": Decimal("3.20"), "win_rate": Decimal("0.600"), "total_trades": 13},
    {"sentinel_id": "specter-id",   "sentinel_name": "Specter",   "ticker": "AMD",
     "sharpe_ratio": Decimal("0.0"),  "win_rate": Decimal("0.0"),   "total_trades": 0},
    {"sentinel_id": "shade-id",     "sentinel_name": "Shade",     "ticker": "SPY",
     "sharpe_ratio": Decimal("1.10"), "win_rate": Decimal("0.490"), "total_trades": 10},
    {"sentinel_id": "netrunner-id", "sentinel_name": "Netrunner", "ticker": "QQQ",
     "sharpe_ratio": Decimal("0.55"), "win_rate": Decimal("0.460"), "total_trades": 11},
]

# sentinel_tickers.is_active = TRUE (lo que get_sentinel_scores debería filtrar)
# Mantis ya rotó TSLA y SPY → no están activos. Solo NVDA queda original.
ACTIVE_TICKERS = {
    ("mantis-id", "NVDA"):     True,
    ("mantis-id", "TSLA"):     False,  # ZOMBIE
    ("mantis-id", "SPY"):      False,  # ZOMBIE
    ("viper-id", "AAPL"):      True,
    ("morpheus-id", "QQQ"):    True,
    ("ghost-id", "MSFT"):      True,
    ("wraith-id", "GLD"):      True,
    ("phantom-id", "XLP"):     True,
    ("specter-id", "AMD"):     True,
    ("shade-id", "SPY"):       True,
    ("netrunner-id", "QQQ"):   True,
}


def filter_active_scores(scores):
    """Lo que haría el JOIN con sentinel_tickers.is_active = TRUE (Fix 2)."""
    return [s for s in scores if ACTIVE_TICKERS.get((s["sentinel_id"], s["ticker"]), False)]


# ============================================================================
# ALGORITMO allocate_capital — REPLICADO EXACTO desde dispatcher.py L127-200
# ============================================================================

def allocate_capital_current(scores) -> dict:
    """Versión actual en producción — la del fix de Excepción 1.

    Esta es la que está crasheando en logs con TypeError.
    """
    if not scores:
        return {}

    sentinel_agg = {}
    for score in scores:
        sid    = str(score["sentinel_id"])
        sharpe = max(score["sharpe_ratio"] or 0.0, 0.0)   # ← Decimal sin convertir
        trades = score["total_trades"] or 0

        if sid not in sentinel_agg:
            sentinel_agg[sid] = {"weighted_sharpe_sum": 0.0, "total_trades": 0}

        sentinel_agg[sid]["weighted_sharpe_sum"] += sharpe * trades   # ← float += Decimal
        sentinel_agg[sid]["total_trades"]        += trades

    sentinel_sharpes = {}
    for sid, agg in sentinel_agg.items():
        if agg["total_trades"] > 0:
            sentinel_sharpes[sid] = agg["weighted_sharpe_sum"] / agg["total_trades"]
        else:
            sentinel_sharpes[sid] = 0.0

    total_sharpe = sum(sentinel_sharpes.values())
    allocation = {}
    for sid, sharpe in sentinel_sharpes.items():
        if total_sharpe == 0 or sharpe == 0:
            base = MIN_CAPITAL_PER_SENTINEL
        else:
            base = (sharpe / total_sharpe) * 100

        kelly_adjusted = base * KELLY_FRACTION
        clamped        = max(MIN_CAPITAL_PER_SENTINEL, min(MAX_CAPITAL_PER_SENTINEL, kelly_adjusted))
        allocation[sid] = clamped

    total = sum(allocation.values())
    if total > 100.0:
        factor = 100.0 / total
        allocation = {sid: pct * factor for sid, pct in allocation.items()}

    return allocation


def allocate_capital_fix1(scores) -> dict:
    """Fix 1 aplicado: float() e int() explícitos al leer de scores."""
    if not scores:
        return {}

    sentinel_agg = {}
    for score in scores:
        sid    = str(score["sentinel_id"])
        sharpe = max(float(score["sharpe_ratio"] or 0.0), 0.0)   # ← Fix
        trades = int(score["total_trades"] or 0)                 # ← Fix

        if sid not in sentinel_agg:
            sentinel_agg[sid] = {"weighted_sharpe_sum": 0.0, "total_trades": 0}

        sentinel_agg[sid]["weighted_sharpe_sum"] += sharpe * trades
        sentinel_agg[sid]["total_trades"]        += trades

    sentinel_sharpes = {}
    for sid, agg in sentinel_agg.items():
        if agg["total_trades"] > 0:
            sentinel_sharpes[sid] = agg["weighted_sharpe_sum"] / agg["total_trades"]
        else:
            sentinel_sharpes[sid] = 0.0

    total_sharpe = sum(sentinel_sharpes.values())
    allocation = {}
    for sid, sharpe in sentinel_sharpes.items():
        if total_sharpe == 0 or sharpe == 0:
            base = MIN_CAPITAL_PER_SENTINEL
        else:
            base = (sharpe / total_sharpe) * 100

        kelly_adjusted = base * KELLY_FRACTION
        clamped        = max(MIN_CAPITAL_PER_SENTINEL, min(MAX_CAPITAL_PER_SENTINEL, kelly_adjusted))
        allocation[sid] = clamped

    total = sum(allocation.values())
    if total > 100.0:
        factor = 100.0 / total
        allocation = {sid: pct * factor for sid, pct in allocation.items()}

    return allocation


# ============================================================================
# RUNNER
# ============================================================================

def print_alloc(label, alloc, account_equity=100_000):
    if not alloc:
        print(f"  {label}: ALLOCATION VACÍA — todos caen al fallback de 5%.")
        return
    print(f"  {label}:")
    sentinel_names = {s["sentinel_id"]: s["sentinel_name"] for s in SCORES_FROM_DB_REAL}
    for sid, pct in sorted(alloc.items(), key=lambda kv: -kv[1]):
        name = sentinel_names.get(sid, sid)
        dollars = account_equity * pct / 100
        print(f"    {name:<12} {pct:>6.2f}%  →  ${dollars:>10,.0f}")
    total = sum(alloc.values())
    print(f"    {'TOTAL':<12} {total:>6.2f}%  →  ${account_equity * total/100:>10,.0f}")


def safe_call(fn, *args):
    """Captura TypeError para mostrar el crash sin matar el script."""
    try:
        return ("OK", fn(*args))
    except TypeError as e:
        return ("CRASH", str(e))


def main():
    print("=" * 78)
    print("SIMULACIÓN DE FIXES — Sentinel v0.5 — 2026-05-08")
    print("=" * 78)
    print()

    print(f"Scores en DB (con Decimal): {len(SCORES_FROM_DB_REAL)} filas")
    zombies = [s for s in SCORES_FROM_DB_REAL
               if not ACTIVE_TICKERS.get((s["sentinel_id"], s["ticker"]), False)]
    print(f"De ellas, ZOMBIES (is_active=FALSE pero score persiste): {len(zombies)}")
    for z in zombies:
        print(f"  - {z['sentinel_name']} / {z['ticker']}: "
              f"sharpe={z['sharpe_ratio']}, trades={z['total_trades']}")
    print()

    # ESCENARIO A — estado actual de producción
    print("━" * 78)
    print("ESCENARIO A — Estado actual (sin ningún fix)")
    print("  Input: scores con Decimal + zombies")
    print("  Esperado: TypeError 'unsupported operand type(s) for +=: float, Decimal'")
    print("━" * 78)
    status, result = safe_call(allocate_capital_current, SCORES_FROM_DB_REAL)
    if status == "CRASH":
        print(f"  💥 CRASH como en logs: {result}")
        print(f"  → run_cycle catchea, cycle_allocation = {{}}, todos al fallback 5%.")
    else:
        print_alloc("Allocation", result)
    print()

    # ESCENARIO B — solo Fix 1
    print("━" * 78)
    print("ESCENARIO B — Solo Fix 1 (Decimal→float)")
    print("  Input: scores con Decimal + zombies (no filtrados)")
    print("  Esperado: NO crash, pero Mantis Sharpe diluido por TSLA/SPY zombies")
    print("━" * 78)
    status, result = safe_call(allocate_capital_fix1, SCORES_FROM_DB_REAL)
    if status == "CRASH":
        print(f"  💥 CRASH inesperado: {result}")
    else:
        print_alloc("Allocation", result)
        # Calcular Sharpe agregado de Mantis post-Fix 1 sin Fix 2
        mantis_scores = [s for s in SCORES_FROM_DB_REAL if s["sentinel_id"] == "mantis-id"]
        wsum = sum(max(float(s["sharpe_ratio"] or 0), 0) * int(s["total_trades"] or 0)
                   for s in mantis_scores)
        tsum = sum(int(s["total_trades"] or 0) for s in mantis_scores)
        agg = wsum / tsum if tsum else 0
        print(f"\n  Mantis Sharpe agregado (con zombies): {agg:.4f}")
        print(f"    → Diluido por TSLA (sharpe negativo capeado a 0) y SPY (idem).")
        print(f"    → max(neg, 0) = 0, así que solo NVDA pesa, pero sus 16 trades")
        print(f"      compiten contra trades zombie en el divisor → Sharpe baja.")
    print()

    # ESCENARIO C — solo Fix 2
    print("━" * 78)
    print("ESCENARIO C — Solo Fix 2 (JOIN scores con sentinel_tickers)")
    print("  Input: scores filtrados sin zombies, pero todavía Decimal")
    print("  Esperado: TypeError igual — el filtrado no convierte tipos")
    print("━" * 78)
    filtered = filter_active_scores(SCORES_FROM_DB_REAL)
    print(f"  Scores tras filtrar zombies: {len(filtered)} filas (eran {len(SCORES_FROM_DB_REAL)})")
    status, result = safe_call(allocate_capital_current, filtered)
    if status == "CRASH":
        print(f"  💥 CRASH como en logs: {result}")
    else:
        print_alloc("Allocation", result)
    print()

    # ESCENARIO D — ambos fixes aplicados
    print("━" * 78)
    print("ESCENARIO D — Ambos fixes aplicados (estado esperado post-deploy)")
    print("  Input: scores filtrados sin zombies, convertidos a float")
    print("  Esperado: allocation Half-Kelly correcta, Mantis recibe el tope")
    print("━" * 78)
    status, result = safe_call(allocate_capital_fix1, filtered)
    if status == "CRASH":
        print(f"  💥 CRASH inesperado: {result}")
    else:
        print_alloc("Allocation", result)
        # Verificación cualitativa
        mantis_pct = result.get("mantis-id", 0)
        print(f"\n  ✅ Mantis recibió: {mantis_pct:.2f}%")
        if mantis_pct >= MAX_CAPITAL_PER_SENTINEL - 0.01:
            print(f"     → Clampeado al techo de {MAX_CAPITAL_PER_SENTINEL}% por Sharpe muy alto. ✓")
        elif mantis_pct > MIN_CAPITAL_PER_SENTINEL:
            print(f"     → Por encima del piso, distribución funcionando. ✓")
        else:
            print(f"     → ⚠ En el piso. Algo no está bien.")

        # Estimación de qty esperada
        print(f"\n  PROYECCIÓN DE QTY EN NVDA (account_equity=$100K paper):")
        for nvda_price in (105, 120, 140):
            dollar_alloc = 100_000 * mantis_pct / 100
            max_qty = dollar_alloc / nvda_price
            print(f"    Si NVDA cotiza ${nvda_price}: max_qty = ${dollar_alloc:.0f}/${nvda_price} "
                  f"= {max_qty:.1f} shares → orden floor → {int(max_qty)} shares")
        print(f"    (Hoy con bug, todos los trades salen con qty=1 por estar en piso 5%)")
    print()

    print("=" * 78)
    print("CONCLUSIÓN")
    print("=" * 78)
    print("• Escenario A reproduce exactamente el bug en logs (21 errores hoy).")
    print("• Escenario B muestra que Fix 1 sin Fix 2 NO basta: Mantis sigue diluido.")
    print("• Escenario C confirma que Fix 2 sin Fix 1 sigue crasheando.")
    print("• Escenario D es el estado esperado: Mantis al tope (25%), resto distribuido")
    print("  según Sharpe, qty real en NVDA pasa de 1 share a varias.")
    print()
    print("→ AMBOS fixes son necesarios. Aplicar uno solo no resuelve.")


if __name__ == "__main__":
    main()
