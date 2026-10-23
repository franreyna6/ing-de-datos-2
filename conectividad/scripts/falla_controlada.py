#!/usr/bin/env python3
"""Fallas controladas y recuperacion (RF17, RF20, RF21, seccion 5.7).

Escenarios (todos reversibles; ninguno borra datos, volumenes ni bases):

  redis_detenido   'docker stop' del contenedor de Redis (Hito 7) con la API
                   corriendo; se observa la API, se hace 'docker start' y se
                   repite la prueba. Se comparan DBSIZE y la sesion de prueba
                   antes y despues para mostrar que los datos se conservaron.
  timeout_bajo     una segunda instancia de la API con DEP_TIMEOUT_S=0.001
                   (timeout configurado demasiado bajo). Al terminar se detiene;
                   la configuracion normal no se toca.
  influx_sin_token una instancia de la API sin INFLUXDB3_TOKEN (credencial
                   ausente). Se compara con la instancia con token.

Para cada escenario registra: condicion inicial, cambio aplicado, prueba
ejecutada, respuesta de la API, mensaje de log, tiempo de espera, recuperacion,
resultado despues de recuperar y datos conservados (5.7).

Uso: python falla_controlada.py [--escenario redis_detenido,timeout_bajo,influx_sin_token]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import time
import uuid

import api_local
from lib_conectividad import (DIR_EVIDENCIA, FALLA, INFO, OK, Config, Resultado,
                              describir_excepcion, docker_disponible, encabezado_corrida,
                              guardar_resultados, http, imprimir, intercambio_crudo, medir, probar_tcp,
                              registrar_secretos)

ESCENARIOS = ["redis_detenido", "timeout_bajo", "influx_sin_token"]
DIR_FALLA = DIR_EVIDENCIA / "falla_controlada"


def _get(base, ruta, rid, timeout=20.0):
    t0 = time.perf_counter()
    st, hdr, cuerpo, err = http("GET", base + ruta, timeout, {"X-Request-ID": rid})
    ms = (time.perf_counter() - t0) * 1000
    try:
        datos = json.loads(cuerpo) if cuerpo else {}
    except ValueError:
        datos = {}
    code = (datos.get("error") or {}).get("code", "") if isinstance(datos, dict) else ""
    return st, code, ms, datos, err


def _paso(esc, etapa, prueba, resultado, detalle, **kw) -> Resultado:
    return imprimir(Resultado(esc, etapa, prueba, resultado, detalle, **kw))


def _docker(*args, timeout=60) -> tuple[int, str]:
    r = subprocess.run(["docker", *args], capture_output=True, text=True, timeout=timeout)
    return r.returncode, (r.stdout + r.stderr).strip()


# ---------------------------------------------------------------------------
def redis_detenido(cfg: Config) -> list[Resultado]:
    import redis
    E, res = "redis_detenido", []
    cont, sesion = cfg["REDIS_CONTAINER"], f"sesion:{cfg['PRUEBA_SESION']}"
    log = DIR_EVIDENCIA / "logs" / "crudos" / "api_falla_redis.log"
    puerto = api_local.puerto_libre(8000)
    proc = api_local.iniciar(cfg, puerto, log)
    if proc is None:
        return [_paso(E, "inicial", "Levantar la API", FALLA, "la API no inicio; ver log crudo")]
    base = f"http://127.0.0.1:{puerto}"
    try:
        cli = redis.from_url(cfg["REDIS_URL"], socket_connect_timeout=cfg.timeout,
                             socket_timeout=cfg.timeout, decode_responses=True)
        _, montajes = _docker("inspect", "-f", "{{range .Mounts}}{{.Source}}->{{.Destination}} {{end}}", cont)
        dbsize0, tipo0, ttl0 = cli.dbsize(), cli.type(sesion), cli.ttl(sesion)
        res.append(_paso(E, "inicial", "Estado del contenedor y de los datos", INFO,
                         f"{cont} running | DBSIZE={dbsize0} | {sesion}: tipo={tipo0} TTL={ttl0} s | "
                         f"montajes: {montajes}", objetivo=cont, cliente="docker inspect + redis-py"))
        st, code, ms, _, _ = _get(base, "/sesiones/no-existe-h11", "h11-falla-redis-ini")
        res.append(_paso(E, "inicial", "API GET /sesiones/no-existe-h11 con Redis arriba",
                         OK if st == 404 else FALLA, f"HTTP {st} {code} en {ms:.0f} ms (la base respondio)",
                         duracion_ms=ms, extra={"request_id": "h11-falla-redis-ini",
                                                "log": api_local.lineas_de(log, "h11-falla-redis-ini")}))

        # Cambio aplicado: detener (NO 'down -v', NO borrar volumenes).
        t0 = time.perf_counter()
        rc, out = _docker("stop", cont)
        res.append(_paso(E, "cambio", f"docker stop {cont}", OK if rc == 0 else FALLA,
                         f"detenido en {(time.perf_counter() - t0):.1f} s (el volumen y la carpeta "
                         "de datos no se tocan)", objetivo=cont, cliente="docker CLI"))

        host = cli.connection_pool.connection_kwargs.get("host", "localhost")
        puerto_r = cli.connection_pool.connection_kwargs.get("port", 6379)
        for destino in (host, "127.0.0.1", "::1"):
            clase, det, ms = probar_tcp(destino, puerto_r, cfg.timeout)
            if clase == "exito":
                resp, e_resp, _ = medir(intercambio_crudo, destino, puerto_r,
                                        b"*1\r\n$4\r\nPING\r\n", cfg.timeout)
                det += (f" | PING RESP crudo -> {resp[:20]!r}" if resp else
                        f" | PING RESP crudo -> sin respuesta ({describir_excepcion(e_resp) if e_resp else 'conexion cerrada'})")
                det += (" => el puerto publicado sigue aceptando TCP (proxy de puertos de Docker "
                        "Desktop) aunque Redis este detenido: TCP exitoso NO prueba disponibilidad")
            res.append(_paso(E, "prueba", f"TCP + PING crudo a {destino}:{puerto_r} desde la notebook", INFO,
                             f"{clase}: {det}", duracion_ms=ms, cliente="socket (RESP)"))
        v, e, ms = medir(cli.ping)
        res.append(_paso(E, "prueba", "PING con redis-py", INFO,
                         describir_excepcion(e) if e else "PONG (inesperado)", duracion_ms=ms,
                         cliente="redis-py"))
        for rid, ruta, dep in [("h11-falla-redis-404", "/sesiones/no-existe-h11", "redis"),
                               ("h11-falla-redis-s01", f"/sesiones/{cfg['PRUEBA_SESION']}", "redis"),
                               ("h11-falla-redis-neo", f"/partidos/{cfg['PRUEBA_PARTIDO']}/eventos", "neo4j")]:
            st, code, ms, _, err = _get(base, ruta, rid)
            esperado = 503 if dep == "redis" else 200
            res.append(_paso(E, "prueba", f"API GET {ruta} con Redis detenido ({dep})",
                             OK if st == esperado else FALLA,
                             f"HTTP {st} {code} en {ms:.0f} ms" if st else f"sin respuesta: {err}",
                             duracion_ms=ms, esperado=str(esperado),
                             responde="La API falla en forma controlada y solo en la ruta afectada?",
                             extra={"request_id": rid, "log": api_local.lineas_de(log, rid)}))
        st, code, ms, datos, _ = _get(base, "/salud", "h11-falla-redis-salud", 60)
        deps = {d["fuente"]: d["disponible"] for d in datos.get("dependencias", [])}
        res.append(_paso(E, "prueba", "API GET /salud con Redis detenido", INFO,
                         f"HTTP {st} en {ms:.0f} ms | redis={deps.get('redis')} | el endpoint responde "
                         "200 aunque una fuente este caida (no hay readiness)", duracion_ms=ms,
                         extra={"dependencias": deps}))

        # Recuperacion.
        t0 = time.perf_counter()
        rc, _ = _docker("start", cont)
        listo, intentos = False, 0
        while time.perf_counter() - t0 < 60:
            intentos += 1
            try:
                if cli.ping():
                    listo = True
                    break
            except Exception:  # noqa: BLE001
                time.sleep(0.5)
        espera = time.perf_counter() - t0
        res.append(_paso(E, "recuperacion", f"docker start {cont} + espera de PING (max 60 s)",
                         OK if listo else FALLA,
                         f"PONG tras {espera:.1f} s ({intentos} intentos)" if listo else "no respondio en 60 s",
                         duracion_ms=espera * 1000, cliente="docker CLI + redis-py"))
        st, code, ms, _, _ = _get(base, "/sesiones/no-existe-h11", "h11-falla-redis-fin")
        res.append(_paso(E, "despues", "API GET /sesiones/no-existe-h11 tras recuperar",
                         OK if st == 404 else FALLA,
                         f"HTTP {st} {code} en {ms:.0f} ms: la API se reconecto sola (sin reiniciarla)",
                         duracion_ms=ms, extra={"request_id": "h11-falla-redis-fin",
                                                "log": api_local.lineas_de(log, "h11-falla-redis-fin")}))
        dbsize1, tipo1, ttl1 = cli.dbsize(), cli.type(sesion), cli.ttl(sesion)
        res.append(_paso(E, "despues", "Datos conservados", OK if tipo1 == tipo0 else FALLA,
                         f"DBSIZE antes={dbsize0} despues={dbsize1} | {sesion}: tipo={tipo1} TTL={ttl1} s "
                         "(AOF + RDB del Hito 7 en ~/docker/data/redis). Una diferencia en DBSIZE solo "
                         "puede venir de claves con TTL que vencieron durante la prueba",
                         objetivo=cont, cliente="redis-py"))
        cli.close()
    finally:
        api_local.detener(proc)
        api_local.copiar_redactado(log, DIR_FALLA / "api_redis_detenido.log")
    return res


# ---------------------------------------------------------------------------
def timeout_bajo(cfg: Config) -> list[Resultado]:
    E, res = "timeout_bajo", []
    rutas = [("neo4j", f"/partidos/{cfg['PRUEBA_PARTIDO']}/eventos"),
             ("mongodb", "/equipos/ZZZ"),
             ("redis", "/sesiones/no-existe-h11"),
             ("cassandra", f"/partidos/{cfg['PRUEBA_CASSANDRA_PARTIDO']}/comentarios"
                           f"?instante={cfg['PRUEBA_CASSANDRA_INSTANTE']}&limit=5"),
             ("influxdb", f"/partidos/{cfg['PRUEBA_INFLUX_PARTIDO']}/estadisticas"
                          f"?desde={cfg['PRUEBA_INFLUX_DESDE']}&hasta={cfg['PRUEBA_INFLUX_HASTA']}"),
             ("iris", f"/partidos/{cfg['PRUEBA_PARTIDO_INEXISTENTE']}/detalle")]
    for etiqueta, alterada, extra in [("normal (DEP_TIMEOUT_S=3.0)", False, {"DEP_TIMEOUT_S": "3.0"}),
                                      ("alterada (DEP_TIMEOUT_S=0.001)", True, {"DEP_TIMEOUT_S": "0.001"})]:
        nombre = "alterada" if alterada else "normal"
        puerto = api_local.puerto_libre(8000)
        log = DIR_EVIDENCIA / "logs" / "crudos" / f"api_timeout_{nombre}.log"
        proc = api_local.iniciar(cfg, puerto, log, extra)
        if proc is None:
            res.append(_paso(E, "cambio", f"API {etiqueta}", FALLA, "no inicio"))
            continue
        res.append(_paso(E, "cambio" if alterada else "inicial",
                         f"Instancia de la API {etiqueta} en 127.0.0.1:{puerto}", INFO,
                         "solo cambia la variable de entorno; el codigo y las bases no se tocan"))
        try:
            for dep, ruta in rutas:
                rid = f"h11-timeout-{nombre}-{dep}-{uuid.uuid4().hex[:3]}"
                st, code, ms, _, err = _get(f"http://127.0.0.1:{puerto}", ruta, rid)
                time.sleep(0.05)
                lineas = api_local.lineas_de(log, rid)
                causa = next((x.split("causa=", 1)[1] for x in lineas if "causa=" in x), "-")
                res.append(_paso(E, "prueba" if alterada else "inicial",
                                 f"[{etiqueta}] GET {ruta.split('?')[0]} ({dep})", INFO,
                                 f"HTTP {st} {code} en {ms:.0f} ms | causa en el log: {causa[:140]}"
                                 if st else f"sin respuesta: {err}",
                                 duracion_ms=ms, extra={"request_id": rid, "log": lineas, "status": st}))
        finally:
            api_local.detener(proc)
            api_local.copiar_redactado(log, DIR_FALLA / f"api_timeout_{nombre}.log")
    res.append(_paso(E, "recuperacion", "Detener la instancia alterada", OK,
                     "la instancia con DEP_TIMEOUT_S=0.001 se detuvo; la configuracion versionada y "
                     "la de la API normal no cambiaron"))
    return res


# ---------------------------------------------------------------------------
def influx_sin_token(cfg: Config) -> list[Resultado]:
    E, res = "influx_sin_token", []
    ruta = (f"/partidos/{cfg['PRUEBA_INFLUX_PARTIDO']}/estadisticas?desde={cfg['PRUEBA_INFLUX_DESDE']}"
            f"&hasta={cfg['PRUEBA_INFLUX_HASTA']}")
    for etiqueta, nombre, quitar in [("con token", "con_token", []),
                                     ("sin INFLUXDB3_TOKEN", "sin_token", ["INFLUXDB3_TOKEN"])]:
        puerto = api_local.puerto_libre(8000)
        log = DIR_EVIDENCIA / "logs" / "crudos" / f"api_token_{nombre}.log"
        proc = api_local.iniciar(cfg, puerto, log, quitar_env=quitar)
        if proc is None:
            res.append(_paso(E, "cambio", f"API {etiqueta}", FALLA, "no inicio"))
            continue
        try:
            rid = f"h11-token-{nombre}-{uuid.uuid4().hex[:3]}"
            st, code, ms, _, err = _get(f"http://127.0.0.1:{puerto}", ruta, rid)
            time.sleep(0.05)
            lineas = api_local.lineas_de(log, rid)
            causa = next((x.split("causa=", 1)[1] for x in lineas if "causa=" in x), "-")
            res.append(_paso(E, "prueba" if quitar else "inicial", f"[{etiqueta}] GET {ruta.split('?')[0]}",
                             INFO, f"HTTP {st} {code} en {ms:.0f} ms | causa en el log: {causa}",
                             duracion_ms=ms, extra={"request_id": rid, "log": lineas, "status": st}))
        finally:
            api_local.detener(proc)
            api_local.copiar_redactado(log, DIR_FALLA / f"api_token_{nombre}.log")
    res.append(_paso(E, "recuperacion", "Detener la instancia sin token", OK,
                     "el token sigue en influxdb/.influxdb3-token; no se regenero ni se modifico"))
    return res


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--escenario", default=",".join(ESCENARIOS))
    a = ap.parse_args()
    cfg = Config()
    registrar_secretos(cfg.secretos())
    ok, info = docker_disponible()
    enc = encabezado_corrida("Fallas controladas", cfg)
    print(enc)
    res: list[Resultado] = []
    for esc in a.escenario.split(","):
        if esc == "redis_detenido" and not ok:
            res.append(_paso(esc, "inicial", "Docker", FALLA, f"se necesita Docker: {info}"))
            continue
        if esc in ESCENARIOS:
            print(f"--- escenario {esc}")
            res += globals()[esc](cfg)
    guardar_resultados("falla_controlada", res, enc, DIR_FALLA)


if __name__ == "__main__":
    main()
