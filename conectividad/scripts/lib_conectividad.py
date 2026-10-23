"""Utilidades comunes de la evaluacion de conectividad (Hito 11).

Responsabilidades de este archivo (y solo estas):
  - leer la configuracion externa (variables de entorno o config/configuracion.env)
    sin mostrar nunca un secreto (RF3, RNF7);
  - redactar cualquier texto antes de imprimirlo o guardarlo (RNF8);
  - definir el registro de una prueba (Resultado) con fecha, commit, entorno,
    producto, capa, prueba, resultado, duracion y limitaciones (RNF18);
  - clasificar el resultado de una conexion TCP segun la tabla 5.3 del enunciado;
  - ofrecer helpers para docker exec y HTTP con timeout (RNF5).

Ningun helper reintenta indefinidamente: cada operacion tiene un limite de espera.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from urllib.parse import urlparse

RAIZ_MODULO = Path(__file__).resolve().parent.parent          # conectividad/
RAIZ_REPO = RAIZ_MODULO.parent                                 # ing-de-datos-2/
DIR_EVIDENCIA = RAIZ_MODULO / "docs" / "evidencia"
DIR_LOGS = DIR_EVIDENCIA / "logs"
ARCHIVO_CONFIG = RAIZ_MODULO / "config" / "configuracion.env"

PRODUCTOS = ["mongodb", "neo4j", "cassandra", "redis", "influxdb", "iris"]

# Capas en el orden del enunciado (5.2): de menor a mayor costo.
CAPAS = ["configuracion", "resolucion", "tcp", "protocolo", "autenticacion",
         "autorizacion", "contexto", "lectura", "api"]

# Resultado de UNA prueba. SKIP = no se ejecuto por falta de herramienta o de
# configuracion; NO significa producto caido (seccion 5.8).
OK, FALLA, SKIP, INFO = "OK", "FALLA", "SKIP", "INFO"

# --------------------------------------------------------------------------
# Configuracion
# --------------------------------------------------------------------------
# Valores por defecto SIN secretos: coinciden con los docker-compose del repo.
# Las credenciales no tienen valor por defecto: si faltan, la capa de
# configuracion lo informa y el producto queda "no_configurado".
DEFECTOS = {
    "TIMEOUT_S": "3.0",
    "API_BASE_URL": "http://localhost:8000",
    # MongoDB (Hito 4)
    "MONGODB_URI": "",
    "MONGODB_DATABASE": "fixture2030",
    "MONGO_CONTAINER": "fixture2030-mongodb",
    # Neo4j (Hito 5)
    "NEO4J_URI": "bolt://localhost:7687",
    "NEO4J_HTTP_URL": "http://localhost:7474",
    "NEO4J_USER": "neo4j",
    "NEO4J_PASSWORD": "",
    "NEO4J_DATABASE": "neo4j",
    "NEO4J_CONTAINER": "fixture2030-neo4j",
    # Cassandra (Hito 6)
    "CASSANDRA_HOST": "localhost",
    "CASSANDRA_PORT": "9042",
    "CASSANDRA_KEYSPACE": "fixture2030_comentarios",
    "CASSANDRA_CONTAINER": "fixture2030-cassandra",
    # Redis (Hito 7)
    "REDIS_URL": "redis://localhost:6379/0",
    "REDIS_CONTAINER": "fixture2030-redis",
    # InfluxDB 3 Core (Hito 8)
    "INFLUX_URL": "http://localhost:8181",
    "INFLUX_DATABASE": "fixture2030_vivo",
    "INFLUXDB3_TOKEN": "",
    "INFLUXDB3_TOKEN_FILE": "",
    "INFLUX_CONTAINER": "fixture2030-influxdb",
    # IRIS (Hito 9)
    "IRIS_HOST": "localhost",
    "IRIS_PORT": "1972",
    "IRIS_PORTAL_URL": "http://localhost:52773",
    "IRIS_NAMESPACE": "USER",
    "IRIS_USER": "_SYSTEM",
    "IRIS_PASSWORD": "",
    "IRIS_CONTAINER": "fixture2030-iris",
    # Datos de prueba (lecturas minimas sobre datos del propio equipo)
    "PRUEBA_EQUIPO": "ARG",
    "PRUEBA_PARTIDO": "F2030-001",
    "PRUEBA_PARTIDO_INEXISTENTE": "F2030-999",
    "PRUEBA_CASSANDRA_PARTIDO": "F2030-063",
    "PRUEBA_CASSANDRA_INSTANTE": "2030-06-22T20:03:00Z",
    "PRUEBA_SESION": "S0001",
    "PRUEBA_INFLUX_PARTIDO": "F2030-018",
    "PRUEBA_INFLUX_DESDE": "2030-06-13T08:00:00Z",
    "PRUEBA_INFLUX_HASTA": "2030-06-13T08:05:00Z",
}

# Variables cuyo valor es secreto: nunca se imprimen.
SECRETAS = {"MONGODB_URI", "NEO4J_PASSWORD", "INFLUXDB3_TOKEN", "IRIS_PASSWORD", "REDIS_URL"}


def _leer_env_archivo(ruta: Path) -> dict:
    valores = {}
    if not ruta.exists():
        return valores
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        k, v = linea.split("=", 1)
        valores[k.strip()] = v.strip().strip('"').strip("'")
    return valores


class Config:
    """Configuracion efectiva. Prioridad: entorno > configuracion.env > defecto."""

    def __init__(self, archivo: Path = ARCHIVO_CONFIG) -> None:
        self.archivo = archivo
        self.archivo_existe = archivo.exists()
        del_archivo = _leer_env_archivo(archivo)
        self.origen: dict[str, str] = {}
        self.valores: dict[str, str] = {}
        for k, defecto in DEFECTOS.items():
            if os.environ.get(k) not in (None, ""):
                self.valores[k], self.origen[k] = os.environ[k], "entorno"
            elif del_archivo.get(k) not in (None, ""):
                self.valores[k], self.origen[k] = del_archivo[k], "configuracion.env"
            else:
                self.valores[k], self.origen[k] = defecto, ("defecto" if defecto else "ausente")
        # El token de InfluxDB puede venir de un archivo local (el del Hito 8),
        # asi no hace falta copiar el secreto a otro lugar.
        if not self.valores["INFLUXDB3_TOKEN"] and self.valores["INFLUXDB3_TOKEN_FILE"]:
            ruta = Path(self.valores["INFLUXDB3_TOKEN_FILE"])
            if not ruta.is_absolute():
                ruta = (RAIZ_MODULO / ruta).resolve()
            if ruta.exists():
                self.valores["INFLUXDB3_TOKEN"] = ruta.read_text(encoding="utf-8").strip()
                self.origen["INFLUXDB3_TOKEN"] = "archivo INFLUXDB3_TOKEN_FILE"

    def __getitem__(self, k: str) -> str:
        return self.valores[k]

    @property
    def timeout(self) -> float:
        return float(self.valores["TIMEOUT_S"])

    def secretos(self) -> list[str]:
        """Valores que jamas deben aparecer en una salida.

        Se excluyen los que coinciden con un valor publico de la configuracion
        (p. ej. una password de laboratorio igual al nombre de una database o al
        usuario): ocultarlos borraria informacion de diagnostico y no protegeria
        nada, porque ese texto ya es publico. Esas credenciales igual se ocultan
        en las URI y en los campos de password, que se redactan por estructura.
        """
        s = []
        for k in ("NEO4J_PASSWORD", "INFLUXDB3_TOKEN", "IRIS_PASSWORD"):
            if self.valores.get(k):
                s.append(self.valores[k])
        publicos = [v for k, v in self.valores.items() if k not in SECRETAS and v]
        for k in ("MONGODB_URI", "REDIS_URL"):
            u = urlparse(self.valores.get(k, ""))
            if u.password:
                s.append(u.password)
            if u.username:
                publicos.append(u.username)
        return [x for x in s if len(x) >= 3 and not any(x in p for p in publicos)]

    def entorno_para_api(self) -> dict:
        """Variables que la API del Hito 10 lee (mismos nombres)."""
        claves = ["MONGODB_URI", "MONGODB_DATABASE", "NEO4J_URI", "NEO4J_USER",
                  "NEO4J_PASSWORD", "NEO4J_DATABASE", "CASSANDRA_HOST", "CASSANDRA_PORT",
                  "CASSANDRA_KEYSPACE", "CASSANDRA_CONTAINER", "REDIS_URL", "INFLUX_URL",
                  "INFLUX_DATABASE", "INFLUXDB3_TOKEN", "IRIS_HOST", "IRIS_PORT",
                  "IRIS_NAMESPACE", "IRIS_USER", "IRIS_PASSWORD"]
        return {k: self.valores[k] for k in claves if self.valores.get(k)}


# --------------------------------------------------------------------------
# Redaccion de secretos (RNF7, RNF8)
# --------------------------------------------------------------------------
_RE_URI_CRED = re.compile(r"(?P<esq>[a-z][a-z0-9+.-]*://)(?P<usr>[^:/@\s]+):(?P<pwd>[^@/\s]+)@", re.I)
_RE_TOKEN = re.compile(r"apiv3_[A-Za-z0-9_\-]+")
_RE_BEARER = re.compile(r"(Bearer\s+)[A-Za-z0-9_\-\.]+", re.I)

_SECRETOS_EXTRA: list[str] = []


def registrar_secretos(valores: list[str]) -> None:
    for v in valores:
        if v and v not in _SECRETOS_EXTRA:
            _SECRETOS_EXTRA.append(v)


def redactar(texto) -> str:
    """Oculta credenciales sin borrar lo necesario para el diagnostico."""
    t = str(texto)
    t = _RE_URI_CRED.sub(lambda m: f"{m.group('esq')}{m.group('usr')}:****@", t)
    t = _RE_TOKEN.sub("apiv3_****", t)
    t = _RE_BEARER.sub(r"\1****", t)
    for s in sorted(_SECRETOS_EXTRA, key=len, reverse=True):
        t = re.sub(r"(?<![A-Za-z0-9_])" + re.escape(s) + r"(?![A-Za-z0-9_])", "****", t)
    return t


def describir_valor(cfg: Config, clave: str) -> str:
    """Valor apto para publicar: los secretos se describen, no se muestran."""
    v = cfg.valores.get(clave, "")
    if clave in ("NEO4J_PASSWORD", "IRIS_PASSWORD", "INFLUXDB3_TOKEN"):
        return f"definido ({len(v)} caracteres, oculto)" if v else "NO definido"
    if clave in ("MONGODB_URI", "REDIS_URL"):
        if not v:
            return "NO definido"
        u = urlparse(v)
        cred = "con credencial (oculta)" if u.password else "sin credencial"
        return f"{redactar(v)} [{cred}]"
    return v if v else "NO definido"


# --------------------------------------------------------------------------
# Registro de una prueba
# --------------------------------------------------------------------------
def _commit() -> str:
    try:
        r = subprocess.run(["git", "-C", str(RAIZ_REPO), "rev-parse", "--short", "HEAD"],
                           capture_output=True, text=True, timeout=5)
        # La evidencia que reescribe cada corrida no cuenta como cambio local del codigo.
        sucio = subprocess.run(["git", "-C", str(RAIZ_REPO), "status", "--porcelain", "--untracked-files=no",
                                "--", ".", ":(exclude)conectividad/docs/evidencia"],
                               capture_output=True, text=True, timeout=5).stdout.strip()
        return r.stdout.strip() + ("+cambios_locales" if sucio else "")
    except Exception:
        return "desconocido"


COMMIT = _commit()
ENTORNO_NOTEBOOK = (f"notebook {platform.system()} {platform.release()} | "
                    f"Python {platform.python_version()} ({Path(sys.executable).parent.parent.name})")


def ahora_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class Resultado:
    producto: str
    capa: str
    prueba: str
    resultado: str                  # OK | FALLA | SKIP | INFO
    detalle: str = ""
    objetivo: str = ""              # host:puerto, database, keyspace, clave, ventana...
    origen: str = ENTORNO_NOTEBOOK  # desde donde se ejecuto la prueba (RNF3)
    cliente: str = ""               # driver, CLI o protocolo usado (RNF4)
    duracion_ms: float | None = None
    responde: str = ""              # que pregunta responde (5.2)
    no_permite: str = ""            # que conclusion NO permite todavia (5.2)
    esperado: str = ""              # resultado esperado declarado antes de probar
    fecha: str = field(default_factory=ahora_iso)
    commit: str = COMMIT
    extra: dict = field(default_factory=dict)

    def a_dict(self) -> dict:
        d = asdict(self)
        d["detalle"] = redactar(d["detalle"])
        d["objetivo"] = redactar(d["objetivo"])
        d["extra"] = json.loads(redactar(json.dumps(d["extra"], ensure_ascii=False, default=str)))
        return d

    def linea(self) -> str:
        dur = f"{self.duracion_ms:7.1f} ms" if self.duracion_ms is not None else "     -    "
        return redactar(f"[{self.resultado:5}] {self.producto:9} {self.capa:13} {dur}  "
                        f"{self.prueba} -> {self.detalle}")


def medir(fn, *args, **kwargs):
    """Ejecuta fn y devuelve (valor, excepcion, ms). Nunca lanza."""
    t0 = time.perf_counter()
    try:
        v = fn(*args, **kwargs)
        return v, None, (time.perf_counter() - t0) * 1000
    except Exception as e:  # noqa: BLE001 - se clasifica afuera
        return None, e, (time.perf_counter() - t0) * 1000


def describir_excepcion(e: BaseException) -> str:
    msg = str(e).strip().splitlines()[0] if str(e).strip() else ""
    return redactar(f"{e.__class__.__name__}: {msg}"[:300])


# --------------------------------------------------------------------------
# Resolucion y TCP (tabla 5.3)
# --------------------------------------------------------------------------
def resolver(host: str) -> tuple[list[str] | None, str]:
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
        ips = sorted({i[4][0] for i in infos})
        return ips, "resuelto"
    except socket.gaierror as e:
        return None, f"host no resuelto ({e.strerror or e})"


def probar_tcp(host: str, puerto: int, timeout: float) -> tuple[str, str, float]:
    """Devuelve (clase, detalle, ms). clase: exito|refused|timeout|no_resuelto|error."""
    t0 = time.perf_counter()
    try:
        with socket.create_connection((host, puerto), timeout=timeout) as s:
            local = s.getsockname()
            remoto = s.getpeername()
        ms = (time.perf_counter() - t0) * 1000
        return "exito", f"conexion establecida {local[0]} -> {remoto[0]}:{remoto[1]}", ms
    except ConnectionRefusedError:
        return "refused", "connection refused: el host respondio pero no hay listener", \
            (time.perf_counter() - t0) * 1000
    except socket.timeout:
        return "timeout", f"sin respuesta en {timeout:.1f} s", (time.perf_counter() - t0) * 1000
    except socket.gaierror as e:
        return "no_resuelto", f"host no resuelto ({e.strerror or e})", \
            (time.perf_counter() - t0) * 1000
    except OSError as e:
        return "error", describir_excepcion(e), (time.perf_counter() - t0) * 1000


def intercambio_crudo(host: str, puerto: int, enviar: bytes, timeout: float,
                      leer: int = 4096) -> bytes:
    """Abre TCP, envia bytes de un protocolo y devuelve la primera respuesta."""
    with socket.create_connection((host, puerto), timeout=timeout) as s:
        s.settimeout(timeout)
        s.sendall(enviar)
        datos = b""
        fin = time.monotonic() + timeout
        while time.monotonic() < fin:
            try:
                parte = s.recv(leer)
            except socket.timeout:
                break
            if not parte:
                break
            datos += parte
            if len(datos) >= 4:
                break
        return datos


# --------------------------------------------------------------------------
# HTTP con timeout (urllib de la biblioteca estandar)
# --------------------------------------------------------------------------
def http(metodo: str, url: str, timeout: float, headers: dict | None = None,
         cuerpo: bytes | None = None) -> tuple[int | None, dict, bytes, str]:
    """Devuelve (status, headers, cuerpo, error). status None = no hubo respuesta HTTP."""
    req = urllib.request.Request(url, data=cuerpo, method=metodo, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, dict(r.headers), r.read(), ""
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers or {}), e.read() if e.fp else b"", ""
    except urllib.error.URLError as e:
        razon = e.reason
        if isinstance(razon, ConnectionRefusedError):
            return None, {}, b"", "connection refused"
        if isinstance(razon, socket.timeout) or "timed out" in str(razon):
            return None, {}, b"", "timeout"
        if isinstance(razon, socket.gaierror):
            return None, {}, b"", "host no resuelto"
        return None, {}, b"", describir_excepcion(e)
    except (socket.timeout, TimeoutError):
        return None, {}, b"", "timeout"
    except Exception as e:  # noqa: BLE001
        return None, {}, b"", describir_excepcion(e)


# --------------------------------------------------------------------------
# Docker (clientes nativos dentro del contenedor)
# --------------------------------------------------------------------------
def docker_disponible() -> tuple[bool, str]:
    if not shutil.which("docker"):
        return False, "docker no esta en el PATH"
    try:
        r = subprocess.run(["docker", "version", "--format", "{{.Server.Version}}"],
                           capture_output=True, text=True, timeout=10)
    except subprocess.TimeoutExpired:
        return False, "docker no respondio en 10 s"
    if r.returncode != 0:
        return False, "el daemon de Docker no responde (Docker Desktop cerrado?)"
    return True, f"Docker Engine {r.stdout.strip()}"


def estado_contenedor(nombre: str) -> str:
    """'running', 'exited', ... o 'inexistente'."""
    try:
        r = subprocess.run(["docker", "inspect", "-f", "{{.State.Status}}", nombre],
                           capture_output=True, text=True, timeout=10)
    except Exception:
        return "desconocido"
    return r.stdout.strip() if r.returncode == 0 else "inexistente"


def docker_exec(contenedor: str, comando: list[str], timeout: float,
                entrada: str | None = None, env: dict | None = None) -> tuple[int, str, str]:
    """docker exec con limite de espera. Los -e se pasan por nombre (el valor
    viaja en el entorno del proceso, no en la linea de comando)."""
    args = ["docker", "exec"]
    if entrada is not None:
        args.append("-i")
    entorno = os.environ.copy()
    for k, v in (env or {}).items():
        args += ["-e", k]
        entorno[k] = v
    args += [contenedor] + comando
    try:
        r = subprocess.run(args, input=entrada, capture_output=True, text=True,
                           timeout=timeout, env=entorno, encoding="utf-8", errors="replace")
        return r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        return -1, "", f"timeout de {timeout:.0f} s en docker exec"


# --------------------------------------------------------------------------
# Escritura de evidencia
# --------------------------------------------------------------------------
def guardar_resultados(nombre: str, resultados: list[Resultado], encabezado: str = "",
                       carpeta: Path | None = None) -> Path:
    """Guarda resultados_<nombre>.json y .txt (redactados).

    Por defecto en docs/evidencia/ (ultima corrida). El orquestador pasa una
    carpeta por corrida para conservar el 'antes' y el 'despues' (RF20)."""
    carpeta = carpeta or DIR_EVIDENCIA
    carpeta.mkdir(parents=True, exist_ok=True)
    datos = {"generado": ahora_iso(), "commit": COMMIT, "origen": ENTORNO_NOTEBOOK,
             "resultados": [r.a_dict() for r in resultados]}
    ruta_json = carpeta / f"resultados_{nombre}.json"
    ruta_json.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    lineas = [redactar(encabezado)] if encabezado else []
    lineas += [r.linea() for r in resultados]
    (carpeta / f"resultados_{nombre}.txt").write_text("\n".join(lineas) + "\n", encoding="utf-8", newline="\n")
    return ruta_json


def imprimir(r: Resultado) -> Resultado:
    print(r.linea(), flush=True)
    return r


def encabezado_corrida(titulo: str, cfg: Config) -> str:
    ok_docker, info_docker = docker_disponible()
    return "\n".join([
        f"# {titulo}",
        f"# fecha UTC: {ahora_iso()} | commit: {COMMIT}",
        f"# origen de las pruebas: {ENTORNO_NOTEBOOK}",
        f"# docker: {info_docker}",
        f"# configuracion: {cfg.archivo.name} {'presente' if cfg.archivo_existe else 'AUSENTE (se usan entorno y defectos)'}",
        f"# timeout por operacion: {cfg.timeout:.1f} s",
    ])
