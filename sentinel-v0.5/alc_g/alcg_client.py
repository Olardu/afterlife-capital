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

from alc_g.config_alc_g import AlcgParams
from alc_g.core import (
    AccountSnapshot,
    plan_rebalance_orders,
    sell_qty_from_position,
)


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
    def submit_rebalance(self, orders: list[dict], *,
                         min_order_usd, p: AlcgParams | None = ...) -> list[dict]: ...


class AlpacaAlcgBroker:
    """Broker real sobre la cuenta paper #2. Lectura de equity/posiciones.
    NO ejecuta órdenes salvo `submit_rebalance` con allow_execute=True."""

    def __init__(self, api_key: str, secret_key: str, *,
                 allow_execute: bool = False, client=None):
        # `client` inyectable (DIP) para tests sin red; en prod se crea el real.
        if client is None:
            if not api_key or not secret_key:
                raise ValueError("AlpacaAlcgBroker: faltan credenciales de la cuenta #2")
            from alpaca.trading.client import TradingClient

            client = TradingClient(api_key, secret_key, paper=True)
        self._client = client
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

    def _safe_get_position(self, ticker: str):
        """Posición abierta del ticker o None (Alpaca lanza si no existe)."""
        try:
            return self._client.get_open_position(ticker)
        except Exception:  # noqa: BLE001 — sin posición / error de red -> tratar como vacía
            return None

    @staticmethod
    def _order_result(ticker: str, side: str, order, *, qty=None, notional=None) -> dict:
        """Normaliza la respuesta del SDK (Order) a un dict JSON-safe para la UI."""
        status = order.status.value.upper() if getattr(order, "status", None) else "PENDING"
        filled = getattr(order, "filled_avg_price", None)
        res = {
            "ticker": ticker,
            "side": side,
            "status": status,
            "order_id": str(getattr(order, "id", "")),
            "filled_avg_price": str(filled) if filled else None,
            "skipped": False,
        }
        if qty is not None:
            res["qty"] = str(qty)
        if notional is not None:
            res["notional"] = str(notional)
        return res

    def submit_rebalance(self, orders: list[dict], *, min_order_usd,
                         p: AlcgParams | None = None) -> list[dict]:
        """Ejecuta el rebalanceo en la cuenta #2 (market DAY). BLOQUEADO salvo
        allow_execute=True. BUY = orden por notional ($); SELL = acciones enteras
        desde la posición real (o cierre total si el monto la cubre). Órdenes
        triviales (< min_order_usd) o sin posición para vender se omiten.

        Mercado cerrado -> las market DAY quedan pendientes y se llenan al open."""
        if not self._allow_execute:
            raise PermissionError(
                "submit_rebalance bloqueado: ejecución deshabilitada (allow_execute=False)"
            )
        from alpaca.trading.enums import OrderSide, TimeInForce
        from alpaca.trading.requests import MarketOrderRequest

        actions = plan_rebalance_orders(orders, _D(min_order_usd), p)
        results: list[dict] = []
        for a in actions:
            if a.side == "BUY":
                req = MarketOrderRequest(
                    symbol=a.ticker, notional=str(a.notional),
                    side=OrderSide.BUY, time_in_force=TimeInForce.DAY,
                )
                order = self._client.submit_order(req)
                results.append(self._order_result(a.ticker, "BUY", order, notional=a.notional))
                continue

            # SELL: traducir a acciones enteras desde la posición real
            pos = self._safe_get_position(a.ticker)
            if pos is None:
                results.append({"ticker": a.ticker, "side": "SELL", "skipped": True,
                                "reason": "sin posición para vender"})
                continue
            qty, close_all = sell_qty_from_position(
                a.notional, getattr(pos, "qty", 0), getattr(pos, "market_value", 0),
            )
            if close_all:
                order = self._client.close_position(a.ticker)
                results.append(self._order_result(a.ticker, "SELL", order, qty=qty))
            elif qty > 0:
                req = MarketOrderRequest(
                    symbol=a.ticker, qty=str(qty),
                    side=OrderSide.SELL, time_in_force=TimeInForce.DAY,
                )
                order = self._client.submit_order(req)
                results.append(self._order_result(a.ticker, "SELL", order, qty=qty))
            else:
                results.append({"ticker": a.ticker, "side": "SELL", "skipped": True,
                                "reason": "menos de 1 acción entera"})
        return results
