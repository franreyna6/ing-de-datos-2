# Evidencia — Hito 6 (Cassandra)

Registro verificable de la creación del esquema, la carga, las consultas CQL y la prueba de
medición (RF13, RNF9).

## Qué hay en esta carpeta

| Archivo | Contenido | Estado |
| :--- | :--- | :--- |
| `distribucion_generada.txt` | Resumen de distribución del generador (1.100.000 de comentarios, semilla 2030) | **Incluido** (producido por `generar_datos.py`) |
| `logs/00_estado_nodo.log` | Fecha y `nodetool status` | Se genera con `ejecutar_todo.*` |
| `logs/01_esquema.log` | `SHOW VERSION`, creación de keyspace y tablas, `DESCRIBE KEYSPACE` | Se genera con `ejecutar_todo.*` |
| `logs/02_carga_muestra.log` | Carga de los 13 comentarios y su verificación | Se genera con `ejecutar_todo.*` |
| `logs/03_crud.log` | Create, read, update y delete (más TTL) | Se genera con `ejecutar_todo.*` |
| `logs/04_consultas.log` | Consultas P1–P4 y el trazado (`TRACING`) | Se genera con `ejecutar_todo.*` |
| `logs/carga_<fecha>.log` | Versión, recursos, tasa de `COPY` y verificación de conteos | Se genera con `carga_o_prueba.*` |

> **Importante.** Los registros de `logs/` solo existen después de ejecutar los scripts sobre
> Cassandra. No se incluyen resultados inventados: cada integrante debe correr el ambiente en
> su notebook y subir los logs generados.

## Cómo generar la evidencia

```bash
docker compose up -d
bash scripts/ejecutar_todo.sh        # esquema, muestra, CRUD y consultas -> logs/00..04
bash scripts/carga_o_prueba.sh       # 1.100.000 de comentarios y medición -> logs/carga_*.log
```
En Windows: `scripts\ejecutar_todo.ps1` y `scripts\carga_o_prueba.ps1`.

## Capturas opcionales

Si el grupo desea agregar capturas de pantalla (como en el Hito 5), conviene guardar:

1. `docker compose ps` con el contenedor en estado *healthy*.
2. `nodetool status` con el nodo en `UN`.
3. `DESCRIBE KEYSPACE fixture2030_comentarios` completo.
4. El resultado de la consulta P1 y del `TRACING`.
5. Las líneas finales del `COPY` con la tasa informada.

## Registro del ambiente

| Dato | Valor |
| :--- | :--- |
| Fecha de la prueba | 02/10/2026 (hora de Argentina; 2026-10-03 ≈ 00:30 UTC) |
| Versión (`SHOW VERSION`) | `cqlsh 6.2.0 \| Cassandra 5.0.9 \| CQL spec 3.4.7 \| Native protocol v5` |
| Sistema operativo | Windows, versión 10.0.26200 |
| Recursos de Docker (CPU / memoria) | 12 CPUs / 3.939.123.200 bytes (≈ 3,7 GiB) |
