-- Agregaciones del Hito 8 (InfluxDB 3 Core, SQL). Base: fixture2030_vivo.
-- Cada bloque justifica la funcion segun la SEMANTICA de la medida:
--   muestra instantanea (posesion_pct, usuarios_conectados, latencia_ms,
--       velocidad_kmh)            -> AVG (tendencia), MAX/MIN (extremos)
--   contador acumulado (pases_acum, tiros_acum, recuperaciones_acum,
--       distancia_acum_m)         -> MAX (valor al cierre); NUNCA SUM
--   conteo por segundo (interacciones, solicitudes, errores) -> SUM
-- Formato: "-- ## id | titulo", "-- patron:", "-- semantica:" y la sentencia.

-- ## A1 | Posesion promedio por equipo en ventanas de 5 minutos
-- patron: PA1 (tendencia de un partido para el dashboard)
-- semantica: posesion_pct es una muestra instantanea -> AVG por ventana.
--            (date_bin agrupa en ventanas de ancho fijo; ver nota en README)
SELECT date_bin(INTERVAL '5 minutes', time) AS ventana, equipo_id,
       AVG(posesion_pct) AS posesion_promedio
FROM estadisticas_equipo
WHERE partido_id = 'F2030-018'
  AND time >= '2030-06-13T08:00:00Z' AND time < '2030-06-13T09:40:00Z'
GROUP BY date_bin(INTERVAL '5 minutes', time), equipo_id
ORDER BY ventana, equipo_id;

-- ## A2 | Contador acumulado: forma correcta (MAX) frente a la incorrecta (SUM)
-- patron: PA1 (totales de tiros del partido)
-- semantica: tiros_acum ya es un total acumulado; sumar cada lectura repite
--            el mismo tiro cientos de veces. El valor final es el MAX.
SELECT equipo_id,
       MAX(tiros_acum) AS tiros_finales_correcto,
       SUM(tiros_acum) AS suma_de_acumulados_INCORRECTA
FROM estadisticas_equipo
WHERE partido_id = 'F2030-018'
  AND time >= '2030-06-13T08:00:00Z' AND time < '2030-06-13T09:40:00Z'
GROUP BY equipo_id
ORDER BY equipo_id;

-- ## A3 | Tiros acumulados al cierre de cada tramo de 15 minutos
-- patron: PA1 (evolucion por tramos del partido)
-- semantica: contador -> MAX dentro de la ventana = valor al cierre del tramo.
--            Los tiros del tramo se obtienen restando el tramo anterior.
SELECT date_bin(INTERVAL '15 minutes', time) AS tramo, equipo_id,
       MAX(tiros_acum) AS tiros_acumulados_al_cierre
FROM estadisticas_equipo
WHERE partido_id = 'F2030-018'
  AND time >= '2030-06-13T08:00:00Z' AND time < '2030-06-13T09:40:00Z'
GROUP BY date_bin(INTERVAL '15 minutes', time), equipo_id
ORDER BY tramo, equipo_id;

-- ## A4 | Pico de usuarios simultaneos totales (suma de regiones por segundo)
-- patron: PA2 (capacidad maxima requerida durante un partido)
-- semantica: se suma entre regiones en el MISMO instante (GROUP BY time) y se
--            toma el maximo: el pico es un extremo, no un promedio.
SELECT time, SUM(usuarios_conectados) AS usuarios_totales
FROM actividad_usuarios
WHERE partido_id = 'F2030-018'
  AND time >= '2030-06-13T08:00:00Z' AND time < '2030-06-13T09:40:00Z'
GROUP BY time
ORDER BY usuarios_totales DESC
LIMIT 3;

-- ## A5 | Minutos con mayor actividad de interaccion del partido
-- patron: PA2 (momentos de interes; comparar con los minutos de gol del grafo)
-- semantica: interacciones es un conteo por segundo -> SUM por minuto.
SELECT date_trunc('minute', time) AS minuto, SUM(interacciones) AS interacciones
FROM actividad_usuarios
WHERE partido_id = 'F2030-018'
  AND time >= '2030-06-13T08:00:00Z' AND time < '2030-06-13T09:40:00Z'
GROUP BY date_trunc('minute', time)
ORDER BY interacciones DESC
LIMIT 5;

-- ## A6 | Errores por millon de solicitudes, por servicio
-- patron: PA4 (salud operativa)
-- semantica: errores y solicitudes son conteos por segundo -> se suman por
--            separado y luego se dividen; promediar tasas por segundo
--            distorsionaria el total. Se expresa por millon porque la tasa es
--            muy baja.
SELECT servicio,
       SUM(errores) AS errores_totales,
       SUM(solicitudes) AS solicitudes_totales,
       1000000.0 * CAST(SUM(errores) AS DOUBLE) / SUM(solicitudes) AS errores_por_millon
FROM metricas_plataforma
WHERE partido_id = 'F2030-018'
  AND time >= '2030-06-13T08:00:00Z' AND time < '2030-06-13T09:40:00Z'
GROUP BY servicio
ORDER BY errores_por_millon DESC;

-- ## A7 | Partidos del torneo cargados con mas tiros totales (torneo)
-- patron: PA3 (comparacion entre partidos del torneo)
-- semantica: MAX por (partido, equipo) = tiros finales; luego SUM de los dos
--            equipos. Rango acotado al periodo del torneo (13 al 30/06/2030).
SELECT partido_id, SUM(tiros_finales) AS tiros_totales
FROM (
  SELECT partido_id, equipo_id, MAX(tiros_acum) AS tiros_finales
  FROM estadisticas_equipo
  WHERE time >= '2030-06-01T00:00:00Z' AND time < '2030-07-15T00:00:00Z'
  GROUP BY partido_id, equipo_id
) AS por_equipo
GROUP BY partido_id
ORDER BY tiros_totales DESC
LIMIT 5;
