"""Corrida completa del Hito 13 en un solo comando (para repetir la evidencia).

  1. Instala en el entorno de la API lo que falte (prometheus_client).
  2. Inicia las bases de los Hitos 4 a 9 y la capa de monitoreo.
  3. Levanta la API del Hito 10 con la cache del Hito 12 encendida
     (CACHE_COMENTARIOS_TTL_S=2) y espera a que /salud vea las 6 bases.
  4. Verifica los targets de Prometheus y guarda la evidencia.
  5. Mide la operacion normal: 3 minutos de carga sobre las 6 bases, sin fallas.
  6. Ejecuta la prueba de falla controlada bajo carga (experimentos A y B) y
     guarda informe, series y capturas del tablero.
  7. Verifica los targets otra vez (todo debe volver a UP) y detiene la API.
     Las bases y el monitoreo quedan corriendo para la demostracion.

Tarda unos 25 minutos. No borra volumenes ni datos de las bases (RNF11).
Toda la salida queda tambien en
  monitoreo/evidencia/resultados_sin_secretos/ejecucion_<etiqueta>.log

Uso (desde la raiz del repositorio):
  PowerShell:  .\\monitoreo\\scripts\\ejecutar_todo_h13.ps1
  bash:        ./monitoreo/scripts/ejecutar_todo_h13.sh
"""
from __future__ import annotations

import argparse
import gzip
import os
import socket
import subprocess
import sys
import time

import ejecutar_prueba_controlada
import iniciar_monitoreo
import verificar_targets
from lib_monitoreo import (API, CLAVES_API, CONFIG_CONECTIVIDAD, DIR_EVIDENCIA, DIR_RESULTADOS,
                           REPO, aviso, config_conectividad, enmascarar,
                           escribir_json, esperar, etiqueta_nueva, http_json, info, paso,
                           prom_valor, python_api, token_influx)


class Duplicador:
    """Escribe la salida en consola y en un archivo de log a la vez."""

    def __init__(self, archivo):
        self.archivo, self.consola = archivo, sys.stdout

    def write(self, texto):
        self.consola.write(texto)
        self.archivo.write(enmascarar(texto))

    def flush(self):
        self.consola.flush()
        self.archivo.flush()


def asegurar_dependencias_api() -> None:
    py = python_api()
    r = subprocess.run([py, "-c", "import prometheus_client, fastapi"], capture_output=True)
    if r.returncode == 0:
        info("Entorno de la API: prometheus_client ya instalado.")
        return
    paso("Instalando dependencias de la API (requirements.txt, incluye prometheus_client)")
    subprocess.run([py, "-m", "pip", "install", "-q", "-r", str(REPO / "api" / "requirements.txt")],
                   check=False)


def entorno_api() -> dict:
    """Entorno de la API: variables ya definidas > configuracion del Hito 11 > valores de laboratorio."""
    env = os.environ.copy()
    for clave, valor in config_conectividad().items():
        if clave in CLAVES_API and valor and clave not in env:
            env[clave] = valor
    # 127.0.0.1 y no localhost: en Windows localhost prueba IPv6 primero y suma
    # demoras que no son de la base (diagnostico C2 del Hito 11).
    por_defecto = {
        "MONGODB_URI": "mongodb://admin:admin@127.0.0.1:27017",
        "NEO4J_URI": "bolt://127.0.0.1:7687",
        "CASSANDRA_HOST": "127.0.0.1",
        "REDIS_URL": "redis://127.0.0.1:6379",
        "INFLUX_URL": "http://127.0.0.1:8181",
        "IRIS_HOST": "127.0.0.1",
    }
    for k, v in por_defecto.items():
        env.setdefault(k, v)
    tok = token_influx()
    if tok:
        env["INFLUXDB3_TOKEN"] = tok
    env.update({"CACHE_COMENTARIOS_TTL_S": "2",     # cache del Hito 12 encendida
                "CORTOCIRCUITO_S": os.environ.get("H13_CORTOCIRCUITO_S", "10"),
                "METRICAS_INTERVALO_S": "15",        # chequeo de disponibilidad cada 15 s
                "PYTHONUNBUFFERED": "1"})
    return env


def puerto_ocupado(puerto: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex(("127.0.0.1", puerto)) == 0


def levantar_api(host: str, log_path) -> subprocess.Popen | None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    salida = open(log_path, "a", encoding="utf-8")
    proc = subprocess.Popen(
        [python_api(), "-m", "uvicorn", "app.main:app", "--host", host, "--port", "8000",
         "--log-level", "warning"],
        cwd=str(REPO / "api"), env=entorno_api(), stdout=salida, stderr=subprocess.STDOUT)
    if not esperar(f"{API}/openapi.json", 90, "La API"):
        detener_api(proc)
        return None
    return proc


def detener_api(proc: subprocess.Popen | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()


def esperar_salud(segundos: int) -> dict | None:
    fin, ultimo = time.monotonic() + segundos, None
    while time.monotonic() < fin:
        st, js = http_json("GET", f"{API}/salud", timeout=30)
        if st == 200 and js:
            ultimo = js
            caidas = [d["fuente"] for d in js["dependencias"] if not d["disponible"]]
            if not caidas:
                info("/salud: las 6 bases disponibles.")
                return js
            info(f"/salud: esperando a {', '.join(caidas)}...")
        time.sleep(15)
    aviso("No todas las bases quedaron disponibles; se sigue igual y queda registrado en la evidencia.")
    return ultimo


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--fase", type=int, default=150)
    ap.add_argument("--usuarios", type=int, default=20)
    ap.add_argument("--sin-cassandra", action="store_true")
    ap.add_argument("--operacion-normal", type=int, metavar="SEGUNDOS", default=180,
                    help="segundos de carga sin fallas antes de la prueba de fallas (0 = no medir)")
    ap.add_argument("--solo-operacion-normal", action="store_true",
                    help="medir solo la operacion normal, sin la prueba de fallas")
    ap.add_argument("--sin-cortocircuito", action="store_true",
                    help="API sin corte rapido (CORTOCIRCUITO_S=0), para comparar con la mejora")
    a = ap.parse_args(argv)
    os.environ["H13_CORTOCIRCUITO_S"] = "0" if a.sin_cortocircuito else "10"

    etiqueta = etiqueta_nueva()
    DIR_RESULTADOS.mkdir(parents=True, exist_ok=True)
    log = open(DIR_RESULTADOS / f"ejecucion_{etiqueta}.log", "w", encoding="utf-8")
    sys.stdout = Duplicador(log)
    dir_prueba = DIR_EVIDENCIA / "prueba_de_falla" / etiqueta
    log_api = dir_prueba / "api_crudo.log"
    proc = None
    try:
        paso(f"Hito 13 - corrida completa, etiqueta {etiqueta}")
        asegurar_dependencias_api()
        if iniciar_monitoreo.main(["--con-bases"]) != 0:
            aviso("No se pudo iniciar el monitoreo. Ver mensajes arriba.")
            return 1

        paso("Levantando la API del Hito 10 (cache del Hito 12 encendida)")
        if puerto_ocupado(8000):
            aviso("Ya hay algo escuchando en el puerto 8000. Cerrar esa API (Ctrl+C en su terminal) y volver a correr.")
            return 1
        host = "127.0.0.1"
        proc = levantar_api(host, log_api)
        if proc is None:
            aviso(f"La API no arranco. Ultimas lineas de su log ({log_api}):")
            print(enmascarar("".join(open(log_api, encoding="utf-8", errors="replace").readlines()[-20:])))
            return 1
        salud = esperar_salud(300)
        escribir_json(DIR_RESULTADOS / f"salud_{etiqueta}.json", salud)
        if salud and not next((d["disponible"] for d in salud["dependencias"] if d["fuente"] == "iris"), True):
            aviso("IRIS no disponible para la API. Si su log dice 'Access Denied', falta la contrasena "
                  f"de _SYSTEM en {CONFIG_CONECTIVIDAD.relative_to(REPO)} (IRIS_PASSWORD, Hito 11 C1).")

        paso("Comprobando que Prometheus lee /metrics de la API")
        fin = time.monotonic() + 60
        while time.monotonic() < fin and prom_valor('max(up{job="api-fixture"})') != 1:
            time.sleep(5)
        if prom_valor('max(up{job="api-fixture"})') != 1:
            aviso("Prometheus no llega a la API en 127.0.0.1; se reinicia escuchando en 0.0.0.0.")
            detener_api(proc)
            host = "0.0.0.0"
            proc = levantar_api(host, log_api)
            fin = time.monotonic() + 60
            while time.monotonic() < fin and prom_valor('max(up{job="api-fixture"})') != 1:
                time.sleep(5)
        estado_api = "UP" if prom_valor('max(up{job="api-fixture"})') == 1 else "DOWN"
        info(f"target api-fixture: {estado_api} (API en {host}:8000)")

        paso("Verificacion de targets (antes de la prueba)")
        verificar_targets.main(["--esperar", "90"])

        if a.operacion_normal:
            ejecutar_prueba_controlada.medir_operacion_normal(a.usuarios, a.operacion_normal, etiqueta)
        if a.solo_operacion_normal:
            return 0
        args = ["--etiqueta", etiqueta, "--fase", str(a.fase), "--usuarios", str(a.usuarios)]
        if a.sin_cassandra:
            args.append("--sin-cassandra")
        ejecutar_prueba_controlada.main_seguro(args)

        paso("Verificacion de targets (despues de la prueba: todo deberia volver a UP)")
        time.sleep(30)
        verificar_targets.main(["--esperar", "120"])
        return 0
    finally:
        detener_api(proc)
        if log_api.exists():
            with open(log_api, encoding="utf-8", errors="replace") as f, \
                    gzip.open(dir_prueba / "api_redactado.log.gz", "wt", encoding="utf-8") as g:
                for linea in f:
                    g.write(enmascarar(linea))
        paso("Fin. La API se detuvo; las bases y el monitoreo siguen corriendo (http://localhost:3000).")
        sys.stdout = sys.stdout.consola if isinstance(sys.stdout, Duplicador) else sys.stdout
        log.close()


if __name__ == "__main__":
    sys.exit(main())
