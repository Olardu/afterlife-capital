"""Tests de la lista negra del Universe Selector + filtros técnicos de elegibilidad.

Cubre:
  - `_filter_candidate_eligibility(ticker, client)`: valida que un asset esté
    ACTIVE, tradable y fractionable vía Alpaca Assets API antes de proponerlo o
    confirmarlo como rotación (defensa técnica).
  - `SYSTEM_PROMPT`: contiene la lista negra explícita de productos leveraged /
    inverse / volatilidad / decay (defensa preventiva — evita el bucle de
    rotación zombie tipo Mantis 08-may con SQQQ / UVXY / USO).

Mock del client Alpaca (sin red ni DB). Correr:
  venv\\Scripts\\python.exe -m pytest tests/test_universe_selector_filters.py -v
"""
import asyncio
import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

from alpaca.trading.enums import AssetStatus

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from universe_selector import SYSTEM_PROMPT, _filter_candidate_eligibility


def _run(coro):
    return asyncio.run(coro)


def _asset(*, status=AssetStatus.ACTIVE, tradable=True, fractionable=True,
           marginable=True, shortable=True):
    """Asset Alpaca falso con los flags que mira el filtro."""
    return SimpleNamespace(
        status=status, tradable=tradable, fractionable=fractionable,
        marginable=marginable, shortable=shortable,
    )


def _client(asset=None, raises=None):
    """Client Alpaca mock. get_asset es SÍNCRONO (la función lo corre en to_thread)."""
    client = MagicMock()
    if raises is not None:
        client.get_asset = MagicMock(side_effect=raises)
    else:
        client.get_asset = MagicMock(return_value=asset)
    return client


# --- Caso 1: asset elegible -------------------------------------------------
def test_asset_activo_tradable_fractionable_es_elegible():
    result = _run(_filter_candidate_eligibility("NVDA", _client(_asset())))
    assert result["eligible"] is True
    assert result["reason"] is None
    assert result["asset"] is not None


# --- Caso 2: no fractionable (Sentinel opera fraccional) --------------------
def test_asset_no_fractionable_es_rechazado():
    result = _run(_filter_candidate_eligibility("XYZ", _client(_asset(fractionable=False))))
    assert result["eligible"] is False
    assert result["reason"] == "not_fractionable"


# --- Caso 3: lookup falla (ticker inexistente / error de red) ---------------
def test_lookup_fallido_es_rechazado_sin_crashear():
    result = _run(_filter_candidate_eligibility("ZZZZ", _client(raises=Exception("404 not found"))))
    assert result["eligible"] is False
    assert result["reason"].startswith("asset_lookup_failed")


# --- Caso 4: asset inactivo -------------------------------------------------
def test_asset_inactivo_es_rechazado():
    result = _run(_filter_candidate_eligibility("DEAD", _client(_asset(status=AssetStatus.INACTIVE))))
    assert result["eligible"] is False
    assert result["reason"].startswith("not_active")


# --- Caso 5: lista negra presente en el SYSTEM_PROMPT -----------------------
def test_system_prompt_contiene_lista_negra():
    # Símbolos representativos de cada familia prohibida (decay / contango).
    for simbolo in ("SQQQ", "TQQQ", "UVXY", "VXX", "USO", "BITI"):
        assert simbolo in SYSTEM_PROMPT, f"{simbolo} falta en la lista negra del prompt"
    assert "PROHIBIDO PROPONER" in SYSTEM_PROMPT
