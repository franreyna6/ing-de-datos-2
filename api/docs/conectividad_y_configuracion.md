# Conectividad y configuración — API integrada (Hito 10)

**Grupo N.º 8** · Fixture 2030

## 1. Configuración por entorno (sin secretos en el repo)

Toda la configuración de conexión se lee de variables de entorno (RF16, RNF6).
El archivo `.env.example` lista todas las variables con los valores que coinciden
con los `docker-compose` de los hitos anteriores. Se copia a `.env` (excluido de
git por `.gitignore`, RNF7) y se ajusta en cada máquina.

## 2. Hosts y puertos de cada fuente

Los valores por defecto asumen que las bases corren en la notebook (localhost) y
la API también. Si la API corriera dentro de un contenedor, los hosts cambiarían
al nombre de servicio de Docker (p. ej. `mongodb` en vez de `localhost`).

| Fuente | Variable principal | Puerto | Contexto |
| :--- | :--- | :--- | :--- |
| MongoDB | `MONGODB_URI` | 27017 | db `fixture2030` (Hito 4) |
| Neo4j | `NEO4J_URI` | 7687 (Bolt) | db `neo4j` (Hito 5) |
| Cassandra | `CASSANDRA_HOST` | 9042 | keyspace `fixture2030_comentarios` (Hito 6) |
| Redis | `REDIS_URL` | 6379 | claves `sesion:*` (Hito 7) |
| InfluxDB | `INFLUX_URL` | 8181 | db `fixture2030_vivo`, token local (Hito 8) |
| IRIS | `IRIS_HOST` / `IRIS_PORT` | 1972 | namespace `USER`, esquema `Fixture` (Hito 9) |

## 3. Procedimiento de prueba

1. Levantar las fuentes que se vayan a probar (no hace falta tenerlas todas; ver §5).
2. Copiar `.env.example` a `.env` y, si se usa InfluxDB, pegar el token del Hito 8.
3. Iniciar la API: `scripts/iniciar_api.*`.
4. Verificar disponibilidad: `scripts/verificar_conectividad.*` consulta `/salud`.
5. Abrir Swagger UI (`/docs`) o importar la colección Postman y ejecutar los casos.
6. Contrastar cada respuesta con el cliente nativo de la práctica (mongosh, cypher-shell, cqlsh, redis-cli, Influx, Terminal IRIS): la API no inventa datos.

## 4. Diferencia notebook vs. Docker

- **API en la notebook (recomendado para este hito):** los hosts son `localhost` y los puertos, los publicados por cada `docker-compose`.
- **API en un contenedor:** los hosts pasan a ser los nombres de servicio de la red Docker y los puertos, los internos. En ese caso hay que ajustar las variables del `.env` y conectar la API a la misma red.

Este hito se prueba con la **API en la notebook** contra las bases en Docker.

## 5. Probar por tandas (recursos acotados)

Levantar las seis bases a la vez es exigente de memoria (Cassandra e IRIS son las
más pesadas). Como la API tolera dependencias caídas (una fuente apagada responde
503 y las demás siguen), se puede probar por grupos:

- **Tanda liviana:** MongoDB + Redis + Neo4j.
- **Tanda temporal:** InfluxDB (requiere el token del Hito 8).
- **Tandas pesadas:** Cassandra y IRIS por separado.

`/salud` muestra en cada momento qué fuentes están disponibles.

## 6. Detener sin borrar datos

Las bases se detienen con `docker compose stop` / `down` de cada módulo (según su
README). Ninguna operación de la API borra datos ni dispara cargas destructivas:
solo consulta el estado existente, salvo el `POST` de comentarios, que inserta una
fila en la tabla del Hito 6.
