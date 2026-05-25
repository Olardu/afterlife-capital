# backtest/__main__.py
# CLI del framework de backtesting (#HE-4):
#   python -m backtest --sentinel s2 --ticker SPY --start 2026-01-01 --end 2026-04-01
#   python -m backtest --sentinel s1 --ticker AAPL --source csv --csv bars.csv --json
#   python -m backtest --sentinel s2 --ticker SPY --start ... --end ... --paper-json paper.json

import argparse
import json
import sys

from backtest import data, runner

# Métricas propias que se muestran en el reporte (orden estable).
_METRIC_LABELS = [
    ("total_return", "Retorno total"),
    ("max_drawdown", "Max drawdown"),
    ("sharpe", "Sharpe (per-trade)"),
    ("sortino", "Sortino (per-trade)"),
    ("win_rate", "Win rate"),
    ("profit_factor", "Profit factor"),
    ("return_to_drawdown", "Return/Drawdown"),
    ("n_trades", "# Trades"),
]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m backtest",
        description="Backtest de un Sentinel de Sentinel v0.5 sobre datos históricos.",
    )
    p.add_argument("--sentinel", required=True, help="s1..s9 o strategy_type (ej. rsi_short)")
    p.add_argument("--ticker", required=True, help="Símbolo a operar (ej. SPY)")
    p.add_argument("--source", default="alpaca", choices=["alpaca", "csv", "yahoo"])
    p.add_argument("--start", help="Fecha inicio (alpaca/yahoo), ISO ej. 2026-01-01")
    p.add_argument("--end", help="Fecha fin (alpaca/yahoo), ISO ej. 2026-04-01")
    p.add_argument("--csv", dest="csv_path", help="Ruta CSV (source=csv)")
    p.add_argument("--timeframe", default="15Min", help="15Min | 1Hour | 1Day (default 15Min)")
    p.add_argument("--feed", default="IEX", help="Feed Alpaca (default IEX)")
    p.add_argument("--cash", type=float, default=100_000.0)
    p.add_argument("--commission", type=float, default=0.0, help="Fracción por trade (ej. 0.001)")
    p.add_argument("--allow-short", action="store_true", help="Permite shorts (default long-only)")
    p.add_argument("--paper-json", dest="paper_json", help="JSON de métricas paper para comparar")
    p.add_argument("--json", action="store_true", help="Salida en JSON (no reporte de texto)")
    p.add_argument("--output", help="Escribe el JSON del resultado a esta ruta")
    return p


def _fmt(value) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:,.4f}"
    return str(value)


def format_report(result: runner.BacktestResult, comparison: dict | None = None) -> str:
    """Reporte de texto legible del resultado (pura → testeable sin capturar stdout)."""
    lines = [
        "=" * 64,
        f"BACKTEST  {result.sentinel_key}  |  {result.ticker}  |  {result.n_bars} barras",
        "=" * 64,
        "Métricas (backtest.metrics):",
    ]
    for key, label in _METRIC_LABELS:
        lines.append(f"  {label:<20} {_fmt(result.metrics.get(key))}")
    lines.append("")
    lines.append("Stats nativas (Backtesting.py):")
    for key in ("return_pct", "buy_hold_return_pct", "max_drawdown_pct",
                "win_rate_pct", "profit_factor_native", "exposure_pct",
                "equity_final", "n_trades"):
        lines.append(f"  {key:<22} {_fmt(result.native.get(key))}")
    if comparison:
        lines.append("")
        lines.append("Comparación vs paper (backtest / paper / Δ):")
        for k, row in comparison.items():
            lines.append(
                f"  {k:<20} {_fmt(row['backtest'])} / {_fmt(row['paper'])} / {_fmt(row['delta'])}"
            )
    lines.append("=" * 64)
    return "\n".join(lines)


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        bars = data.load_bars(
            args.ticker, source=args.source, start=args.start, end=args.end,
            timeframe=args.timeframe, feed=args.feed, csv_path=args.csv_path,
        )
        result = runner.run_backtest(
            args.sentinel, bars, ticker=args.ticker, cash=args.cash,
            commission=args.commission, allow_short=args.allow_short,
        )
    except (ValueError, ImportError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    comparison = None
    if args.paper_json:
        with open(args.paper_json, encoding="utf-8") as fh:
            paper = json.load(fh)
        comparison = runner.compare_to_paper(result.metrics, paper)

    payload = result.to_dict()
    if comparison is not None:
        payload["comparison"] = comparison

    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)

    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(format_report(result, comparison))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
