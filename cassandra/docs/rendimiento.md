# Rendimiento y distribución — Comentarios masivos (Hito 6)

**Grupo N.º 8** · Apache Cassandra · Fixture 2030

Cubre el apartado *Rendimiento y distribución* del análisis (RF12, RNF9). El enunciado prohíbe
declarar tasas de escritura sin método, entorno y resultado observado, y aclara que si el
hardware no alcanza las 10.000 escrituras/s se evalúa la calidad del método y del análisis, no
una cifra inventada. Los resultados de este documento corresponden a **una corrida real**, hecha
el 02/10/2026 (hora de Argentina) en la notebook de un integrante del grupo; el log completo
está en `docs/evidencia/logs/carga_20261003_002948.log`. Antes se hizo una corrida con
1.000.000 de comentarios (`carga_20261001_190333.log`, 28.499 escrituras/s); se repitió con
1.100.000 porque el enunciado pide un volumen **superior** a 1.000.000. Se informa la de 1.100.000.

## 1. Método de medición

| Elemento | Definición |
| :--- | :--- |
| Herramienta | `COPY … FROM` de `cqlsh`, ejecutado dentro del contenedor (Clase 6: carga por archivo y `COPY`) |
| Datos | 1.100.000 de comentarios sintéticos (`scripts/generar_datos.py`, semilla 2030) en **dos CSV** con las mismas filas, uno por tabla |
| Qué se mide | Tiempo de pared de cada `COPY` y tasa informada, más la verificación de conteos |
| Escrituras físicas | 2 por comentario (una por tabla): 2.200.000 en total |
| Cálculo | filas ÷ segundos por tabla; escrituras físicas ÷ segundos totales |
| Estado inicial | **Tablas vacías.** Solo se registra la primera corrida: repetirla sobrescribe filas existentes (upsert) y no es comparable. En la corrida informada las tablas se vaciaron con `TRUNCATE` justo antes de medir (tenían la carga anterior de 1.000.000) |
| Script | `scripts/carga_o_prueba.sh` o `.ps1` (deja el registro en `docs/evidencia/logs/`) |
| Variables | `NUMPROCESSES` (procesos de `COPY`, por defecto 2) y `CHUNKSIZE` (por defecto 1000) |

**Qué NO mide.** `COPY` corre en el cliente (`cqlsh`, escrito en Python): su tasa incluye la
lectura y conversión del CSV y no equivale al máximo de escritura que admite el nodo. Se usa
porque es la herramienta de carga que ofrece la Clase 6. Medir con una herramienta de estrés
dedicada queda como mejora (§5).

## 2. Ambiente de prueba

Datos tomados del log de la corrida (`docs/evidencia/logs/carga_20261003_002948.log`):

| Dato | Valor |
| :--- | :--- |
| Fecha de la prueba (UTC) | 2026-10-03, ≈ 00:30 (21:30 del 02/10 hora de Argentina) |
| Versión de Cassandra (`SHOW VERSION`) | `[cqlsh 6.2.0 \| Cassandra 5.0.9 \| CQL spec 3.4.7 \| Native protocol v5]` |
| Estado del nodo (`nodetool status`) | `UN` (Up/Normal), 1 nodo, 16 tokens, 100 % efectivo |
| Sistema operativo del host | Windows, versión 10.0.26200 |
| Procesadores del host | 12 procesadores lógicos |
| CPUs y memoria visibles para Docker | 12 CPUs y 3.939.123.200 bytes de memoria (≈ 3,7 GiB) |
| Parámetros de `COPY` | `NUMPROCESSES = 2`, `CHUNKSIZE = 1000` |
| Topología | 1 nodo, `SimpleStrategy`, factor de replicación 1, `CONSISTENCY` por defecto de `cqlsh` |

## 3. Resultados observados

| Tabla | Filas | Tiempo (s) | Tasa (filas/s) |
| :--- | :--- | :--- | :--- |
| `comentarios_por_partido` | 1.100.000 | 55,4 | 19.846 |
| `comentarios_por_usuario` | 1.100.000 | 44,7 | 24.620 |
| **Total** | **2.200.000 escrituras** | **100,1** | **21.977** |

**Comparación con el objetivo (10.000 escrituras/s):** en esta corrida **se superó el objetivo**:
21.977 escrituras/s medidas contra 10.000 pedidas (≈ 2,2 veces). Lo medido es el promedio de toda
la carga, con el método y el ambiente de arriba. En la corrida anterior de 1.000.000 se había
obtenido 28.499 escrituras/s con el mismo método y el mismo equipo: la diferencia (≈ 23 %) muestra
que la tasa varía entre corridas y con el volumen, por lo que conviene leerla como un orden de
grandeza y no como una cifra exacta.

**Cómo leer la cifra.** Se midió un `COPY` ejecutado desde `cqlsh` (el cliente), contra un nodo
único con factor de replicación 1 y con 2 procesos de carga. No es la capacidad máxima del nodo ni
una prueba de concurrencia de lectores y escritores, y no incluye el costo de confirmar en varias
réplicas.

**Verificación de conteos** (el script compara el CSV con Cassandra):

| Partición | Esperado (CSV) | Observado (`COUNT`) |
| :--- | :--- | :--- |
| `(F2030-063, 2030-06-22 20:35)` | 9.165 | 9.165 |
| usuario `U000001` | 2.438 | 2.438 |

Los dos conteos coinciden, por lo que no se perdieron ni se duplicaron filas en esas particiones.
Es una verificación por muestreo de dos particiones, no un conteo de las 2.200.000 de filas.

Los valores esperados salen del generador con semilla 2030 y 1.100.000 de filas. Si la versión
de Python difiere, los números del generador podrían cambiar levemente; el script calcula el valor
esperado directamente del CSV generado, que es el que cuenta.

## 4. Distribución de los datos (medido sobre los datos generados)

Fuente: `docs/evidencia/distribucion_generada.txt`, producido por `generar_datos.py`.

| Métrica | Valor |
| :--- | :--- |
| Comentarios | 1.100.000 en 96 partidos |
| Usuarios distintos | 195.180 |
| Estados | `visible` 93,02 % · `pendiente` 4,01 % · `oculto` 2,98 % |
| Partido caliente | `F2030-063`: 132.000 comentarios (12 %) |
| Particiones de `comentarios_por_partido` | 2.688 (96 partidos × 28 ventanas) |
| Filas por partición | mín 35 · mediana 215 · p95 1.253 · p99 3.250 · **máx 12.087** |
| Tamaño de la partición máxima | ≈ 2,0 MiB — **estimación** (12.087 × 170 B), no medición |
| Particiones de `comentarios_por_usuario` | 195.180 · filas por usuario: mediana 4 · p99 29 · máx 2.438 |

**Qué indica.** La distribución es sesgada: pocas ventanas del partido más popular concentran las
particiones más grandes (8 de las 10 primeras son de `F2030-063`; las otras dos son de `F2030-043` y `F2030-085`), pero
ninguna supera las 12.100 filas. La mediana (215 filas) muestra que la mayoría de las
particiones es pequeña. Es el comportamiento buscado con el bucket de 5 minutos.

**Límite de lo medido.** Los bytes por partición son una estimación. Una medición real del
tamaño en disco requiere herramientas de administración de Cassandra que quedan fuera de lo
visto en clase; el conteo de filas por partición (`consultas.cql`, P4) sí se puede verificar con
`COUNT(*)`.

## 5. Límites esperables y mejoras posibles

| Limitación | Efecto esperable | Mejora posible |
| :--- | :--- | :--- |
| `COPY` corre en un cliente Python de un solo contenedor | La tasa queda limitada por el cliente, no por el nodo | Más `NUMPROCESSES`, varias cargas en paralelo por partido, o un cliente de carga dedicado |
| Nodo único en una notebook | Compite por CPU, memoria y disco con el resto del sistema y con el cliente | Dedicar recursos al contenedor; probar con SSD |
| Docker ve solo ≈ 3,7 GiB de memoria (12 CPUs) | La memoria disponible para el nodo y el cliente `COPY` es acotada | Subir la memoria asignada a Docker Desktop y repetir la medición |
| Solo se probó `NUMPROCESSES = 2` con 12 CPUs disponibles | Es posible, aunque **no se probó**, que más procesos de `COPY` suban la tasa | Repetir con otros valores de `NUMPROCESSES` y `CHUNKSIZE` y comparar |
| Docker Desktop (Windows/macOS) | El montaje de `~/docker/data/cassandra` atraviesa una capa de virtualización | Comparar contra un volumen nombrado de Docker |
| Una escritura por tabla | La duplicación (P3) duplica el trabajo de escritura | Evaluar si el volumen del historial justifica diferir la escritura de la segunda tabla |
| Sin réplicas | No se mide el costo de confirmar en varias réplicas | Repetir en un cluster de varios nodos |
| Tamaño de partición estimado | No se conoce el tamaño en disco real | Medir con las herramientas de administración correspondientes |

## 6. Supuestos que deben acompañar cualquier resultado (pregunta guía 11)

1. Versión exacta de Cassandra y fecha (la imagen es `latest`).
2. Recursos asignados a Docker y tipo de disco.
3. Parámetros de `COPY` y cantidad de filas.
4. Estado inicial de las tablas (vacías o no).
5. Datos sintéticos con distribución sesgada: otra distribución daría otra tasa.
6. Nodo único, factor de replicación 1: la tasa **no** incluye costo de replicación.
