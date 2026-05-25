"""
adopt_orphan_positions.py
==========================
Registra trades BUY retroactivos para posiciones huérfanas en Alpaca
que no tienen registro de compra en la DB local.

Contexto:
    MSFT y XLP tienen posiciones abiertas en Alpaca pero ningún trade
    BUY registrado en la DB. Esto ocurrió porque las compras se
    ejecutaron antes del inicio del período de observación (2026-04-28).

    Registrarlas permite que los Sentinels asignados (Neo para MSFT,
    Oracle para XLP) las reconozcan como propias y operen normalmente,
    manteniendo el flujo de datos limpio y evitando ruido en los datos
    que se recolectan durante el período de observación.

Uso:
    cd sentinel-v0.5
    venv\\Scripts\\python.exe adopt_orphan_positions.py

Modo DRY-RUN por defecto (solo muestra qué haría). Para aplicar:
    venv\\Scripts\\python.exe adopt_orphan_positions.py --apply

Creado: 2026-05-02 (Auditoría del sistema — posiciones huérfanas)
"""

import argparse
import asyncio
import os
import sys
from uuid import UUID

from dotenv import load_dotenv
load_dotenv()

import asyncpg

DATABASE_URL = os.getenv("DATABASE_URL")
OWNER_USERNAME = os.getenv("OWNER_USERNAME", "roman")

# ── Posiciones huérfanas a registrar ──────────────────────────────────
# Datos tomados de Alpaca positions API el 2026-05-02.
# avg_entry_price es el precio real de compra según Alpaca.
ORPHANS = [
    {
        "ticker": "MSFT",
        "sentinel_name": "S-8 RSI Divergence",
        "sentinel_id": UUID("be8e42cf-117e-4304-96dc-5b524b18745d"),
        "side": "BUY",
        "qty": 1,
        "filled_price": 424.60,
        "slippage": 0.0,
        "status": "FILLED",
        "note": "Posición huérfana — compra previa al período de observación",
    },
    {
        "ticker": "XLP",
        "sentinel_name": "S-3 Bollinger Bounce",
        "sentinel_id": UUID("33b98cac-16eb-4955-8427-683db8593c9d"),
        "side": "BUY",
        "qty": 1,
        "filled_price": 82.75,
        "slippage": 0.0,
        "status": "FILLED",
        "note": "Posición huérfana — compra previa al período de observación",
    },
]


async def main(apply: bool):
    if not DATABASE_URL:
        print("ERROR: DATABASE_URL no está configurada en .env")
        sys.exit(1)

    conn = await asyncpg.connect(DATABASE_URL)

    # Obtener owner_id
    row = await conn.fetchrow(
        "SELECT user_id FROM users WHERE username = $1", OWNER_USERNAME
    )
    if not row:
        print(f"ERROR: Usuario '{OWNER_USERNAME}' no encontrado en tabla users")
        await conn.close()
        sys.exit(1)

    owner_id = row["user_id"]
    print(f"Owner: {OWNER_USERNAME} ({owner_id})")
    print(f"Modo: {'APPLY' if apply else 'DRY-RUN (usar --apply para ejecutar)'}")
    print("=" * 60)

    for orphan in ORPHANS:
        ticker = orphan["ticker"]
        sentinel_name = orphan["sentinel_name"]

        # Verificar que no exista ya un BUY para este ticker/sentinel
        existing = await conn.fetchrow(
            """
            SELECT trade_id, created_at FROM trades
            WHERE sentinel_id = $1 AND ticker = $2 AND side = 'BUY' AND status = 'FILLED'
            ORDER BY created_at DESC LIMIT 1
            """,
            orphan["sentinel_id"], ticker
        )

        if existing:
            print(f"  SKIP {ticker} ({sentinel_name}): ya tiene BUY registrado "
                  f"(trade_id={existing['trade_id']}, {existing['created_at']})")
            continue

        print(f"\n  {ticker} → {sentinel_name}")
        print(f"    Side: {orphan['side']}, Qty: {orphan['qty']}, "
              f"Price: ${orphan['filled_price']:.2f}")
        print(f"    Nota: {orphan['note']}")

        if apply:
            trade_id = await conn.fetchval(
                """
                INSERT INTO trades
                    (signal_id, sentinel_id, owner_id, ticker, side, qty,
                     filled_price, slippage, status, order_id)
                VALUES (NULL, $1, $2, $3, $4, $5, $6, $7, $8, NULL)
                RETURNING trade_id
                """,
                orphan["sentinel_id"], owner_id, ticker,
                orphan["side"], orphan["qty"],
                orphan["filled_price"], orphan["slippage"], orphan["status"],
            )
            print(f"    ✓ Insertado: trade_id = {trade_id}")
        else:
            print("    → Se insertaría (dry-run)")

    print("\n" + "=" * 60)
    if not apply:
        print("Dry-run completado. Ejecutar con --apply para insertar.")
    else:
        print("Trades huérfanos registrados exitosamente.")
        print("Los Sentinels ahora reconocerán estas posiciones como propias.")

    await conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Adoptar posiciones huérfanas en la DB")
    parser.add_argument("--apply", action="store_true", help="Ejecutar los INSERT (sin esto solo muestra)")
    args = parser.parse_args()
    asyncio.run(main(apply=args.apply))
