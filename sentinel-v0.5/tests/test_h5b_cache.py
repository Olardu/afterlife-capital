"""Tests del fix #H-5b: sincronización del cache `open_positions` tras un fill.

Bug: tras un SELL FILLED (que cierra el long), el dispatcher sobreescribía
`open_positions[ticker]` con side='SELL' en vez de removerlo. Eso dejaba entradas
fantasma que el sync con Alpaca detectaba como desincronización y que habilitaban
shorts accidentales (incidentes SPY 11-may, QQQ 15-may; 45 warnings 18-22 may
confirmaron que es crónico, no aislado).

Fix: en SELL FILLED se hace `open_positions.pop(ticker, None)`.

Unidad bajo test: `Dispatcher._apply_fill_to_cache`, que solo toca `self.open_positions`.
Se instancia el Dispatcher con `__new__` para no requerir historian/the_ear/etc.
Correr:  venv\\Scripts\\python.exe tests\\test_h5b_cache.py
"""
import os
import sys
import unittest

# Permite `from dispatcher import Dispatcher` corriendo desde cualquier cwd.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dispatcher import Dispatcher


def _dispatcher_solo_cache() -> Dispatcher:
    """Dispatcher con solo `open_positions` (bypass __init__: el fix no usa más)."""
    dispatcher = Dispatcher.__new__(Dispatcher)
    dispatcher.open_positions = {}
    return dispatcher


def _posicion(ticker: str, side: str) -> dict:
    return {"ticker": ticker, "qty": 1, "side": side, "sentinel_id": "s-test"}


class TestApplyFillToCache(unittest.TestCase):
    def test_sell_filled_remueve_la_posicion_del_cache(self):
        """SELL FILLED debe sacar el ticker del cache (no dejar fantasma) — núcleo de #H-5b."""
        dispatcher = _dispatcher_solo_cache()
        dispatcher.open_positions["NVDA"] = _posicion("NVDA", "BUY")
        self.assertIn("NVDA", dispatcher.open_positions, "precondición: posición abierta antes")

        dispatcher._apply_fill_to_cache("NVDA", "FILLED", _posicion("NVDA", "SELL"))

        self.assertNotIn("NVDA", dispatcher.open_positions)

    def test_buy_filled_agrega_la_posicion_al_cache(self):
        """BUY FILLED debe registrar la posición en el cache."""
        dispatcher = _dispatcher_solo_cache()

        dispatcher._apply_fill_to_cache("AAPL", "FILLED", _posicion("AAPL", "BUY"))

        self.assertIn("AAPL", dispatcher.open_positions)
        self.assertEqual(dispatcher.open_positions["AAPL"]["side"], "BUY")

    def test_status_no_filled_deja_el_cache_intacto(self):
        """Un status distinto de FILLED (CANCELLED/PENDING) no debe alterar el cache."""
        dispatcher = _dispatcher_solo_cache()
        dispatcher.open_positions["SPY"] = _posicion("SPY", "BUY")

        dispatcher._apply_fill_to_cache("SPY", "CANCELLED", _posicion("SPY", "SELL"))

        self.assertIn("SPY", dispatcher.open_positions)

    def test_sell_filled_sin_posicion_previa_no_lanza(self):
        """SELL FILLED de un ticker ausente no debe lanzar (pop idempotente)."""
        dispatcher = _dispatcher_solo_cache()

        dispatcher._apply_fill_to_cache("TSLA", "FILLED", _posicion("TSLA", "SELL"))

        self.assertNotIn("TSLA", dispatcher.open_positions)


if __name__ == "__main__":
    unittest.main(verbosity=2)
