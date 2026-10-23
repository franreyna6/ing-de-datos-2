#!/usr/bin/env python3
"""Capa 1 - Configuracion (RF3): que variables usaria la API y si estan completas.

Pregunta que responde: la configuracion necesaria para conectarse a cada
producto existe, es sintacticamente valida y de donde sale (entorno, archivo o
valor por defecto)?
No permite concluir: nada sobre la red, el servidor ni las credenciales. Que una
password este definida no significa que sea la correcta.

Tambien inventaria las herramientas: drivers importables en este Python, Docker
y estado de cada contenedor. Un contenedor 'running' se informa como INFO, no
como disponibilidad (nota 7 del enunciado).

Nunca imprime secretos: las passwords y el token se describen ("definido, N
caracteres, oculto") y las URI se muestran con la credencial enmascarada.

Uso: python prueba_configuracion.py [--producto redis,neo4j]
"""
from __future__ import annotations

import argparse
import importlib
from urllib.parse import urlparse

from dependencias import construir
from lib_conectividad import (FALLA, INFO, OK, PRODUCTOS, SKIP, Config, Resultado,
                              describir_valor, docker_disponible, encabezado_corrida,
                              estado_contenedor, guardar_resultados, imprimir,
                              registrar_secretos)

DRIVERS = {
    "mongodb": ("pymongo", "pymongo"),
    "neo4j": ("neo4j", "neo4j"),
    "cassandra": ("cassandra.cluster", "cassandra-driver"),
    "redis": ("redis", "redis"),
    "influxdb": ("http.client", "biblioteca estandar"),
    "iris": ("iris", "intersystems-irispython"),
}


def _validar_formato(cfg: Config, producto: str) -> list[str]:
    """Errores de forma (no de red) en la configuracion del producto."""
    errores = []
    if producto == "mongodb" and cfg["MONGODB_URI"]:
        u = urlparse(cfg["MONGODB_URI"])
        if u.scheme not in ("mongodb", "mongodb+srv"):
            errores.append("MONGODB_URI no empieza con mongodb://")
        if not u.password:
            errores.append("MONGODB_URI no incluye credencial (el Hito 4 exige usuario)")
    if producto == "neo4j" and urlparse(cfg["NEO4J_URI"]).scheme not in (
            "bolt", "neo4j", "bolt+s", "neo4j+s"):
        errores.append("NEO4J_URI debe usar bolt:// o neo4j://")
    if producto == "redis" and urlparse(cfg["REDIS_URL"]).scheme not in ("redis", "rediss"):
        errores.append("REDIS_URL debe empezar con redis://")
    if producto == "influxdb" and urlparse(cfg["INFLUX_URL"]).scheme not in ("http", "https"):
        errores.append("INFLUX_URL debe ser http(s)://")
    for k in ("CASSANDRA_PORT", "IRIS_PORT"):
        if producto in k.lower() and not cfg[k].isdigit():
            errores.append(f"{k} no es un numero de puerto")
    return errores


def ejecutar(cfg: Config, productos: list[str]) -> list[Resultado]:
    registrar_secretos(cfg.secretos())
    deps = construir(cfg)
    res: list[Resultado] = []

    ok_docker, info_docker = docker_disponible()
    res.append(imprimir(Resultado(
        "herramientas", "configuracion", "Docker disponible para clientes nativos",
        INFO if ok_docker else SKIP, info_docker, cliente="docker CLI",
        responde="Se pueden ejecutar los clientes nativos dentro de los contenedores?",
        no_permite="Que los productos esten disponibles.")))

    for p in productos:
        d = deps[p]
        faltan = [k for k in d.obligatorias if not cfg[k]]
        valores = "; ".join(f"{k}={describir_valor(cfg, k)} [{cfg.origen.get(k)}]"
                            for k in d.variables)
        errores = _validar_formato(cfg, p)
        if faltan:
            resultado, detalle = FALLA, f"faltan {', '.join(faltan)} | {valores}"
        elif errores:
            resultado, detalle = FALLA, f"{'; '.join(errores)} | {valores}"
        else:
            resultado, detalle = OK, valores
        destinos = ", ".join(f"{e.host}:{e.puerto} ({e.protocolo})" for e in d.endpoints)
        res.append(imprimir(Resultado(
            p, "configuracion", "Variables de conexion completas y validas", resultado,
            detalle, objetivo=f"{destinos} | {d.contexto}", cliente="lectura de configuracion",
            esperado="todas las variables obligatorias definidas",
            responde="Existe la configuracion que necesita la API para este producto?",
            no_permite="Que el host resuelva, que el puerto escuche o que la credencial sea valida.",
            extra={"faltantes": faltan, "errores_formato": errores})))

        modulo, paquete = DRIVERS[p]
        try:
            m = importlib.import_module(modulo)
            version = getattr(m, "__version__", "") or getattr(
                importlib.import_module(modulo.split(".")[0]), "__version__", "")
            r_drv = Resultado(p, "configuracion", "Driver de la API importable en este Python", OK,
                              f"{paquete} {version}".strip(), cliente=paquete)
        except Exception as e:  # noqa: BLE001
            r_drv = Resultado(p, "configuracion", "Driver de la API importable en este Python",
                              SKIP, f"{paquete} no disponible ({e.__class__.__name__}); las "
                              "pruebas con driver quedaran en SKIP", cliente=paquete)
        r_drv.responde = "Puede este entorno usar el mismo cliente que la API?"
        r_drv.no_permite = "Que el servidor responda."
        res.append(imprimir(r_drv))

        if ok_docker:
            estado = estado_contenedor(d.contenedor)
            res.append(imprimir(Resultado(
                p, "configuracion", "Estado del contenedor (informativo)", INFO,
                f"{d.contenedor}: {estado}", objetivo=d.contenedor, cliente="docker inspect",
                responde="El proceso del producto esta iniciado en Docker?",
                no_permite="Que acepte conexiones, autentique o tenga los datos: un "
                           "contenedor activo NO equivale a una dependencia disponible.",
                extra={"estado_contenedor": estado})))
    return res


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--producto", default=",".join(PRODUCTOS))
    a = ap.parse_args()
    cfg = Config()
    productos = [p for p in a.producto.split(",") if p in PRODUCTOS]
    enc = encabezado_corrida("Capa de configuracion", cfg)
    print(enc)
    res = ejecutar(cfg, productos)
    guardar_resultados("configuracion", res, enc)


if __name__ == "__main__":
    main()
