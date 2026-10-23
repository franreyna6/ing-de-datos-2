#!/usr/bin/env python3
"""Capas 2 y 3 - Resolucion de host y conectividad TCP (RF4, RF5).

Se ejecuta DESDE EL MISMO ENTORNO QUE LA API (la notebook): usa exactamente los
hosts y puertos que la API tomaria de su configuracion.

Pregunta que responde: el nombre resuelve y existe un listener aceptando
conexiones en host:puerto?
No permite concluir: que el listener hable el protocolo esperado, que la
credencial sea valida ni que exista la database/keyspace/namespace. Una
conexion TCP exitosa NO es una prueba de salud (5.3).

Opciones:
  --demostrar-fallas   provoca, sin tocar ningun producto, los cinco tipos de
                       resultado de la tabla 5.3 (exito, refused, timeout, host
                       no resuelto, puerto incorrecto) para documentar su forma.
  --desde-contenedor   repite resolucion y TCP desde DENTRO de un contenedor,
                       para mostrar que localhost no significa lo mismo (RNF3).

Uso: python prueba_tcp.py [--producto ...] [--demostrar-fallas] [--desde-contenedor]
"""
from __future__ import annotations

import argparse

from dependencias import construir
from lib_conectividad import (FALLA, INFO, OK, PRODUCTOS, SKIP, Config, Resultado,
                              docker_disponible, docker_exec, encabezado_corrida,
                              estado_contenedor, guardar_resultados, imprimir,
                              intercambio_crudo, probar_tcp, registrar_secretos, resolver)

INTERPRETACION = {
    "exito": "Existe un listener accesible en el host y puerto probados.",
    "refused": "El host respondio, pero no hay listener en ese puerto (servicio detenido, "
               "puerto no publicado o puerto equivocado).",
    "timeout": "No hubo respuesta en el tiempo limite: red, firewall, ruta o saturacion.",
    "no_resuelto": "El nombre no se pudo convertir en direccion desde este entorno.",
    "error": "Error de red no clasificado; ver detalle.",
}


def ejecutar(cfg: Config, productos: list[str]) -> list[Resultado]:
    registrar_secretos(cfg.secretos())
    deps = construir(cfg)
    res: list[Resultado] = []
    for p in productos:
        for ep in deps[p].endpoints:
            if not ep.host:
                res.append(imprimir(Resultado(
                    p, "resolucion", f"Resolver host ({ep.rol})", SKIP,
                    "sin host configurado (ver capa de configuracion)")))
                continue
            ips, det = resolver(ep.host)
            res.append(imprimir(Resultado(
                p, "resolucion", f"Resolver host ({ep.rol})", OK if ips else FALLA,
                f"{ep.host} -> {', '.join(ips)}" if ips else det, objetivo=ep.host,
                cliente="socket.getaddrinfo",
                responde="El nombre configurado se convierte en una direccion desde la notebook?",
                no_permite="Que haya un proceso escuchando en el puerto.")))
            if not ips:
                res.append(imprimir(Resultado(
                    p, "tcp", f"Conexion TCP ({ep.rol})", SKIP,
                    "no se intenta: el host no resolvio", objetivo=f"{ep.host}:{ep.puerto}")))
                continue
            clase, det, ms = probar_tcp(ep.host, ep.puerto, cfg.timeout)
            res.append(imprimir(Resultado(
                p, "tcp", f"Conexion TCP ({ep.rol})", OK if clase == "exito" else FALLA,
                f"{clase}: {det}", objetivo=f"{ep.host}:{ep.puerto} [{ep.protocolo}]",
                cliente="socket.create_connection", duracion_ms=ms,
                esperado="exito",
                responde="Hay un listener aceptando conexiones en host:puerto?",
                no_permite="Que sea el producto correcto, que el protocolo responda, que la "
                           "credencial o el contexto sean validos.",
                extra={"clase_tcp": clase, "interpretacion": INTERPRETACION.get(clase, ""),
                       "usado_por_api": ep.usado_por_api})))
            # Cada direccion por separado: 'localhost' resuelve a ::1 y a 127.0.0.1, y un
            # puerto publicado solo en 127.0.0.1 hace que el intento IPv6 falle antes de
            # caer a IPv4. Esa demora la paga cada conexion nueva de la API.
            if len(ips) > 1:
                partes = []
                for ip in ips:
                    c_ip, _, ms_ip = probar_tcp(ip, ep.puerto, cfg.timeout)
                    partes.append(f"{ip} -> {c_ip} ({ms_ip:.0f} ms)")
                demora = ms > 500
                res.append(imprimir(Resultado(
                    p, "tcp", f"TCP por familia de direcciones ({ep.rol})",
                    INFO, "; ".join(partes) + (
                        f" | la conexion por nombre tardo {ms:.0f} ms: el primer intento va a una "
                        "direccion sin listener" if demora else ""),
                    objetivo=f"{ep.host}:{ep.puerto}", cliente="socket.create_connection",
                    responde="El nombre configurado lleva directo al listener o pasa por un intento fallido?",
                    no_permite="-", extra={"demora_por_resolucion": demora,
                                           "hallazgo": "H4" if demora else ""})))
    return res


def demostrar_fallas(cfg: Config) -> list[Resultado]:
    """Tabla 5.3: un caso de cada tipo, sin detener ni modificar productos."""
    res: list[Resultado] = []
    t = cfg.timeout
    casos = [
        ("exito", "localhost", 6379, "Puerto publicado por el contenedor de Redis"),
        ("refused", "localhost", 27018, "Puerto donde no escucha ningun proceso"),
        ("timeout", "10.255.255.1", 27017, "Direccion no enrutable: nadie contesta"),
        ("no_resuelto", "mongodb", 27017,
         "Nombre de servicio de Docker usado desde la notebook (solo existe dentro de la red de Compose)"),
    ]
    for esperado, host, puerto, motivo in casos:
        clase, det, ms = probar_tcp(host, puerto, t)
        res.append(imprimir(Resultado(
            "demostracion", "tcp", f"Tipo de falla '{esperado}': {motivo}",
            OK if clase == esperado else FALLA, f"{clase}: {det}",
            objetivo=f"{host}:{puerto}", cliente="socket.create_connection", duracion_ms=ms,
            esperado=esperado, extra={"clase_tcp": clase,
                                      "interpretacion": INTERPRETACION.get(clase, "")})))
    # Puerto incorrecto: el TCP conecta, pero el listener habla otro protocolo.
    # Se envia el handshake Bolt (magic 0x6060B017 + versiones) al puerto HTTP de Neo4j.
    bolt = bytes.fromhex("6060B017") + bytes.fromhex("00000505" "00000404" "00000004" "00000003")
    clase, det, ms = probar_tcp("localhost", 7474, t)
    if clase == "exito":
        try:
            resp = intercambio_crudo("localhost", 7474, bolt, t)
            es_http = resp.startswith(b"HTTP/")
            detalle = (f"TCP exito, pero la respuesta al handshake Bolt fue "
                       f"{resp[:24]!r}: {'el listener habla HTTP, no Bolt' if es_http else 'no es Bolt'}")
            resultado = OK
        except Exception as e:  # noqa: BLE001
            detalle, resultado = f"TCP exito, handshake sin respuesta valida ({e.__class__.__name__})", OK
    else:
        detalle, resultado = f"no se pudo demostrar: 7474 respondio {clase}", SKIP
    res.append(imprimir(Resultado(
        "demostracion", "protocolo",
        "Tipo de falla 'puerto incorrecto': handshake Bolt contra el puerto HTTP 7474 de Neo4j",
        resultado, detalle, objetivo="localhost:7474", cliente="socket (bytes del handshake Bolt)",
        esperado="TCP exitoso pero protocolo no coincide",
        responde="Por que un puerto abierto no prueba que el protocolo sea el correcto?",
        no_permite="-")))
    return res


def desde_contenedor(cfg: Config) -> list[Resultado]:
    """RNF3: la misma prueba desde dentro de un contenedor cambia de significado."""
    res: list[Resultado] = []
    ok, info = docker_disponible()
    cont = cfg["REDIS_CONTAINER"]
    if not ok or estado_contenedor(cont) != "running":
        res.append(imprimir(Resultado("topologia", "tcp", "Pruebas desde un contenedor", SKIP,
                                      f"se necesita Docker y {cont} en ejecucion ({info})")))
        return res
    origen = f"contenedor {cont} (red Docker del Hito 7)"
    # bash /dev/tcp: disponible en la imagen oficial de Redis (Debian), sin instalar nada.
    pruebas = [
        ("localhost", 6379, "localhost dentro del contenedor = el propio contenedor de Redis"),
        ("localhost", 27017, "Mongo NO corre en este contenedor: localhost:27017 no es la notebook"),
        ("host.docker.internal", 27017, "Puerto publicado de Mongo visto desde un contenedor (Docker Desktop)"),
        ("fixture2030-mongodb", 27017, "Nombre de otro contenedor: esta en otra red de Compose"),
    ]
    for host, puerto, motivo in pruebas:
        script = (f"getent hosts {host} >/dev/null 2>&1 || {{ echo NO_RESUELVE; exit 0; }}; "
                  f"timeout {int(cfg.timeout) or 1} bash -c '</dev/tcp/{host}/{puerto}' 2>/dev/null "
                  f"&& echo EXITO || echo FALLA_TCP")
        rc, out, err = docker_exec(cont, ["bash", "-c", script], timeout=cfg.timeout + 10)
        salida = (out or err).strip().splitlines()[-1] if (out or err).strip() else "sin salida"
        clase = {"EXITO": "exito", "NO_RESUELVE": "no_resuelto"}.get(salida, "refused_o_timeout")
        res.append(imprimir(Resultado(
            "topologia", "tcp", motivo, INFO, f"{clase} ({salida})",
            objetivo=f"{host}:{puerto}", origen=origen, cliente="bash /dev/tcp + getent",
            responde="Que ve un proceso que corre dentro de Docker al usar el mismo host?",
            no_permite="Nada sobre la API actual, que corre en la notebook.",
            extra={"clase_tcp": clase})))
    return res


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--producto", default=",".join(PRODUCTOS))
    ap.add_argument("--demostrar-fallas", action="store_true")
    ap.add_argument("--desde-contenedor", action="store_true")
    a = ap.parse_args()
    cfg = Config()
    enc = encabezado_corrida("Resolucion y TCP", cfg)
    print(enc)
    res = ejecutar(cfg, [p for p in a.producto.split(",") if p in PRODUCTOS])
    if a.demostrar_fallas:
        res += demostrar_fallas(cfg)
    if a.desde_contenedor:
        res += desde_contenedor(cfg)
    guardar_resultados("tcp", res, enc)


if __name__ == "__main__":
    main()
