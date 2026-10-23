#!/usr/bin/env python3
"""Capas 4 a 8 - Protocolo, autenticacion, autorizacion, contexto y lectura minima
con el cliente o driver adecuado de cada producto (RF6 a RF14, RNF4).

Dos origenes por producto, para no confundir entornos (RNF3):
  * driver  -> desde la notebook, con el MISMO driver y la MISMA configuracion
               que usa la API del Hito 10 (pymongo, neo4j, cassandra-driver,
               redis-py, HTTP v3 de InfluxDB, intersystems-irispython);
  * cli     -> el cliente nativo dentro del contenedor (mongosh, cypher-shell,
               cqlsh, redis-cli, influxdb3, iris session). Dentro del contenedor
               "localhost" es el propio servidor: prueba el producto, no la ruta
               que usa la API.

El handshake de protocolo de Neo4j (Bolt), Cassandra (CQL) y Redis (RESP) se
hace con bytes del propio protocolo, sin driver: un puerto abierto no prueba que
el protocolo sea el correcto (nota 7).

Casos negativos (credencial invalida, database/keyspace/namespace inexistente,
recurso inexistente, consulta invalida): se marcan con extra.caso = "negativo".
Su resultado es OK cuando el producto responde con el error ESPERADO y
distinguible; no cuentan para el estado de salud de la dependencia.

Todas las operaciones son de lectura, ping o retorno constante (RNF6): no se
escribe, borra ni modifica ningun dato del dominio.

Uso: python prueba_clientes_nativos.py [--producto mongodb,redis] [--solo driver|cli]
"""
from __future__ import annotations

import argparse
import json
import struct
from urllib.parse import quote, urlparse, urlunparse

from lib_conectividad import (FALLA, INFO, OK, PRODUCTOS, SKIP, Config, Resultado,
                              describir_excepcion, docker_disponible, docker_exec,
                              encabezado_corrida, estado_contenedor, guardar_resultados, http,
                              imprimir, intercambio_crudo, medir, registrar_secretos)

NEG = {"caso": "negativo"}


def _r(producto, capa, prueba, resultado, detalle, **kw) -> Resultado:
    return imprimir(Resultado(producto, capa, prueba, resultado, detalle, **kw))


def _sin_driver(producto: str, paquete: str, e: Exception) -> list[Resultado]:
    return [_r(producto, "protocolo", f"Pruebas con driver ({paquete})", SKIP,
               f"driver no disponible en este Python ({e.__class__.__name__}); "
               "no significa que el producto este caido", cliente=paquete)]


def _cli_disponible(cfg: Config, producto: str, contenedor: str) -> Resultado | None:
    ok, info = docker_disponible()
    if not ok:
        return _r(producto, "protocolo", "Cliente nativo en el contenedor", SKIP,
                  f"Docker no disponible: {info}")
    estado = estado_contenedor(contenedor)
    if estado != "running":
        return _r(producto, "protocolo", "Cliente nativo en el contenedor", SKIP,
                  f"contenedor {contenedor} en estado '{estado}': no se puede usar su CLI",
                  objetivo=contenedor)
    return None


def _uri_con_password(uri: str, nueva: str) -> str:
    u = urlparse(uri)
    if not u.password:
        return uri
    netloc = f"{u.username}:{quote(nueva)}@{u.hostname}" + (f":{u.port}" if u.port else "")
    return urlunparse(u._replace(netloc=netloc))


# ===========================================================================
# MongoDB (RF9)
# ===========================================================================
def mongodb_driver(cfg: Config) -> list[Resultado]:
    try:
        from pymongo import MongoClient
        from pymongo.errors import OperationFailure
    except Exception as e:  # noqa: BLE001
        return _sin_driver("mongodb", "pymongo", e)
    res, P, cli = [], "mongodb", "pymongo"
    ms = int(cfg.timeout * 1000)
    opts = dict(serverSelectionTimeoutMS=ms, connectTimeoutMS=ms, socketTimeoutMS=ms)
    uri = cfg["MONGODB_URI"]
    if not uri:
        return [_r(P, "autenticacion", "Pruebas con driver", SKIP, "MONGODB_URI no configurada")]
    u = urlparse(uri)
    base = f"mongodb://{u.hostname}:{u.port or 27017}"
    db_name, equipo = cfg["MONGODB_DATABASE"], cfg["PRUEBA_EQUIPO"]

    # Protocolo: 'hello' no requiere autenticacion.
    c = MongoClient(base, **opts)
    v, e, t = medir(c.admin.command, "hello")
    res.append(_r(P, "protocolo", "Handshake del Wire Protocol (comando hello, sin credencial)",
                  OK if v else FALLA,
                  f"maxWireVersion={v.get('maxWireVersion')} primario={v.get('isWritablePrimary')}"
                  if v else describir_excepcion(e), objetivo=base, cliente=cli, duracion_ms=t,
                  responde="El listener habla el protocolo de MongoDB?",
                  no_permite="Que la credencial sea valida ni que exista la database."))
    c.close()
    if not v:
        return res

    # Autenticacion con la identidad configurada.
    c = MongoClient(uri, **opts)
    v, e, t = medir(c.admin.command, "connectionStatus")
    usuarios = [f"{x['user']}@{x['db']}" for x in (v or {}).get("authInfo", {}).get(
        "authenticatedUsers", [])]
    res.append(_r(P, "autenticacion", "Identidad configurada autentica (connectionStatus)",
                  OK if usuarios else FALLA,
                  f"autenticado como {', '.join(usuarios)}" if usuarios else
                  (describir_excepcion(e) if e else "conexion sin usuario autenticado"),
                  objetivo=f"{base} authSource={u.query or 'admin'}", cliente=cli, duracion_ms=t,
                  responde="La identidad de MONGODB_URI es aceptada?",
                  no_permite="Que tenga permiso sobre la database del Fixture."))

    # Negativo: credencial invalida en el entorno local de prueba.
    cmal = MongoClient(_uri_con_password(uri, "credencial-invalida-h11"), **opts)
    v2, e2, t2 = medir(cmal.admin.command, "connectionStatus")
    codigo = getattr(e2, "code", None)
    res.append(_r(P, "autenticacion", "[negativo] Password invalida",
                  OK if codigo == 18 else FALLA,
                  f"rechazada: {describir_excepcion(e2)} (code {codigo})" if e2 else
                  "ACEPTADA: la base no exige autenticacion", cliente=cli, duracion_ms=t2,
                  esperado="OperationFailure code 18 AuthenticationFailed", extra=NEG,
                  responde="Se distingue credencial invalida de servidor caido?"))
    cmal.close()

    # Autorizacion + contexto: listar colecciones de la database configurada.
    v, e, t = medir(c[db_name].list_collection_names)
    faltan = [x for x in ("equipos", "jugadores") if v is not None and x not in v]
    res.append(_r(P, "autorizacion", f"Permiso de lectura de catalogo en '{db_name}'",
                  OK if v is not None else FALLA,
                  f"colecciones: {', '.join(sorted(v))}" if v is not None else describir_excepcion(e),
                  objetivo=db_name, cliente=cli, duracion_ms=t,
                  responde="La identidad autenticada puede operar en la database?",
                  no_permite="Que los documentos de prueba existan."))
    dbs, e3, t3 = medir(c.list_database_names)
    existe = dbs is not None and db_name in dbs
    res.append(_r(P, "contexto", f"Database '{db_name}' existe con las colecciones del modulo",
                  OK if existe and not faltan else FALLA,
                  (f"database presente; faltan colecciones {faltan}" if faltan else
                   "database y colecciones equipos/jugadores presentes") if existe else
                  (f"'{db_name}' NO figura en el catalogo" if dbs is not None else
                   describir_excepcion(e3)), objetivo=db_name, cliente=cli, duracion_ms=t3,
                  responde="El contexto configurado es el que tiene los datos del Hito 4?",
                  no_permite="-"))
    inexistente = db_name + "_inexistente_h11"
    v4, e4, t4 = medir(c[inexistente].equipos.find_one, {})
    res.append(_r(P, "contexto", "[negativo] Database inexistente",
                  OK if (v4 is None and e4 is None and dbs is not None and inexistente not in dbs)
                  else FALLA,
                  "MongoDB NO devuelve error: la lectura vuelve vacia (None). Solo el catalogo "
                  "(listDatabases) revela que la database no existe" if e4 is None else
                  describir_excepcion(e4), objetivo=inexistente, cliente=cli, duracion_ms=t4,
                  esperado="lectura vacia sin error (MongoDB crea las databases en forma perezosa)",
                  extra=NEG,
                  responde="Un contexto mal escrito produce error o un silencioso 'no encontrado'?"))

    # Lectura minima: un equipo por su codigo de negocio y el plantel acotado.
    col = c[db_name].equipos
    v, e, t = medir(col.find_one, {"codigo": equipo},
                    {"_id": 0, "codigo": 1, "nombre": 1, "confederacion": 1})
    res.append(_r(P, "lectura", f"Lectura de equipo por codigo de negocio {{codigo: '{equipo}'}}",
                  OK if v else FALLA, json.dumps(v, ensure_ascii=False) if v else
                  (describir_excepcion(e) if e else "documento no encontrado"),
                  objetivo=f"{db_name}.equipos", cliente=cli, duracion_ms=t,
                  responde="El cliente puede leer el documento del modulo?", no_permite="-"))
    n, e, t = medir(c[db_name].jugadores.count_documents, {"equipoCodigo": equipo}, limit=100)
    res.append(_r(P, "lectura", f"Conteo acotado de jugadores {{equipoCodigo: '{equipo}'}} (limit 100)",
                  OK if n else FALLA, f"{n} jugadores" if n is not None else describir_excepcion(e),
                  objetivo=f"{db_name}.jugadores", cliente=cli, duracion_ms=t))
    # La MISMA consulta que hace el adaptador de la API (busca por _id).
    v, e, t = medir(col.find_one, {"_id": equipo}, {"_id": 1})
    res.append(_r(P, "lectura", f"Consulta identica al adaptador de la API {{_id: '{equipo}'}}",
                  OK if v else FALLA,
                  "documento encontrado" if v else
                  ("sin resultados: en los datos del Hito 4 el _id es un ObjectId y el codigo FIFA "
                   "esta en el campo 'codigo'. El cliente nativo funciona, pero la API respondera "
                   "404 para un equipo que existe" if e is None else describir_excepcion(e)),
                  objetivo=f"{db_name}.equipos", cliente=cli, duracion_ms=t,
                  esperado="encontrar el equipo",
                  responde="La operacion que ejecuta la API coincide con el modelo cargado?",
                  extra={"hallazgo": "H1", "compatibilidad_api": True}))
    v, e, t = medir(col.find_one, {"codigo": "ZZZ"})
    res.append(_r(P, "lectura", "[negativo] Documento inexistente {codigo: 'ZZZ'}",
                  OK if v is None and e is None else FALLA,
                  "None (ausencia valida: la base respondio)" if e is None else describir_excepcion(e),
                  objetivo=f"{db_name}.equipos", cliente=cli, duracion_ms=t,
                  esperado="None sin error", extra=NEG))
    c.close()
    return res


def mongodb_cli(cfg: Config) -> list[Resultado]:
    cont = cfg["MONGO_CONTAINER"]
    skip = _cli_disponible(cfg, "mongodb", cont)
    if skip:
        return [skip]
    u = urlparse(cfg["MONGODB_URI"])
    js = ("const c = connect('mongodb://' + encodeURIComponent(process.env.H11_U) + ':' + "
          "encodeURIComponent(process.env.H11_P) + '@localhost:27017/' + process.env.H11_DB + "
          "'?authSource=admin&serverSelectionTimeoutMS=3000');"
          "const e = c.equipos.findOne({codigo: process.env.H11_EQ}, {_id: 0, codigo: 1, nombre: 1});"
          "print(JSON.stringify({ping: c.runCommand({ping: 1}).ok, version: c.version(), "
          "db: c.getName(), equipos: c.equipos.estimatedDocumentCount(), equipo: e}));")
    env = {"H11_U": u.username or "", "H11_P": u.password or "",
           "H11_DB": cfg["MONGODB_DATABASE"], "H11_EQ": cfg["PRUEBA_EQUIPO"]}
    (rc, out, err), _, t = medir(docker_exec, cont, ["mongosh", "--quiet", "--nodb", "--eval", js],
                                 timeout=cfg.timeout + 20, env=env)
    linea = (out.strip().splitlines() or [""])[-1]
    return [_r("mongodb", "lectura",
               "mongosh: ping + database + lectura de un equipo (dentro del contenedor)",
               OK if rc == 0 and '"ping":1' in linea else FALLA,
               linea if rc == 0 else (err or out).strip()[:300], origen=f"contenedor {cont}",
               objetivo=f"localhost:27017 (interno) / {cfg['MONGODB_DATABASE']}",
               cliente="mongosh", duracion_ms=t,
               responde="El producto funciona visto desde su propio contenedor?",
               no_permite="Que la notebook (donde corre la API) llegue al puerto publicado.")]


# ===========================================================================
# Neo4j (RF10)
# ===========================================================================
def neo4j_http(cfg: Config) -> list[Resultado]:
    url = cfg["NEO4J_HTTP_URL"].rstrip("/") + "/"
    v, e, t = medir(http, "GET", url, cfg.timeout, {"Accept": "application/json"})
    st, _, cuerpo, err = v
    try:
        info = json.loads(cuerpo or b"{}")
    except ValueError:
        info = {}
    detalle = (f"HTTP {st}: neo4j_version={info.get('neo4j_version')} "
               f"edition={info.get('neo4j_edition')} bolt_direct={info.get('bolt_direct')}"
               if st else err)
    return [_r("neo4j", "protocolo", "Portal HTTP (Neo4j Browser / discovery)",
               OK if st == 200 else FALLA, detalle, objetivo=url, cliente="HTTP GET", duracion_ms=t,
               responde="El servidor web de Neo4j responde?",
               no_permite="Nada sobre Bolt, que es lo que usa la API: el portal puede estar arriba "
                          "y Bolt no (o al reves).")]


def neo4j_bolt_handshake(cfg: Config) -> list[Resultado]:
    u = urlparse(cfg["NEO4J_URI"])
    host, puerto = u.hostname, u.port or 7687
    # magic + 4 propuestas: 5.8..5.0 (rango), 4.4, 4.3, 3.0
    propuesta = bytes.fromhex("6060B017") + bytes.fromhex("00080805" "00000404" "00000304" "00000003")
    v, e, t = medir(intercambio_crudo, host, puerto, propuesta, cfg.timeout)
    if v and len(v) >= 4 and v[:4] != b"\x00\x00\x00\x00":
        detalle, res = f"servidor acepto Bolt {v[3]}.{v[2]}", OK
    elif v is not None:
        detalle, res = f"respuesta {v[:8]!r}: no es un servidor Bolt o no acepto ninguna version", FALLA
    else:
        detalle, res = describir_excepcion(e), FALLA
    return [_r("neo4j", "protocolo", "Handshake Bolt (bytes del protocolo, sin driver)", res, detalle,
               objetivo=f"{host}:{puerto}", cliente="socket (magic 0x6060B017)", duracion_ms=t,
               responde="El puerto que usa la API habla Bolt y acepta una version compatible?",
               no_permite="Que la credencial ni la database sean validas.")]


def neo4j_driver(cfg: Config) -> list[Resultado]:
    try:
        from neo4j import GraphDatabase
    except Exception as e:  # noqa: BLE001
        return _sin_driver("neo4j", "neo4j", e)
    P, cli, res = "neo4j", "neo4j (driver Bolt)", []
    uri, usr, pwd, dbn = (cfg["NEO4J_URI"], cfg["NEO4J_USER"], cfg["NEO4J_PASSWORD"],
                          cfg["NEO4J_DATABASE"])
    drv = GraphDatabase.driver(uri, auth=(usr, pwd), connection_timeout=cfg.timeout,
                               connection_acquisition_timeout=cfg.timeout)
    v, e, t = medir(drv.verify_authentication)
    res.append(_r(P, "autenticacion", f"Identidad '{usr}' autentica por Bolt",
                  OK if v else FALLA, "autenticacion aceptada" if v else describir_excepcion(e),
                  objetivo=uri, cliente=cli, duracion_ms=t,
                  responde="El usuario y la password configurados son aceptados?",
                  no_permite="Que la database configurada exista."))
    if not v:
        drv.close()
        return res
    res.append(_r(P, "autorizacion", "Permisos del usuario autenticado", INFO,
                  "Neo4j Community no tiene control de acceso por roles: un usuario autenticado "
                  "puede leer todas las databases. La autorizacion no se puede separar de la "
                  "autenticacion en esta edicion", cliente=cli))

    def _sesion(db, q, **p):
        with drv.session(database=db) as s:
            return s.run(q, **p).data()

    v, e, t = medir(_sesion, "system", "SHOW DATABASE $n YIELD name, currentStatus", n=dbn)
    est = v[0]["currentStatus"] if v else None
    res.append(_r(P, "contexto", f"Database '{dbn}' existe y esta online",
                  OK if est == "online" else FALLA,
                  f"currentStatus={est}" if v else (describir_excepcion(e) if e else
                                                   "la database no figura en el catalogo"),
                  objetivo=dbn, cliente=cli, duracion_ms=t, no_permite="Que contenga los datos del Hito 5."))
    v, e, t = medir(_sesion, "neo4j_inexistente_h11", "RETURN 1 AS ok")
    res.append(_r(P, "contexto", "[negativo] Database inexistente",
                  OK if e is not None and "DatabaseNotFound" in str(getattr(e, "code", e)) else FALLA,
                  f"error esperado: {getattr(e, 'code', '')}" if e else "NO fallo",
                  objetivo="neo4j_inexistente_h11", cliente=cli, duracion_ms=t,
                  esperado="Neo.ClientError.Database.DatabaseNotFound", extra=NEG))
    q = ("MATCH (p:Partido {codigo: $codigo}) "
         "OPTIONAL MATCH (e:Evento)-[:OCURRE_EN]->(p) "
         "RETURN p.codigo AS partido, toString(p.fecha) AS fecha, count(e) AS eventos LIMIT 1")
    partido = cfg["PRUEBA_PARTIDO"]
    v, e, t = medir(_sesion, dbn, q, codigo=partido)
    res.append(_r(P, "lectura", f"Lectura Cypher parametrizada y acotada (partido {partido})",
                  OK if v else FALLA, json.dumps(v[0]) if v else
                  (describir_excepcion(e) if e else "sin filas"),
                  objetivo=f"{dbn} / (:Partido)<-[:OCURRE_EN]-(:Evento)", cliente=cli, duracion_ms=t,
                  responde="El cliente puede recorrer el grafo del Hito 5?", no_permite="-"))
    inex = cfg["PRUEBA_PARTIDO_INEXISTENTE"]
    v, e, t = medir(_sesion, dbn, q, codigo=inex)
    res.append(_r(P, "lectura", f"[negativo] Partido inexistente ({inex})",
                  OK if v == [] else FALLA,
                  "0 filas y sin error: la base respondio; la API lo traduce a 404" if v == [] else
                  (describir_excepcion(e) if e else json.dumps(v)), cliente=cli, duracion_ms=t,
                  esperado="lista vacia sin error", extra=NEG))
    v, e, t = medir(_sesion, dbn, "MATCH (p:Partido) WHERE NOT (:Evento)-[:OCURRE_EN]->(p) "
                                  "RETURN p.codigo AS partido LIMIT 1")
    res.append(_r(P, "lectura", "[negativo] Partido existente sin eventos (resultado vacio valido)",
                  OK if v is not None else FALLA,
                  (f"{v[0]['partido']} existe y tiene 0 eventos: la API debe responder 200 con "
                   "lista vacia, no 404" if v else "todos los partidos tienen eventos") if v is not None
                  else describir_excepcion(e), cliente=cli, duracion_ms=t, extra=NEG))
    drv.close()

    # Negativo: password invalida (un solo intento para no disparar el bloqueo por intentos).
    # verify_authentication() devuelve False (no lanza) ante credencial invalida; para
    # registrar el codigo de error del servidor se ejecuta una lectura constante.
    dmal = GraphDatabase.driver(uri, auth=(usr, "credencial-invalida-h11"),
                                connection_timeout=cfg.timeout)
    v, e, t = medir(dmal.execute_query, "RETURN 1 AS ok", database_=dbn)
    dmal.close()
    res.append(_r(P, "autenticacion", "[negativo] Password invalida",
                  OK if e is not None and "Unauthorized" in str(getattr(e, "code", e)) else FALLA,
                  f"rechazada: {getattr(e, 'code', describir_excepcion(e))}" if e else "ACEPTADA",
                  cliente=cli, duracion_ms=t, esperado="Neo.ClientError.Security.Unauthorized",
                  extra=NEG))
    # Negativo: error de conexion (puerto sin listener) para distinguirlo de los anteriores.
    u = urlparse(uri)
    dcaido = GraphDatabase.driver(f"bolt://{u.hostname}:7688", auth=(usr, pwd),
                                  connection_timeout=cfg.timeout)
    v, e, t = medir(dcaido.verify_connectivity)
    dcaido.close()
    res.append(_r(P, "tcp", "[negativo] Error de conexion (puerto Bolt sin listener)",
                  OK if e is not None else FALLA,
                  describir_excepcion(e) if e else "conecto (inesperado)",
                  objetivo=f"{u.hostname}:7688", cliente=cli, duracion_ms=t,
                  esperado="ServiceUnavailable", extra=NEG))
    return res


def neo4j_cli(cfg: Config) -> list[Resultado]:
    cont = cfg["NEO4J_CONTAINER"]
    skip = _cli_disponible(cfg, "neo4j", cont)
    if skip:
        return [skip]
    q = ("MATCH (p:Partido {codigo: $codigo}) OPTIONAL MATCH (e:Evento)-[:OCURRE_EN]->(p) "
         "RETURN p.codigo AS partido, count(e) AS eventos LIMIT 1")
    env = {"NEO4J_USERNAME": cfg["NEO4J_USER"], "NEO4J_PASSWORD": cfg["NEO4J_PASSWORD"]}
    cmd = ["cypher-shell", "-a", "bolt://localhost:7687", "-d", cfg["NEO4J_DATABASE"],
           "--format", "plain", "-P", f"{{codigo: '{cfg['PRUEBA_PARTIDO']}'}}", q]
    (rc, out, err), _, t = medir(docker_exec, cont, cmd, timeout=cfg.timeout + 25, env=env)
    return [_r("neo4j", "lectura", "cypher-shell: lectura parametrizada (dentro del contenedor)",
               OK if rc == 0 and cfg["PRUEBA_PARTIDO"] in out else FALLA,
               " | ".join(out.strip().splitlines()) if rc == 0 else (err or out).strip()[:300],
               origen=f"contenedor {cont}", objetivo="bolt://localhost:7687 (interno)",
               cliente="cypher-shell", duracion_ms=t,
               no_permite="Que la notebook llegue al puerto Bolt publicado.")]


# ===========================================================================
# Cassandra (RF11)
# ===========================================================================
def _frame_cql(opcode: int, cuerpo: bytes = b"", version: int = 4) -> bytes:
    return struct.pack(">BBhBi", version, 0, 1, opcode, len(cuerpo)) + cuerpo


def _string_map(d: dict) -> bytes:
    b = struct.pack(">H", len(d))
    for k, v in d.items():
        for s in (k, v):
            s = s.encode()
            b += struct.pack(">H", len(s)) + s
    return b


def _leer_multimap(cuerpo: bytes) -> dict:
    n, = struct.unpack(">H", cuerpo[:2])
    i, res = 2, {}
    for _ in range(n):
        lk, = struct.unpack(">H", cuerpo[i:i + 2]); i += 2
        k = cuerpo[i:i + lk].decode(); i += lk
        nl, = struct.unpack(">H", cuerpo[i:i + 2]); i += 2
        vals = []
        for _ in range(nl):
            lv, = struct.unpack(">H", cuerpo[i:i + 2]); i += 2
            vals.append(cuerpo[i:i + lv].decode()); i += lv
        res[k] = vals
    return res


def _cql_crudo(host: str, puerto: int, frame: bytes, timeout: float) -> tuple[int, bytes]:
    import socket
    with socket.create_connection((host, puerto), timeout=timeout) as s:
        s.settimeout(timeout)
        s.sendall(frame)
        cab = b""
        while len(cab) < 9:
            parte = s.recv(9 - len(cab))
            if not parte:
                raise ConnectionError("conexion cerrada por el servidor")
            cab += parte
        _, _, _, opcode, largo = struct.unpack(">BBhBi", cab)
        cuerpo = b""
        while len(cuerpo) < largo:
            parte = s.recv(largo - len(cuerpo))
            if not parte:
                break
            cuerpo += parte
        return opcode, cuerpo


def cassandra_protocolo(cfg: Config) -> list[Resultado]:
    P, h, p = "cassandra", cfg["CASSANDRA_HOST"], int(cfg["CASSANDRA_PORT"])
    res = []
    v, e, t = medir(_cql_crudo, h, p, _frame_cql(0x05), cfg.timeout)  # OPTIONS
    if v and v[0] == 0x06:  # SUPPORTED
        mm = _leer_multimap(v[1])
        detalle = (f"SUPPORTED: CQL_VERSION={mm.get('CQL_VERSION')} "
                   f"PROTOCOL_VERSIONS={mm.get('PROTOCOL_VERSIONS')}")
        ok = OK
    else:
        detalle, ok = (f"opcode inesperado 0x{v[0]:02x}" if v else describir_excepcion(e)), FALLA
    res.append(_r(P, "protocolo", "Handshake CQL: frame OPTIONS -> SUPPORTED (sin driver)", ok, detalle,
                  objetivo=f"{h}:{p}", cliente="socket (frame CQL v4)", duracion_ms=t,
                  responde="El puerto 9042 habla el protocolo binario de CQL?",
                  no_permite="Que el keyspace exista."))
    if ok != OK:
        return res
    v, e, t = medir(_cql_crudo, h, p, _frame_cql(0x01, _string_map({"CQL_VERSION": "3.0.0"})),
                    cfg.timeout)  # STARTUP
    if v and v[0] == 0x02:
        detalle = ("READY: el servidor NO exige autenticacion (AllowAllAuthenticator del "
                   "laboratorio); no hay identidad que validar")
        ok = OK
    elif v and v[0] == 0x03:
        detalle, ok = "AUTHENTICATE: el servidor exige credenciales (la API no las envia)", FALLA
    else:
        detalle, ok = (f"opcode 0x{v[0]:02x}" if v else describir_excepcion(e)), FALLA
    res.append(_r(P, "autenticacion", "Frame STARTUP: el servidor exige autenticacion?", ok, detalle,
                  objetivo=f"{h}:{p}", cliente="socket (frame CQL v4)", duracion_ms=t,
                  responde="Hace falta una identidad para abrir sesion?",
                  no_permite="En produccion, la ausencia de autenticacion seria un riesgo, no un OK."))
    return res


def cassandra_driver(cfg: Config) -> list[Resultado]:
    try:
        from cassandra.cluster import Cluster
        from cassandra import InvalidRequest
    except Exception as e:  # noqa: BLE001
        return _sin_driver("cassandra", "cassandra-driver", e)
    import datetime as dt
    P, cli, res = "cassandra", "cassandra-driver", []
    h, p, ks = cfg["CASSANDRA_HOST"], int(cfg["CASSANDRA_PORT"]), cfg["CASSANDRA_KEYSPACE"]
    cl = Cluster([h], port=p, connect_timeout=cfg.timeout, control_connection_timeout=cfg.timeout)
    ses, e, t = medir(cl.connect)
    if ses is None:
        res.append(_r(P, "autenticacion", "Sesion con el driver", FALLA, describir_excepcion(e),
                      objetivo=f"{h}:{p}", cliente=cli, duracion_ms=t))
        cl.shutdown()
        return res
    ses.default_timeout = cfg.timeout
    fila = ses.execute("SELECT release_version, cluster_name FROM system.local").one()
    res.append(_r(P, "autenticacion", "Sesion abierta con el driver de la API", OK,
                  f"Cassandra {fila.release_version}, cluster '{fila.cluster_name}'",
                  objetivo=f"{h}:{p}", cliente=cli, duracion_ms=t))
    res.append(_r(P, "autorizacion", "Permisos sobre el keyspace", INFO,
                  "sin autenticacion no hay autorizacion por rol (AllowAllAuthorizer): cualquier "
                  "cliente que llegue al puerto puede leer y escribir", cliente=cli))

    v, e, t = medir(lambda: ses.execute(
        "SELECT keyspace_name, replication FROM system_schema.keyspaces WHERE keyspace_name = %s",
        (ks,)).one())
    res.append(_r(P, "contexto", f"Keyspace '{ks}' existe", OK if v else FALLA,
                  f"replicacion={dict(v.replication)}" if v else
                  (describir_excepcion(e) if e else "el keyspace no existe"),
                  objetivo=ks, cliente=cli, duracion_ms=t))
    v, e, t = medir(lambda: list(ses.execute(
        "SELECT column_name, kind, position FROM system_schema.columns "
        "WHERE keyspace_name = %s AND table_name = 'comentarios_por_partido'", (ks,))))
    if v:
        pk = [c.column_name for c in sorted(v, key=lambda c: c.position) if c.kind == "partition_key"]
        ck = [c.column_name for c in sorted(v, key=lambda c: c.position) if c.kind == "clustering"]
        det, ok = f"PRIMARY KEY (({', '.join(pk)}), {', '.join(ck)})", OK
    else:
        det, ok = (describir_excepcion(e) if e else "la tabla no existe"), FALLA
    res.append(_r(P, "contexto", "Tabla comentarios_por_partido y patron de particion", ok, det,
                  objetivo=f"{ks}.comentarios_por_partido", cliente=cli, duracion_ms=t,
                  responde="La tabla que lee la API existe con la clave (partido_id, ventana)?"))

    partido = cfg["PRUEBA_CASSANDRA_PARTIDO"]
    inst = dt.datetime.fromisoformat(cfg["PRUEBA_CASSANDRA_INSTANTE"].replace("Z", "+00:00"))
    ventana = inst.replace(minute=(inst.minute // 5) * 5, second=0, microsecond=0)
    ps, e, _ = medir(ses.prepare, f"SELECT creado_en, usuario_id, estado FROM {ks}.comentarios_por_partido "
                                  "WHERE partido_id = ? AND ventana = ? LIMIT 5")
    if ps is not None:
        v, e, t = medir(lambda: list(ses.execute(ps, (partido, ventana))))
        res.append(_r(P, "lectura", f"Lectura limitada de UNA particion ({partido}, {ventana:%Y-%m-%d %H:%M}Z) LIMIT 5",
                      OK if v else FALLA, f"{len(v)} filas" if v is not None else describir_excepcion(e),
                      objetivo=f"{ks}.comentarios_por_partido", cliente=cli, duracion_ms=t,
                      responde="El cliente puede leer la particion que pide la API?", no_permite="-"))
        v, e, t = medir(lambda: list(ses.execute(ps, (partido, ventana.replace(year=2029)))))
        res.append(_r(P, "lectura", "[negativo] Particion sin datos (ventana de 2029)",
                      OK if v == [] else FALLA, "0 filas sin error: respuesta vacia valida"
                      if v == [] else describir_excepcion(e), cliente=cli, duracion_ms=t, extra=NEG))
    v, e, t = medir(lambda: ses.execute("SELECT * FROM comentarios_por_partido LIMIT 1"))
    res.append(_r(P, "contexto", "[negativo] Sesion sin keyspace seleccionado (tabla sin calificar)",
                  OK if isinstance(e, InvalidRequest) else FALLA,
                  describir_excepcion(e) if e else "NO fallo", cliente=cli, duracion_ms=t,
                  esperado="InvalidRequest: No keyspace has been specified", extra=NEG))
    v, e, t = medir(ses.set_keyspace, ks + "_inexistente_h11")
    res.append(_r(P, "contexto", "[negativo] Keyspace inexistente",
                  OK if e is not None else FALLA, describir_excepcion(e) if e else "NO fallo",
                  objetivo=ks + "_inexistente_h11", cliente=cli, duracion_ms=t,
                  esperado="InvalidRequest: keyspace does not exist", extra=NEG))
    v, e, t = medir(lambda: ses.execute(f"SELECT * FROM {ks}.tabla_inexistente_h11 LIMIT 1"))
    res.append(_r(P, "contexto", "[negativo] Tabla inexistente", OK if isinstance(e, InvalidRequest) else FALLA,
                  describir_excepcion(e) if e else "NO fallo", cliente=cli, duracion_ms=t,
                  esperado="InvalidRequest: unconfigured table", extra=NEG))
    v, e, t = medir(lambda: ses.execute(
        f"SELECT * FROM {ks}.comentarios_por_partido WHERE usuario_id = 'DEMO01' LIMIT 1"))
    res.append(_r(P, "lectura", "[negativo] Consulta invalida (filtro fuera de la clave, sin ALLOW FILTERING)",
                  OK if isinstance(e, InvalidRequest) else FALLA,
                  describir_excepcion(e) if e else "NO fallo", cliente=cli, duracion_ms=t,
                  esperado="InvalidRequest inmediato (la red funciona; el error es de la consulta)",
                  extra=NEG))
    cl.shutdown()
    # Contraste: timeout de CONEXION (direccion sin respuesta) vs la consulta invalida de arriba.
    cl2 = Cluster(["10.255.255.1"], port=p, connect_timeout=cfg.timeout,
                  control_connection_timeout=cfg.timeout)
    v, e, t = medir(cl2.connect)
    cl2.shutdown()
    res.append(_r(P, "tcp", "[negativo] Timeout de conexion (direccion sin respuesta)",
                  OK if e is not None else FALLA, describir_excepcion(e) if e else "conecto",
                  objetivo=f"10.255.255.1:{p}", cliente=cli, duracion_ms=t,
                  esperado="NoHostAvailable tras ~timeout (distinto del InvalidRequest inmediato)",
                  extra=NEG))
    return res


def cassandra_cli(cfg: Config) -> list[Resultado]:
    cont = cfg["CASSANDRA_CONTAINER"]
    skip = _cli_disponible(cfg, "cassandra", cont)
    if skip:
        return [skip]
    cql = (f"SELECT partido_id, ventana, creado_en FROM comentarios_por_partido "
           f"WHERE partido_id = '{cfg['PRUEBA_CASSANDRA_PARTIDO']}' "
           f"AND ventana = '2030-06-22 20:00:00+0000' LIMIT 3")
    (rc, out, err), _, t = medir(docker_exec, cont, ["cqlsh", "-k", cfg["CASSANDRA_KEYSPACE"],
                                                     "-e", cql], timeout=cfg.timeout + 30)
    filas = [x for x in out.splitlines() if "rows)" in x]
    return [_r("cassandra", "lectura", "cqlsh: lectura limitada de una particion (dentro del contenedor)",
               OK if rc == 0 and filas else FALLA,
               filas[0].strip() if rc == 0 and filas else (err or out).strip()[:300],
               origen=f"contenedor {cont}", objetivo=f"localhost:9042 (interno) / {cfg['CASSANDRA_KEYSPACE']}",
               cliente="cqlsh", duracion_ms=t)]


# ===========================================================================
# Redis (RF12)
# ===========================================================================
def redis_protocolo(cfg: Config) -> list[Resultado]:
    u = urlparse(cfg["REDIS_URL"])
    h, p = u.hostname, u.port or 6379
    v, e, t = medir(intercambio_crudo, h, p, b"*1\r\n$4\r\nPING\r\n", cfg.timeout)
    if v and v.startswith(b"+PONG"):
        det, ok = "+PONG (respuesta RESP basica, sin autenticar)", OK
    elif v and v.startswith(b"-NOAUTH"):
        det, ok = "-NOAUTH: el servidor responde RESP pero exige password", OK
    else:
        det, ok = (f"respuesta inesperada {v[:30]!r}" if v else describir_excepcion(e)), FALLA
    return [_r("redis", "protocolo", "Handshake RESP: PING crudo (sin driver)", ok, det,
               objetivo=f"{h}:{p}", cliente="socket (RESP)", duracion_ms=t,
               responde="El listener habla RESP?", no_permite="Que existan las claves del modulo.")]


def redis_driver(cfg: Config) -> list[Resultado]:
    try:
        import redis
    except Exception as e:  # noqa: BLE001
        return _sin_driver("redis", "redis-py", e)
    P, cli, res = "redis", "redis-py", []
    r = redis.from_url(cfg["REDIS_URL"], socket_connect_timeout=cfg.timeout,
                       socket_timeout=cfg.timeout, decode_responses=True)
    v, e, t = medir(r.ping)
    res.append(_r(P, "autenticacion", "PING con el cliente de la API (aplica AUTH si la URL tiene password)",
                  OK if v else FALLA, "PONG" if v else describir_excepcion(e),
                  objetivo=cfg["REDIS_URL"], cliente=cli, duracion_ms=t))
    if not v:
        return res
    v, e, t = medir(r.execute_command, "AUTH", "credencial-invalida-h11")
    msg = str(e) if e else ""
    if "without any password configured" in msg:
        det = "el servidor NO tiene password configurada (requirepass vacio): no hay identidad que validar"
    elif "WRONGPASS" in msg or "invalid" in msg.lower():
        det = "password invalida rechazada (WRONGPASS)"
    else:
        det = describir_excepcion(e) if e else "AUTH aceptada (inesperado)"
    res.append(_r(P, "autenticacion", "[negativo] AUTH con password invalida", OK if e else FALLA, det,
                  cliente=cli, duracion_ms=t, extra=NEG))
    res.append(_r(P, "autorizacion", "Permisos del usuario 'default'", INFO,
                  "sin ACL configuradas: el usuario default tiene acceso a todas las claves y comandos",
                  cliente=cli))
    v, e, t = medir(r.dbsize)
    res.append(_r(P, "contexto", f"Base logica {urlparse(cfg['REDIS_URL']).path.strip('/') or '0'}: DBSIZE",
                  OK if v else FALLA, f"{v} claves" if v is not None else describir_excepcion(e),
                  cliente=cli, duracion_ms=t,
                  no_permite="DBSIZE=0 no es una falla de conexion: puede ser una base vacia o la "
                             "base logica equivocada."))
    clave = f"sesion:{cfg['PRUEBA_SESION']}"
    tipo, e, t = medir(r.type, clave)
    ttl = r.ttl(clave) if tipo and tipo != "none" else -2
    if tipo == "hash":
        campos = r.hmget(clave, "usuario_id", "estado")
        det = f"existe, tipo=hash, TTL={ttl} s, usuario_id={campos[0]}, estado={campos[1]}"
        ok = OK
    elif tipo == "none":
        det, ok = ("NO existe (TTL=-2): nunca se cargo o EXPIRO. Las sesiones del Hito 7 tienen "
                   "TTL de 1800 s: repetir la carga de muestra"), FALLA
    else:
        det, ok = (f"existe con tipo={tipo}, TTL={ttl}" if tipo else describir_excepcion(e)), OK if tipo else FALLA
    res.append(_r(P, "lectura", f"Clave de demostracion '{clave}': tipo, TTL y campos", ok, det,
                  objetivo=clave, cliente=cli, duracion_ms=t,
                  responde="Existe la sesion de prueba y cuanto le queda de vida?", no_permite="-"))
    if tipo and tipo != "none":
        v, e, t = medir(r.get, clave)
        res.append(_r(P, "lectura", f"Operacion identica al adaptador de la API: GET {clave}",
                      OK if e is None else FALLA,
                      "GET funciona" if e is None else
                      f"{describir_excepcion(e)}: el Hito 7 guarda la sesion como HASH y la API usa "
                      "GET (string). La API traduce este error a 503 'dependencia no disponible' "
                      "aunque Redis responde", objetivo=clave, cliente=cli, duracion_ms=t,
                      esperado="lectura de la sesion", extra={"hallazgo": "H2", "compatibilidad_api": True}))
    ausente = "sesion:no-existe-h11"
    v, e, t = medir(lambda: (r.exists(ausente), r.ttl(ausente)))
    res.append(_r(P, "lectura", f"[negativo] Clave ausente '{ausente}'",
                  OK if v == (0, -2) else FALLA,
                  "EXISTS=0, TTL=-2: Redis respondio; ausencia valida (404 en la API, no 503)"
                  if v == (0, -2) else (describir_excepcion(e) if e else str(v)),
                  objetivo=ausente, cliente=cli, duracion_ms=t, extra=NEG))
    v, e, t = medir(r.info, "stats")
    res.append(_r(P, "lectura", "Clave expirada vs ausente: contadores del servidor", INFO,
                  f"expired_keys={v.get('expired_keys')} evicted_keys={v.get('evicted_keys')} "
                  "| una clave expirada se ve igual que una ausente (TTL=-2); solo los contadores "
                  "del servidor o la aplicacion pueden distinguirlas" if v else describir_excepcion(e),
                  cliente=cli, duracion_ms=t, extra=NEG))
    r.close()
    return res


def redis_cli(cfg: Config) -> list[Resultado]:
    cont = cfg["REDIS_CONTAINER"]
    skip = _cli_disponible(cfg, "redis", cont)
    if skip:
        return [skip]
    clave = f"sesion:{cfg['PRUEBA_SESION']}"
    script = f"redis-cli PING; redis-cli TYPE {clave}; redis-cli TTL {clave}; redis-cli INFO server | grep redis_version"
    (rc, out, err), _, t = medir(docker_exec, cont, ["sh", "-c", script], timeout=cfg.timeout + 10)
    return [_r("redis", "lectura", f"redis-cli: PING, TYPE y TTL de {clave} (dentro del contenedor)",
               OK if rc == 0 and "PONG" in out else FALLA,
               " | ".join(x.strip() for x in out.splitlines() if x.strip()) if rc == 0 else err.strip(),
               origen=f"contenedor {cont}", objetivo="localhost:6379 (interno)",
               cliente="redis-cli", duracion_ms=t)]


# ===========================================================================
# InfluxDB 3 Core (RF13)
# ===========================================================================
def influxdb_http(cfg: Config) -> list[Resultado]:
    P, cli, res = "influxdb", "HTTP API v3", []
    base, token, db = cfg["INFLUX_URL"].rstrip("/"), cfg["INFLUXDB3_TOKEN"], cfg["INFLUX_DATABASE"]
    v, e, t = medir(http, "GET", base + "/health", cfg.timeout)
    st, _, cuerpo, err = v
    res.append(_r(P, "protocolo", "GET /health SIN token",
                  OK if st in (200, 401) else FALLA,
                  (f"HTTP {st}: el servicio responde HTTP; "
                   + ("exige autorizacion incluso para /health (InfluxDB 3 Core por defecto)" if st == 401
                      else "health abierto")) if st else err,
                  objetivo=base + "/health", cliente=cli, duracion_ms=t,
                  responde="Hay un servidor InfluxDB respondiendo HTTP?",
                  no_permite="Un 401 NO es caida: el servicio esta accesible y pide credencial."))
    if st is None:
        return res
    if not token:
        res.append(_r(P, "autenticacion", "Token configurado", SKIP,
                      "INFLUXDB3_TOKEN / INFLUXDB3_TOKEN_FILE sin valor: no se puede probar la "
                      "autorizacion (la API respondera 503)", cliente=cli))
        return res
    auth = {"Authorization": f"Bearer {token}"}
    v, e, t = medir(http, "GET", base + "/health", cfg.timeout, auth)
    st, _, cuerpo, err = v
    res.append(_r(P, "autenticacion", "GET /health CON el token configurado",
                  OK if st == 200 else FALLA, f"HTTP {st} {cuerpo[:20].decode(errors='replace')}"
                  if st else err, objetivo=base + "/health", cliente=cli, duracion_ms=t,
                  no_permite="Que el token tenga permiso sobre la database."))
    v, e, t = medir(http, "GET", base + "/health", cfg.timeout,
                    {"Authorization": "Bearer apiv3_token_invalido_h11"})
    st2 = v[0]
    res.append(_r(P, "autenticacion", "[negativo] Token invalido",
                  OK if st2 in (401, 403) else FALLA, f"HTTP {st2} (rechazado)" if st2 else v[3],
                  cliente=cli, duracion_ms=t, esperado="401 Unauthorized", extra=NEG))
    v, e, t = medir(http, "GET", base + "/api/v3/configure/database?format=json", cfg.timeout, auth)
    st, _, cuerpo, err = v
    try:
        nombres = [d.get("iox::database") for d in json.loads(cuerpo)] if st == 200 else []
    except ValueError:
        nombres = []
    res.append(_r(P, "autorizacion", "El token puede listar las databases (permiso de administracion)",
                  OK if st == 200 else FALLA, f"HTTP {st}: {', '.join(nombres)}" if st else err,
                  cliente=cli, duracion_ms=t))
    res.append(_r(P, "contexto", f"Database '{db}' configurada existe",
                  OK if db in nombres else FALLA,
                  "presente en el catalogo" if db in nombres else f"'{db}' no esta en {nombres}",
                  objetivo=db, cliente=cli))

    def q(database, sql, params):
        cuerpo = json.dumps({"db": database, "q": sql, "params": params, "format": "json"}).encode()
        return http("POST", base + "/api/v3/query_sql", cfg.timeout,
                    dict(auth, **{"Content-Type": "application/json"}), cuerpo)

    sql = ("SELECT equipo_id, COUNT(*) AS puntos, ROUND(AVG(posesion_pct), 1) AS posesion_prom, "
           "MAX(pases_acum) AS pases_al_cierre FROM estadisticas_equipo "
           "WHERE partido_id = $p AND time >= $d AND time < $h GROUP BY equipo_id ORDER BY equipo_id")
    par = {"p": cfg["PRUEBA_INFLUX_PARTIDO"], "d": cfg["PRUEBA_INFLUX_DESDE"],
           "h": cfg["PRUEBA_INFLUX_HASTA"]}
    ventana = f"{par['p']} [{par['d']}, {par['h']})"
    v, e, t = medir(q, db, sql, par)
    st, _, cuerpo, err = v
    filas = json.loads(cuerpo) if st == 200 and cuerpo else []
    res.append(_r(P, "lectura", f"Consulta temporal acotada {ventana}: COUNT, AVG(posesion), MAX(pases_acum)",
                  OK if st == 200 and filas else FALLA,
                  json.dumps(filas) if st == 200 else f"HTTP {st} {cuerpo[:160]!r}" if st else err,
                  objetivo=f"{db}.estadisticas_equipo", cliente=cli, duracion_ms=t,
                  responde="El cliente puede leer una ventana temporal con la agregacion correcta "
                           "(AVG para muestras, MAX para contadores acumulados)?", no_permite="-"))
    # El MISMO cuerpo que arma el adaptador de la API (app/adapters/influx_adapter.py).
    cuerpo_api = json.dumps({
        "db": db,
        "query": "SELECT time, equipo_id, posesion_pct, pases_acum, tiros_acum, recuperaciones_acum "
                 "FROM estadisticas_equipo WHERE partido_id = $p_partido "
                 "AND time >= $p_desde AND time < $p_hasta ORDER BY time",
        "params": {"p_partido": par["p"], "p_desde": par["d"], "p_hasta": par["h"]},
        "format": "json"}).encode()
    v, e, t = medir(http, "POST", base + "/api/v3/query_sql", cfg.timeout,
                    dict(auth, **{"Content-Type": "application/json"}), cuerpo_api)
    st, _, cuerpo, err = v
    res.append(_r(P, "lectura", "Peticion identica al adaptador de la API (cuerpo JSON con campo 'query')",
                  OK if st == 200 else FALLA,
                  f"HTTP {st}: {cuerpo[:90].decode(errors='replace')}" + (
                      " -> la API v3 espera el campo 'q'; el adaptador envia 'query'. Toda consulta "
                      "de la API (y su /salud) recibe 400 y se informa como 503" if st == 400 else "")
                  if st else err, objetivo=f"{db}.estadisticas_equipo", cliente=cli, duracion_ms=t,
                  esperado="HTTP 200 con los puntos de la ventana",
                  extra={"hallazgo": "H6", "compatibilidad_api": True}))
    par_vacia = dict(par, d=par["d"][:11] + "09:00:00Z", h=par["d"][:11] + "09:15:00Z")
    v, e, t = medir(q, db, sql, par_vacia)
    st, _, cuerpo, err = v
    res.append(_r(P, "lectura", f"[negativo] Ventana sin puntos [{par_vacia['d']}, {par_vacia['h']})",
                  OK if st == 200 and json.loads(cuerpo or b"[]") == [] else FALLA,
                  "HTTP 200 con [] : ausencia de puntos, no error" if st == 200 else
                  f"HTTP {st}" if st else err, cliente=cli, duracion_ms=t, extra=NEG))
    v, e, t = medir(q, db + "_inexistente_h11", "SELECT 1", {})
    st, _, cuerpo, err = v
    res.append(_r(P, "contexto", "[negativo] Database inexistente",
                  OK if st and 400 <= st < 500 else FALLA,
                  f"HTTP {st}: {cuerpo[:120].decode(errors='replace')}" if st else err,
                  objetivo=db + "_inexistente_h11", cliente=cli, duracion_ms=t,
                  esperado="4xx database not found (distinto de 401 y de 200 vacio)", extra=NEG))
    return res


def influxdb_cli(cfg: Config) -> list[Resultado]:
    cont = cfg["INFLUX_CONTAINER"]
    skip = _cli_disponible(cfg, "influxdb", cont)
    if skip:
        return [skip]
    if not cfg["INFLUXDB3_TOKEN"]:
        return [_r("influxdb", "lectura", "influxdb3 CLI", SKIP, "sin token configurado")]
    sql = (f"SELECT COUNT(*) AS puntos FROM estadisticas_equipo WHERE partido_id = "
           f"'{cfg['PRUEBA_INFLUX_PARTIDO']}' AND time >= '{cfg['PRUEBA_INFLUX_DESDE']}' "
           f"AND time < '{cfg['PRUEBA_INFLUX_HASTA']}'")
    (rc, out, err), _, t = medir(
        docker_exec, cont, ["influxdb3", "query", "--database", cfg["INFLUX_DATABASE"], sql],
        timeout=cfg.timeout + 20, env={"INFLUXDB3_AUTH_TOKEN": cfg["INFLUXDB3_TOKEN"]})
    rc2, ver, _ = docker_exec(cont, ["influxdb3", "--version"], timeout=15)
    filas = [x for x in out.splitlines() if x.startswith("|") and "puntos" not in x]
    return [_r("influxdb", "lectura", "influxdb3 query: conteo en la ventana (dentro del contenedor)",
               OK if rc == 0 and filas else FALLA,
               (f"puntos={filas[0].strip('| ').strip()} | {ver.strip()}" if rc == 0 and filas
                else (err or out).strip()[:300]),
               origen=f"contenedor {cont}", objetivo=f"localhost:8181 (interno) / {cfg['INFLUX_DATABASE']}",
               cliente="influxdb3 CLI", duracion_ms=t)]


# ===========================================================================
# IRIS (RF14)
# ===========================================================================
def iris_portal(cfg: Config) -> list[Resultado]:
    url = cfg["IRIS_PORTAL_URL"].rstrip("/") + "/csp/sys/UtilHome.csp"
    v, e, t = medir(http, "GET", url, cfg.timeout)
    st, hdr, cuerpo, err = v
    return [_r("iris", "protocolo", "Management Portal HTTP",
               OK if st and st < 500 else FALLA,
               f"HTTP {st} ({'pagina de login' if b'Login' in cuerpo or b'login' in cuerpo else 'respuesta'})"
               if st else err, objetivo=url, cliente="HTTP GET", duracion_ms=t,
               responde="El servidor web de IRIS responde?",
               no_permite="Nada sobre el Superserver (1972), que es el que usa el driver de la API.")]


def iris_driver(cfg: Config) -> list[Resultado]:
    try:
        import iris
    except Exception as e:  # noqa: BLE001
        return _sin_driver("iris", "intersystems-irispython", e)
    P, cli, res = "iris", "intersystems-irispython", []
    h, p, ns, usr, pwd = (cfg["IRIS_HOST"], int(cfg["IRIS_PORT"]), cfg["IRIS_NAMESPACE"],
                          cfg["IRIS_USER"], cfg["IRIS_PASSWORD"])

    def conectar(namespace, password):
        return iris.connect(h, p, namespace, usr, password, timeout=max(1, int(cfg.timeout)))

    con, e, t = medir(conectar, ns, pwd)
    if con is None:
        msg = describir_excepcion(e)
        if "Password change required" in msg:
            det = ("Superserver responde y la identidad existe, pero la password esta EXPIRADA "
                   "(IRIS Community exige cambiarla en el primer ingreso). La API no puede abrir "
                   "sesion: " + msg)
        elif "Access Denied" in msg:
            det = "credencial rechazada (Access Denied): " + msg
        else:
            det = msg
        res.append(_r(P, "autenticacion", f"Conexion al Superserver como '{usr}' en '{ns}'", FALLA, det,
                      objetivo=f"{h}:{p} / {ns}", cliente=cli, duracion_ms=t, extra={"hallazgo": "H3"}
                      if "Password change required" in msg else {}))
        return res
    res.append(_r(P, "autenticacion", f"Conexion al Superserver como '{usr}' en '{ns}'", OK,
                  "sesion abierta (autenticacion y seleccion de namespace en el mismo paso)",
                  objetivo=f"{h}:{p} / {ns}", cliente=cli, duracion_ms=t))
    cur = con.cursor()

    def uno(sql, params=()):
        cur.execute(sql, list(params))
        return cur.fetchone()

    v, e, t = medir(uno, "SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = ?", ["Fixture"])
    res.append(_r(P, "contexto", "Metadato: tablas del esquema Fixture (proyeccion SQL de las clases)",
                  OK if v and v[0] else FALLA, f"{v[0]} tablas en el esquema Fixture" if v else
                  describir_excepcion(e), objetivo=f"{ns} / Fixture", cliente=cli, duracion_ms=t,
                  responde="El namespace tiene las clases del Hito 9 compiladas?"))
    v, e, t = medir(uno, "SELECT COUNT(*) FROM Fixture.Partido")
    res.append(_r(P, "autorizacion", "Permiso SELECT sobre Fixture.Partido",
                  OK if v else FALLA, f"{v[0]} partidos visibles" if v else describir_excepcion(e),
                  cliente=cli, duracion_ms=t))
    partido = cfg["PRUEBA_PARTIDO"]
    v, e, t = medir(uno, "SELECT Codigo, Estado, GolesLocal, GolesVisitante FROM Fixture.Partido WHERE Codigo = ?",
                    [partido])
    res.append(_r(P, "lectura", f"Lectura de la entidad Partido {partido}", OK if v else FALLA,
                  str(tuple(v)) if v else (describir_excepcion(e) if e else "sin filas"),
                  objetivo="Fixture.Partido", cliente=cli, duracion_ms=t))
    # El MISMO SQL que ejecuta el adaptador de la API (app/adapters/iris_adapter.py).
    sql_api = ("SELECT p.Codigo, p.Fecha, p.Fase, p.Estado, p.GolesLocal, p.GolesVisitante, "
               "local.Codigo AS LocalCodigo, visita.Codigo AS VisitaCodigo, "
               "s.Codigo AS SedeCodigo, s.Nombre AS SedeNombre FROM Fixture.Partido p "
               "LEFT JOIN Fixture.Equipo local ON p.EquipoLocal = local.ID "
               "LEFT JOIN Fixture.Equipo visita ON p.EquipoVisitante = visita.ID "
               "LEFT JOIN Fixture.Sede s ON p.Sede = s.ID WHERE p.Codigo = ?")
    v, e, t = medir(uno, sql_api, [partido])
    res.append(_r(P, "lectura", "SQL identico al adaptador de la API (JOIN con alias 'local')",
                  OK if v else FALLA,
                  "consulta valida" if v else
                  (f"{describir_excepcion(e)} -> 'LOCAL' es palabra reservada de IRIS SQL: la consulta "
                   "no compila, la API responde 503 aunque /salud informe iris disponible"
                   if e else "sin filas"),
                  objetivo="Fixture.Partido + Equipo + Sede", cliente=cli, duracion_ms=t,
                  esperado="una fila con el detalle del partido",
                  extra={"hallazgo": "H7", "compatibilidad_api": True}))
    v, e, t = medir(uno, "SELECT Codigo FROM Fixture.Partido WHERE Codigo = ?",
                    [cfg["PRUEBA_PARTIDO_INEXISTENTE"]])
    res.append(_r(P, "lectura", f"[negativo] Objeto inexistente ({cfg['PRUEBA_PARTIDO_INEXISTENTE']})",
                  OK if v is None and e is None else FALLA,
                  "sin filas y sin error (404 en la API)" if e is None else describir_excepcion(e),
                  cliente=cli, duracion_ms=t, extra=NEG))
    cur.close()
    con.close()
    con2, e, t = medir(conectar, "NOEXISTE_H11", pwd)
    if con2:
        con2.close()
    res.append(_r(P, "contexto", "[negativo] Namespace incorrecto",
                  OK if e is not None else FALLA, describir_excepcion(e) if e else "conecto (inesperado)",
                  objetivo="NOEXISTE_H11", cliente=cli, duracion_ms=t, extra=NEG))
    return res


def iris_cli(cfg: Config) -> list[Resultado]:
    cont = cfg["IRIS_CONTAINER"]
    skip = _cli_disponible(cfg, "iris", cont)
    if skip:
        return [skip]
    partido = cfg["PRUEBA_PARTIDO"]
    entrada = (f'Write "NS=",$NAMESPACE," EXISTE=",##class(Fixture.Partido).CodigoIdxExists("{partido}"),!\n'
               'Write "VERSION=",$ZVERSION,!\nHalt\n')
    (rc, out, err), _, t = medir(docker_exec, cont, ["iris", "session", "IRIS", "-U", cfg["IRIS_NAMESPACE"]],
                                 timeout=cfg.timeout + 20, entrada=entrada)
    lineas = [x.strip() for x in out.splitlines() if x.strip().startswith(("NS=", "VERSION="))]
    res = [_r("iris", "lectura", f"Terminal (iris session): existe {partido} por indice CodigoIdx",
              OK if any("EXISTE=1" in x for x in lineas) else FALLA,
              " | ".join(lineas) if lineas else (err or out).strip()[:300],
              origen=f"contenedor {cont} (autenticacion del sistema operativo)",
              objetivo=f"namespace {cfg['IRIS_NAMESPACE']}", cliente="iris session", duracion_ms=t,
              no_permite="La sesion del Terminal entra con la identidad del SO del contenedor: NO "
                         "prueba la password que usa la API por el Superserver.")]
    (rc, out, err), _, t = medir(docker_exec, cont, ["iris", "session", "IRIS", "-U", "NOEXISTE_H11"],
                                 timeout=cfg.timeout + 20, entrada="Halt\n")
    salida = " ".join((out + err).split())[:200]
    res.append(_r("iris", "contexto", "[negativo] Terminal con namespace incorrecto",
                  OK if rc != 0 or "NAMESPACE" in salida.upper() else FALLA, salida or f"rc={rc}",
                  origen=f"contenedor {cont}", cliente="iris session", duracion_ms=t, extra=NEG))
    return res


PRUEBAS = {
    "mongodb": {"driver": [mongodb_driver], "cli": [mongodb_cli]},
    "neo4j": {"driver": [neo4j_http, neo4j_bolt_handshake, neo4j_driver], "cli": [neo4j_cli]},
    "cassandra": {"driver": [cassandra_protocolo, cassandra_driver], "cli": [cassandra_cli]},
    "redis": {"driver": [redis_protocolo, redis_driver], "cli": [redis_cli]},
    "influxdb": {"driver": [influxdb_http], "cli": [influxdb_cli]},
    "iris": {"driver": [iris_portal, iris_driver], "cli": [iris_cli]},
}


def ejecutar(cfg: Config, productos: list[str], solo: str | None = None) -> list[Resultado]:
    registrar_secretos(cfg.secretos())
    res: list[Resultado] = []
    for p in productos:
        print(f"--- {p}", flush=True)
        for origen in ("driver", "cli"):
            if solo and origen != solo:
                continue
            for fn in PRUEBAS[p][origen]:
                try:
                    res += fn(cfg)
                except Exception as e:  # noqa: BLE001 - una prueba rota no corta la evaluacion
                    res.append(_r(p, "protocolo", f"{fn.__name__}", FALLA,
                                  f"error no controlado en la prueba: {describir_excepcion(e)}"))
    return res


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--producto", default=",".join(PRODUCTOS))
    ap.add_argument("--solo", choices=["driver", "cli"])
    a = ap.parse_args()
    cfg = Config()
    enc = encabezado_corrida("Clientes nativos y drivers", cfg)
    print(enc)
    res = ejecutar(cfg, [p for p in a.producto.split(",") if p in PRODUCTOS], a.solo)
    guardar_resultados("clientes", res, enc)


if __name__ == "__main__":
    main()
