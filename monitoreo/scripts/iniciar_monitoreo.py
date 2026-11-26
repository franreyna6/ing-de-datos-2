"""Inicia la capa de monitoreo del Hito 13 (y, opcionalmente, las bases).

Pasos:
  1. Crea monitoreo/.env desde .env.example si no existe (contrasena de Grafana
     al azar) y copia el token de InfluxDB del Hito 8 a monitoreo/secretos/.
     Los dos quedan fuera de Git (RNF6).
  2. Con --con-bases: inicia los contenedores de los Hitos 4 a 9. Si un
     contenedor ya existe, solo hace "docker start" (no lo recrea ni toca sus
     datos); si no existe, usa el docker compose de su carpeta.
  3. docker compose up -d de monitoreo/ y espera a Prometheus y Grafana.

No borra nada (RNF11). Para detener: scripts/limpiar_entorno.

Uso:
  python scripts/iniciar_monitoreo.py
  python scripts/iniciar_monitoreo.py --con-bases
"""
from __future__ import annotations

import argparse
import os
import sys

from lib_monitoreo import (ALERTMANAGER, CONTENEDORES, GRAFANA, MODULOS_BASES, PROMETHEUS, RAIZ,
                           REPO, asegurar_env, asegurar_token_influx, aviso, contenedor_corriendo,
                           docker, esperar, http, info, paso)


PUERTOS_ALTERNATIVOS = {"iris": RAIZ / "compose" / "iris-puertos-windows.yml"}


def _compose_up(modulo: str, recrear: bool = False, alternativo: bool = False):
    archivos = ["-f", "docker-compose.yml"]
    if modulo == "iris" and os.name == "nt":
        # Igual que el README del Hito 9 en Windows: volumen de Docker para /durable.
        archivos += ["-f", "docker-compose.windows.yml"]
    if alternativo:
        archivos += ["-f", str(PUERTOS_ALTERNATIVOS[modulo])]
    extra = ["--force-recreate", modulo] if recrear else []
    return docker("compose", *archivos, "up", "-d", *extra, timeout=600, cwd=REPO / modulo)


def _recrear(modulo: str, alternativo: bool = False) -> tuple[bool, str]:
    """Recrea el contenedor del modulo con su compose. Nunca borra volumenes (RNF11)."""
    nombre = CONTENEDORES[modulo]
    r = _compose_up(modulo, recrear=True, alternativo=alternativo)
    if r.returncode != 0 and "already in use" in r.stderr:
        # Lo creo otro proyecto de compose (otra carpeta): se quita SOLO el
        # contenedor (no su volumen) y se vuelve a crear desde esta carpeta.
        docker("stop", nombre, timeout=120)
        docker("rm", nombre, timeout=60)
        r = _compose_up(modulo, alternativo=alternativo)
    if (r.returncode != 0 and "ports are not available" in r.stderr
            and modulo in PUERTOS_ALTERNATIVOS and not alternativo):
        # Windows reservo el puerto (rango dinamico de Hyper-V/WSL): se usa el
        # ajuste de puertos del modulo (ver compose/iris-puertos-windows.yml).
        ok, detalle = _recrear(modulo, alternativo=True)
        return ok, "puerto reservado por Windows; " + detalle
    if r.returncode != 0:
        return False, f"no se pudo recrear: {r.stderr.strip()[-200:]}"
    return True, ("recreado con puertos alternativos (compose/iris-puertos-windows.yml)"
                  if alternativo else "recreado con su docker compose")


def iniciar_bases() -> dict:
    paso("Bases de datos del TPO (Hitos 4 a 9)")
    estado = {}
    for modulo in MODULOS_BASES:
        nombre = CONTENEDORES[modulo]
        corriendo = contenedor_corriendo(nombre)
        if corriendo is True:
            estado[modulo] = "ya estaba corriendo"
        elif corriendo is False:
            r = docker("start", nombre, timeout=180)
            if r.returncode == 0:
                estado[modulo] = "iniciado (docker start)"
            else:
                ok, detalle = _recrear(modulo)
                estado[modulo] = f"docker start fallo ({r.stderr.strip()[:80]}); {detalle}"
        else:
            r = _compose_up(modulo)
            if r.returncode == 0:
                estado[modulo] = "creado (docker compose up -d)"
            else:
                ok, detalle = _recrear(modulo)
                estado[modulo] = detalle
        # Un contenedor que corre pero no publica puertos es inalcanzable desde la
        # API. Paso en las primeras corridas con IRIS (puerto reservado por
        # Windows). Se recrea; los datos viven en su volumen y se conservan.
        if contenedor_corriendo(nombre) and not docker("port", nombre, timeout=30).stdout.strip():
            ok, detalle = _recrear(modulo)
            estado[modulo] += f" -> sin puertos publicados: {detalle}"
        puertos = " ".join(docker("port", nombre, timeout=30).stdout.split())
        info(f"{modulo:<10} {nombre:<24} {estado[modulo]}  [{puertos or 'sin puertos'}]")
        estado[modulo] += f" [{puertos or 'sin puertos'}]"
    return estado


def conectar_prometheus_a_bases() -> None:
    """Conecta a Prometheus a la red de Docker de las bases que se leen por nombre.

    IRIS se lee como fixture2030-iris:52773 (ver prometheus.yml), sin depender
    del puerto publicado en la maquina. Es idempotente: si ya esta conectado,
    docker responde que ya existe y no pasa nada.
    """
    for modulo in ("iris",):
        nombre = CONTENEDORES[modulo]
        if not contenedor_corriendo(nombre):
            continue
        redes = docker("inspect", "-f", "{{range $k, $v := .NetworkSettings.Networks}}{{$k}} {{end}}",
                       nombre, timeout=30).stdout.split()
        for red in redes:
            r = docker("network", "connect", red, "fixture2030-prometheus", timeout=30)
            if r.returncode == 0:
                info(f"Prometheus conectado a la red {red} ({modulo})")


def recargar_configuracion() -> None:
    """Hace que Prometheus, Alertmanager y blackbox relean sus archivos.

    'docker compose up -d' no reinicia un contenedor si solo cambio un archivo
    montado: sin esto, una configuracion corregida no se aplica (paso en la
    segunda corrida con las sondas TCP).
    """
    for nombre, url in (("Prometheus", f"{PROMETHEUS}/-/reload"),
                        ("Alertmanager", f"{ALERTMANAGER}/-/reload"),
                        ("blackbox", "http://127.0.0.1:9115/-/reload")):
        st, _, _ = http("POST", url, timeout=15)
        info(f"{nombre}: configuracion recargada" if st == 200 else f"{nombre}: recarga HTTP {st}")


def iniciar_monitoreo() -> bool:
    paso("Configuracion local (fuera de Git)")
    env = asegurar_env()
    if not env.get("GRAFANA_ADMIN_PASSWORD"):
        aviso("monitoreo/.env no tiene GRAFANA_ADMIN_PASSWORD.")
    hay_token = asegurar_token_influx()
    info(f".env listo; token de InfluxDB {'copiado' if hay_token else 'NO disponible'} en monitoreo/secretos/")

    paso("docker compose up -d (Prometheus, Alertmanager, exporters, Grafana)")
    r = docker("compose", "up", "-d", timeout=900, cwd=RAIZ)
    if r.returncode != 0:
        aviso(r.stderr.strip()[-800:])
        return False
    ok = esperar(f"{PROMETHEUS}/-/ready", 90, "Prometheus")
    ok &= esperar(f"{ALERTMANAGER}/-/ready", 60, "Alertmanager")
    ok &= esperar(f"{GRAFANA}/api/health", 120, "Grafana")
    conectar_prometheus_a_bases()
    recargar_configuracion()
    if ok:
        info("Prometheus:   http://localhost:9090/targets")
        info("Grafana:      http://localhost:3000  (tablero 'Fixture 2030 - War Room'; usuario y clave en monitoreo/.env)")
        info("Alertmanager: http://localhost:9093")
    return ok


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--con-bases", action="store_true", help="iniciar tambien los contenedores de las bases")
    a = ap.parse_args(argv)
    if docker("version", "--format", "{{.Server.Version}}", timeout=30).returncode != 0:
        aviso("Docker no responde. Abrir Docker Desktop y volver a intentar.")
        return 2
    if a.con_bases:
        iniciar_bases()
    return 0 if iniciar_monitoreo() else 1


if __name__ == "__main__":
    sys.exit(main())
