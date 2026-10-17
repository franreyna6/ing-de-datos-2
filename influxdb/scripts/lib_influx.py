#!/usr/bin/env python3
"""Utilidades compartidas por los scripts del Hito 8 (InfluxDB 3 Core).

Solo usa la biblioteca estandar de Python (3.8 o superior): no hay que
instalar nada en la maquina del integrante.

Contenido:
  - constantes del ambiente (host, puerto, contenedor, nombres de bases);
  - lectura del token local (variable de entorno o archivo fuera de Git);
  - Sesion: conexion HTTP persistente para escribir (line protocol) y
    consultar (SQL) contra la API de InfluxDB 3 Core;
  - un formateador de tablas para los logs.
"""
import http.client
import json
import os
import pathlib
import subprocess
import sys
import time

RAIZ = pathlib.Path(__file__).resolve().parent.parent

HOST = os.environ.get("INFLUX_HOST", "127.0.0.1")
PUERTO = int(os.environ.get("INFLUX_PORT", "8181"))
CONTENEDOR = os.environ.get("INFLUX_CONTENEDOR", "fixture2030-influxdb")

# Tres bases logicas (ver docs/retencion_y_granularidad.md):
DB_VIVO = "fixture2030_vivo"   # puntos originales, retencion acotada
DB_HIST = "fixture2030_hist"   # resumenes de 1 minuto, sin expiracion
DB_LAB = "fixture2030_lab"     # pruebas descartables (lotes, dato tardio, tipos)

# Precision de los timestamps: SEGUNDOS en todo el modulo (RF6 / RNF6).
PRECISION = "second"

ARCHIVO_TOKEN = RAIZ / ".influxdb3-token"   # ignorado por Git (.gitignore)


def leer_token():
    """Devuelve el token de administracion local.

    Orden de busqueda: variable INFLUXDB3_TOKEN, luego el archivo
    .influxdb3-token (creado por inicializacion.py y excluido del repo).
    El token nunca se imprime ni se versiona.
    """
    token = os.environ.get("INFLUXDB3_TOKEN", "").strip()
    if token:
        return token
    if ARCHIVO_TOKEN.exists():
        return ARCHIVO_TOKEN.read_text(encoding="utf-8").strip()
    sys.exit("No se encontro el token local. Ejecutar primero "
             "scripts/inicializacion.py (crea .influxdb3-token).")


class Sesion:
    """Conexion HTTP persistente (una por hilo) hacia InfluxDB 3 Core."""

    def __init__(self, token=None, host=HOST, puerto=PUERTO, timeout=300):
        self.token = token or leer_token()
        self.host = host
        self.puerto = puerto
        self.timeout = timeout
        self._conn = None

    def _conexion(self):
        if self._conn is None:
            self._conn = http.client.HTTPConnection(
                self.host, self.puerto, timeout=self.timeout)
        return self._conn

    def _cerrar(self):
        if self._conn is not None:
            try:
                self._conn.close()
            finally:
                self._conn = None

    def _pedir(self, metodo, ruta, cuerpo=None, cabeceras=None):
        cab = {"Authorization": "Bearer " + self.token}
        if cabeceras:
            cab.update(cabeceras)
        try:
            conn = self._conexion()
            conn.request(metodo, ruta, body=cuerpo, headers=cab)
            resp = conn.getresponse()
            datos = resp.read()
            return resp.status, datos.decode("utf-8", errors="replace")
        except (OSError, http.client.HTTPException):
            # La conexion persistente pudo cerrarse: se recrea y se propaga
            # el error para que quien llama decida si reintenta.
            self._cerrar()
            raise

    def escribir(self, db, cuerpo_lp, precision=PRECISION):
        """POST /api/v3/write_lp. Devuelve (status_http, texto_respuesta)."""
        ruta = "/api/v3/write_lp?db=%s&precision=%s" % (db, precision)
        if isinstance(cuerpo_lp, str):
            cuerpo_lp = cuerpo_lp.encode("utf-8")
        return self._pedir("POST", ruta, cuerpo_lp,
                           {"Content-Type": "text/plain; charset=utf-8"})

    def consultar(self, db, sql):
        """POST /api/v3/query_sql. Devuelve la lista de filas (dicts)."""
        cuerpo = json.dumps({"db": db, "q": sql, "format": "json"})
        estado, texto = self._pedir(
            "POST", "/api/v3/query_sql", cuerpo.encode("utf-8"),
            {"Content-Type": "application/json"})
        if estado != 200:
            raise RuntimeError("Consulta rechazada (HTTP %d): %s"
                               % (estado, texto[:400]))
        return json.loads(texto) if texto.strip() else []

    def estado_servidor(self):
        """GET /health. Devuelve el status HTTP (200 = listo; 401 tambien
        indica que el servidor responde pero exige token)."""
        estado, _ = self._pedir("GET", "/health")
        return estado


def esperar_servidor(segundos=90):
    """Espera hasta que el puerto HTTP responda (cualquier status)."""
    limite = time.time() + segundos
    while time.time() < limite:
        try:
            conn = http.client.HTTPConnection(HOST, PUERTO, timeout=3)
            conn.request("GET", "/ping")
            conn.getresponse().read()
            conn.close()
            return True
        except (OSError, http.client.HTTPException):
            time.sleep(1.5)
    return False


def tabla_texto(filas, max_filas=15):
    """Formatea una lista de dicts como tabla de texto para los logs."""
    if not filas:
        return "(sin filas)"
    columnas = list(filas[0].keys())
    vistas = filas[:max_filas]
    ancho = {c: max(len(str(c)), *(len(_fmt(f.get(c))) for f in vistas))
             for c in columnas}
    linea = " | ".join(str(c).ljust(ancho[c]) for c in columnas)
    sep = "-+-".join("-" * ancho[c] for c in columnas)
    cuerpo = [" | ".join(_fmt(f.get(c)).ljust(ancho[c]) for c in columnas)
              for f in vistas]
    pie = []
    if len(filas) > max_filas:
        pie.append("... (%d filas en total, se muestran %d)"
                   % (len(filas), max_filas))
    return "\n".join([linea, sep] + cuerpo + pie)


def _fmt(valor):
    if isinstance(valor, float):
        return "%.2f" % valor
    return "" if valor is None else str(valor)


CLAVES_NOTA = ("patron", "lectura", "semantica")


def leer_bloques(ruta_sql):
    """Lee un archivo .sql con bloques '-- ## id | titulo'.

    Devuelve una lista de dicts: id, titulo, notas (lineas '-- clave: texto'
    como lista de (clave, texto)) y sql (la sentencia sin comentarios).
    """
    bloques, actual = [], None
    for linea in pathlib.Path(ruta_sql).read_text(encoding="utf-8").splitlines():
        if linea.startswith("-- ##"):
            ident, _, titulo = linea[5:].partition("|")
            actual = {"id": ident.strip(), "titulo": titulo.strip(),
                      "notas": [], "sql": []}
            bloques.append(actual)
        elif actual is None:
            continue                      # cabecera general del archivo
        elif linea.startswith("--"):
            texto = linea[2:].strip()
            clave, separador, resto = texto.partition(":")
            if separador and clave.strip() in CLAVES_NOTA:
                actual["notas"].append([clave.strip(), resto.strip()])
            elif actual["notas"]:
                actual["notas"][-1][1] += " " + texto      # continuacion
            else:
                actual["notas"].append(["nota", texto])
        elif linea.strip():
            actual["sql"].append(linea)
    for b in bloques:
        b["sql"] = "\n".join(b["sql"]).strip().rstrip(";")
    return bloques


def ejecutar_bloques(ruta_sql, db, max_filas=15, solo=None):
    """Ejecuta cada bloque contra InfluxDB e imprime resultado y tiempo."""
    sesion = Sesion()
    fallos = 0
    for b in leer_bloques(ruta_sql):
        if solo and b["id"] not in solo:
            continue
        print("=" * 78)
        print("%s | %s" % (b["id"], b["titulo"]))
        for clave, texto in b["notas"]:
            print("  %s: %s" % (clave, texto))
        print("  SQL:")
        for linea in b["sql"].splitlines():
            print("    " + linea)
        t0 = time.time()
        try:
            filas = sesion.consultar(db, b["sql"])
        except Exception as exc:          # se registra y se sigue
            fallos += 1
            print("  RESULTADO: ERROR -> %s" % exc)
            continue
        ms = (time.time() - t0) * 1000
        print("  RESULTADO (%d filas, %.0f ms, 1 ejecucion, incluye red local):"
              % (len(filas), ms))
        print("\n".join("    " + l for l in tabla_texto(filas, max_filas).splitlines()))
    return fallos


def epoch_desde_iso(texto):
    """Convierte '2030-06-13T09:00:00[.fff][Z]' o '2030-06-13 09:00:00' en
    segundos desde epoch (UTC). Solo se usan los primeros 19 caracteres."""
    import calendar
    import time as _t
    base = str(texto)[:19].replace("T", " ")
    return calendar.timegm(_t.strptime(base, "%Y-%m-%d %H:%M:%S"))


def ejecutar(cmd, entorno=None, ok_si_falla=False):
    """Ejecuta un comando local (docker, docker compose) y devuelve el
    resultado. Si falla y no se tolera, termina el script con el detalle."""
    r = subprocess.run(cmd, cwd=str(RAIZ), env=entorno, capture_output=True,
                       text=True)
    if r.returncode != 0 and not ok_si_falla:
        sys.exit("Fallo: %s\n%s%s" % (" ".join(cmd[:6]), r.stdout, r.stderr))
    return r


def influxdb3(args, token=None, ok_si_falla=False):
    """Ejecuta el CLI influxdb3 DENTRO del contenedor. El token viaja por la
    variable de entorno INFLUXDB3_AUTH_TOKEN (no por la linea de comandos)."""
    entorno = dict(os.environ)
    cmd = ["docker", "exec"]
    if token:
        entorno["INFLUXDB3_AUTH_TOKEN"] = token
        cmd += ["-e", "INFLUXDB3_AUTH_TOKEN"]
    cmd += [CONTENEDOR, "influxdb3"] + args
    return ejecutar(cmd, entorno, ok_si_falla)
