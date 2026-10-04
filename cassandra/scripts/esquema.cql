-- =============================================================================
-- Hito 6 - Comentarios masivos del Fixture 2030 (Grupo 8)
-- esquema.cql : creacion del keyspace y de las tablas de acceso (RF2, RF4-RF7, RF10)
--
-- Ejecucion (desde la carpeta cassandra/):
--   docker exec -i fixture2030-cassandra cqlsh -f /scripts/esquema.cql
--
-- Idempotente (RNF7): todo usa IF NOT EXISTS, se puede ejecutar varias veces.
-- Diseno dirigido por consultas (RNF4): cada tabla responde a consultas
-- concretas de scripts/consultas.cql. Ver docs/modelo_tabular.md.
-- =============================================================================

-- Version de Cassandra en uso (RNF9). Con la imagen 'latest' se registra la
-- version observada en cada prueba.
SHOW VERSION;

-- -----------------------------------------------------------------------------
-- 1. KEYSPACE (RF2)
-- SimpleStrategy con factor de replicacion 1: SOLO para el laboratorio de un
-- nodo. No hay tolerancia a fallas. En produccion multirregional se usaria
-- NetworkTopologyStrategy con replicas por datacenter (ver
-- docs/decisiones_de_particionamiento.md, seccion 6).
-- -----------------------------------------------------------------------------
CREATE KEYSPACE IF NOT EXISTS fixture2030_comentarios
WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1};

USE fixture2030_comentarios;

-- -----------------------------------------------------------------------------
-- 2. TABLA PRINCIPAL: comentarios_por_partido (RF4, RF5, RF6, RF7)
-- Responde: "feed de un partido": los comentarios mas recientes de un partido
-- y los de una ventana de tiempo, del mas nuevo al mas viejo.
--
--   Clave de particion : (partido_id, ventana)
--       partido_id = codigo del partido (mismo codigo F2030-xxx del Hito 5)
--       ventana    = inicio (UTC) de la ventana de 5 minutos que contiene al
--                    comentario. Es el bucket temporal: acota el tamano de cada
--                    particion y reparte un partido popular entre muchas
--                    particiones a lo largo del tiempo (RF7).
--   Clustering         : creado_en DESC, comentario_id ASC
--       creado_en ordena del mas reciente al mas antiguo dentro de la ventana;
--       comentario_id desempata comentarios del mismo instante y los hace unicos.
--
--   estado: moderacion ('visible' | 'pendiente' | 'oculto'); lo valida la
--           aplicacion, Cassandra no restringe los valores.
--   likes : metrica de interaccion.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS comentarios_por_partido (
    partido_id     text,
    ventana        timestamp,
    creado_en      timestamp,
    comentario_id  uuid,
    usuario_id     text,
    contenido      text,
    estado         text,
    likes          int,
    PRIMARY KEY ((partido_id, ventana), creado_en, comentario_id)
) WITH CLUSTERING ORDER BY (creado_en DESC, comentario_id ASC);

-- -----------------------------------------------------------------------------
-- 3. TABLA DE ACCESO SECUNDARIA: comentarios_por_usuario (RF10)
-- Responde: "historial de comentarios de un usuario" (desde su perfil).
-- La tabla principal no puede responderla sin recorrer todas las particiones de
-- todos los partidos, y ALLOW FILTERING no es una solucion aceptable. Se agrega
-- una tabla propia con los mismos comentarios ordenados por usuario
-- (duplicacion controlada: ver docs/modelo_tabular.md).
--
--   Clave de particion : usuario_id
--   Clustering         : creado_en DESC, comentario_id ASC
--
-- partido_id y ventana se guardan como columnas comunes para poder ubicar la
-- fila correspondiente en la tabla principal (su clave primaria completa).
-- No incluye 'likes': es la metrica que mas cambia y vive solo en la principal.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS comentarios_por_usuario (
    usuario_id     text,
    creado_en      timestamp,
    comentario_id  uuid,
    partido_id     text,
    ventana        timestamp,
    contenido      text,
    estado         text,
    PRIMARY KEY (usuario_id, creado_en, comentario_id)
) WITH CLUSTERING ORDER BY (creado_en DESC, comentario_id ASC);

-- -----------------------------------------------------------------------------
-- 4. VERIFICACION DEL ESQUEMA (evidencia de RF13)
-- -----------------------------------------------------------------------------
DESCRIBE KEYSPACE fixture2030_comentarios;
