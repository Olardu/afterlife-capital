"""Read-only: verifica conexion a la cuenta Alpaca paper #2 de ALC-G.
Lee .env.alc-g (ALCG_*). NO imprime las keys. NO modifica nada.
Uso: venv/Scripts/python.exe scripts/_chk_alcg_conn.py
"""
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
    env = load_env(Path(__file__).resolve().parent.parent / ".env.alc-g")
    key = env.get("ALCG_ALPACA_API_KEY")
    secret = env.get("ALCG_ALPACA_SECRET_KEY")
    base = env.get("ALCG_ALPACA_BASE_URL", "")
    if not key or not secret:
        print("FALTAN ALCG_ALPACA_API_KEY / ALCG_ALPACA_SECRET_KEY en .env.alc-g")
        return
    print(f"key tail=...{key[-4:]}  base_url={base or '(default paper)'}")
    from alpaca.trading.client import TradingClient

    client = TradingClient(key, secret, paper=True)
    acct = client.get_account()
    print("--- CUENTA #2 (ALC-G) ---")
    print(f"account_number : {acct.account_number}")
    print(f"status         : {acct.status}")
    print(f"equity         : {acct.equity}")
    print(f"cash           : {acct.cash}")
    print(f"buying_power   : {acct.buying_power}")
    print(f"long_mkt_value : {acct.long_market_value}")
    pos = client.get_all_positions()
    syms = ", ".join(p.symbol for p in pos[:15]) or "(ninguna)"
    print(f"posiciones     : {len(pos)}  -> {syms}")


if __name__ == "__main__":
    main()
