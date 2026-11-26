"""Prueba rapida de IRIS (Hito 9) tal como la usa la API: unos segundos, sin carga.

Revisa, en orden, cada capa por la que puede fallar IRIS:
  1. Contenedor: si corre y que puertos publica en la maquina.
  2. Red: si el superserver (1972) acepta conexiones TCP en 127.0.0.1.
  3. Credenciales: de donde sale IRIS_PASSWORD (sin mostrarla).
  4. Driver: el MISMO adaptador de la API (app/adapters/iris_adapter.py), con el
     MISMO entorno que usa ejecutar_todo_h13: chequeo y lectura de F2030-001.
  5. Monitoreo: si Prometheus esta leyendo /api/monitor/metrics (si esta levantado).
Al final indica la causa mas probable y que hacer. No modifica nada.

Uso (desde la raiz del repositorio):
  .\\monitoreo\\scripts\\probar_iris.ps1
"""
from __future__ import annotations

import os
import socket
import sys

from ejecutar_todo_h13 import entorno_api
from lib_monitoreo import (CONFIG_CONECTIVIDAD, CONTENEDORES, PROMETHEUS, REPO, config_conectividad,
                           contenedor_corriendo,
                           docker, enmascarar, http, info, paso, prom_valor)


def marca(ok: bool) -> str:
    return "OK   " if ok else "FALLA"


def main() -> int:
    nombre = CONTENEDORES["iris"]
    problemas = []

    paso("1. Contenedor")
    corriendo = contenedor_corriendo(nombre)
    puertos = " ".join(docker("port", nombre, timeout=30).stdout.split())
    info(f"{marca(bool(corriendo))} {nombre}: {'corriendo' if corriendo else 'no esta corriendo'}; "
         f"puertos: {puertos or 'ninguno publicado'}")
    if not corriendo:
        problemas.append("El contenedor no corre: .\\monitoreo\\scripts\\iniciar_monitoreo.ps1 --con-bases")
    elif not puertos:
        problemas.append("El contenedor no publica puertos (puerto reservado por Windows): "
                         ".\\monitoreo\\scripts\\iniciar_monitoreo.ps1 --con-bases lo recrea con puertos alternativos")

    paso("2. Red: superserver en 127.0.0.1:1972")
    try:
        with socket.create_connection(("127.0.0.1", 1972), timeout=5):
            tcp_ok = True
    except OSError as e:
        tcp_ok = False
        info(f"      {type(e).__name__}: {e}")
    info(f"{marca(tcp_ok)} conexion TCP a 1972")
    if corriendo and puertos and not tcp_ok:
        problemas.append("El 1972 no acepta conexiones: IRIS puede estar arrancando (esperar 1-2 minutos).")

    paso("3. Credenciales")
    env = entorno_api()
    if os.environ.get("IRIS_PASSWORD"):
        origen = "variable de entorno IRIS_PASSWORD"
    elif config_conectividad().get("IRIS_PASSWORD"):
        origen = f"{CONFIG_CONECTIVIDAD.relative_to(REPO)} (Hito 11)"
    else:
        origen = "valor por defecto del laboratorio (SYS)"
    info(f"Usuario {env.get('IRIS_USER', '_SYSTEM')}, namespace {env.get('IRIS_NAMESPACE', 'USER')}, "
         f"host {env.get('IRIS_HOST', 'localhost')}:{env.get('IRIS_PORT', '1972')}; contrasena tomada de: {origen}")

    paso("4. Driver de la API (mismo adaptador y mismo entorno)")
    os.environ.update({k: v for k, v in env.items() if k.startswith("IRIS_") or k == "DEP_TIMEOUT_S"})
    sys.path.insert(0, str(REPO / "api"))
    driver_ok = False
    try:
        from app.adapters.iris_adapter import iris_adapter
        from app.core.errores import ErrorDependencia
        try:
            detalle = iris_adapter.detalle_partido("F2030-001")
            driver_ok = detalle is not None
            info(f"{marca(driver_ok)} detalle de F2030-001: "
                 f"{detalle if detalle else 'no existe el partido (IRIS responde pero faltan los datos del Hito 9)'}")
            if not detalle:
                problemas.append("IRIS responde pero no tiene los datos: cd iris; .\\scripts\\ejecutar_todo.ps1 -VolumenDocker")
        except ErrorDependencia as e:
            causa = enmascarar(str(getattr(e, "causa", e)))
            info(f"FALLA conexion del driver: {causa[:300]}")
            if "Access Denied" in causa:
                problemas.append(
                    "IRIS rechaza la contrasena de _SYSTEM. La imagen Community obliga a cambiarla (Hito 11, C1): "
                    f"poner la correcta en {CONFIG_CONECTIVIDAD.relative_to(REPO)} como IRIS_PASSWORD=... "
                    "(archivo fuera de Git).")
            elif "Password change required" in causa:
                problemas.append(
                    "IRIS exige cambiar la contrasena de _SYSTEM (primer uso de la imagen Community). Ver "
                    "conectividad/docs/diagnostico_de_fallas.md, H3/C1, y guardar la nueva como IRIS_PASSWORD "
                    f"en {CONFIG_CONECTIVIDAD.relative_to(REPO)}.")
            elif "No module named" in causa:
                problemas.append("Falta el driver en api/.venv: "
                                 "api\\.venv\\Scripts\\python.exe -m pip install intersystems-irispython")
            elif tcp_ok:
                problemas.append("El driver no conecta aunque el puerto responde: ver el error de arriba.")
    except ImportError as e:
        info(f"FALLA no se pudo cargar el driver de IRIS ({e}).")
        problemas.append("Falta el driver en api/.venv: api\\.venv\\Scripts\\python.exe -m pip install intersystems-irispython")

    paso("5. Monitoreo")
    if http("GET", f"{PROMETHEUS}/-/ready", timeout=3)[0] == 200:
        up = prom_valor('max(up{job="iris"})')
        info(f"{marca(up == 1)} Prometheus lee /api/monitor/metrics de IRIS (up={up})")
    else:
        info("Prometheus no esta levantado: se omite (no afecta a la API).")

    paso("Resultado")
    if driver_ok and not problemas:
        info("IRIS OK: la API va a poder usarlo. Ya se puede correr ejecutar_todo_h13.")
        return 0
    for p in problemas:
        info(f"-> {p}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
