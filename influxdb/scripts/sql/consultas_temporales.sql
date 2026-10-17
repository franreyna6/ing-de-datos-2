-- Consultas temporales del Hito 8 (InfluxDB 3 Core, SQL).
-- Base: fixture2030_vivo. Partido de referencia: F2030-018 (TUN local vs ALG),
-- inicio 2030-06-13T08:00:00Z; captura de 100 min (hasta 09:39:59Z).
-- Todas acotan rango temporal y dimensiones (RNF8). El formato de cada bloque
-- es: "-- ## id | titulo", lineas "-- patron:" y "-- lectura:", y la sentencia.
-- Las ventanas son [inicio, fin): inclusivo al inicio, exclusivo al final.

-- ## C1 | Ventana corta de un equipo, ordenada por tiempo
-- patron: PA1 (pantalla de partido: evolucion de estadisticas de un equipo)
-- lectura: 10 puntos consecutivos (1 por segundo) con las 4 medidas del equipo.
SELECT time, equipo_id, posesion_pct, pases_acum, tiros_acum, recuperaciones_acum
FROM estadisticas_equipo
WHERE partido_id = 'F2030-018' AND equipo_id = 'TUN'
  AND time >= '2030-06-13T09:00:00Z' AND time < '2030-06-13T09:00:10Z'
ORDER BY time;

-- ## C2 | Cantidad de puntos de la ventana de los minutos 60 a 75
-- patron: PA1 (verifica densidad: 15 min x 60 s = 900 puntos por equipo)
-- lectura: debe haber 900 puntos por equipo si no hubo huecos de captura.
SELECT equipo_id, COUNT(*) AS puntos_en_ventana
FROM estadisticas_equipo
WHERE partido_id = 'F2030-018'
  AND time >= '2030-06-13T09:00:00Z' AND time < '2030-06-13T09:15:00Z'
GROUP BY equipo_id
ORDER BY equipo_id;

-- ## C3 | Filtro por sede y grupo (dimensiones de contexto)
-- patron: PA3 (comparacion de partidos de una sede o grupo durante una jornada)
-- lectura: valores finales de los contadores por equipo, solo partidos de la
--          sede CAMP y el grupo C de esa jornada.
SELECT partido_id, equipo_id,
       MAX(tiros_acum) AS tiros_finales,
       MAX(pases_acum) AS pases_finales,
       MAX(recuperaciones_acum) AS recuperaciones_finales
FROM estadisticas_equipo
WHERE sede = 'CAMP' AND grupo = 'C'
  AND time >= '2030-06-13T00:00:00Z' AND time < '2030-06-14T00:00:00Z'
GROUP BY partido_id, equipo_id
ORDER BY partido_id, equipo_id;

-- ## C4 | Comparacion entre dos equipos del mismo partido, minuto a minuto
-- patron: PA1 / PA3 (comparar dimensiones: equipo_id local vs visitante)
-- lectura: la posesion promedio por minuto de ambos equipos suma ~100.
SELECT date_trunc('minute', time) AS minuto, equipo_id,
       AVG(posesion_pct) AS posesion_promedio
FROM estadisticas_equipo
WHERE partido_id = 'F2030-018'
  AND time >= '2030-06-13T09:00:00Z' AND time < '2030-06-13T09:05:00Z'
GROUP BY date_trunc('minute', time), equipo_id
ORDER BY minuto, equipo_id;

-- ## C5 | Comparacion entre regiones: pico, promedio e interacciones
-- patron: PA2 (actividad de usuarios por region durante un partido)
-- lectura: pico = capacidad maxima observada; promedio = carga sostenida;
--          interacciones = suma de eventos por segundo (medida de conteo).
SELECT region,
       MAX(usuarios_conectados) AS pico_usuarios,
       AVG(usuarios_conectados) AS promedio_usuarios,
       SUM(interacciones) AS interacciones_totales
FROM actividad_usuarios
WHERE partido_id = 'F2030-018'
  AND time >= '2030-06-13T08:00:00Z' AND time < '2030-06-13T09:40:00Z'
GROUP BY region
ORDER BY pico_usuarios DESC;

-- ## C6 | Comparacion entre servicios de la plataforma durante el partido
-- patron: PA4 (salud operativa de la plataforma en la ventana del partido)
-- lectura: latencia promedio y maxima, volumen de solicitudes y errores.
SELECT servicio,
       AVG(latencia_ms) AS latencia_promedio_ms,
       MAX(latencia_ms) AS latencia_maxima_ms,
       SUM(solicitudes) AS solicitudes_totales,
       SUM(errores) AS errores_totales
FROM metricas_plataforma
WHERE partido_id = 'F2030-018'
  AND time >= '2030-06-13T08:00:00Z' AND time < '2030-06-13T09:40:00Z'
GROUP BY servicio
ORDER BY latencia_promedio_ms DESC;

-- ## C7 | Los 5 jugadores que mas distancia recorrieron en el partido
-- patron: PA5 (rendimiento fisico de titulares durante un partido)
-- lectura: distancia_final = maximo del contador acumulado; velocidad maxima
--          es el maximo de las muestras (cada 5 s).
SELECT jugador_id, equipo_id,
       MAX(velocidad_kmh) AS velocidad_maxima_kmh,
       MAX(distancia_acum_m) AS distancia_final_m
FROM estadisticas_jugador
WHERE partido_id = 'F2030-018'
  AND time >= '2030-06-13T08:00:00Z' AND time < '2030-06-13T09:40:00Z'
GROUP BY jugador_id, equipo_id
ORDER BY distancia_final_m DESC
LIMIT 5;
