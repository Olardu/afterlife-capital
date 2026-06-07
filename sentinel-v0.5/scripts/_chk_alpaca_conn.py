"""Read-only: verifica conexion a Alpaca y muestra QUE cuenta se ve.
No imprime las API keys. No modifica nada (solo get_account + get_all_positions).
Uso: venv/Scripts/python.exe scripts/_chk_alpaca_conn.py
"""
import os
from pathlib import Path


def load_env(path: Path) -> dict:
    env = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def main():
    env = load_env(Path(__file__).resolve().parent.parent / ".env")
    key = env.get("ALPACA_API_KEY")
    secret = env.get("ALPACA_SECRET_KEY")
    base = env.get("ALPACA_BASE_URL", "")
    if not key or not secret:
        print("FALTAN credenciales ALPACA en .env")
        return
    print(f"key tail=...{key[-4:]}  base_url={base or '(default paper)'}")
    try:
        from alpaca.trading.client import TradingClient
    except ImportError:
        print("alpaca-py no instalado en este venv")
        return
    client = TradingClient(key, secret, paper=True)
    acct = client.get_account()
    print("--- CUENTA QUE VEO ---")
    print(f"account_number : {acct.account_number}")
    print(f"status         : {acct.status}")
    print(f"equity         : {acct.equity}")
    print(f"cash           : {acct.cash}")
    print(f"buying_power   : {acct.buying_power}")
    print(f"long_mkt_value : {acct.long_market_value}")
    pos = client.get_all_positions()
    print(f"posiciones     : {len(pos)}  -> {', '.join(p.symbol for p in pos[:15])}")


if __name__ == "__main__":
    main()
