# alc_g/alcg_api.py
# API mínima del cockpit ALC-G (FastAPI). Sirve la cabina estática + expone el
# estado del runtime y el slider de leverage. Formato estándar §6.2 {data, meta}.
#
# Independiente del bot: corre en su propio puerto (8081 sugerido), su propio
# servicio systemd. NO toca api.py del bot. Fase 0 = modo informe (no ejecuta).

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from alc_g.config_alc_g import PRESETS
from alc_g.core_runner import AlcgRunner

COCKPIT_DIR = Path(__file__).resolve().parent / "cockpit"


def _ok(data, **meta) -> JSONResponse:
    return JSONResponse({"data": data, "meta": {"ok": True, **meta}})


def _err(message: str, code: str = "bad_request", status: int = 400) -> JSONResponse:
    return JSONResponse({"error": message, "codigo": code, "status": status}, status_code=status)


class LeverageBody(BaseModel):
    target: float


class PresetBody(BaseModel):
    preset: str


def create_app(runner: AlcgRunner) -> FastAPI:
    """Factory: arma la app sobre un runner inyectado (testeable con fake broker)."""
    app = FastAPI(title="ALC-G Cockpit", version="0.1")

    @app.get("/api/alcg/status")
    def status():
        try:
            snap = runner.run_once()
        except Exception as exc:  # noqa: BLE001 — el broker puede fallar (red/creds)
            return _err(f"no se pudo leer la cuenta #2: {exc}", "broker_error", 502)
        return _ok(snap, mode=runner.params.mode)

    @app.get("/api/alcg/presets")
    def presets():
        data = {name: {"leverage": str(p.leverage), "ballast_pct": str(p.ballast_pct)}
                for name, p in PRESETS.items()}
        return _ok(data)

    @app.post("/api/alcg/leverage")
    def set_leverage(body: LeverageBody):
        try:
            target = Decimal(str(body.target))
        except (InvalidOperation, ValueError):
            return _err("target inválido", "invalid_target")
        if target < Decimal("1.0") or target > Decimal("2.0"):
            return _err("target fuera de rango [1.0, 2.0]", "out_of_range")
        runner.params = runner.params.with_(leverage_target=target)
        return _ok({"leverage_target": str(target)})

    @app.post("/api/alcg/preset")
    def set_preset(body: PresetBody):
        name = body.preset.strip().lower()
        if name not in PRESETS:
            return _err(f"preset desconocido: {name}", "unknown_preset")
        # aplicar preset = fijar leverage del preset + su composición
        runner.params = runner.params.with_(preset=name, leverage_target=PRESETS[name].leverage)
        return _ok({"preset": name, "leverage_target": str(PRESETS[name].leverage)})

    @app.get("/")
    def cockpit():
        index = COCKPIT_DIR / "index.html"
        if index.exists():
            return FileResponse(index)
        return _err("cockpit no encontrado", "not_found", 404)

    if COCKPIT_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(COCKPIT_DIR)), name="static")

    return app


def build_default_app() -> FastAPI:
    """App de producción: construye el broker real desde .env.alc-g (modo informe)."""
    from alc_g.alcg_client import AlpacaAlcgBroker, load_dotenv
    from alc_g.config_alc_g import load_params_from_env

    env = load_dotenv(Path(__file__).resolve().parent.parent / ".env.alc-g")
    params = load_params_from_env(env)
    broker = AlpacaAlcgBroker.from_env(env, allow_execute=False)
    return create_app(AlcgRunner(broker, params))
