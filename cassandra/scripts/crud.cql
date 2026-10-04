-- =============================================================================
-- Hito 6 - Comentarios masivos del Fixture 2030 (Grupo 8)
-- crud.cql : operaciones de creacion, lectura, actualizacion y eliminacion (RF8)
--
-- Ejecucion (despues de esquema.cql):
--   docker exec -i fixture2030-cassandra cqlsh -f /scripts/crud.cql
--
-- Se trabaja sobre un comentario de prueba propio (usuario DEMO09, id aaaaaaaa-...)
-- para no alterar la muestra. El script es idempotente (RNF7): el orden
-- INSERT -> UPDATE -> DELETE deja el mismo estado final en cada ejecucion.
--
-- Recordatorios de la Clase 6:
--   * INSERT es un upsert: si la clave primaria existe, la sobrescribe.
--   * UPDATE y DELETE exigen la clave primaria COMPLETA de la fila.
--   * UPDATE sobre una clave inexistente CREA la fila (tambien es upsert).
--   * DELETE deja tombstones: no se usa de forma masiva (ver seccion D).
-- La duplicacion controlada obliga a escribir en las dos tablas dentro de un
-- BATCH acotado a UN comentario (atomicidad de 2 filas).
-- =============================================================================

USE fixture2030_comentarios;
CONSISTENCY ONE;

-- -----------------------------------------------------------------------------
-- A. CREATE: publicar un comentario en las dos tablas de acceso
-- Ventana de 5 minutos: 20:10 contiene al instante 20:10:30.
-- -----------------------------------------------------------------------------
BEGIN BATCH
  INSERT INTO comentarios_por_partido
    (partido_id, ventana, creado_en, comentario_id, usuario_id, contenido, estado, likes)
  VALUES ('F2030-063', '2030-06-22 20:10:00+0000', '2030-06-22 20:10:30+0000',
          aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa, 'DEMO09',
          'Comentario de prueba del CRUD', 'visible', 0);
  INSERT INTO comentarios_por_usuario
    (usuario_id, creado_en, comentario_id, partido_id, ventana, contenido, estado)
  VALUES ('DEMO09', '2030-06-22 20:10:30+0000', aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa,
          'F2030-063', '2030-06-22 20:10:00+0000',
          'Comentario de prueba del CRUD', 'visible');
APPLY BATCH;

-- -----------------------------------------------------------------------------
-- B. READ: recuperar el comentario por su clave en cada tabla
-- -----------------------------------------------------------------------------
-- B.1 En la tabla principal (clave de particion completa + clustering)
SELECT partido_id, ventana, creado_en, comentario_id, usuario_id, contenido, estado, likes
FROM comentarios_por_partido
WHERE partido_id = 'F2030-063'
  AND ventana = '2030-06-22 20:10:00+0000'
  AND creado_en = '2030-06-22 20:10:30+0000'
  AND comentario_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa;

-- B.2 En la tabla de historial por usuario
SELECT usuario_id, creado_en, comentario_id, partido_id, ventana, contenido, estado
FROM comentarios_por_usuario
WHERE usuario_id = 'DEMO09'
  AND creado_en = '2030-06-22 20:10:30+0000'
  AND comentario_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa;

-- -----------------------------------------------------------------------------
-- C. UPDATE: actualizacion delimitada por la clave primaria completa
-- -----------------------------------------------------------------------------
-- C.1 Interaccion: sumar likes. 'likes' solo existe en la tabla principal.
--     (El valor se calcula en la aplicacion; este laboratorio no trata la
--     concurrencia de dos usuarios que dan like en el mismo instante.)
UPDATE comentarios_por_partido
SET likes = 10
WHERE partido_id = 'F2030-063'
  AND ventana = '2030-06-22 20:10:00+0000'
  AND creado_en = '2030-06-22 20:10:30+0000'
  AND comentario_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa;

-- C.2 Moderacion: ocultar el comentario sin borrarlo (estado = 'oculto').
--     El estado esta duplicado, por eso se actualiza en las dos tablas en un batch.
BEGIN BATCH
  UPDATE comentarios_por_partido
  SET estado = 'oculto'
  WHERE partido_id = 'F2030-063'
    AND ventana = '2030-06-22 20:10:00+0000'
    AND creado_en = '2030-06-22 20:10:30+0000'
    AND comentario_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa;
  UPDATE comentarios_por_usuario
  SET estado = 'oculto'
  WHERE usuario_id = 'DEMO09'
    AND creado_en = '2030-06-22 20:10:30+0000'
    AND comentario_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa;
APPLY BATCH;

-- C.3 Verificacion del cambio
SELECT creado_en, usuario_id, estado, likes
FROM comentarios_por_partido
WHERE partido_id = 'F2030-063'
  AND ventana = '2030-06-22 20:10:00+0000'
  AND creado_en = '2030-06-22 20:10:30+0000'
  AND comentario_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa;

-- -----------------------------------------------------------------------------
-- D. DELETE: eliminacion controlada de UN comentario (en las dos tablas)
-- Moderar = cambiar 'estado' (seccion C.2). El borrado fisico se reserva para
-- casos puntuales (por ejemplo, pedido del autor). Cada DELETE deja tombstones
-- que se procesan en lecturas y compaction, por eso NO se usa para limpiezas
-- masivas ni para expirar comentarios.
-- -----------------------------------------------------------------------------
BEGIN BATCH
  DELETE FROM comentarios_por_partido
  WHERE partido_id = 'F2030-063'
    AND ventana = '2030-06-22 20:10:00+0000'
    AND creado_en = '2030-06-22 20:10:30+0000'
    AND comentario_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa;
  DELETE FROM comentarios_por_usuario
  WHERE usuario_id = 'DEMO09'
    AND creado_en = '2030-06-22 20:10:30+0000'
    AND comentario_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa;
APPLY BATCH;

-- D.1 Verificacion: ambas consultas deben devolver 0 filas
SELECT * FROM comentarios_por_partido
WHERE partido_id = 'F2030-063'
  AND ventana = '2030-06-22 20:10:00+0000'
  AND creado_en = '2030-06-22 20:10:30+0000'
  AND comentario_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa;

SELECT * FROM comentarios_por_usuario
WHERE usuario_id = 'DEMO09'
  AND creado_en = '2030-06-22 20:10:30+0000'
  AND comentario_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa;

-- -----------------------------------------------------------------------------
-- E. TTL: demostracion de una fila que expira (NO se usa en el modelo real)
-- Los comentarios del Fixture 2030 no expiran: se conservan. Esta seccion solo
-- muestra la sintaxis USING TTL (en segundos). Al vencer, la fila pasa a ser un
-- tombstone, con el mismo costo de lectura y compaction que un DELETE.
-- Ejecutarla de nuevo renueva el TTL de la misma fila (idempotente).
-- -----------------------------------------------------------------------------
INSERT INTO comentarios_por_partido
  (partido_id, ventana, creado_en, comentario_id, usuario_id, contenido, estado, likes)
VALUES ('F2030-063', '2030-06-22 20:10:00+0000', '2030-06-22 20:12:00+0000',
        bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb, 'DEMO09',
        'Comentario de prueba con TTL de 5 minutos', 'visible', 0)
USING TTL 300;

-- Mientras no expire, se recupera con normalidad:
SELECT creado_en, usuario_id, contenido
FROM comentarios_por_partido
WHERE partido_id = 'F2030-063'
  AND ventana = '2030-06-22 20:10:00+0000'
  AND creado_en = '2030-06-22 20:12:00+0000'
  AND comentario_id = bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb;
