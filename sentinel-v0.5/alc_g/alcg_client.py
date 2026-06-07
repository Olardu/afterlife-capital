# alc_g/alcg_client.py
# Wrapper de la cuenta Alpaca paper #2 (ALC-G). SOLO lectura en Fase 0 modo
# informe. La ejecución de órdenes está aislada tras `submit_rebalance` y exige
# mode="ejecutar" + GO de Roman (no se activa por default).
#
# DIP: el runner recibe un broker que cumple esta interfaz; en tests se inyecta
# un fake. El cliente real toca Alpaca; el fake no toca red -> tests 100%.

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Protocol

from alc_g.core import AccountSnapshot


def _D(x) -> Decimal:
    return x if isinstance(x, Decimal) else Decimal(str(x))


def load_dotenv(path: Path) -> dict[str, str]:
    """Parser mínimo de .env.alc-g (sin dependencias). Ignora comentarios/vacíos."""
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


class Broker(Protocol):
    """Interfaz mínima que el runner necesita del broker (DIP)."""

    def get_snapshot(self) -> AccountSnapshot: ...
    def get_vix_close(self) -> Decimal | None: ...


class AlpacaAlcgBroker:
    """Broker real sobre la cuenta paper #2. Lectura de equity/posiciones.
    NO ejecuta órdenes salvo `submit_rebalance` con allow_execute=True."""

    def __init__(self, api_key: str, secret_key: str, *, allow_execute: bool = False):
        if not api_key or not secret_key:
            raise ValueError("AlpacaAlcgBroker: faltan credenciales de la cuenta #2")
        from alpaca.trading.client import TradingClient

        self._client = TradingClient(api_key, secret_key, paper=True)
        self._allow_execute = allow_execute

    @classmethod
    def from_env(cls, env: dict[str, str], *, allow_execute: bool = False) -> "AlpacaAlcgBroker":
        return cls(
            env.get("ALCG_ALPACA_API_KEY", ""),
            env.get("ALCG_ALPACA_SECRET_KEY", ""),
            allow_execute=allow_execute,
        )

    def get_snapshot(self) -> AccountSnapshot:
        acct = self._client.get_account()
        positions = {p.symbol: _D(p.market_value) for p in self._client.get_all_positions()}
        return AccountSnapshot(
            equity=_D(acct.equity),
            long_value=_D(acct.long_market_value),
            positions=positions,
        )

    def get_vix_close(self) -> Decimal | None:
        """VIX diario. Fase 0: no se cablea fuente todavía (el modo auto se activa
        en Fase 3). Devuelve None -> el runner trata el modo auto como inactivo."""
        return None

    def submit_rebalance(self, orders: list[dict]) -> list[dict]:
        """Ejecuta órdenes de rebalanceo (modo ejecutar). BLOQUEADO salvo
        allow_execute=True (GO de Roman). En Fase 0 informe NUNCA se llama."""
        if not self._allow_execute:
            raise PermissionError(
                "submit_rebalance bloqueado: ALC-G en modo informe (allow_execute=False)"
            )
        raise NotImplementedError(
            "Ejecución de órdenes ALC-G pendiente de GO de Roman (Fase 0 = informe)"
        )
