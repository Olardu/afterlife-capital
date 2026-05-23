"""
reconcile_pending_trades.py
===========================
Reconciliación de trades PENDING_NEW: cruza el status local con Alpaca y actualiza.

Dos modos:
  - Auto-poller (main.py): `reconcile_pending(pool, apply=True, verbose=False)` cada 5 min (#H-6b).
  - CLI manual: `venv\\Scripts\\python.exe reconcile_pending_trades.py [--apply]` (dry-run por default).

Creado: 2026-05-02 (auditoría). Refactor a función reutilizable + integración al
main_loop como poller automático: 2026-05-23 (#H-6b).
"""

import argparse
import asyncio
import logging
import os
from datetime import datetime
from decimal import Decimal

from dotenv import load_dotenv
load_dotenv()

import asyncpg
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetOrdersRequest
from alpaca.trading.enums import QueryOrderStatus

logger = logging.getLogger("sentinel.reconciler")

ALPACA_API_KEY    = os.getenv("ALPACA_API_KEY")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")
DATABASE_URL      = os.getenv("DATABASE_URL")


async def reconcile_pending(
    pool: asyncpg.Pool,
    apply: bool = True,
    max_age_minutes: int = 5,
    verbose: bool = False,
) -> dict:
    """
    Reconcilia trades PENDING_NEW con su status real en Alpaca.

    Args:
        pool: connection pool asyncpg.
        apply: True = aplica los UPDATE; False = dry-run (solo reporta).
        max_age_minutes: solo reconciliar PENDING_NEW más viejos que esto (evita
                         tocar trades recién creados que Alpaca aún no procesó).
        verbose: True = print() al stdout (modo CLI); False = logger (auto-poller).

    Returns:
        {pending_checked, updates_applied, filled, cancelled, not_found_in_alpaca, no_order_id}
    """
    def out(msg: str):
        if verbose:
            print(msg)
        else:
            logger.debug(msg)

    stats = {
        "pending_checked": 0, "updates_applied": 0, "filled": 0,
        "cancelled": 0, "not_found_in_alpaca": 0, "no_order_id": 0,
    }

    # 1. Trades PENDING_NEW más viejos que max_age_minutes (param para evitar inyección).
    async with pool.acquire() as conn:
        pending_trades = await conn.fetch(
            """
            SELECT trade_id, order_id, ticker, side, qty, status, created_at
            FROM trades
            WHERE status = 'PENDING_NEW'
              AND created_at < NOW() - (($1)::text || ' minutes')::interval
            ORDER BY created_at
            """,
            str(max_age_minutes),
        )
    stats["pending_checked"] = len(pending_trades)
    out(f"Trades PENDING_NEW (>{max_age_minutes}min) en DB: {len(pending_trades)}")
    if not pending_trades:
        return stats

    # 2. Órdenes de Alpaca, indexadas por order_id.
    client = TradingClient(ALPACA_API_KEY, ALPACA_SECRET_KEY, paper=True)
    request_all = GetOrdersRequest(status=QueryOrderStatus.ALL, limit=500, after=datetime(2026, 4, 25))
    alpaca_orders = client.get_orders(filter=request_all)
    alpaca_index = {str(o.id): o for o in alpaca_orders}
    out(f"Órdenes en Alpaca: {len(alpaca_index)}")

    # 3. Cruzar y determinar actualizaciones.
    updates = []
    for trade in pending_trades:
        order_id = trade["order_id"]
        if not order_id:
            stats["no_order_id"] += 1
            out(f"  sin order_id: {trade['ticker']} {trade['side']} trade_id={trade['trade_id']}")
            continue
        alpaca_order = alpaca_index.get(order_id)
        if not alpaca_order:
            stats["not_found_in_alpaca"] += 1
            out(f"  sin match en Alpaca: {trade['ticker']} {trade['side']} order_id={order_id}")
            continue
        real_status  = alpaca_order.status.value.upper() if alpaca_order.status else "UNKNOWN"
        filled_price = Decimal(str(alpaca_order.filled_avg_price)) if alpaca_order.filled_avg_price else None
        updates.append({
            "trade_id": trade["trade_id"], "order_id": order_id,
            "ticker": trade["ticker"], "side": trade["side"],
            "new_status": real_status, "filled_price": filled_price,
        })
        out(f"  {trade['ticker']} {trade['side']} PENDING_NEW → {real_status} filled={filled_price}")

    # 4. Aplicar (si no es dry-run).
    if apply:
        async with pool.acquire() as conn:
            for u in updates:
                slippage = None
                if u["new_status"] == "FILLED" and u["filled_price"] is not None:
                    row = await conn.fetchrow(
                        """
                        SELECT s.price_at_signal
                        FROM trades t
                        LEFT JOIN signals s ON t.signal_id = s.signal_id
                        WHERE t.trade_id = $1
                        """,
                        u["trade_id"],
                    )
                    if row and row["price_at_signal"] is not None:
                        # asyncpg devuelve Decimal para NUMERIC → resta exacta (#H-4)
                        slippage = u["filled_price"] - row["price_at_signal"]
                await conn.execute(
                    """
                    UPDATE trades SET status = $1, filled_price = $2, slippage = $3
                    WHERE trade_id = $4
                    """,
                    u["new_status"], u["filled_price"], slippage, u["trade_id"],
                )
                stats["updates_applied"] += 1
                if u["new_status"] == "FILLED":
                    stats["filled"] += 1
                elif u["new_status"] == "CANCELLED":
                    stats["cancelled"] += 1
                out(f"  ✓ {u['ticker']} {u['side']} → {u['new_status']} filled={u['filled_price']} slippage={slippage}")
    else:
        out(f"[DRY-RUN] Se actualizarían {len(updates)} trades. Usar --apply para ejecutar.")

    out(f"Resumen: {stats['updates_applied']} aplicados | {stats['filled']} FILLED | {stats['cancelled']} CANCELLED")
    return stats


async def _cli_main(apply: bool):
    """Wrapper CLI: mantiene el comportamiento manual (dry-run por default, verbose)."""
    print("=" * 60)
    print("RECONCILIACIÓN DE TRADES PENDING_NEW")
    print(f"Modo: {'APLICAR CAMBIOS' if apply else 'DRY-RUN (solo muestra)'}")
    print("=" * 60)
    pool = await asyncpg.create_pool(DATABASE_URL)
    try:
        # CLI reconcilia TODOS los PENDING_NEW (max_age_minutes=0), como el script original.
        stats = await reconcile_pending(pool, apply=apply, max_age_minutes=0, verbose=True)
    finally:
        await pool.close()
    print(f"\nResumen final: {stats}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reconcilia trades PENDING_NEW con Alpaca")
    parser.add_argument("--apply", action="store_true", help="Aplicar cambios (default: dry-run)")
    args = parser.parse_args()
    asyncio.run(_cli_main(apply=args.apply))
