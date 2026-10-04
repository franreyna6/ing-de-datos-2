# Datos cargados — Comentarios masivos (Hito 6)

**Grupo N.º 8** · Apache Cassandra · Fixture 2030

Cubre el apartado *Datos cargados* del análisis (RF11, sección 5.3 del enunciado).

## 1. Dos niveles de carga

| Nivel | Qué es | Cómo se carga | Para qué |
| :--- | :--- | :--- | :--- |
| **Muestra funcional** | 13 comentarios, 2 partidos, 5 usuarios de prueba (`DEMO01`–`DEMO05`) | `scripts/carga_muestra.cql` | Desarrollo, CRUD y consultas en segundos |
| **Volumen objetivo** | **1.100.000** de comentarios, 96 partidos, 195.180 usuarios | `scripts/generar_datos.py` + `scripts/carga_o_prueba.*` (`COPY`) | Prueba de volumen y de carga |

El volumen objetivo **no se versiona en el repositorio** (cada CSV pesa ≈ 130 MB): se regenera de
forma determinista. `data/generado/` está en `.gitignore`.

## 2. Origen de los datos

- **Contexto real (del Hito 5):** `data/origen/` contiene los CSV `partidos`, `equipos`,
  `participaciones` y `eventos` del módulo de grafos. De ahí salen los 96 códigos de partido
  (`F2030-001` … `F2030-096`), sus fechas, el ranking de cada selección y los minutos de goles y
  tarjetas.
- **Datos sintéticos:** los comentarios, los usuarios y los instantes son generados. No
  existían en hitos anteriores.

## 3. Reglas de generación

| Aspecto | Regla |
| :--- | :--- |
| Cantidad por partido | El partido de mayor popularidad (`F2030-063`, Australia–Argentina) recibe el **12 %** del total; el 88 % restante se reparte según `1 / √(ranking local × ranking visitante)` (selecciones mejor rankeadas atraen más comentarios) |
| Instante | Inicio supuesto a las 20:00 UTC de la fecha del partido. 10 % en los 15 min previos, 10 % entre el minuto 110 y el 125, 45 % uniforme durante el partido y 35 % en picos: después de un gol o una tarjeta, con caída exponencial (media de 90 s) |
| Ventana | Inicio del tramo de 5 minutos que contiene al instante |
| Usuario | `U000001` … `U200000`, con sesgo hacia identificadores bajos (unos pocos usuarios muy activos) |
| Estado | 93 % `visible`, 4 % `pendiente`, 3 % `oculto` |
| Likes | al menos 65 % con 0; el resto sigue una distribución exponencial (tope 500) |
| Contenido | 26 frases cortas, algunas con el nombre de una de las selecciones del partido |
| Identificador | `comentario_id` uuid v4 derivado de la semilla: **mismo valor en cada corrida** |

## 4. Cantidad y distribución (corrida de referencia)

Resultado de `python scripts/generar_datos.py --total 1100000` (semilla 2030). El detalle completo
está en `docs/evidencia/distribucion_generada.txt`.

| Dato | Valor |
| :--- | :--- |
| Comentarios | 1.100.000 (2.200.000 de filas físicas, dos tablas) |
| Partidos | 96, entre 2.401 (`F2030-036`) y 132.000 (`F2030-063`) comentarios |
| Top 5 partidos | `F2030-063` 132.000 · `F2030-028` 45.568 · `F2030-065` 36.351 · `F2030-070` 34.803 · `F2030-066` 28.820 |
| Estados | `visible` 1.023.168 · `pendiente` 44.090 · `oculto` 32.742 |
| Particiones (partido, ventana) | 2.688; mediana 215 filas; máximo 12.087 |
| Usuarios | 195.180 distintos; mediana 4 comentarios; máximo 2.438 (`U000001`) |

## 5. Cómo se reproduce

```bash
python scripts/generar_datos.py                 # 1.100.000 de filas en data/generado/
python scripts/generar_datos.py --total 20000   # prueba rápida del flujo
```

Opciones: `--semilla`, `--partido-caliente`, `--cuota-caliente`, `--salida`.
La generación completa tarda ≈ 30 segundos y usa solo la biblioteca estándar de Python.

**Control de reproducibilidad.** Con Python 3.11.15, dos corridas consecutivas generaron
archivos idénticos (MD5 de `comentarios_por_partido.csv`:
`a47958a715a31693627039eae7287b0f`; de `comentarios_por_usuario.csv`:
`71ccb0e74acacae584fc5edb27b1cc27`). Con otra versión de Python el generador de números
aleatorios podría producir valores distintos; los conteos de partidos y estados se mantendrían
aproximadamente, pero no necesariamente idénticos.

## 6. Idempotencia de la carga (RNF7)

- Los `comentario_id` de la muestra son fijos y los del CSV son deterministas.
- `INSERT` y `COPY` son *upserts* sobre la clave primaria: repetir la carga sobrescribe las mismas
  filas y no crea duplicados.
- Dos tablas con las mismas filas: ambas CSV salen del mismo generador y de la misma lista de
  comentarios.

## 7. Limitaciones

- Los comentarios y los usuarios no son datos reales ni existen en otro módulo.
- La hora de inicio (20:00 UTC) es un supuesto único para todos los partidos.
- Solo se modela la fase de grupos (96 partidos), igual que el Hito 5.
- No se generan reacciones distintas de los *likes*.
