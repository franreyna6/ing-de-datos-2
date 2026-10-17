# Coherencia con el TPO y los hitos anteriores

El módulo temporal es la implementación de una decisión ya tomada, no una tecnología nueva.

| Hito | Qué decidió o produjo | Cómo se relaciona con el Hito 8 |
| :--- | :--- | :--- |
| Hito 1 | Diagnosticó las estadísticas en vivo como dato de escritura masiva y crecimiento constante | Es el problema que describe `patrones_de_acceso.md`, sección 1 |
| Hito 2 | La matriz asignó las **estadísticas en vivo a series temporales (InfluxDB)**, con puntaje de 3,90 frente a 3,45 de Cassandra, que quedó como alternativa descartada | El hito implementa esa decisión sin cambiar de tecnología. Se aceptó el compromiso que la matriz declaró: InfluxDB prioriza ingesta y consulta por rango de tiempo sobre consultas relacionales arbitrarias, y todas las consultas del módulo son por rango |
| Hito 3 | Clasificó las estadísticas en vivo como **AP** (disponibilidad) con consistencia eventual: la ingesta no puede detenerse y el consumo, que es evolución en el tiempo, tolera convergencia eventual | El módulo es coherente con esa decisión: acepta datos tardíos y desordenados (V9), no rellena los segundos faltantes y reescribir un punto es seguro (V8). **Lo que este hito no demuestra:** el laboratorio es de un solo nodo, así que no hay particiones ni réplicas y la decisión AP no se pone a prueba; solo se ve que el modelo de datos no la contradice |
| Hito 4 (MongoDB) | Equipos y jugadores | `equipo_id` y `jugador_id` son los códigos de `equipos.csv` y `jugadores.csv`; los nombres no se duplican |
| Hito 5 (Neo4j) | Partidos, sedes, participaciones y eventos (goles y tarjetas) | Es la **fuente de los datos**: 96 partidos, 12 sedes, 192 participaciones y los minutos de gol. La validación V6b comprueba que los tiros finales no sean menores que los goles de `partidos.csv`, y V11 que la actividad de usuarios suba tras los goles de `eventos.csv` |
| Hito 6 (Cassandra) | Comentarios masivos | Aquí no se guardan comentarios. Ambos módulos comparten `partido_id`, lo que permite cruzar la actividad de usuarios con los comentarios de un partido |
| Hito 7 (Redis) | Sesiones y caché | `usuarios_conectados` es un **agregado por región**, no una sesión. La actividad por usuario sigue en Redis; acá no se guarda ningún identificador de usuario |

## Qué comparte y qué no con los otros módulos

- **Clave de unión:** `partido_id` (códigos `F2030-001` a `F2030-096`), idéntico en los hitos 5, 6 y 8.
- **Sin duplicación de entidades:** el módulo temporal no guarda nombres, fichas ni relaciones. Quien necesite el nombre de un equipo lo obtiene del módulo documental o del grafo con el mismo código.
- **Qué NO hace:** no reemplaza ninguna base anterior ni expone una API; el enunciado del hito excluye API REST, interfaz web y dashboard.
