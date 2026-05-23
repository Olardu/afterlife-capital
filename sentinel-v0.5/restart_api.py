"""
restart_api.py
==============
Detiene la API vieja (libera puerto 8080) y lanza la nueva.

Uso:
    venv\Scripts\python.exe restart_api.py
"""

import subprocess
import sys
import time
import os

def main():
    print("=" * 50)
    print("REINICIO DE API - Sentinel v0.5")
    print("=" * 50)

    # 1. Buscar y matar procesos en puerto 8080
    print("\n[1/2] Buscando proceso en puerto 8080...")
    try:
        result = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True, text=True
        )
        pids_killed = set()
        for line in result.stdout.splitlines():
            if ":8080" in line and "LISTENING" in line:
                parts = line.split()
                pid = parts[-1]
                if pid not in pids_killed:
                    print(f"  Matando proceso PID={pid} en puerto 8080...")
                    subprocess.run(["taskkill", "/F", "/PID", pid],
                                   capture_output=True)
                    pids_killed.add(pid)

        if pids_killed:
            print(f"  {len(pids_killed)} proceso(s) detenido(s). Esperando 2s...")
            time.sleep(2)
        else:
            print("  No se encontro proceso en puerto 8080.")
    except Exception as e:
        print(f"  Error buscando procesos: {e}")
        print("  Intentando continuar de todas formas...")

    # 2. Lanzar la nueva API
    print("\n[2/2] Lanzando api.py...")
    api_path = os.path.join(os.path.dirname(__file__), "api.py")
    python_path = sys.executable

    # Reemplazar este proceso con api.py
    os.execv(python_path, [python_path, api_path])


if __name__ == "__main__":
    main()
