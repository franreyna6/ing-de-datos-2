"""Configuracion de la API por variables de entorno (RF16, RNF6, RNF7).

Todos los valores de conexion (hosts, puertos, bases, keyspaces, namespaces,
credenciales, token de InfluxDB) se leen del entorno. Ningun secreto queda en el
codigo. Para el laboratorio hay valores por defecto que coinciden con los
docker-compose de los hitos anteriores; en una maquina real se sobreescriben con
un archivo .env local (excluido de git, ver .gitignore).

Las credenciales por defecto (admin/admin, neo4j/fixture2030) son las del
ambiente de aprendizaje del grupo, no secretos de produccion. Aun asi se dejan
como variables para poder cambiarlas sin tocar el codigo.
"""
import os
from functools import lru_cache


def _leer(nombre: str, defecto: str) -> str:
    valor = os.environ.get(nombre)
    return valor if valor not in (None, "") else defecto


class Config:
    """Configuracion efectiva de la API. Se construye una sola vez."""

    def __init__(self) -> None:
        # --- Servicio HTTP ---
        self.api_host: str = _leer("API_HOST", "0.0.0.0")
        self.api_port: int = int(_leer("API_PORT", "8000"))
        # Timeout por defecto para operaciones contra las dependencias (RNF8).
        # Segundos. Si una base tarda mas que esto, se traduce a 503 (RNF9).
        self.dep_timeout_s: float = float(_leer("DEP_TIMEOUT_S", "3.0"))

        # --- MongoDB (Hito 4) ---
        self.mongodb_uri: str = _leer("MONGODB_URI", "mongodb://admin:admin@localhost:27017")
        self.mongodb_db: str = _leer("MONGODB_DATABASE", "fixture2030")

        # --- Neo4j (Hito 5) ---
        self.neo4j_uri: str = _leer("NEO4J_URI", "bolt://localhost:7687")
        self.neo4j_user: str = _leer("NEO4J_USER", "neo4j")
        self.neo4j_password: str = _leer("NEO4J_PASSWORD", "fixture2030")
        self.neo4j_database: str = _leer("NEO4J_DATABASE", "neo4j")

        # --- Cassandra (Hito 6) ---
        self.cassandra_host: str = _leer("CASSANDRA_HOST", "localhost")
        self.cassandra_port: int = int(_leer("CASSANDRA_PORT", "9042"))
        self.cassandra_keyspace: str = _leer("CASSANDRA_KEYSPACE", "fixture2030_comentarios")
        # Contenedor Docker donde corre Cassandra (Hito 6). Se usa solo como
        # alternativa al driver nativo: si en una maquina el driver Python no puede
        # cargar (incompatibilidad conocida de cassandra-driver con Python 3.12,
        # que quito el modulo asyncore), el adaptador ejecuta las consultas con
        # cqlsh --el cliente oficial de Cassandra-- dentro de este contenedor.
        self.cassandra_container: str = _leer("CASSANDRA_CONTAINER", "fixture2030-cassandra")

        # --- Redis (Hito 7) ---
        self.redis_url: str = _leer("REDIS_URL", "redis://localhost:6379")

        # --- InfluxDB 3 Core (Hito 8) ---
        self.influx_url: str = _leer("INFLUX_URL", "http://localhost:8181")
        self.influx_database: str = _leer("INFLUX_DATABASE", "fixture2030_vivo")
        # El token NO tiene valor por defecto: se lee del entorno o de un archivo
        # local (RNF7). Si falta, el adaptador responde 503 y lo explica.
        self.influx_token: str = _leer("INFLUXDB3_TOKEN", "")

        # --- IRIS (Hito 9) ---
        self.iris_host: str = _leer("IRIS_HOST", "localhost")
        self.iris_port: int = int(_leer("IRIS_PORT", "1972"))
        self.iris_namespace: str = _leer("IRIS_NAMESPACE", "USER")
        self.iris_user: str = _leer("IRIS_USER", "_SYSTEM")
        self.iris_password: str = _leer("IRIS_PASSWORD", "SYS")

        # Limite maximo de elementos que cualquier endpoint de lista puede
        # devolver (RNF12): aunque el cliente pida mas, se recorta a este tope.
        self.max_limit: int = int(_leer("MAX_LIMIT", "100"))


@lru_cache(maxsize=1)
def obtener_config() -> Config:
    return Config()
