-- =============================================================================
-- Hito 6 - Comentarios masivos del Fixture 2030 (Grupo 8)
-- carga_muestra.cql : muestra funcional para desarrollo (RF11)
--
-- Ejecucion (despues de esquema.cql):
--   docker exec -i fixture2030-cassandra cqlsh -f /scripts/carga_muestra.cql
--
-- Contenido: 13 comentarios sinteticos de 2 partidos del Hito 5
--   F2030-063 (Australia vs Argentina, 22/06/2030): el partido de mayor
--             popularidad del conjunto, con goles en los minutos 23, 30, 46, 49, 62 y 79.
--   F2030-001 (14/06/2030).
-- escritos por 5 usuarios de prueba (DEMO01..DEMO05).
--
-- Idempotente (RNF7): INSERT es un upsert. Cada comentario tiene un comentario_id
-- fijo; volver a ejecutar el archivo sobrescribe las mismas filas y NO duplica.
--
-- Duplicacion controlada: cada comentario se escribe en las dos tablas dentro de
-- un BATCH (logged). Aqui el batch se usa con su proposito de atomicidad acotada
-- (2 filas del mismo comentario), no como acelerador de carga masiva.
-- Los 1.100.000 comentarios del volumen masivo se cargan con COPY (scripts/carga_o_prueba.*).
-- =============================================================================

USE fixture2030_comentarios;

-- Escritura con consistencia ONE: basta una replica (postura AP de los Hitos 1 a 3).
CONSISTENCY ONE;

-- Comentario 01: F2030-063 / DEMO01 / ventana 20:00
BEGIN BATCH
  INSERT INTO comentarios_por_partido
    (partido_id, ventana, creado_en, comentario_id, usuario_id, contenido, estado, likes)
  VALUES ('F2030-063', '2030-06-22 20:00:00+0000', '2030-06-22 20:00:41+0000', 00000000-0000-4000-8000-000000000001, 'DEMO01', 'Arranca Australia contra Argentina, que nervios', 'visible', 3);
  INSERT INTO comentarios_por_usuario
    (usuario_id, creado_en, comentario_id, partido_id, ventana, contenido, estado)
  VALUES ('DEMO01', '2030-06-22 20:00:41+0000', 00000000-0000-4000-8000-000000000001, 'F2030-063', '2030-06-22 20:00:00+0000', 'Arranca Australia contra Argentina, que nervios', 'visible');
APPLY BATCH;

-- Comentario 02: F2030-063 / DEMO02 / ventana 20:00
BEGIN BATCH
  INSERT INTO comentarios_por_partido
    (partido_id, ventana, creado_en, comentario_id, usuario_id, contenido, estado, likes)
  VALUES ('F2030-063', '2030-06-22 20:00:00+0000', '2030-06-22 20:03:10+0000', 00000000-0000-4000-8000-000000000002, 'DEMO02', 'Vamos Argentina', 'visible', 5);
  INSERT INTO comentarios_por_usuario
    (usuario_id, creado_en, comentario_id, partido_id, ventana, contenido, estado)
  VALUES ('DEMO02', '2030-06-22 20:03:10+0000', 00000000-0000-4000-8000-000000000002, 'F2030-063', '2030-06-22 20:00:00+0000', 'Vamos Argentina', 'visible');
APPLY BATCH;

-- Comentario 03: F2030-063 / DEMO03 / ventana 20:15
BEGIN BATCH
  INSERT INTO comentarios_por_partido
    (partido_id, ventana, creado_en, comentario_id, usuario_id, contenido, estado, likes)
  VALUES ('F2030-063', '2030-06-22 20:15:00+0000', '2030-06-22 20:19:40+0000', 00000000-0000-4000-8000-000000000003, 'DEMO03', 'Se escucha todo el estadio', 'visible', 1);
  INSERT INTO comentarios_por_usuario
    (usuario_id, creado_en, comentario_id, partido_id, ventana, contenido, estado)
  VALUES ('DEMO03', '2030-06-22 20:19:40+0000', 00000000-0000-4000-8000-000000000003, 'F2030-063', '2030-06-22 20:15:00+0000', 'Se escucha todo el estadio', 'visible');
APPLY BATCH;

-- Comentario 04: F2030-063 / DEMO01 / ventana 20:20
BEGIN BATCH
  INSERT INTO comentarios_por_partido
    (partido_id, ventana, creado_en, comentario_id, usuario_id, contenido, estado, likes)
  VALUES ('F2030-063', '2030-06-22 20:20:00+0000', '2030-06-22 20:23:20+0000', 00000000-0000-4000-8000-000000000004, 'DEMO01', 'Gol de Australia, no lo puedo creer', 'visible', 12);
  INSERT INTO comentarios_por_usuario
    (usuario_id, creado_en, comentario_id, partido_id, ventana, contenido, estado)
  VALUES ('DEMO01', '2030-06-22 20:23:20+0000', 00000000-0000-4000-8000-000000000004, 'F2030-063', '2030-06-22 20:20:00+0000', 'Gol de Australia, no lo puedo creer', 'visible');
APPLY BATCH;

-- Comentario 05: F2030-063 / DEMO04 / ventana 20:20
BEGIN BATCH
  INSERT INTO comentarios_por_partido
    (partido_id, ventana, creado_en, comentario_id, usuario_id, contenido, estado, likes)
  VALUES ('F2030-063', '2030-06-22 20:20:00+0000', '2030-06-22 20:23:48+0000', 00000000-0000-4000-8000-000000000005, 'DEMO04', 'Que error de la defensa', 'visible', 2);
  INSERT INTO comentarios_por_usuario
    (usuario_id, creado_en, comentario_id, partido_id, ventana, contenido, estado)
  VALUES ('DEMO04', '2030-06-22 20:23:48+0000', 00000000-0000-4000-8000-000000000005, 'F2030-063', '2030-06-22 20:20:00+0000', 'Que error de la defensa', 'visible');
APPLY BATCH;

-- Comentario 06: F2030-063 / DEMO05 / ventana 20:20
BEGIN BATCH
  INSERT INTO comentarios_por_partido
    (partido_id, ventana, creado_en, comentario_id, usuario_id, contenido, estado, likes)
  VALUES ('F2030-063', '2030-06-22 20:20:00+0000', '2030-06-22 20:24:05+0000', 00000000-0000-4000-8000-000000000006, 'DEMO05', 'Mensaje de prueba pendiente de revision', 'pendiente', 0);
  INSERT INTO comentarios_por_usuario
    (usuario_id, creado_en, comentario_id, partido_id, ventana, contenido, estado)
  VALUES ('DEMO05', '2030-06-22 20:24:05+0000', 00000000-0000-4000-8000-000000000006, 'F2030-063', '2030-06-22 20:20:00+0000', 'Mensaje de prueba pendiente de revision', 'pendiente');
APPLY BATCH;

-- Comentario 07: F2030-063 / DEMO02 / ventana 20:30
BEGIN BATCH
  INSERT INTO comentarios_por_partido
    (partido_id, ventana, creado_en, comentario_id, usuario_id, contenido, estado, likes)
  VALUES ('F2030-063', '2030-06-22 20:30:00+0000', '2030-06-22 20:30:02+0000', 00000000-0000-4000-8000-000000000007, 'DEMO02', 'Otro gol de Australia, increible', 'visible', 7);
  INSERT INTO comentarios_por_usuario
    (usuario_id, creado_en, comentario_id, partido_id, ventana, contenido, estado)
  VALUES ('DEMO02', '2030-06-22 20:30:02+0000', 00000000-0000-4000-8000-000000000007, 'F2030-063', '2030-06-22 20:30:00+0000', 'Otro gol de Australia, increible', 'visible');
APPLY BATCH;

-- Comentario 08: F2030-063 / DEMO03 / ventana 20:45
BEGIN BATCH
  INSERT INTO comentarios_por_partido
    (partido_id, ventana, creado_en, comentario_id, usuario_id, contenido, estado, likes)
  VALUES ('F2030-063', '2030-06-22 20:45:00+0000', '2030-06-22 20:46:30+0000', 00000000-0000-4000-8000-000000000008, 'DEMO03', 'Gol de Argentina, empatamos', 'visible', 15);
  INSERT INTO comentarios_por_usuario
    (usuario_id, creado_en, comentario_id, partido_id, ventana, contenido, estado)
  VALUES ('DEMO03', '2030-06-22 20:46:30+0000', 00000000-0000-4000-8000-000000000008, 'F2030-063', '2030-06-22 20:45:00+0000', 'Gol de Argentina, empatamos', 'visible');
APPLY BATCH;

-- Comentario 09: F2030-063 / DEMO01 / ventana 20:45
BEGIN BATCH
  INSERT INTO comentarios_por_partido
    (partido_id, ventana, creado_en, comentario_id, usuario_id, contenido, estado, likes)
  VALUES ('F2030-063', '2030-06-22 20:45:00+0000', '2030-06-22 20:49:12+0000', 00000000-0000-4000-8000-000000000009, 'DEMO01', 'Dos goles en tres minutos, que partido', 'visible', 9);
  INSERT INTO comentarios_por_usuario
    (usuario_id, creado_en, comentario_id, partido_id, ventana, contenido, estado)
  VALUES ('DEMO01', '2030-06-22 20:49:12+0000', 00000000-0000-4000-8000-000000000009, 'F2030-063', '2030-06-22 20:45:00+0000', 'Dos goles en tres minutos, que partido', 'visible');
APPLY BATCH;

-- Comentario 10: F2030-063 / DEMO02 / ventana 21:15
BEGIN BATCH
  INSERT INTO comentarios_por_partido
    (partido_id, ventana, creado_en, comentario_id, usuario_id, contenido, estado, likes)
  VALUES ('F2030-063', '2030-06-22 21:15:00+0000', '2030-06-22 21:19:50+0000', 00000000-0000-4000-8000-000000000010, 'DEMO02', 'Gol de Argentina otra vez', 'visible', 20);
  INSERT INTO comentarios_por_usuario
    (usuario_id, creado_en, comentario_id, partido_id, ventana, contenido, estado)
  VALUES ('DEMO02', '2030-06-22 21:19:50+0000', 00000000-0000-4000-8000-000000000010, 'F2030-063', '2030-06-22 21:15:00+0000', 'Gol de Argentina otra vez', 'visible');
APPLY BATCH;

-- Comentario 11: F2030-001 / DEMO03 / ventana 20:00
BEGIN BATCH
  INSERT INTO comentarios_por_partido
    (partido_id, ventana, creado_en, comentario_id, usuario_id, contenido, estado, likes)
  VALUES ('F2030-001', '2030-06-14 20:00:00+0000', '2030-06-14 20:01:15+0000', 00000000-0000-4000-8000-000000000011, 'DEMO03', 'Arranca el grupo A', 'visible', 1);
  INSERT INTO comentarios_por_usuario
    (usuario_id, creado_en, comentario_id, partido_id, ventana, contenido, estado)
  VALUES ('DEMO03', '2030-06-14 20:01:15+0000', 00000000-0000-4000-8000-000000000011, 'F2030-001', '2030-06-14 20:00:00+0000', 'Arranca el grupo A', 'visible');
APPLY BATCH;

-- Comentario 12: F2030-001 / DEMO04 / ventana 20:55
BEGIN BATCH
  INSERT INTO comentarios_por_partido
    (partido_id, ventana, creado_en, comentario_id, usuario_id, contenido, estado, likes)
  VALUES ('F2030-001', '2030-06-14 20:55:00+0000', '2030-06-14 20:55:30+0000', 00000000-0000-4000-8000-000000000012, 'DEMO04', 'Gol del visitante, se complica', 'visible', 4);
  INSERT INTO comentarios_por_usuario
    (usuario_id, creado_en, comentario_id, partido_id, ventana, contenido, estado)
  VALUES ('DEMO04', '2030-06-14 20:55:30+0000', 00000000-0000-4000-8000-000000000012, 'F2030-001', '2030-06-14 20:55:00+0000', 'Gol del visitante, se complica', 'visible');
APPLY BATCH;

-- Comentario 13: F2030-001 / DEMO05 / ventana 21:20
BEGIN BATCH
  INSERT INTO comentarios_por_partido
    (partido_id, ventana, creado_en, comentario_id, usuario_id, contenido, estado, likes)
  VALUES ('F2030-001', '2030-06-14 21:20:00+0000', '2030-06-14 21:20:00+0000', 00000000-0000-4000-8000-000000000013, 'DEMO05', 'Gol del local en el final', 'visible', 6);
  INSERT INTO comentarios_por_usuario
    (usuario_id, creado_en, comentario_id, partido_id, ventana, contenido, estado)
  VALUES ('DEMO05', '2030-06-14 21:20:00+0000', 00000000-0000-4000-8000-000000000013, 'F2030-001', '2030-06-14 21:20:00+0000', 'Gol del local en el final', 'visible');
APPLY BATCH;

-- Verificacion rapida: ventana de la previa/arranque del partido F2030-063
SELECT creado_en, usuario_id, contenido, estado, likes
FROM comentarios_por_partido
WHERE partido_id = 'F2030-063' AND ventana = '2030-06-22 20:00:00+0000';
