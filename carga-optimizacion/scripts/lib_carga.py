"""Funciones comunes del Hito 12 (pruebas de carga y optimizacion).

Lo usan todos los scripts de esta carpeta. Esta separado por bloques:
  1. Rutas y configuracion (archivo .env local + escenario.json).
  2. Metricas: percentiles y resumen de latencias.
  3. Acceso a los productos por su cliente oficial dentro del contenedor
     (cqlsh y nodetool en Cassandra, redis-cli en Redis), igual que en los
     Hitos 6 y 7. Solo se usa para MEDIR y VALIDAR, nunca para generar carga:
     la carga siempre pasa por la API.
  4. Muestreo de recursos (docker stats y, si esta instalado, psutil).
  5. Trazabilidad: commit, versiones e informacion del entorno.

Solo usa la biblioteca estandar de Python. psutil y matplotlib son opcionales:
si no estan, se omite esa medicion y queda registrado que se omitio.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

# --------------------------------------------------------------------------
# 1. Rutas y configuracion
# --------------------------------------------------------------------------
RAIZ = Path(__file__).resolve().parent.parent          # carga-optimizacion/
REPO = RAIZ.parent                                     # raiz del repositorio
DIR_CONFIG = RAIZ / "config"
DIR_DATOS = RAIZ / "datos"
DIR_EVIDENCIA = RAIZ / "docs" / "evidencia"
ARCHIVO_ESCENARIO = DIR_CONFIG / "escenario.json"
ARCHIVO_PLAN = DIR_DATOS / "plan.jsonl"
ARCHIVO_RESUMEN_PLAN = DIR_DATOS / "resumen_plan.json"

VENTANA_MIN = 5  # minutos por particion de comentarios (igual que el Hito 6)

# En Windows la consola puede no ser UTF-8; evitamos que un acento corte el script.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def _leer_env(archivo: Path) -> dict:
    valores = {}
    if not archivo.exists():
        return valores
    for linea in archivo.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        k, v = linea.split("=", 1)
        valores[k.strip()] = v.strip()
    return valores


def cargar_config() -> dict:
    """Config efectiva: ejemplo < configuracion.env local < variables de entorno."""
    cfg = _leer_env(DIR_CONFIG / "configuracion-ejemplo.env")
    cfg.update(_leer_env(DIR_CONFIG / "configuracion.env"))
    for k in list(cfg):
        if os.environ.get(k):
            cfg[k] = os.environ[k]
    return cfg


def cargar_escenario() -> dict:
    return json.loads(ARCHIVO_ESCENARIO.read_text(encoding="utf-8"))


def sha256_escenario() -> str:
    """Hash del CONTENIDO del escenario (JSON canonico), no de sus bytes: asi no
    cambia si git convierte fines de linea (CRLF en Windows)."""
    canon = json.dumps(cargar_escenario(), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def sha256_archivo(ruta: Path) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def ahora_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def ventana_de(instante: dt.datetime) -> dt.datetime:
    """Inicio UTC del bucket de 5 minutos (misma regla que la API y el Hito 6)."""
    instante = instante.astimezone(dt.timezone.utc)
    minuto = instante.minute - (instante.minute % VENTANA_MIN)
    return instante.replace(minute=minuto, second=0, microsecond=0)


def ventanas_entre(desde: dt.datetime, hasta: dt.datetime) -> list[dt.datetime]:
    """Todas las ventanas de 5 min que toca el intervalo [desde, hasta]."""
    v = ventana_de(desde)
    fin = ventana_de(hasta)
    res = []
    while v <= fin:
        res.append(v)
        v += dt.timedelta(minutes=VENTANA_MIN)
    return res


def codigo_partido(etiqueta: str, clave: str) -> str:
    """Codigo de partido de LABORATORIO de una corrida (RNF7: aislamiento).

    Cada corrida escribe en partidos propios ('H12-<etiqueta>-P1'...), que no
    existen en el fixture real. Asi no se mezclan datos entre corridas ni con
    los comentarios del Hito 6, y el conteo de integridad es exacto.
    """
    return f"H12-{etiqueta}-{clave}"


def escribir_json(ruta: Path, datos) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(datos, indent=2, ensure_ascii=False, default=str),
                    encoding="utf-8")


def leer_json(ruta: Path):
    return json.loads(Path(ruta).read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# 2. Metricas
# --------------------------------------------------------------------------
def percentil(valores_ordenados: list[float], p: float) -> float | None:
    """Percentil por rango mas cercano (nearest-rank). Lista ya ordenada."""
    if not valores_ordenados:
        return None
    k = max(0, min(len(valores_ordenados) - 1,
                   int(-(-p * len(valores_ordenados) // 100)) - 1))
    return valores_ordenados[k]


def resumen_latencias(valores: list[float]) -> dict:
    """min, p50, p90, p95, p99, max y promedio en milisegundos."""
    if not valores:
        return {"n": 0}
    v = sorted(valores)
    return {
        "n": len(v),
        "min": round(v[0], 2),
        "p50": round(percentil(v, 50), 2),
        "p90": round(percentil(v, 90), 2),
        "p95": round(percentil(v, 95), 2),
        "p99": round(percentil(v, 99), 2),
        "max": round(v[-1], 2),
        "promedio": round(sum(v) / len(v), 2),
    }


# --------------------------------------------------------------------------
# 3. Clientes oficiales dentro de los contenedores (solo medir / validar)
# --------------------------------------------------------------------------
def ejecutar(cmd: list[str], timeout: float = 60) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout)


def docker_disponible() -> bool:
    try:
        return ejecutar(["docker", "version", "--format", "{{.Server.Version}}"],
                        timeout=15).returncode == 0
    except Exception:
        return False


def cqlsh(cfg: dict, cql: str, timeout: float = 120) -> str:
    """Ejecuta CQL con cqlsh dentro del contenedor de Cassandra (Hito 6)."""
    cmd = ["docker", "exec", cfg["CASSANDRA_CONTAINER"], "cqlsh",
           "--request-timeout=60", "-k", cfg["CASSANDRA_KEYSPACE"], "-e", cql]
    res = ejecutar(cmd, timeout=timeout)
    if res.returncode != 0:
        raise RuntimeError(f"cqlsh fallo: {(res.stderr or res.stdout).strip()[:400]}")
    return res.stdout


def filas_json_cqlsh(salida: str) -> list[dict]:
    """Extrae las filas de un 'SELECT JSON' de cqlsh (una linea JSON por fila)."""
    filas = []
    for linea in salida.splitlines():
        t = linea.strip()
        if t.startswith("{") and t.endswith("}"):
            try:
                filas.append(json.loads(t))
            except json.JSONDecodeError:
                pass
    return filas


def redis_cli(cfg: dict, *args: str, timeout: float = 60) -> str:
    """Ejecuta redis-cli dentro del contenedor de Redis (Hito 7)."""
    cmd = ["docker", "exec", cfg["REDIS_CONTAINER"], "redis-cli", *args]
    res = ejecutar(cmd, timeout=timeout)
    if res.returncode != 0:
        raise RuntimeError(f"redis-cli fallo: {(res.stderr or res.stdout).strip()[:400]}")
    return res.stdout


def info_redis(cfg: dict) -> dict:
    """Campos de INFO relevantes para la prueba (memoria, aciertos, expulsiones)."""
    salida = redis_cli(cfg, "INFO")
    datos = {}
    for linea in salida.splitlines():
        if ":" in linea and not linea.startswith("#"):
            k, v = linea.split(":", 1)
            datos[k.strip()] = v.strip()
    campos = ["redis_version", "used_memory", "used_memory_human", "maxmemory",
              "maxmemory_human", "maxmemory_policy", "evicted_keys", "expired_keys",
              "keyspace_hits", "keyspace_misses", "connected_clients",
              "total_commands_processed"]
    return {k: datos.get(k) for k in campos}


def contar_claves(cfg: dict, patron: str) -> int:
    salida = redis_cli(cfg, "--scan", "--pattern", patron)
    return len([l for l in salida.splitlines() if l.strip()])


def stats_tabla_cassandra(cfg: dict) -> dict:
    """Contadores locales de la tabla de comentarios (nodetool tablestats).

    Los contadores son acumulados desde que arranco el nodo: lo util es la
    DIFERENCIA entre antes y despues de la prueba (cuantas lecturas y
    escrituras llegaron realmente a Cassandra).
    """
    tabla = f"{cfg['CASSANDRA_KEYSPACE']}.comentarios_por_partido"
    res = ejecutar(["docker", "exec", cfg["CASSANDRA_CONTAINER"], "nodetool",
                    "tablestats", tabla], timeout=90)
    if res.returncode != 0:
        raise RuntimeError(f"nodetool tablestats fallo: {res.stderr.strip()[:300]}")
    datos = {}
    patrones = {
        "lecturas_locales": r"Local read count:\s*(\d+)",
        "latencia_lectura_local_ms": r"Local read latency:\s*([\d.]+|NaN)",
        "escrituras_locales": r"Local write count:\s*(\d+)",
        "latencia_escritura_local_ms": r"Local write latency:\s*([\d.]+|NaN)",
    }
    for clave, patron in patrones.items():
        m = re.search(patron, res.stdout)
        if m:
            valor = m.group(1)
            datos[clave] = None if valor == "NaN" else float(valor)
    return datos


def histogramas_tabla_cassandra(cfg: dict) -> dict:
    """Percentiles de latencia LOCAL de Cassandra (nodetool tablehistograms).

    Es el tiempo que la base tarda en resolver la operacion, sin red, sin API y
    sin cliente. Sirve para separar 'tiempo de base' de 'tiempo de API'.
    """
    res = ejecutar(["docker", "exec", cfg["CASSANDRA_CONTAINER"], "nodetool",
                    "tablehistograms", cfg["CASSANDRA_KEYSPACE"],
                    "comentarios_por_partido"], timeout=90)
    if res.returncode != 0:
        raise RuntimeError(f"nodetool tablehistograms fallo: {res.stderr.strip()[:300]}")
    datos = {}
    for linea in res.stdout.splitlines():
        partes = linea.split()
        if partes and partes[0] in ("50%", "95%", "99%", "Max"):
            try:
                datos[partes[0]] = {"lectura_us": float(partes[1]),
                                    "escritura_us": float(partes[2])}
            except (IndexError, ValueError):
                pass
    return datos


# --------------------------------------------------------------------------
# 4. Muestreo de recursos
# --------------------------------------------------------------------------
def _a_mib(texto: str) -> float | None:
    m = re.match(r"([\d.]+)\s*([KMGT]?i?B)", texto.strip())
    if not m:
        return None
    n, u = float(m.group(1)), m.group(2)
    factor = {"B": 1 / 1048576, "KiB": 1 / 1024, "KB": 1 / 1024, "MiB": 1, "MB": 1,
              "GiB": 1024, "GB": 1024, "TiB": 1048576, "TB": 1048576}.get(u, 1)
    return round(n * factor, 1)


class MuestreoRecursos(threading.Thread):
    """Toma muestras periodicas de CPU y memoria mientras corre la prueba.

    - Contenedores (Cassandra, Redis): 'docker stats --no-stream'.
    - Proceso de la API (uvicorn) y la maquina: psutil, si esta instalado.
    - Generador de carga (este mismo proceso): tiempo de CPU propio.
    Cada muestra lleva el segundo relativo al inicio de la prueba.
    """

    def __init__(self, cfg: dict, intervalo_s: float, t0: float, usar_docker: bool):
        super().__init__(daemon=True)
        self.cfg, self.intervalo, self.t0 = cfg, intervalo_s, t0
        self.usar_docker = usar_docker
        self.muestras: list[dict] = []
        self.detener = threading.Event()
        self.notas: list[str] = []
        try:
            import psutil  # noqa: F401
            self.psutil = True
        except ImportError:
            self.psutil = False
            self.notas.append("psutil no instalado: no se midio CPU/memoria de la API ni de la maquina")
        self._procs_api = None

    def _procesos_api(self):
        import psutil
        if self._procs_api is None:
            procs = []
            for p in psutil.process_iter(["cmdline"]):
                try:
                    cmd = " ".join(p.info["cmdline"] or [])
                except Exception:
                    continue
                if "uvicorn" in cmd and "app.main" in cmd:
                    procs.append(p)
            self._procs_api = procs
            if not procs:
                self.notas.append("no se encontro el proceso uvicorn de la API (psutil)")
        return self._procs_api

    def run(self):
        if self.psutil:
            import psutil
            psutil.cpu_percent(None)
            for p in self._procesos_api():
                try:
                    p.cpu_percent(None)
                except Exception:
                    pass
        cpu_gen_prev, t_prev = time.process_time(), time.perf_counter()
        while not self.detener.wait(self.intervalo):
            m = {"t": round(time.perf_counter() - self.t0, 1)}
            ahora_cpu, ahora_t = time.process_time(), time.perf_counter()
            # CPU del generador: % de UN nucleo (puede superar 100 si usa varios)
            m["generador_cpu_pct"] = round(100 * (ahora_cpu - cpu_gen_prev) / max(1e-6, ahora_t - t_prev), 1)
            cpu_gen_prev, t_prev = ahora_cpu, ahora_t
            if self.psutil:
                import psutil
                m["host_cpu_pct"] = psutil.cpu_percent(None)
                m["host_mem_pct"] = psutil.virtual_memory().percent
                cpu, rss = 0.0, 0.0
                for p in self._procesos_api():
                    try:
                        cpu += p.cpu_percent(None)
                        rss += p.memory_info().rss / 1048576
                    except Exception:
                        pass
                m["api_cpu_pct"] = round(cpu, 1)
                m["api_rss_mib"] = round(rss, 1)
            if self.usar_docker:
                try:
                    res = ejecutar(["docker", "stats", "--no-stream", "--format",
                                    "{{.Name}};{{.CPUPerc}};{{.MemUsage}}",
                                    self.cfg["CASSANDRA_CONTAINER"],
                                    self.cfg["REDIS_CONTAINER"]], timeout=30)
                    for linea in res.stdout.splitlines():
                        partes = linea.split(";")
                        if len(partes) != 3:
                            continue
                        nombre = "cassandra" if partes[0] == self.cfg["CASSANDRA_CONTAINER"] else "redis"
                        m[f"{nombre}_cpu_pct"] = float(partes[1].strip().rstrip("%") or 0)
                        m[f"{nombre}_mem_mib"] = _a_mib(partes[2].split("/")[0])
                except Exception as e:
                    self.notas.append(f"docker stats fallo en t={m['t']}: {e.__class__.__name__}")
            self.muestras.append(m)


def resumen_recursos(muestras: list[dict]) -> dict:
    res = {}
    if not muestras:
        return res
    claves = sorted({k for m in muestras for k in m if k != "t"})
    for k in claves:
        vals = [m[k] for m in muestras if m.get(k) is not None]
        if vals:
            res[k] = {"promedio": round(sum(vals) / len(vals), 1), "max": round(max(vals), 1),
                      "muestras": len(vals)}
    return res


# --------------------------------------------------------------------------
# 5. Trazabilidad
# --------------------------------------------------------------------------
def info_git() -> dict:
    def g(*args):
        try:
            r = ejecutar(["git", "-C", str(REPO), *args], timeout=15)
            return r.stdout.strip() if r.returncode == 0 else None
        except Exception:
            return None
    cambios = g("status", "--porcelain", "--", "api", "carga-optimizacion/scripts",
                "carga-optimizacion/config")
    return {"commit": g("rev-parse", "--short", "HEAD"),
            "rama": g("rev-parse", "--abbrev-ref", "HEAD"),
            "cambios_sin_commitear_en_codigo": bool(cambios)}


def info_entorno() -> dict:
    datos = {
        "sistema": platform.platform(),
        "procesador": platform.processor() or platform.machine(),
        "nucleos_logicos": os.cpu_count(),
        "python_generador": platform.python_version(),
    }
    try:
        import psutil
        datos["memoria_total_gib"] = round(psutil.virtual_memory().total / 1073741824, 1)
    except ImportError:
        datos["memoria_total_gib"] = "no medido (psutil no instalado)"
    return datos


def versiones_productos(cfg: dict) -> dict:
    """Version OBSERVADA de cada producto (no la etiqueta 'latest')."""
    v = {}
    try:
        salida = cqlsh(cfg, "SELECT release_version FROM system.local;")
        m = re.search(r"\b\d+\.\d+(\.\d+)?\S*", salida)
        v["cassandra"] = m.group(0) if m else salida.strip()[:60]
    except Exception as e:
        v["cassandra"] = f"no disponible ({e.__class__.__name__})"
    try:
        v["redis"] = info_redis(cfg).get("redis_version")
    except Exception as e:
        v["redis"] = f"no disponible ({e.__class__.__name__})"
    try:
        r = ejecutar(["docker", "version", "--format", "{{.Server.Version}}"], timeout=15)
        v["docker"] = r.stdout.strip()
    except Exception:
        v["docker"] = "no disponible"
    return v
