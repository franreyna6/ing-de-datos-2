"""Funciones comunes de los scripts del Hito 13 (monitoreo).

Solo biblioteca estandar de Python: los scripts corren con el mismo Python de la
API (api/.venv) o con cualquier Python 3.10+, en Windows, Linux o macOS.

Reglas que respetan todos los scripts:
  - RNF6 (seguridad): ningun secreto se imprime ni se guarda. Todo texto que va
    a evidencia pasa por enmascarar().
  - RNF2 (trazabilidad): cada archivo de evidencia lleva fecha UTC y commit.
  - RNF11 (no destructivo): los scripts detienen e inician contenedores, pero
    nunca borran volumenes de las bases.
"""
from __future__ import annotations

import base64
import datetime as dt
import json
import os
import re
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]          # monitoreo/
REPO = RAIZ.parent                                   # raiz del repositorio
DIR_EVIDENCIA = RAIZ / "evidencia"
DIR_RESULTADOS = DIR_EVIDENCIA / "resultados_sin_secretos"
ARCHIVO_ENV = RAIZ / ".env"
ARCHIVO_ENV_EJEMPLO = RAIZ / ".env.example"
DIR_SECRETOS = RAIZ / "secretos"
TOKEN_INFLUX_ORIGEN = REPO / "influxdb" / ".influxdb3-token"
TOKEN_INFLUX_DESTINO = DIR_SECRETOS / "influxdb3-token"

PROMETHEUS = "http://127.0.0.1:9090"
GRAFANA = "http://127.0.0.1:3000"
ALERTMANAGER = "http://127.0.0.1:9093"
API = "http://127.0.0.1:8000"
UID_TABLERO = "fixture2030-war-room"

# Modulos del TPO que tienen docker-compose propio (Hitos 4 a 9).
MODULOS_BASES = ["mongodb", "neo4j", "cassandra", "redis", "influxdb", "iris"]
CONTENEDORES = {
    "mongodb": "fixture2030-mongodb", "neo4j": "fixture2030-neo4j",
    "cassandra": "fixture2030-cassandra", "redis": "fixture2030-redis",
    "influxdb": "fixture2030-influxdb", "iris": "fixture2030-iris",
}


# --------------------------------------------------------------------------
# Salida por consola
# --------------------------------------------------------------------------
def paso(texto: str) -> None:
    print(f"\n== {texto}", flush=True)


def info(texto: str) -> None:
    print(f"   {texto}", flush=True)


def aviso(texto: str) -> None:
    print(f"   [!] {texto}", flush=True)


# --------------------------------------------------------------------------
# Tiempo, git y archivos
# --------------------------------------------------------------------------
def ahora_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def iso(momento: dt.datetime | float) -> str:
    if isinstance(momento, (int, float)):
        momento = dt.datetime.fromtimestamp(momento, dt.timezone.utc)
    return momento.astimezone(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def etiqueta_nueva() -> str:
    return ahora_utc().strftime("%Y%m%d-%H%M%S")


def info_git() -> dict:
    def g(*args: str) -> str:
        try:
            r = subprocess.run(["git", "-C", str(REPO), *args], capture_output=True,
                               text=True, timeout=15)
            return r.stdout.strip()
        except Exception:
            return ""
    estado = g("status", "--porcelain", "--", "api", "monitoreo")
    return {"commit": g("rev-parse", "HEAD"), "commit_corto": g("rev-parse", "--short", "HEAD"),
            "rama": g("rev-parse", "--abbrev-ref", "HEAD"),
            "cambios_sin_commit_en_api_o_monitoreo": bool(estado)}


def escribir_texto(ruta: Path, texto: str) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(enmascarar(texto), encoding="utf-8", newline="\n")


def escribir_json(ruta: Path, datos) -> None:
    escribir_texto(ruta, json.dumps(datos, indent=2, ensure_ascii=False, default=str) + "\n")


def leer_json(ruta: Path):
    return json.loads(ruta.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# Configuracion local (.env) y secretos
# --------------------------------------------------------------------------
def leer_env(ruta: Path = ARCHIVO_ENV) -> dict:
    datos: dict[str, str] = {}
    if not ruta.exists():
        return datos
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        k, v = linea.split("=", 1)
        datos[k.strip()] = v.strip()
    return datos


def asegurar_env() -> dict:
    """Crea monitoreo/.env a partir del ejemplo si no existe.

    La contrasena de administrador de Grafana se genera al azar en cada maquina:
    no hay ninguna contrasena real escrita en el repositorio (RNF6).
    """
    if not ARCHIVO_ENV.exists():
        texto = ARCHIVO_ENV_EJEMPLO.read_text(encoding="utf-8")
        texto = texto.replace("GRAFANA_ADMIN_PASSWORD=cambiar-esto",
                              f"GRAFANA_ADMIN_PASSWORD={secrets.token_urlsafe(18)}")
        ARCHIVO_ENV.write_text(texto, encoding="utf-8", newline="\n")
        info("Se creo monitoreo/.env (excluido de Git) con una contrasena de Grafana al azar.")
    return leer_env()


def asegurar_token_influx() -> bool:
    """Copia el token de InfluxDB del Hito 8 a monitoreo/secretos/ (excluido de Git).

    Prometheus lo lee con credentials_file. Si el token no existe en esta maquina
    se deja un archivo vacio: el target influxdb quedara DOWN con 401, y eso se
    documenta como limitacion en vez de inventar un token.
    """
    DIR_SECRETOS.mkdir(parents=True, exist_ok=True)
    if TOKEN_INFLUX_ORIGEN.exists():
        token = TOKEN_INFLUX_ORIGEN.read_text(encoding="utf-8").strip()
        TOKEN_INFLUX_DESTINO.write_text(token, encoding="utf-8", newline="")
        return bool(token)
    TOKEN_INFLUX_DESTINO.write_text("", encoding="utf-8")
    aviso("No se encontro influxdb/.influxdb3-token: el target influxdb quedara DOWN (401).")
    return False


# Configuracion local del Hito 11 (fuera de Git): tiene las credenciales reales
# de esta maquina, por ejemplo la contrasena de _SYSTEM que hubo que cambiar en
# IRIS (diagnostico C1 del Hito 11: la imagen Community exige cambiarla).
CONFIG_CONECTIVIDAD = REPO / "conectividad" / "config" / "configuracion.env"
CLAVES_API = ["MONGODB_URI", "MONGODB_DATABASE", "NEO4J_URI", "NEO4J_USER", "NEO4J_PASSWORD",
              "NEO4J_DATABASE", "CASSANDRA_HOST", "CASSANDRA_PORT", "CASSANDRA_KEYSPACE",
              "CASSANDRA_CONTAINER", "REDIS_URL", "INFLUX_URL", "INFLUX_DATABASE",
              "IRIS_HOST", "IRIS_PORT", "IRIS_NAMESPACE", "IRIS_USER", "IRIS_PASSWORD"]


def config_conectividad() -> dict:
    return leer_env(CONFIG_CONECTIVIDAD)


def token_influx() -> str:
    if TOKEN_INFLUX_ORIGEN.exists():
        return TOKEN_INFLUX_ORIGEN.read_text(encoding="utf-8").strip()
    return os.environ.get("INFLUXDB3_TOKEN", "")


_PATRONES_SECRETOS = [
    re.compile(r"apiv3_[A-Za-z0-9_\-]+"),                          # tokens de InfluxDB 3
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]+"),
    re.compile(r"(://)[^/\s:@]+:[^/\s@]+(@)"),                      # usuario:clave en URIs
    re.compile(r"(?i)((?:password|passwd|token|secret)[\"']?\s*[=:]\s*[\"']?)[^\s\"',}]+"),
]


def enmascarar(texto: str) -> str:
    texto = _PATRONES_SECRETOS[0].sub("apiv3_***", texto)
    texto = _PATRONES_SECRETOS[1].sub(r"\1***", texto)
    texto = _PATRONES_SECRETOS[2].sub(r"\1***:***\2", texto)
    texto = _PATRONES_SECRETOS[3].sub(r"\1***", texto)
    for clave, valor in {**config_conectividad(), **leer_env()}.items():
        if valor and len(valor) >= 4 and any(p in clave for p in ("PASSWORD", "TOKEN", "URI")):
            texto = texto.replace(valor, "***")
    tok = token_influx()
    if tok:
        texto = texto.replace(tok, "***")
    return texto


# --------------------------------------------------------------------------
# HTTP minimo (stdlib)
# --------------------------------------------------------------------------
def http(metodo: str, url: str, cuerpo=None, timeout: float = 10.0,
         usuario: str | None = None, clave: str | None = None,
         cabeceras: dict | None = None):
    """Devuelve (status, headers, bytes). status 0 = sin conexion."""
    datos = None
    h = dict(cabeceras or {})
    if cuerpo is not None:
        datos = json.dumps(cuerpo).encode()
        h["Content-Type"] = "application/json"
    if usuario is not None:
        h["Authorization"] = "Basic " + base64.b64encode(f"{usuario}:{clave}".encode()).decode()
    req = urllib.request.Request(url, data=datos, method=metodo, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers or {}), e.read() if e.fp else b""
    except Exception:
        return 0, {}, b""


def http_json(metodo: str, url: str, **kw):
    st, h, b = http(metodo, url, **kw)
    try:
        return st, json.loads(b) if b else None
    except ValueError:
        return st, None


def esperar(url: str, segundos: float, descripcion: str, esperado=(200,)) -> bool:
    fin = time.monotonic() + segundos
    while time.monotonic() < fin:
        st, _, _ = http("GET", url, timeout=3)
        if st in esperado:
            return True
        time.sleep(2)
    aviso(f"{descripcion} no respondio en {segundos:.0f} s ({url}).")
    return False


# --------------------------------------------------------------------------
# Prometheus
# --------------------------------------------------------------------------
def prom_consulta(expr: str, momento: float | None = None) -> list[dict]:
    params = {"query": expr}
    if momento is not None:
        params["time"] = f"{momento:.3f}"
    st, js = http_json("GET", f"{PROMETHEUS}/api/v1/query?{urllib.parse.urlencode(params)}", timeout=15)
    if st != 200 or not js or js.get("status") != "success":
        return []
    return js["data"]["result"]


def prom_valor(expr: str, momento: float | None = None) -> float | None:
    """Primer valor escalar de una consulta instantanea (None si no hay datos)."""
    res = prom_consulta(expr, momento)
    if not res:
        return None
    try:
        v = float(res[0]["value"][1])
    except (KeyError, ValueError, IndexError):
        return None
    return None if v != v else v   # NaN -> None


def prom_rango(expr: str, inicio: float, fin: float, paso_s: int = 15) -> list[dict]:
    params = {"query": expr, "start": f"{inicio:.3f}", "end": f"{fin:.3f}", "step": str(paso_s)}
    st, js = http_json("GET", f"{PROMETHEUS}/api/v1/query_range?{urllib.parse.urlencode(params)}",
                       timeout=30)
    if st != 200 or not js or js.get("status") != "success":
        return []
    return js["data"]["result"]


# --------------------------------------------------------------------------
# Grafana
# --------------------------------------------------------------------------
def credenciales_grafana() -> tuple[str, str]:
    env = leer_env()
    return env.get("GRAFANA_ADMIN_USER", "admin"), env.get("GRAFANA_ADMIN_PASSWORD", "")


def anotar(texto: str, etiquetas: list[str], momento: float | None = None) -> None:
    """Anotacion en el tablero (Clase 14: 'anotaciones en el tiempo')."""
    usuario, clave = credenciales_grafana()
    cuerpo = {"dashboardUID": UID_TABLERO, "text": texto, "tags": etiquetas,
              "time": int((momento or time.time()) * 1000)}
    st, _, _ = http("POST", f"{GRAFANA}/api/annotations", cuerpo=cuerpo, timeout=10,
                    usuario=usuario, clave=clave)
    if st != 200:
        aviso(f"No se pudo crear la anotacion en Grafana (HTTP {st}).")


# --------------------------------------------------------------------------
# Docker
# --------------------------------------------------------------------------
def docker(*args: str, timeout: float = 180, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *args], capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout, cwd=str(cwd) if cwd else None)


def contenedor_corriendo(nombre: str) -> bool | None:
    r = docker("inspect", "-f", "{{.State.Running}}", nombre, timeout=20)
    if r.returncode != 0:
        return None
    return r.stdout.strip() == "true"


def python_api() -> str:
    """Python del entorno virtual de la API (tiene prometheus_client y los drivers)."""
    for c in (REPO / "api" / ".venv" / "Scripts" / "python.exe",
              REPO / "api" / ".venv" / "bin" / "python"):
        if c.exists():
            return str(c)
    return sys.executable
