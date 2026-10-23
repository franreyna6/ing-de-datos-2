"""Inicio y detencion controlada de la API del Hito 10 para la evaluacion.

La API se ejecuta SIN modificar su codigo: mismo uvicorn, mismo modulo
app.main:app, misma configuracion por variables de entorno. Solo se capturan sus
logs en un archivo para poder relacionar request_id, dependencia y resultado
(RF19, RNF11). El log crudo queda en docs/evidencia/logs/crudos/ (excluido de
Git); lo que se versiona es la copia redactada.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

from lib_conectividad import RAIZ_REPO, Config, http, redactar

DIR_API = RAIZ_REPO / "api"


def python_api() -> str:
    """Python del entorno virtual de la API, o el actual si no existe."""
    for c in (DIR_API / ".venv" / "Scripts" / "python.exe", DIR_API / ".venv" / "bin" / "python"):
        if c.exists():
            return str(c)
    return sys.executable


def puerto_libre(preferido: int) -> int:
    """El puerto preferido si esta libre en 127.0.0.1; si no, uno libre que asigne el SO.
    No se asume que 8000/8001 esten disponibles: otro proceso de la notebook puede usarlos."""
    for candidato in (preferido, 0):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", candidato))
                return s.getsockname()[1]
            except OSError:
                continue
    return preferido


def iniciar(cfg: Config, puerto: int, log: Path, extra_env: dict | None = None,
            quitar_env: list[str] | None = None, espera_s: float = 40) -> subprocess.Popen | None:
    """Levanta uvicorn en 127.0.0.1:<puerto>. Devuelve None si no quedo listo a tiempo.
    El puerto debe venir de puerto_libre()."""
    log.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update(cfg.entorno_para_api())
    env.update(extra_env or {})
    for k in quitar_env or []:
        env.pop(k, None)
    env["PYTHONUNBUFFERED"] = "1"
    salida = open(log, "w", encoding="utf-8")
    proc = subprocess.Popen(
        [python_api(), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
         "--port", str(puerto), "--log-level", "warning"],
        cwd=str(DIR_API), env=env, stdout=salida, stderr=subprocess.STDOUT)
    fin = time.monotonic() + espera_s
    while time.monotonic() < fin:
        if proc.poll() is not None:
            return None
        st, _, _, _ = http("GET", f"http://127.0.0.1:{puerto}/openapi.json", 2)
        if st == 200:
            return proc
        time.sleep(0.5)
    detener(proc)
    return None


def detener(proc: subprocess.Popen | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


def lineas_de(log: Path, request_id: str) -> list[str]:
    """Lineas del log de la API correlacionadas por request_id (redactadas)."""
    if not log.exists():
        return []
    marca = f"[req={request_id}]"
    return [redactar(x.rstrip()) for x in log.read_text(encoding="utf-8", errors="replace").splitlines()
            if marca in x]


def copiar_redactado(origen: Path, destino: Path) -> None:
    if origen.exists():
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(redactar(origen.read_text(encoding="utf-8", errors="replace")),
                           encoding="utf-8", newline="\n")
