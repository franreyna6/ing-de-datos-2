# Pruebas, métricas y rendimiento — Caché de usuarios y sesiones (Hito 7)

**Grupo N.º 8** · Redis · Fixture 2030

Cubre los apartados *Pruebas y evidencia* (RF12, RF13) y las métricas del servidor. Regla del
enunciado: no se declara ninguna tasa ni porcentaje de *cache hit* sin indicar método, entorno y
resultado observado. Los números de este documento son los de la **corrida registrada** en
`docs/evidencia/logs/`; al repetir la prueba cambian.

## 1. Ambiente de la corrida registrada (RNF10)

| Dato | Valor |
| :--- | :--- |
| Fecha de la prueba | 2026-10-09 (UTC), ver `00_ambiente.log` |
| Versión de Redis observada | **8.10.2** (`INFO server`, `01_inicializacion.log`), imagen `redis:latest` creada el 2026-10-06 |
| Cómo se ejecutó | `docker compose up -d` con los argumentos del Compose (AOF, `--save 60 1`, `--maxmemory 100mb`, `volatile-lru`) y `scripts/ejecutar_todo.ps1` |
| Sistema | Windows con Docker Desktop (WSL2): kernel Linux 6.18.33.2, 12 núcleos y ≈ 3,7 GiB de memoria visibles |
| Cliente | `redis-cli` 8.10.2 dentro del mismo contenedor (`docker exec`), sin red de por medio |

> Al repetir la prueba, los logs de `docs/evidencia/logs/` se sobrescriben con la versión de
> `latest` de ese día y los recursos del equipo, y las cifras cambian.

## 2. Métodos y resultados

### 2.1 A — Tiempo por comando (`medicion.sh`, `09_medicion.log`)

**Método.** Se arma un archivo con **5000 comandos iguales** y se envía por **una conexión** de
`redis-cli`, un comando a la vez esperando su respuesta (sin *pipelining*). Se mide el tiempo total
con `date`. El resultado incluye la lectura del archivo y el procesamiento de `redis-cli`, por lo
que es una **cota del tiempo por comando visto desde un cliente simple**, no la capacidad máxima de Redis.

| Operación | Patrón | Comandos | Tiempo | Comandos/s | µs por comando |
| :--- | :--- | ---: | ---: | ---: | ---: |
| `INCR` | P7 contador | 5000 | 4916 ms | 1017 | 983 |
| `GET` (cache hit) | P5 ficha | 5000 | 593 ms | 8431 | 118 |
| `HGETALL` | P2 sesión | 5000 | 621 ms | 8051 | 124 |
| `ZINCRBY` | P8 voto | 5000 | 5383 ms | 928 | 1076 |
| `MULTI/EXEC` (`HINCRBY` + `EXPIRE`, 4 líneas por unidad) | P3 renovación, sin el `HSET` | 5000 | 1730 ms | 2890 | 346 |

**Lectura.** En esta corrida hay una diferencia clara entre **lecturas y escrituras**:

- Las lecturas (`GET`, `HGETALL`) cuestan ≈ 120 µs por comando.
- `INCR` y `ZINCRBY` cuestan ≈ 1 ms, unas **ocho veces más**.
- `MULTI/EXEC` queda en el medio (≈ 350 µs por comando de los 5000 enviados; cada unidad `MULTI`,
  `HINCRBY`, `EXPIRE`, `EXEC` tarda ≈ 1,4 ms; la renovación real agrega un `HSET`).

No se investigó la causa. Una explicación plausible es que las escrituras pasan por la
persistencia AOF sobre un volumen de Docker Desktop en Windows, pero **no se verificó**; podría
comprobarse repitiendo la medición con `appendonly no`. Lo que sí se puede afirmar es que el
costo observado depende de la operación y del ambiente. Eso refuerza que **estas cifras no
se extrapolan** a otro equipo ni a los 100.000 solicitudes por segundo de la especificación (ver
`coherencia_con_el_tpo.md`).

### 2.2 B — Tasa de *cache hit* del patrón Cache-Aside (`medicion.sh`, `09_medicion.log`)

**Método.**

1. Se **vacía** la caché de partidos (21 copias borradas): arranque en frío.
2. Se ejecuta un bucle **Cache-Aside real**: `GET`; si falta, se lee la fuente simulada
   (`partidos.csv`) y se hace `SET ... EX 300`.
3. Secuencia **reproducible** de 1000 solicitudes: 80 % a los 20 partidos más consultados
   (`F2030-001` a `F2030-020`) y 20 % uniforme sobre los 96 (generador congruencial con semilla 2030,
   mismo resultado en cada corrida).
4. La tasa se calcula con la **fórmula de la clase** a partir de los **contadores del servidor**
   (`INFO stats`, diferencia antes/después) y se **verifica** contra los contadores del propio bucle.

| | Aciertos | Fallos |
| :--- | ---: | ---: |
| Contadores del bucle (aplicación) | 912 | 88 |
| Diferencia de `INFO stats` (servidor) | 912 | 88 |

```
tasa_de_hit = keyspace_hits / (keyspace_hits + keyspace_misses) × 100 = 912 / 1000 × 100 = 91,2 %
```

**Lectura.**

- Los contadores del servidor **coinciden exactamente** con los de la aplicación: el cálculo se
  puede confiar.
- Partiendo en frío hay **un fallo por cada partido distinto pedido**: se pidieron 88, hubo 88
  fallos. El resto (912) son aciertos.
- **91,2 % es una propiedad de esta secuencia sintética y no una predicción.** Depende de que el TTL
  (300 s) sea mayor que la duración de la prueba (≈ 5 s), de que no hubo invalidaciones y de la
  distribución 80/20 elegida. Con tráfico real la tasa sería otra.

### 2.3 Métricas consultadas del servidor (`08_metricas.log` y `11_metricas_final.log`)

| Métrica | Después de las pruebas funcionales | Después de la presión de memoria | Qué mide |
| :--- | ---: | ---: | :--- |
| `keyspace_hits` | 783 | 11.695 | Búsquedas de clave exitosas (acumulado) |
| `keyspace_misses` | 9 | 97 | Búsquedas fallidas (acumulado) |
| `expired_keys` | 1 | 1 | Claves eliminadas **por TTL** (la sesión de prueba de 3 s) |
| `evicted_keys` | 0 | 3435 | Claves eliminadas **por presión de memoria** |
| `used_memory_human` | 1,84 M | 1,87 M | Memoria en uso |
| `used_memory_peak_human` | 1,90 M | 4,99 M | Pico de memoria (refleja la prueba de presión) |
| Claves / con TTL (`INFO keyspace`) | 352 / 244 | 346 / 238 | Total y con vencimiento |

**Lectura.**

- `expired_keys` y `evicted_keys` son contadores **distintos**: separan lo que venció por tiempo de
  lo que se eliminó por falta de memoria (ver `memoria_y_escalabilidad.md`).
- Los contadores `keyspace_hits` y `keyspace_misses` del servidor son **acumulados de todo lo que
  se ejecutó** (incluidas las pruebas de concurrencia y de presión), por eso la tasa de
  la sección 2.2 se calcula con **diferencias** durante una prueba controlada y no con los totales
  del servidor.

### 2.4 Otras pruebas con evidencia

| Prueba | Resultado | Log |
| :--- | :--- | :--- |
| Ciclo de vida de la sesión (crear, renovar, vencer, cerrar) | TTL 1800 → 100 → 1800; vencida: `TTL` -2 | `03_sesiones.log` |
| Cache hit, miss e invalidación | Miss `(nil)` → carga con TTL 300 → hit; `DEL` y recarga con valor corregido | `04_cache.log` |
| Servidor no disponible (simulado) | `Could not connect to Redis ... Connection refused` | `04_cache.log` (bloque 7) |
| Concurrencia con 4 clientes | Atómicos: 2000/2000; antipatrón: 141/400 | `06_concurrencia_paralela.log` |
| Auditoría de TTL | 0 temporales sin TTL; 0 conservadas con TTL | `07_auditoria_ttl.log` |
| Presión de memoria | `volatile-lru`: 3435 evictadas, 0 rechazos; `noeviction`: 5985 rechazos `OOM` | `10_presion_memoria.log` |
| Persistencia ante reinicio | El TTL siguió corriendo y las 346 claves se conservaron (TTL de la sesión S0001: 1799 → 1795) | `12_persistencia.log` |

## 3. Limitaciones

- **Un solo nodo** y cliente en el mismo equipo, sin red ni carga competidora.
- **Secuencia sintética** para la tasa de hit; los usuarios y la actividad no existen en hitos
  previos.
- El tiempo por comando se mide con **un cliente simple** (`redis-cli`), por lo que está
  dominado por el cliente. No mide capacidad máxima.
- No se midió **latencia en percentiles** ni se probó el objetivo de p95 < 100 ms del TPO.
- No se midió la **memoria por sesión**.
- El valor `avg_ttl` de `INFO keyspace` es una estimación interna de Redis y puede variar entre
  lecturas (incluso tras un reinicio); no se usa para ninguna conclusión.

## 4. Cómo repetir las pruebas

```
docker compose up -d
bash scripts/ejecutar_todo.sh          # Linux / macOS / Git Bash
powershell -ExecutionPolicy Bypass -File .\scripts\ejecutar_todo.ps1     # Windows
```

Pruebas individuales:

```
docker exec fixture2030-redis sh /scripts/medicion.sh
docker exec -e N=20000 -e SOLICITUDES=5000 fixture2030-redis sh /scripts/medicion.sh
docker exec fixture2030-redis sh /scripts/concurrencia_paralela.sh
docker exec fixture2030-redis sh /scripts/presion_memoria.sh
```
