"""Levanta la API del Hito 10 con la configuracion de la defensa (queda en primer plano).

Usa el mismo entorno que la corrida completa (ejecutar_todo_h13):
  - credenciales locales de conectividad/config/configuracion.env (Hito 11, fuera
    de Git), por ejemplo la contrasena de _SYSTEM de IRIS;
  - token de InfluxDB del Hito 8;
  - cache del Hito 12 encendida (CACHE_COMENTARIOS_TTL_S=2);
  - corte rapido del Hito 13 (CORTOCIRCUITO_S=10) y chequeo de bases cada 15 s.
Expone /metrics para Prometheus. Ctrl+C la detiene.

Uso (desde la raiz del repositorio):
  .\\monitoreo\\scripts\\iniciar_api_monitoreada.ps1
"""
from __future__ import annotations

import os
import subprocess
import sys

from ejecutar_todo_h13 import entorno_api
from lib_monitoreo import REPO, info, paso, python_api


def main() -> int:
    os.environ.setdefault("H13_CORTOCIRCUITO_S", "10")
    paso("API del Fixture 2030 en http://127.0.0.1:8000 (Swagger en /docs, metricas en /metrics)")
    info("Ctrl+C para detenerla.")
    try:
        return subprocess.call([python_api(), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
                                "--port", "8000"], cwd=str(REPO / "api"), env=entorno_api())
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
