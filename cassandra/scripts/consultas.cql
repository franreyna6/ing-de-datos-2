-- =============================================================================
-- Hito 6 - Comentarios masivos del Fixture 2030 (Grupo 8)
-- consultas.cql : consultas de lectura compatibles con la clave primaria (RF9)
--
-- Ejecucion (despues de esquema.cql y carga_muestra.cql):
--   docker exec -i fixture2030-cassandra cqlsh -f /scripts/consultas.cql
--
-- Todas parten de la clave de particion completa y usan solo condiciones
-- compatibles con el clustering. Ninguna usa ALLOW FILTERING.
-- Los patrones de acceso (P1..P4) estan descritos en docs/patrones_de_acceso.md.
-- Si tambien se cargo el volumen masivo, las ventanas pueden tener mas filas que
-- la muestra: LIMIT mantiene acotado el tamano de cada respuesta.
-- =============================================================================

USE fixture2030_comentarios;
CONSISTENCY ONE;

-- -----------------------------------------------------------------------------
-- P1. Feed de un partido: ultimos comentarios de la ventana actual
-- Entrada: partido_id + ventana (calculada por la aplicacion a partir de la hora).
-- Orden: creado_en DESC (el clustering ya lo devuelve del mas nuevo al mas viejo).
-- Limite: 20. Una sola particion.
-- -----------------------------------------------------------------------------
SELECT creado_en, usuario_id, contenido, estado, likes
FROM comentarios_por_partido
WHERE partido_id = 'F2030-063'
  AND ventana = '2030-06-22 20:20:00+0000'
LIMIT 20;

-- -----------------------------------------------------------------------------
-- P1b. Seguir el feed hacia atras: ventana inmediatamente anterior
-- Si la ventana actual devuelve menos de 20 filas, la aplicacion consulta la
-- ventana anterior (otra particion) hasta completar el limite o llegar al
-- inicio del partido.
-- -----------------------------------------------------------------------------
SELECT creado_en, usuario_id, contenido, estado, likes
FROM comentarios_por_partido
WHERE partido_id = 'F2030-063'
  AND ventana = '2030-06-22 20:15:00+0000'
LIMIT 20;

-- -----------------------------------------------------------------------------
-- P2. Ventana temporal dentro de un partido: comentarios de un tramo
-- Rango sobre la primera columna de clustering (creado_en), dentro de UNA ventana.
-- Ejemplo: lo que se escribio en los dos minutos posteriores al gol del minuto 23
-- (el partido comenzo a las 20:00 UTC, por lo tanto el gol es cerca de las 20:23).
-- -----------------------------------------------------------------------------
SELECT creado_en, usuario_id, contenido, likes
FROM comentarios_por_partido
WHERE partido_id = 'F2030-063'
  AND ventana = '2030-06-22 20:20:00+0000'
  AND creado_en >= '2030-06-22 20:23:00+0000'
  AND creado_en <  '2030-06-22 20:25:00+0000'
LIMIT 50;

-- -----------------------------------------------------------------------------
-- P3. Historial de un usuario (tabla comentarios_por_usuario)
-- Entrada: usuario_id. Orden: creado_en DESC. Limite: 10.
-- Es la consulta que justifica la tabla adicional (RF10).
-- -----------------------------------------------------------------------------
SELECT creado_en, partido_id, contenido, estado
FROM comentarios_por_usuario
WHERE usuario_id = 'DEMO01'
LIMIT 10;

-- P3b. Historial de un usuario acotado a un rango de tiempo
SELECT creado_en, partido_id, contenido, estado
FROM comentarios_por_usuario
WHERE usuario_id = 'DEMO01'
  AND creado_en >= '2030-06-22 20:00:00+0000'
  AND creado_en <  '2030-06-22 21:00:00+0000';

-- -----------------------------------------------------------------------------
-- P4. Tamano de una particion (control de distribucion, RNF5)
-- COUNT sobre UNA particion: se usa para verificar cuantas filas concentra una
-- ventana. No es una consulta frecuente de la plataforma.
-- -----------------------------------------------------------------------------
SELECT COUNT(*) FROM comentarios_por_partido
WHERE partido_id = 'F2030-063'
  AND ventana = '2030-06-22 20:45:00+0000';

-- -----------------------------------------------------------------------------
-- TRAZADO de una lectura (Clase 6): muestra el coordinador y los pasos de la
-- consulta P1. Sirve para observar que la lectura va a una sola particion.
-- -----------------------------------------------------------------------------
TRACING ON;
SELECT creado_en, usuario_id, contenido
FROM comentarios_por_partido
WHERE partido_id = 'F2030-063'
  AND ventana = '2030-06-22 20:20:00+0000'
LIMIT 5;
TRACING OFF;

-- -----------------------------------------------------------------------------
-- CONSULTAS QUE EL MODELO NO RESUELVE (se dejan comentadas, no se ejecutan)
-- Sirven para explicar el diseno: cada una necesita otra estructura de acceso.
-- -----------------------------------------------------------------------------
-- (1) Todos los comentarios de un partido, sin indicar la ventana:
--     SELECT * FROM comentarios_por_partido WHERE partido_id = 'F2030-063';
--     Falla: la clave de particion es (partido_id, ventana) y esta incompleta.
--     Recorrer todas las ventanas de un partido es una consulta de reporte, no de feed.
--
-- (2) Comentarios ocultos o pendientes de un partido (cola de moderacion):
--     SELECT * FROM comentarios_por_partido WHERE partido_id = 'F2030-063' AND estado = 'oculto';
--     'estado' no es parte de la clave: exigiria ALLOW FILTERING. Si se vuelve una
--     consulta frecuente corresponde una tabla propia (por ejemplo, por estado y
--     partido), con su costo de escritura adicional.
--
-- (3) Comentarios con mas likes del torneo: es una agregacion global (analitica);
--     no corresponde a esta tabla (ver docs/decisiones_de_particionamiento.md).
