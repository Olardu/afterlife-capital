#!/usr/bin/env python
"""
generate_quantstats_report.py — T-F: reporte QuantStats del periodo de
observacion (28-abr -> 23-may 2026).

Fuente de equity: daily_equity_snapshots esta VACIA (verificado 24-may), asi
que se usa Alpaca portfolio history (REST /v2/account/portfolio/history).

Read-only (solo GET a Alpaca). Autorizado por Roman (LOG 12:30 dec.1).

Output: backups/2026-05-24/quantstats_report_2026-04-28_2026-05-23.html
Imprime metricas clave para que Cowork las extraiga al balance.
"""
import json
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "backups" / "2026-05-24" / "quantstats_report_2026-04-28_2026-05-23.html"
P_START = pd.Timestamp("2026-04-28")
P_END = pd.Timestamp("2026-05-23 23:59:59")


def load_env():
    d = {}
    for line in (REPO / "sentinel-v0.5" / ".env").read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            d[k.strip()] = v.strip()
    return d


def fetch_equity(env):
    base = env["ALPACA_BASE_URL"].rstrip("/")
    url = f"{base}/v2/account/portfolio/history?period=2M&timeframe=1D&extended_hours=false"
    req = urllib.request.Request(url, headers={
        "APCA-API-KEY-ID": env["ALPACA_API_KEY"],
        "APCA-API-SECRET-KEY": env["ALPACA_SECRET_KEY"],
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    ts = data.get("timestamp", [])
    eq = data.get("equity", [])
    if not ts or not eq:
        raise RuntimeError(f"portfolio history vacio: keys={list(data.keys())}")
    idx = pd.to_datetime(ts, unit="s")
    s = pd.Series(eq, index=idx, dtype="float64").dropna()
    s = s[s > 0]  # descartar dias sin equity (0)
    return s


def main():
    env = load_env()
    OUT.parent.mkdir(parents=True, exist_ok=True)

    print("Fuente: Alpaca portfolio history (daily_equity_snapshots vacia).")
    equity = fetch_equity(env)
    print(f"Serie cruda Alpaca: {len(equity)} puntos, "
          f"{equity.index.min().date()} -> {equity.index.max().date()}")

    # Filtrar al periodo de observacion (fechas naive)
    equity.index = equity.index.tz_localize(None)
    period = equity[(equity.index >= P_START) & (equity.index <= P_END)]
    print(f"Serie periodo 28-abr->23-may: {len(period)} puntos "
          f"({period.index.min().date() if len(period) else '-'} -> "
          f"{period.index.max().date() if len(period) else '-'})")
    if len(period) < 3:
        print("ERROR: <3 puntos en el periodo; no se puede generar reporte.")
        return 1

    returns = period.pct_change().dropna()
    returns.index = pd.to_datetime(returns.index)

    import quantstats as qs

    # Metricas clave (sin benchmark — robustas)
    def safe(fn, *a, **k):
        try:
            return round(float(fn(returns, *a, **k)), 4)
        except Exception as e:  # noqa: BLE001
            return f"n/a ({type(e).__name__})"

    print("\n===== METRICAS CLAVE (Cowork: extraer al balance) =====")
    print(f"  Puntos serie (dias habiles): {len(period)}")
    print(f"  Equity inicial: {period.iloc[0]:.2f}")
    print(f"  Equity final:   {period.iloc[-1]:.2f}")
    print(f"  Return acumulado: {(period.iloc[-1]/period.iloc[0]-1)*100:.4f}%")
    print(f"  Sharpe:        {safe(qs.stats.sharpe)}")
    print(f"  Sortino:       {safe(qs.stats.sortino)}")
    print(f"  Max Drawdown:  {safe(qs.stats.max_drawdown)}")
    print(f"  Volatility(an):{safe(qs.stats.volatility)}")
    print(f"  Win rate:      {safe(qs.stats.win_rate)}")
    print(f"  Profit factor: {safe(qs.stats.profit_factor)}")

    # Reporte HTML — intentar con benchmark SPY; si falla, sin benchmark.
    title = "Sentinel v0.5 — Periodo de Observacion 28-abr -> 23-may 2026"
    generated = False
    for bench in ("SPY", None):
        try:
            kwargs = dict(output=str(OUT), title=title, rf=0.0, grayscale=False)
            if bench:
                kwargs["benchmark"] = bench
            qs.reports.html(returns, **kwargs)
            print(f"\nHTML generado {'con benchmark ' + bench if bench else 'SIN benchmark'}: {OUT}")
            generated = True
            break
        except Exception as e:  # noqa: BLE001
            print(f"  reporte con benchmark={bench} fallo: {type(e).__name__}: {e}")
    if not generated:
        print("ERROR: no se pudo generar el HTML por ninguna via.")
        return 1
    print(f"Tamano HTML: {OUT.stat().st_size} bytes")
    print(f"Abrir: Start-Process '{OUT}'")
    return 0


if __name__ == "__main__":
    sys.exit(main())
