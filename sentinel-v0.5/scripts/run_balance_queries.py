#!/usr/bin/env python
"""
run_balance_queries.py — T-E: ejecuta las queries del balance del periodo de
observacion (28-abr -> 23-may 2026) y vuelca cada una a CSV.

Read-only puro (SELECT). Autorizado por Roman (LOG 12:30 dec.1).

IMPORTANTE: las queries originales en queries_balance_observacion.sql fueron
escritas contra un schema que NO coincide con la DB real. Este script contiene
las queries ADAPTADAS al schema verificado el 24-may. Columnas que NO existen
en la DB se OMITIERON (no se inventan datos):
  - trades.realized_pnl        -> NO existe (no hay P&L realizado persistido)
  - trades.fill_price          -> es filled_price
  - performance_scores.profit_factor / decay_status / last_updated_at / owner_id -> NO existen
    (hay performance_decay, calculated_at; sin owner_id)
  - sentinel_tickers.owner_id  -> NO existe
  - rotation_decisions: trigger_type->trigger_reason, cost_usd->claude_cost_usd,
    created_at->triggered_at, proposed_ticker->new_ticker, removed_ticker->old_ticker,
    was_executed->(status='executed')
  - macro_events.can_trade / parking_brake_triggered / vix_change_pct / spy_change_pct / owner_id -> NO existen
    (hay vix_level, spy_change_15min)
  - migration_log: migration_id->log_id, applied_at->migrated_at, sin description
  - sentinels.codename -> name

Uso: venv\\Scripts\\python.exe sentinel-v0.5\\scripts\\run_balance_queries.py
"""
import asyncio
import csv
import os
import sys
from datetime import datetime
from pathlib import Path

import asyncpg

OWNER = "***REMOVED-UUID***"
# asyncpg requiere objetos datetime para columnas timestamp (no acepta str).
T0 = datetime(2026, 4, 28, 9, 30, 0)
T1 = datetime(2026, 5, 23, 23, 59, 59)

REPO = Path(__file__).resolve().parents[2]
OUTDIR = REPO / "backups" / "2026-05-24" / "balance_data"

EXOTIC = (
    'SQQQ', 'SOXS', 'TZA', 'SDS', 'FAZ', 'BITI', 'ETHU',
    'TQQQ', 'UPRO', 'SPXL', 'TNA', 'FAS',
    'UVXY', 'VIXY', 'VXX', 'SVXY',
    'USO', 'UNG', 'DBA',
)

# (filename, sql, params) — sql usa $1..$n posicionales
QUERIES = [
    ("q3_1_resumen_sentinels", """
        SELECT s.sentinel_id, s.name, s.strategy_type,
               COUNT(t.trade_id) AS trades_totales,
               COUNT(*) FILTER (WHERE t.status='FILLED') AS fills,
               COUNT(*) FILTER (WHERE t.status='CANCELLED') AS cancelled,
               COUNT(*) FILTER (WHERE t.status='PENDING_NEW') AS pending,
               COUNT(DISTINCT t.ticker) AS tickers_operados,
               ROUND(AVG(COALESCE(t.slippage,0))::numeric,4) AS slippage_promedio
        FROM sentinels s
        LEFT JOIN trades t ON t.sentinel_id=s.sentinel_id AND t.owner_id=s.owner_id
             AND t.created_at>=$2::timestamp AND t.created_at<=$3::timestamp
        WHERE s.owner_id=$1
        GROUP BY s.sentinel_id, s.name, s.strategy_type
        ORDER BY s.strategy_type
    """, (OWNER, T0, T1)),

    ("q3_2_performance_scores", """
        SELECT ps.sentinel_id, s.name, ps.ticker, ps.total_trades,
               ROUND(ps.win_rate::numeric,4) AS win_rate,
               ROUND(ps.sharpe_ratio::numeric,4) AS sharpe,
               ps.performance_decay,
               ps.warning_status, ps.warning_detected_at, ps.calculated_at
        FROM performance_scores ps
        JOIN sentinels s ON s.sentinel_id=ps.sentinel_id
        JOIN sentinel_tickers st ON st.sentinel_id=ps.sentinel_id
             AND st.ticker=ps.ticker AND st.is_active=TRUE
        ORDER BY s.strategy_type, ps.sharpe_ratio DESC NULLS LAST
    """, ()),

    ("q3_3_trades_por_dia", """
        SELECT DATE(t.created_at) AS dia, s.name,
               COUNT(*) AS trades,
               COUNT(*) FILTER (WHERE t.status='FILLED') AS fills
        FROM trades t JOIN sentinels s ON s.sentinel_id=t.sentinel_id
        WHERE t.owner_id=$1 AND t.created_at>=$2::timestamp AND t.created_at<=$3::timestamp
        GROUP BY DATE(t.created_at), s.name
        ORDER BY dia, s.name
    """, (OWNER, T0, T1)),

    ("q3_4_tickers_por_sentinel", """
        SELECT s.name, s.strategy_type,
               STRING_AGG(st.ticker, ', ' ORDER BY st.ticker) AS tickers_activos,
               COUNT(st.ticker) AS num_tickers
        FROM sentinels s
        LEFT JOIN sentinel_tickers st ON st.sentinel_id=s.sentinel_id AND st.is_active=TRUE
        WHERE s.owner_id=$1
        GROUP BY s.name, s.strategy_type
        ORDER BY s.strategy_type
    """, (OWNER,)),

    ("q3_5_fills_detalle", """
        SELECT s.name, t.ticker, t.side, t.qty, t.filled_price, t.created_at,
               t.status, t.slippage
        FROM trades t JOIN sentinels s ON s.sentinel_id=t.sentinel_id
        WHERE t.owner_id=$1 AND t.created_at>=$2::timestamp AND t.created_at<=$3::timestamp
              AND t.status='FILLED'
        ORDER BY s.name, t.ticker, t.created_at
    """, (OWNER, T0, T1)),

    ("q4_1_resumen_rotaciones", """
        SELECT COUNT(*) AS rotaciones_totales,
               COUNT(*) FILTER (WHERE trigger_reason='warning') AS preanticipadas,
               COUNT(*) FILTER (WHERE trigger_reason='decay_confirmed') AS urgentes,
               COUNT(*) FILTER (WHERE trigger_reason='recovery_discard') AS descartadas_por_recovery,
               ROUND(SUM(claude_cost_usd)::numeric,4) AS costo_total_usd,
               ROUND(AVG(claude_cost_usd)::numeric,4) AS costo_promedio_por_call,
               ROUND(MAX(claude_cost_usd)::numeric,4) AS costo_max_call,
               COUNT(DISTINCT sentinel_id) AS sentinels_afectados
        FROM rotation_decisions
        WHERE owner_id=$1 AND triggered_at>=$2::timestamp AND triggered_at<=$3::timestamp
    """, (OWNER, T0, T1)),

    ("q4_2_rotaciones_por_sentinel", """
        SELECT s.name, s.strategy_type, COUNT(*) AS rotaciones,
               ROUND(SUM(rd.claude_cost_usd)::numeric,4) AS costo_usd,
               STRING_AGG(DISTINCT rd.new_ticker, ', ') AS tickers_propuestos
        FROM rotation_decisions rd JOIN sentinels s ON s.sentinel_id=rd.sentinel_id
        WHERE rd.owner_id=$1 AND rd.triggered_at>=$2::timestamp AND rd.triggered_at<=$3::timestamp
        GROUP BY s.name, s.strategy_type
        ORDER BY rotaciones DESC
    """, (OWNER, T0, T1)),

    ("q4_3_detalle_rotaciones", """
        SELECT rd.triggered_at, s.name, rd.trigger_reason,
               rd.old_ticker, rd.new_ticker,
               (rd.status='executed') AS was_executed,
               ROUND(rd.claude_cost_usd::numeric,4) AS costo_usd,
               LEFT(rd.claude_reasoning,200) AS razonamiento_preview
        FROM rotation_decisions rd JOIN sentinels s ON s.sentinel_id=rd.sentinel_id
        WHERE rd.owner_id=$1 AND rd.triggered_at>=$2::timestamp AND rd.triggered_at<=$3::timestamp
        ORDER BY rd.triggered_at
    """, (OWNER, T0, T1)),

    ("q4_4_productos_exoticos", """
        SELECT rd.new_ticker, COUNT(*) AS veces_propuesto,
               STRING_AGG(DISTINCT s.name, ', ') AS sentinels_afectados,
               BOOL_OR(rd.status='executed') AS algunavez_ejecutada
        FROM rotation_decisions rd JOIN sentinels s ON s.sentinel_id=rd.sentinel_id
        WHERE rd.owner_id=$1 AND rd.triggered_at>=$2::timestamp AND rd.triggered_at<=$3::timestamp
              AND rd.new_ticker = ANY($4::text[])
        GROUP BY rd.new_ticker
        ORDER BY veces_propuesto DESC
    """, (OWNER, T0, T1, list(EXOTIC))),

    ("q5_1_resumen_macro", """
        SELECT COUNT(*) AS eventos_totales,
               COUNT(*) FILTER (WHERE circuit_breaker_triggered=TRUE) AS circuit_breaker,
               ROUND(AVG(risk_score)::numeric,4) AS risk_score_promedio,
               ROUND(MAX(risk_score)::numeric,4) AS risk_score_max,
               COUNT(*) FILTER (WHERE risk_score>0.7) AS eventos_alto_riesgo
        FROM macro_events
        WHERE created_at>=$1::timestamp AND created_at<=$2::timestamp
    """, (T0, T1)),

    ("q5_2_eventos_por_dia", """
        SELECT DATE(created_at) AS dia, COUNT(*) AS eventos_dia,
               ROUND(MAX(risk_score)::numeric,4) AS risk_max_dia,
               ROUND(AVG(vix_level)::numeric,4) AS vix_level_avg,
               ROUND(AVG(spy_change_15min)::numeric,4) AS spy_change_15min_avg
        FROM macro_events
        WHERE created_at>=$1::timestamp AND created_at<=$2::timestamp
        GROUP BY DATE(created_at)
        ORDER BY dia
    """, (T0, T1)),

    ("q5_3_titulares_matched", """
        SELECT created_at, ROUND(risk_score::numeric,4) AS risk_score,
               JSONB_ARRAY_LENGTH(COALESCE(news_titles,'[]'::jsonb)) AS num_titulares,
               LEFT(news_titles::text,300) AS titulares_preview
        FROM macro_events
        WHERE created_at>=$1::timestamp AND created_at<=$2::timestamp AND risk_score>0.5
        ORDER BY risk_score DESC, created_at DESC
        LIMIT 20
    """, (T0, T1)),

    ("qB_1_usuarios", """
        SELECT role, COUNT(*) AS count, STRING_AGG(email, ', ') AS emails
        FROM users GROUP BY role ORDER BY role
    """, ()),

    ("qB_2_migraciones", """
        SELECT log_id, migrated_at, records_migrated
        FROM migration_log ORDER BY migrated_at DESC
    """, ()),

    ("qB_3_olarteduarte", """
        SELECT user_id, email, role, created_at
        FROM users WHERE email='***REMOVED-EMAIL***'
    """, ()),

    # § 6 — CorrelationGuard (post-migración 013 / EXP-003). Vacías hasta que el
    # bot corra con el código nuevo + migración aplicada. El runner las tolera
    # (per-query try/except) si las columnas aún no existen.
    ("q6_1_correlation_guard_summary", """
        SELECT COUNT(*) AS senales_evaluadas,
               COUNT(*) FILTER (WHERE reduction_factor = 1.0) AS pasaron_intactas,
               COUNT(*) FILTER (WHERE reduction_factor < 1.0 AND reduction_factor > 0) AS reducidas,
               COUNT(*) FILTER (WHERE reduction_factor = 0.0) AS descartadas,
               ROUND(AVG(avg_correlation_at_decision)::numeric, 4) AS correlacion_promedio,
               ROUND(MAX(avg_correlation_at_decision)::numeric, 4) AS correlacion_max
        FROM signals
        WHERE created_at >= $1::timestamp AND created_at <= $2::timestamp
              AND avg_correlation_at_decision IS NOT NULL
    """, (T0, T1)),

    ("q6_2_correlation_guard_distribution", """
        SELECT CASE
                   WHEN reduction_factor = 1.0  THEN 'intacta'
                   WHEN reduction_factor >= 0.75 THEN 'reducida_leve_>=0.75'
                   WHEN reduction_factor >= 0.5  THEN 'reducida_media_0.5-0.75'
                   WHEN reduction_factor > 0     THEN 'reducida_fuerte_<0.5'
                   ELSE 'descartada_0.0'
               END AS nivel,
               COUNT(*) AS n_senales,
               ROUND(AVG(avg_correlation_at_decision)::numeric, 4) AS avg_corr
        FROM signals
        WHERE created_at >= $1::timestamp AND created_at <= $2::timestamp
              AND avg_correlation_at_decision IS NOT NULL
        GROUP BY 1 ORDER BY n_senales DESC
    """, (T0, T1)),
]


def load_db_url():
    env = REPO / "sentinel-v0.5" / ".env"
    for line in env.read_text(encoding="utf-8").splitlines():
        if line.startswith("DATABASE_URL="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError("DATABASE_URL no encontrada en .env")


async def main():
    OUTDIR.mkdir(parents=True, exist_ok=True)
    conn = await asyncpg.connect(load_db_url())
    ok, fail = 0, 0
    print(f"OUTDIR: {OUTDIR}")
    try:
        for name, sql, params in QUERIES:
            try:
                rows = await conn.fetch(sql, *params)
                path = OUTDIR / f"{name}.csv"
                with open(path, "w", newline="", encoding="utf-8") as f:
                    w = csv.writer(f)
                    if rows:
                        w.writerow(rows[0].keys())
                        for r in rows:
                            w.writerow(list(r.values()))
                    else:
                        # query valida sin filas: dejar header si lo conocemos no es trivial;
                        # escribir archivo vacio-con-nota
                        w.writerow(["(sin filas)"])
                size = path.stat().st_size
                print(f"  OK  {name}.csv  filas={len(rows):<4} bytes={size}")
                ok += 1
            except Exception as e:  # noqa: BLE001
                print(f"  FAIL {name}: {type(e).__name__}: {e}")
                fail += 1
    finally:
        await conn.close()
    print(f"\nResumen: {ok} OK, {fail} FAIL de {len(QUERIES)} queries.")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
