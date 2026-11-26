"""Capturas reproducibles del tablero de Grafana (evidencia, RNF2).

Usa el servicio oficial grafana-image-renderer (levantado por el compose de
monitoreo) para guardar el tablero o un panel como PNG, con un rango de tiempo
EXACTO. Asi una captura siempre se puede vincular con la corrida que muestra
(etiqueta, horario y commit), y se puede volver a generar mientras Prometheus
conserve los datos (retencion de 7 dias).

Las capturas no contienen secretos: el tablero solo muestra metricas.

Uso:
  python scripts/capturar_dashboard.py --ultimos-minutos 15
  python scripts/capturar_dashboard.py --desde 2026-11-26T03:00:00Z --hasta 2026-11-26T03:10:00Z --nombre prueba
"""
from __future__ import annotations

import argparse
import datetime as dt
import urllib.parse
from pathlib import Path

from lib_monitoreo import (DIR_EVIDENCIA, GRAFANA, UID_TABLERO, aviso, credenciales_grafana,
                           http, info, leer_json)

ARCHIVO_TABLERO = Path(__file__).resolve().parents[1] / "grafana" / "dashboards" / "fixture2030-war-room.json"

# Paneles que se guardan sueltos (titulo del tablero -> nombre de archivo).
PANELES_CLAVE = {
    "Estado de salud por base: vista de infraestructura": "salud_infraestructura",
    "Disponibilidad vista por la API": "salud_vista_api",
    "Throughput: requests por segundo por ruta": "throughput",
    "Latencia de la API: p50, p95 y p99": "latencia_api",
    "Respuestas no exitosas por segundo": "errores",
    "Latencia p95 por base de datos": "latencia_por_base",
    "Operaciones por segundo por base": "operaciones_por_base",
    "Tasa de aciertos de cache": "cache",
    "Memoria de Redis usada": "memoria_redis",
    "Escrituras de comentarios en Cassandra por partido": "escrituras_cassandra",
    "Corte rapido por base": "corte_rapido",
}


def ids_de_paneles() -> dict[str, int]:
    tablero = leer_json(ARCHIVO_TABLERO)
    res = {}
    for p in tablero["panels"]:
        for prefijo, nombre in PANELES_CLAVE.items():
            if p.get("title", "").startswith(prefijo):
                res[nombre] = p["id"]
    return res


def renderizar(desde_ms: int, hasta_ms: int, destino: Path, panel_id: int | None = None,
               ancho: int = 1800, alto: int = 2100) -> bool:
    usuario, clave = credenciales_grafana()
    params = {"orgId": 1, "from": desde_ms, "to": hasta_ms, "width": ancho, "height": alto,
              "tz": "America/Argentina/Buenos_Aires", "theme": "light"}
    if panel_id is None:
        ruta = f"/render/d/{UID_TABLERO}/war-room"
        params["kiosk"] = "true"
    else:
        ruta = f"/render/d-solo/{UID_TABLERO}/war-room"
        params["panelId"] = panel_id
    st, h, cuerpo = http("GET", f"{GRAFANA}{ruta}?{urllib.parse.urlencode(params)}",
                         timeout=120, usuario=usuario, clave=clave)
    if st != 200 or not cuerpo.startswith(b"\x89PNG"):
        aviso(f"No se pudo renderizar {destino.name} (HTTP {st}).")
        return False
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(cuerpo)
    info(f"captura: {destino.relative_to(DIR_EVIDENCIA.parent)}")
    return True


def capturar(desde: dt.datetime, hasta: dt.datetime, nombre: str,
             salida: Path | None = None, paneles: bool = True) -> list[str]:
    salida = salida or (DIR_EVIDENCIA / "dashboards")
    d_ms, h_ms = int(desde.timestamp() * 1000), int(hasta.timestamp() * 1000)
    hechas = []
    archivo = salida / f"{nombre}_tablero_completo.png"
    if renderizar(d_ms, h_ms, archivo):
        hechas.append(archivo.name)
    if paneles:
        for panel, pid in ids_de_paneles().items():
            archivo = salida / f"{nombre}_{panel}.png"
            if renderizar(d_ms, h_ms, archivo, panel_id=pid, ancho=1200, alto=520):
                hechas.append(archivo.name)
    return hechas


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--desde")
    ap.add_argument("--hasta")
    ap.add_argument("--ultimos-minutos", type=int, default=15)
    ap.add_argument("--nombre", default=None)
    ap.add_argument("--sin-paneles", action="store_true")
    a = ap.parse_args()
    if a.desde and a.hasta:
        desde = dt.datetime.fromisoformat(a.desde.replace("Z", "+00:00"))
        hasta = dt.datetime.fromisoformat(a.hasta.replace("Z", "+00:00"))
    else:
        hasta = dt.datetime.now(dt.timezone.utc)
        desde = hasta - dt.timedelta(minutes=a.ultimos_minutos)
    nombre = a.nombre or hasta.strftime("captura_%Y%m%d-%H%M%S")
    hechas = capturar(desde, hasta, nombre, paneles=not a.sin_paneles)
    print(f"{len(hechas)} capturas guardadas en monitoreo/evidencia/dashboards/")


if __name__ == "__main__":
    main()
