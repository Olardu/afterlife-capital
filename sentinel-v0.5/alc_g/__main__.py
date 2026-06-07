# alc_g/__main__.py
# Arranque del runtime ALC-G Fase 0 (cockpit + API). Sirve la cabina y lee la
# cuenta #2 on-demand en modo informe. Puerto 8081 por default (no choca con el
# bot en 8080). Producción: systemd unit alc-g.service (ver deploy/).
#
#   python -m alc_g                 # arranca el cockpit en :8081
#   uvicorn alc_g.alcg_api:build_default_app --factory --port 8081

from __future__ import annotations

import os

import uvicorn


def main() -> None:
    port = int(os.environ.get("ALCG_PORT", "8081"))
    host = os.environ.get("ALCG_HOST", "127.0.0.1")
    uvicorn.run("alc_g.alcg_api:build_default_app", factory=True, host=host, port=port)


if __name__ == "__main__":
    main()
