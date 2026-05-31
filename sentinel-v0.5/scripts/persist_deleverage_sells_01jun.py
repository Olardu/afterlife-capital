"""
persist_deleverage_sells_01jun.py
=================================
Persiste en `trades` (DB de PRODUCCIÓN en ALC-P) los fills de las 3 SELL de
desapalancamiento (TLT/GLD/QQQ) encoladas el 29-may, cuando llenen al open del
lunes 1-jun. Reemplaza la persistencia manual del reconcile (el poller del bot no
auto-persiste fills de órdenes EXTERNAS — ver #TD en LOG). Adaptado de
`persist_residual_closes_27may.py`.

SEGURIDAD (escribe en la DB de producción):
- Idempotente: si el order_id ya está en `trades`, SKIP. Re-correrlo no duplica.
- Solo inserta si la orden está FILLED en Alpaca (usa filled_qty/filled_avg_price reales).
- Scope CERRADO: SOLO esos 3 order_ids.
- Backup DB (pg_dump -Fc) ANTES del primer INSERT.
- Poll-retry interno cada POLL_INTERVAL hasta que los 3 llenen o TIMEOUT.
- signal_id=NULL (cierre administrativo). Atribución FIFO B-opt-1: sentinel con
  mayor net long del ticker (calculado en vivo desde `trades`).
- owner_id = el del usuario 'roman' (lookup, no hardcode).
- filled_at: UTC aware -> ET naive (trades.created_at es naive ET).

Uso:  python scripts/persist_deleverage_sells_01jun.py [--apply]
      (dry-run por default; --apply ejecuta INSERTs. El systemd timer usa --apply.)
"""
import argparse
import asyncio
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import asyncpg
from alpaca.trading.client import TradingClient
from zoneinfo import ZoneInfo

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE = Path(__file__).resolve().parent.parent
# Cargar .env (CRLF-safe: strip \r de Windows si el archivo viajó por scp).
for line in (BASE / ".env").read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().rstrip("\r"))

# order_id -> ticker. SCOPE CERRADO (solo estas 3). order_ids del LOG ~5836.
ORDERS = {
    "11edd237-cad4-4e5c-9023-b621d0036b49": "TLT",
    "8589f8b4-5dc5-4915-8399-afbed20d0d73": "GLD",
    "e3180b05-adc7-4272-a1d5-9005b146cd9c": "QQQ",
}

POLL_INTERVAL = 120     # s entre reintentos
TIMEOUT       = 3600    # s (~1h) máximo de espera
ET            = ZoneInfo("America/New_York")

_log_fh = open(BASE / "logs" / "persist_deleverage_01jun.log", "a", encoding="utf-8")


def log(msg: str):
    stamp = datetime.now(tz=ET).strftime("%Y-%m-%d %H:%M:%S ET")
    line = f"[{stamp}] {msg}"
    print(line, flush=True)
    _log_fh.write(line + "\n"); _log_fh.flush()


def backup_db():
    """pg_dump -Fc de la DB de producción ANTES del primer INSERT."""
    outdir = BASE / "backups" / "2026-06-01"
    outdir.mkdir(parents=True, exist_ok=True)
    out = outdir / "db_pre_persist_deleverage.dump"
    if out.exists():
        log(f"backup ya existe: {out.name} (no re-dump)"); return
    r = subprocess.run(["pg_dump", "-Fc", os.environ["DATABASE_URL"], "-f", str(out)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"pg_dump falló: {r.stderr[:300]}")
    log(f"backup DB OK: {out} ({out.stat().st_size} bytes)")


async def attribution_sentinel(conn, ticker: str):
    """B-opt-1: sentinel con mayor net long (BUY-SELL) del ticker en `trades`."""
    row = await conn.fetchrow(
        """SELECT t.sentinel_id, s.name,
                  SUM(CASE WHEN t.side='BUY' THEN t.qty ELSE -t.qty END) AS net
           FROM trades t JOIN sentinels s ON s.sentinel_id = t.sentinel_id
           WHERE t.ticker=$1 AND t.status='FILLED' AND t.sentinel_id IS NOT NULL
           GROUP BY t.sentinel_id, s.name ORDER BY net DESC LIMIT 1""",
        ticker,
    )
    return (row["sentinel_id"], row["name"], row["net"]) if row else (None, None, None)


async def run_once(client, pool, apply: bool, did_backup: dict) -> set:
    """Procesa los 3 order_ids una vez. Devuelve el set de order_ids ya resueltos
    (en trades: insertados o pre-existentes)."""
    done = set()
    for oid, ticker in ORDERS.items():
        async with pool.acquire() as conn:
            if await conn.fetchval("SELECT 1 FROM trades WHERE order_id=$1", oid):
                done.add(oid); continue
        order = client.get_order_by_id(oid)
        status = order.status.value.upper()
        if status != "FILLED" or order.filled_avg_price is None:
            log(f"PEND  {ticker:4s} status={status} — reintento luego"); continue
        qty = Decimal(str(order.filled_qty))
        px  = Decimal(str(order.filled_avg_price))
        filled_et = order.filled_at.astimezone(ET).replace(tzinfo=None)
        async with pool.acquire() as conn:
            sid, sname, net = await attribution_sentinel(conn, ticker)
            if sid is None:
                log(f"ERROR {ticker:4s}: sin sentinel para atribuir (net long) — SKIP, revisar manual"); continue
            log(f"{'INSERT' if apply else 'DRY  '} {ticker:4s} SELL qty={qty} @ {px} ({filled_et}) -> {sname} (net {net}) | B-opt-1")
            if apply:
                if not did_backup["done"]:
                    backup_db(); did_backup["done"] = True
                await conn.execute(
                    """INSERT INTO trades
                       (trade_id, signal_id, sentinel_id, owner_id, ticker, side, qty,
                        filled_price, slippage, status, created_at, order_id)
                       VALUES ($1, NULL, $2, $3, $4, 'SELL', $5, $6, NULL, 'FILLED', $7, $8)""",
                    uuid.uuid4(), sid, OWNER_ID, ticker, qty, px, filled_et, oid,
                )
            # Resuelto: insertado (--apply) o "se persistiría" (dry-run). Así el dry-run
            # también corta el loop al tener los 3 listos (fix del nit de Cowork).
            done.add(oid)
    return done


async def audit(pool, client):
    """Audit inline: net DB (BUY-SELL FILLED) vs posición Alpaca para los 3 tickers."""
    log("=== AUDIT net DB vs Alpaca ===")
    alpaca_pos = {p.symbol: Decimal(str(p.qty)) for p in client.get_all_positions()}
    async with pool.acquire() as conn:
        for ticker in sorted(set(ORDERS.values())):
            net = await conn.fetchval(
                """SELECT COALESCE(SUM(CASE WHEN side='BUY' THEN qty ELSE -qty END),0)
                   FROM trades WHERE ticker=$1 AND status='FILLED'""", ticker)
            apos = alpaca_pos.get(ticker, Decimal(0))
            drift = Decimal(str(net)) - apos
            flag = "OK" if abs(drift) < 1 else "DRIFT"
            log(f"  {ticker:4s} net_db={net} alpaca={apos} drift={drift} [{flag}]")


async def main(apply: bool):
    global OWNER_ID
    client = TradingClient(os.environ["ALPACA_API_KEY"], os.environ["ALPACA_SECRET_KEY"], paper=True)
    pool = await asyncpg.create_pool(os.environ["DATABASE_URL"])
    did_backup = {"done": False}
    try:
        OWNER_ID = await pool.fetchval("SELECT user_id FROM users WHERE username='roman'")
        if OWNER_ID is None:
            raise RuntimeError("owner 'roman' no existe en users — abortando")
        log(f"owner_id={OWNER_ID} | apply={apply} | esperando fills de {list(ORDERS.values())}")
        deadline = time.monotonic() + TIMEOUT
        while True:
            done = await run_once(client, pool, apply, did_backup)
            if len(done) == len(ORDERS):
                log(f"TODOS resueltos ({len(done)}/{len(ORDERS)}).")
                await audit(pool, client)
                return 0
            if time.monotonic() >= deadline:
                log(f"TIMEOUT: {len(done)}/{len(ORDERS)} resueltos. Re-correr manual si hace falta.")
                return 1
            await asyncio.sleep(POLL_INTERVAL)
    finally:
        await pool.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="ejecuta los INSERT (default: dry-run)")
    OWNER_ID = None
    raise SystemExit(asyncio.run(main(ap.parse_args().apply)))
