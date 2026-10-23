#!/usr/bin/env python3
"""Evaluacion de conectividad del Fixture 2030 - orquestador y resumen (Hito 11, 5.8).

Recorre las capas de menor a mayor costo (5.2): configuracion -> resolucion ->
TCP -> protocolo -> autenticacion -> autorizacion -> contexto -> lectura ->
endpoint de la API. Cada modo se puede ejecutar solo, por producto o completo,
sin exigir que todas las dependencias esten disponibles a la vez (RNF13).

Modos:
  completo       todas las capas + demostracion de fallas TCP + vista desde un contenedor
  configuracion  solo la capa de configuracion e inventario de herramientas
  tcp            resolucion y TCP
  nativos        clientes nativos y drivers (protocolo a lectura)
  api            rutas de la API del Hito 10

Al terminar imprime el resumen de estados y escribe la matriz de conectividad
(docs/evidencia/corridas/<fecha>_<etiqueta>/matriz.md y matriz_ultima_corrida.md).

Estados por dependencia (RNF9, 5.6):
  disponible      todas las pruebas positivas del producto terminaron OK y las rutas de
                  la API respondieron segun su contrato
  degradado       el producto responde por su cliente nativo, pero el uso desde la API
                  falla o una prueba posterior a la conexion fallo
  no_disponible   fallo una prueba de red, protocolo, identidad, contexto o lectura
  no_configurado  falta configuracion obligatoria para intentarlo
  desconocido     solo hubo pruebas SKIP (falta herramienta): no hay evidencia suficiente
  no_probado      el modo elegido no incluyo pruebas de ese producto
SKIP significa "prueba no ejecutada por falta de herramienta o configuracion",
NO "producto caido".

Uso:
  python evaluar_conectividad.py --modo completo --iniciar-api --etiqueta inicial
  python evaluar_conectividad.py --modo tcp --producto redis,neo4j
"""
from __future__ import annotations

import argparse
import datetime as dt
from collections import Counter, defaultdict
from pathlib import Path

import api_local
import prueba_api
import prueba_clientes_nativos
import prueba_configuracion
import prueba_tcp
from dependencias import construir
from lib_conectividad import (CAPAS, COMMIT, DIR_EVIDENCIA, ENTORNO_NOTEBOOK, FALLA, INFO, OK,
                              PRODUCTOS, SKIP, Config, Resultado, ahora_iso, docker_disponible,
                              encabezado_corrida, guardar_resultados, redactar)

MODOS = ["completo", "configuracion", "tcp", "nativos", "api"]


def _es_negativo(r: Resultado) -> bool:
    return r.extra.get("caso") == "negativo"


def estado_dependencia(producto: str, res: list[Resultado]) -> dict:
    propios = [r for r in res if r.producto == producto]
    positivos = [r for r in propios if not _es_negativo(r) and r.resultado in (OK, FALLA, SKIP)]
    if not propios:
        return {"estado": "no_probado", "capa": "-", "diagnostico": "sin pruebas en este modo"}
    conf = [r for r in positivos if r.capa == "configuracion" and r.resultado == FALLA]
    if conf:
        return {"estado": "no_configurado", "capa": "configuracion", "diagnostico": conf[0].detalle}
    # Pruebas desde la notebook (el origen de la API) que no sean de compatibilidad con la API.
    nativas = [r for r in positivos if r.capa not in ("configuracion", "api")
               and not r.extra.get("compatibilidad_api")]
    fallas_nativas = [r for r in nativas if r.resultado == FALLA and not r.origen.startswith("contenedor")]
    api = [r for r in positivos if r.capa == "api"]
    compat = [r for r in positivos if r.extra.get("compatibilidad_api") and r.resultado == FALLA]
    fallas_api = [r for r in api if r.resultado == FALLA]
    if not [r for r in positivos if r.capa != "configuracion"]:
        return {"estado": "no_probado", "capa": "-",
                "diagnostico": "solo se evaluo la configuracion (OK); faltan las capas de red en adelante"}
    if fallas_nativas:
        primera = min(fallas_nativas, key=lambda r: CAPAS.index(r.capa))
        return {"estado": "no_disponible", "capa": primera.capa,
                "diagnostico": f"{primera.prueba}: {primera.detalle}"}
    if not [r for r in nativas + api if r.resultado == OK]:
        return {"estado": "desconocido", "capa": "-",
                "diagnostico": "solo pruebas SKIP: falta herramienta o configuracion"}
    if compat or fallas_api:
        motivo = (compat or fallas_api)[0]
        return {"estado": "degradado", "capa": "api" if fallas_api else motivo.capa,
                "diagnostico": f"{motivo.prueba}: {motivo.detalle}"}
    return {"estado": "disponible", "capa": "-", "diagnostico": "todas las pruebas positivas OK"}


def _ms(r: Resultado) -> str:
    return f"{r.duracion_ms:.0f}" if r.duracion_ms is not None else "-"


def _celda(t: str, n: int = 170) -> str:
    t = redactar(t).replace("|", "/").replace("\n", " ")
    return t if len(t) <= n else t[: n - 1] + "…"


def escribir_matriz(res: list[Resultado], productos: list[str], modo: str, etiqueta: str,
                    carpeta: Path, cfg: Config, ultima: bool = True) -> str:
    deps = construir(cfg)
    _, info_docker = docker_disponible()
    L = [f"# Matriz de conectividad — corrida `{etiqueta}`", "",
         f"- **Fecha (UTC):** {ahora_iso()}",
         f"- **Commit:** `{COMMIT}`",
         f"- **Entorno de ejecución:** {ENTORNO_NOTEBOOK} — mismo origen que la API del Hito 10",
         f"- **Docker:** {info_docker}",
         f"- **Modo:** `{modo}` · **timeout por operación:** {cfg.timeout:.1f} s",
         "- **Significado:** OK = esa prueba concreta funcionó en este momento; no garantiza "
         "rendimiento ni disponibilidad permanente (RNF17). SKIP = no se ejecutó por falta de "
         "herramienta o configuración, no producto caído.", "",
         "## Estado por dependencia", "",
         "| Dependencia | Host:puerto (desde la API) | Contexto | Estado | Capa con falla | "
         "OK/FALLA/SKIP | Rutas API según contrato | Diagnóstico automático |",
         "| :--- | :--- | :--- | :--- | :--- | :---: | :---: | :--- |"]
    for p in productos:
        e = estado_dependencia(p, res)
        propios = [r for r in res if r.producto == p and r.resultado in (OK, FALLA, SKIP)]
        c = Counter(r.resultado for r in propios)
        api = [r for r in propios if r.capa == "api"]
        rutas = f"{sum(r.resultado == OK for r in api)}/{len(api)}" if api else "-"
        ep = next((x for x in deps[p].endpoints if x.usado_por_api), deps[p].endpoints[0])
        L.append(f"| **{p}** | `{ep.host}:{ep.puerto}` ({ep.protocolo}) | {deps[p].contexto} | "
                 f"**{e['estado']}** | {e['capa']} | {c[OK]}/{c[FALLA]}/{c[SKIP]} | {rutas} | "
                 f"{_celda(e['diagnostico'])} |")
    for p in productos:
        L += ["", f"## {p}", "",
              "| Capa | Prueba | Origen | Cliente | Resultado | ms | Detalle |",
              "| :--- | :--- | :--- | :--- | :---: | ---: | :--- |"]
        for r in sorted([r for r in res if r.producto == p], key=lambda r: CAPAS.index(r.capa)
                        if r.capa in CAPAS else 99):
            origen = "contenedor" if r.origen.startswith("contenedor") else "notebook"
            L.append(f"| {r.capa} | {_celda(r.prueba, 110)} | {origen} | {_celda(r.cliente, 40)} | "
                     f"{r.resultado} | {_ms(r)} | {_celda(r.detalle)} |")
    otros = sorted({r.producto for r in res} - set(productos))
    for o in otros:
        L += ["", f"## {o}", "", "| Capa | Prueba | Resultado | ms | Detalle |",
              "| :--- | :--- | :---: | ---: | :--- |"]
        for r in [r for r in res if r.producto == o]:
            L.append(f"| {r.capa} | {_celda(r.prueba, 110)} | {r.resultado} | {_ms(r)} | {_celda(r.detalle)} |")
    skips = [r for r in res if r.resultado == SKIP]
    L += ["", "## Herramientas o pruebas no ejecutadas (SKIP)", ""]
    L += [f"- {r.producto} / {r.prueba}: {_celda(r.detalle)}" for r in skips] or ["- ninguna"]
    texto = "\n".join(L) + "\n"
    (carpeta / "matriz.md").write_text(texto, encoding="utf-8", newline="\n")
    if ultima:
        (DIR_EVIDENCIA / "matriz_ultima_corrida.md").write_text(texto, encoding="utf-8", newline="\n")
    return texto


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--modo", choices=MODOS, default="completo")
    ap.add_argument("--producto", default=",".join(PRODUCTOS),
                    help="lista separada por comas: " + ",".join(PRODUCTOS))
    ap.add_argument("--iniciar-api", action="store_true",
                    help="levanta la API del Hito 10 (127.0.0.1:8000) solo durante el modo api")
    ap.add_argument("--etiqueta", default="corrida", help="nombre de la corrida (p. ej. inicial, final)")
    a = ap.parse_args()

    cfg = Config()
    productos = [p for p in a.producto.split(",") if p in PRODUCTOS]
    marca = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    carpeta = DIR_EVIDENCIA / "corridas" / f"{marca}_{a.etiqueta}"
    enc = encabezado_corrida(f"Evaluacion de conectividad - modo {a.modo} - {a.etiqueta}", cfg)
    print(enc)
    res: list[Resultado] = []

    if a.modo in ("completo", "configuracion"):
        print("\n=== Capa 1: configuracion (sin secretos) ===")
        r = prueba_configuracion.ejecutar(cfg, productos)
        guardar_resultados("configuracion", r, enc, carpeta)
        res += r
    if a.modo in ("completo", "tcp"):
        print("\n=== Capas 2 y 3: resolucion y TCP desde la notebook ===")
        r = prueba_tcp.ejecutar(cfg, productos)
        if a.modo == "completo" or a.producto == ",".join(PRODUCTOS):
            print("\n--- Tipos de falla TCP (tabla 5.3) y vista desde un contenedor (RNF3)")
            r += prueba_tcp.demostrar_fallas(cfg) + prueba_tcp.desde_contenedor(cfg)
        guardar_resultados("tcp", r, enc, carpeta)
        res += r
    if a.modo in ("completo", "nativos"):
        print("\n=== Capas 4 a 8: clientes nativos y drivers ===")
        r = prueba_clientes_nativos.ejecutar(cfg, productos)
        guardar_resultados("clientes", r, enc, carpeta)
        res += r
    if a.modo in ("completo", "api"):
        print("\n=== Capa 9: rutas de la API del Hito 10 ===")
        proc, log, base = None, None, cfg["API_BASE_URL"]
        if a.iniciar_api:
            log = DIR_EVIDENCIA / "logs" / "crudos" / f"api_{marca}_{a.etiqueta}.log"
            puerto = api_local.puerto_libre(8000)
            proc = api_local.iniciar(cfg, puerto, log)
            base = f"http://127.0.0.1:{puerto}"
            print(f"# API del Hito 10 iniciada en {base} (log crudo fuera de Git)" if proc
                  else "# la API NO quedo lista: se registra como no alcanzable")
        try:
            r = prueba_api.ejecutar(cfg, base, log, etiqueta=a.etiqueta)
        finally:
            api_local.detener(proc)
        if log:
            api_local.copiar_redactado(log, carpeta / "api_redactado.log")
        r = [x for x in r if x.producto in productos or x.producto == "api"]
        guardar_resultados("api", r, enc, carpeta)
        res += r

    # Copia de la ultima corrida COMPLETA con los nombres del enunciado (resultados_tcp,
    # _clientes, _api). Una corrida parcial (un modo o un producto) no pisa esa copia.
    completa = a.modo == "completo" and len(productos) == len(PRODUCTOS)
    if completa:
        for nombre in ("configuracion", "tcp", "clientes", "api"):
            for ext in ("txt", "json"):
                origen = carpeta / f"resultados_{nombre}.{ext}"
                if origen.exists():
                    (DIR_EVIDENCIA / f"resultados_{nombre}.{ext}").write_text(
                        origen.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")

    escribir_matriz(res, productos, a.modo, a.etiqueta, carpeta, cfg, ultima=completa)
    print("\n=== Resumen de estados ===")
    print(f"{'dependencia':11} {'estado':15} {'capa':14} diagnostico")
    for p in productos:
        e = estado_dependencia(p, res)
        print(redactar(f"{p:11} {e['estado']:15} {e['capa']:14} {e['diagnostico'][:110]}"))
    skips = [r for r in res if r.resultado == SKIP]
    print(f"\nPruebas SKIP (no ejecutadas por herramienta/configuracion, NO producto caido): {len(skips)}")
    for r in skips:
        print(f"  - {r.producto}: {r.prueba} -> {redactar(r.detalle)[:120]}")
    print(f"\nEvidencia: {carpeta.relative_to(DIR_EVIDENCIA.parent.parent)}")


if __name__ == "__main__":
    main()
