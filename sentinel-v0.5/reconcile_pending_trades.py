"""
reconcile_pending_trades.py
===========================
Script de reconciliación: actualiza trades PENDING_NEW en la DB local
cruzando con el status real en Alpaca.

Uso:
    cd sentinel-v0.5
    venv\Scripts\python.exe reconcile_pending_trades.py

Modo DRY-RUN por defecto (solo muestra qué haría). Para aplicar:
    venv\Scripts\python.exe reconcile_pending_trades.py --apply

Creado: 2026-05-02 (Auditoría del sistema)
"""

import argparse
import asyncio
import os
import sys
from datetime import datetime
from uuid import UUID

from dotenv import load_dotenv
load_dotenv()

import asyncpg
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetOrdersRequest
from alpaca.trading.enums import QueryOrderStatus


ALPACA_API_KEY    = os.getenv("ALPACA_API_KEY")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")
DATABASE_URL      = os.getenv("DATABASE_URL")

# Fecha inicio del período de observación
OBSERVATION_START = "2026-04-28"


async def main(apply: bool):
    print("=" * 60)
    print("RECONCILIACIÓN DE TRADES PENDING_NEW")
    print(f"Modo: {'APLICAR CAMBIOS' if apply else 'DRY-RUN (solo muestra)'}")
    print("=" * 60)

    # 1. Conectar a DB y obtener trades PENDING_NEW
    pool = await asyncpg.create_pool(DATABASE_URL)
    async with pool.acquire() as conn:
        pending_trades = await conn.fetch("""
            SELECT trade_id, order_id, ticker, side, qty, status, created_at
            FROM trades
            WHERE status = 'PENDING_NEW'
            ORDER BY created_at
        """)

    print(f"\nTrades PENDING_NEW en DB: {len(pending_trades)}")
    if not pending_trades:
        print("No hay trades pendientes. Nada que hacer.")
        await pool.close()
        return

    # 2. Conectar a Alpaca y obtener todas las órdenes
    client = TradingClient(ALPACA_API_KEY, ALPACA_SECRET_KEY, paper=True)

    # Obtener órdenes closed (FILLED + CANCELLED) y all
    request_all = GetOrdersRequest(
        status=QueryOrderStatus.ALL,
        limit=500,
        after=datetime(2026, 4, 25),
    )
    alpaca_orders = client.get_orders(filter=request_all)

    # Indexar por order_id
    alpaca_index = {}
    for order in alpaca_orders:
        alpaca_index[str(order.id)] = order

    print(f"Órdenes en Alpaca (desde 25 abril): {len(alpaca_index)}")

    # 3. Cruzar y determinar actualizaciones
    updates = []
    not_found = []
    no_order_id = []

    for trade in pending_trades:
        trade_id  = trade["trade_id"]
        order_id  = trade["order_id"]
        ticker    = trade["ticker"]
        side      = trade["side"]
        created   = trade["created_at"]

        if not order_id:
            no_order_id.append(trade)
            continue

        alpaca_order = alpaca_index.get(order_id)
        if not alpaca_order:
            not_found.append(trade)
            continue

        real_status = alpaca_order.status.value.upper() if alpaca_order.status else "UNKNOWN"
        filled_price = float(alpaca_order.filled_avg_price) if alpaca_order.filled_avg_price else None

        updates.append({
            "trade_id":     trade_id,
            "order_id":     order_id,
            "ticker":       ticker,
            "side":         side,
            "created_at":   created,
            "old_status":   "PENDING_NEW",
            "new_status":   real_status,
            "filled_price": filled_price,
        })

    # 4. Mostrar resultados
    print(f"\n--- ACTUALIZACIONES ---")
    for u in updates:
        fp = f"${u['filled_price']:.2f}" if u['filled_price'] else "N/A"
        print(f"  {u['ticker']:5s} {u['side']:4s} | {u['created_at']} | "
              f"PENDING_NEW → {u['new_status']:10s} | filled={fp} | order={u['order_id'][:8]}...")

    if not_found:
        print(f"\n--- SIN MATCH EN ALPACA ({len(not_found)}) ---")
        for t in not_found:
            print(f"  {t['ticker']:5s} {t['side']:4s} | {t['created_at']} | order_id={t['order_id']}")

    if no_order_id:
        print(f"\n--- SIN ORDER_ID ({len(no_order_id)}) ---")
        for t in no_order_id:
            print(f"  {t['ticker']:5s} {t['side']:4s} | {t['created_at']} | trade_id={t['trade_id']}")

    # 5. Aplicar si no es dry-run
    if apply and updates:
        print(f"\nAplicando {len(updates)} actualizaciones...")
        async with pool.acquire() as conn:
            for u in updates:
                # Calcular slippage si es FILLED
                slippage = None
                if u["new_status"] == "FILLED" and u["filled_price"] is not None:
                    row = await conn.fetchrow("""
                        SELECT s.price_at_signal
                        FROM trades t
                        LEFT JOIN signals s ON t.signal_id = s.signal_id
                        WHERE t.trade_id = $1
                    """, u["trade_id"])
                    if row and row["price_at_signal"] is not None:
                        slippage = u["filled_price"] - float(row["price_at_signal"])

                await conn.execute("""
                    UPDATE trades
                    SET status = $1, filled_price = $2, slippage = $3
                    WHERE trade_id = $4
                """, u["new_status"], u["filled_price"], slippage, u["trade_id"])

                fp = f"${u['filled_price']:.2f}" if u['filled_price'] else "N/A"
                sl = f"{slippage:+.4f}" if slippage is not None else "N/A"
                print(f"  ✓ {u['ticker']} {u['side']} → {u['new_status']} filled={fp} slippage={sl}")

        print(f"\n✓ {len(updates)} trades actualizados exitosamente.")
    elif apply:
        print("\nNo hay actualizaciones que aplicar.")
    else:
        print(f"\n[DRY-RUN] Se actualizarían {len(updates)} trades. Usa --apply para ejecutar.")

    # Resumen final
    filled_count = sum(1 for u in updates if u["new_status"] == "FILLED")
    cancelled_count = sum(1 for u in updates if u["new_status"] == "CANCELLED")
    other_count = len(updates) - filled_count - cancelled_count
    print(f"\nResumen: {filled_count} FILLED, {cancelled_count} CANCELLED, {other_count} otros")

    await pool.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reconcilia trades PENDING_NEW con Alpaca")
    parser.add_argument("--apply", action="store_true", help="Aplicar cambios (default: dry-run)")
    args = parser.parse_args()
    asyncio.run(main(apply=args.apply))
