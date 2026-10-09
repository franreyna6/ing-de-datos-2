# Evidencia — Hito 7 (Redis)

Registro verificable de la creación del ambiente, las operaciones, los TTL observados, las
métricas consultadas y los resultados de las pruebas (RF13, RNF10).

## Qué hay en esta carpeta

| Archivo | Contenido |
| :--- | :--- |
| `distribucion_generada.txt` | Resumen de la muestra generada (semilla 2030): sesiones, caché, visitas y votos |
| `logs/00_ambiente.log` | Fecha, versión del servidor y del cliente, recursos del equipo y `docker compose ps` |
| `logs/01_inicializacion.log` | `PING`, versión de Redis, persistencia (AOF/RDB), `maxmemory` y política |
| `logs/02_carga_muestra.log` | Carga de la muestra: comandos enviados y respuestas |
| `logs/03_sesiones.log` | Ciclo de vida de la sesión: **TTL observados** al crear, renovar, vencer y cerrar |
| `logs/04_cache.log` | Cache-Aside: miss, carga con TTL, hit, invalidación; servidor no disponible (simulado) |
| `logs/05_concurrencia_comandos.log` | `INCR`, `ZINCRBY`, ranking Top N y renovación con `MULTI/EXEC` |
| `logs/06_concurrencia_paralela.log` | 4 clientes simultáneos: comandos atómicos contra el antipatrón |
| `logs/07_auditoria_ttl.log` | Verificación con `SCAN` de que todo dato temporal tiene TTL |
| `logs/08_metricas.log` | `INFO stats`, memoria, claves y persistencia tras las pruebas funcionales |
| `logs/09_medicion.log` | Método, ambiente y resultados: tiempo por comando y tasa de hit |
| `logs/10_presion_memoria.log` | Evicción con `volatile-lru` y rechazo `OOM` con `noeviction` |
| `logs/11_metricas_final.log` | Las mismas métricas tras la presión de memoria (`evicted_keys`) |
| `logs/12_persistencia.log` | Estado antes y después de `docker compose restart redis` |

## Cómo generar la evidencia

```
docker compose up -d
bash scripts/ejecutar_todo.sh          # Linux / macOS / Git Bash
```
En Windows: `powershell -ExecutionPolicy Bypass -File .\scripts\ejecutar_todo.ps1`.
Cada corrida **sobrescribe** los logs. Los scripts no usan contraseñas ni tokens reales (RNF7).

## Capturas opcionales

Si el grupo desea agregar capturas de pantalla (como en el Hito 5), conviene guardar:

1. `docker compose ps` con el contenedor en estado *healthy*.
2. `PING` y `INFO server` en `redis-cli`.
3. El bloque 7 de `03_sesiones.log` (vencimiento: `TTL` pasa de 3 a -2).
4. La tabla de `06_concurrencia_paralela.log` (atómicos contra antipatrón).
5. Las líneas finales de `09_medicion.log` (tasa de hit y verificación).

## Registro del ambiente (`redis:latest`)

El enunciado exige anotar la fecha de la prueba y la versión que reporta el servidor, porque
`latest` puede cambiar de comportamiento entre fechas. Datos de la corrida del grupo
(`logs/00_ambiente.log`):

| Dato | Valor |
| :--- | :--- |
| Fecha de la prueba | 2026-10-09 (UTC) |
| Versión (`redis_version`) | `8.10.2` (servidor y `redis-cli`) |
| Imagen | `redis:latest`, id `sha256:2c2dff79...`, creada el 2026-10-06 |
| Cómo se ejecutó | `docker compose up -d` con `redis:latest`; scripts con `ejecutar_todo.ps1` |
| Sistema anfitrión | Windows (NT 10.0.26200), Docker Desktop 29.7.2, Compose v5.5.1 |
| Kernel dentro del contenedor | Linux 6.18.33.2-microsoft-standard-WSL2 |
| Recursos visibles para Docker | 12 núcleos / ≈ 3,7 GiB de memoria |

> **Nota.** Los logs de `logs/` son los de esta corrida. Al repetir la prueba se sobrescriben
> con la versión de `redis:latest` de ese día, y las cifras de `docs/rendimiento.md`,
> `docs/concurrencia.md` y `docs/memoria_y_escalabilidad.md` deben actualizarse con ellos.
