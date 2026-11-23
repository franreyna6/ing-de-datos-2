# Memoria y escalabilidad — Caché de usuarios y sesiones (Hito 7)

**Grupo N.º 8** · Redis · Fixture 2030

Cubre el apartado *Memoria y escalabilidad* del análisis (RF10): política seleccionada, efecto
esperado del TTL y de la evicción, límites del nodo local y pasos futuros de escala.

## 1. Expiración (TTL) y evicción no son lo mismo

| | Expiración (TTL) | Evicción (`maxmemory`) |
| :--- | :--- | :--- |
| Pregunta que responde | ¿Cuánto tiempo sigue siendo válido o seguro este dato? | ¿Qué hace Redis cuando **no hay memoria** para aceptar más datos? |
| Quién decide | El producto, **por dato** (sesión 1800 s, partido 300 s, equipo 3600 s) | La política configurada para toda la instancia |
| Cuándo ocurre | Al vencer el tiempo, aunque sobre memoria | Solo al alcanzar el límite de memoria |
| Efecto sobre una sesión | Vence tras 30 min de inactividad (comportamiento **esperado**) | Puede desaparecer **antes** de tiempo (comportamiento a **tolerar**) |

Consecuencia: **un TTL no garantiza que la clave sobreviva hasta ese instante**. Con una política de
evicción, Redis puede quitarla antes si necesita memoria. Por eso las sesiones se diseñan sabiendo
que su ausencia es un caso normal (reautenticar), y la caché se diseña como copia reconstruible.

## 2. Política elegida (RF10)

En el `docker-compose.yml`:

```
--maxmemory 100mb
--maxmemory-policy volatile-lru
```

### 2.1 Comparación de las políticas vistas en clase

| Política | Qué haría con este módulo | Evaluación |
| :--- | :--- | :--- |
| `noeviction` | Rechaza las escrituras con error al llegar al límite; no borra nada | Protege sesiones y votos, pero una caché llena deja de aceptar **sesiones nuevas** (nadie podría iniciar sesión). Mal efecto para el caso dominante |
| `allkeys-lru` | Evicta lo menos usado entre **todas** las claves | Podría descartar **votos y visitas** (sin TTL), que se decidió conservar. Sería razonable solo en una instancia dedicada exclusivamente a caché |
| `allkeys-lfu` | Conserva lo más consultado | Mismo problema con las claves conservadas |
| **`volatile-lru`** | Evicta lo menos usado, **solo entre claves con TTL** | **Elegida para el laboratorio de una sola instancia.** Las claves conservadas (visitas, votos) nunca se evictan; entre las temporales sale primero lo menos usado. **Límite:** no distingue una copia de caché de una sesión vigente, porque las dos tienen TTL. La prueba de §3 lo muestra y §3.3 explica cómo se resuelve |
| `volatile-ttl` | Evicta primero lo que tiene menos TTL restante | Alternativa válida: las copias de caché (TTL corto) saldrían antes que las sesiones. Se descartó porque depende de que los TTL de cada tipo estén bien escalonados; LRU refleja directamente el uso real |

### 2.2 Condición para que funcione: disciplina de TTL

`volatile-lru` solo puede evictar claves **con TTL**. Si hubiera claves temporales sin TTL, quedarían
fuera de la evicción y, si fueran muchas, la instancia se comportaría como `noeviction`. Por eso el
módulo exige TTL en todo dato temporal y `auditoria_ttl.sh` lo verifica (`07_auditoria_ttl.log`:
0 claves temporales sin TTL; las 108 claves sin TTL son exactamente los contadores y votos
conservados por decisión).

### 2.3 Por qué 100 MB

Es el **límite del laboratorio**: bajo respecto de la RAM del equipo y suficiente para la muestra
(≈ 1,8 MB usados con unas 350 claves, ver `08_metricas.log`). **No es un dimensionamiento de producción.**
No se midió la memoria por sesión, así que no se extrapola cuánta RAM harían falta para 2-3 M de
sesiones; medirlo es un paso futuro (§5).

## 3. Evidencia: qué pasa al llegar al límite

`scripts/presion_memoria.sh` baja `maxmemory` temporalmente a (memoria usada + 3 MB) y escribe lotes
de 6000 claves de ≈ 1 KB, todas con TTL de 600 s. Resultado de la corrida registrada
(`10_presion_memoria.log`):

| Paso | Política | Escrituras aceptadas | Rechazadas (`OOM`) | `evicted_keys` | Sesiones vigentes | Claves de caché |
| :--- | :--- | ---: | ---: | :--- | ---: | ---: |
| Antes | `volatile-lru` | — | — | 0 | 200 | 104 (*) |
| Lote 1 | `volatile-lru` | 6000 | 0 | 0 → 3435 | 200 → 2 | 104 → 2 |
| Lote 2 | `noeviction` | 15 | 5985 | sin cambios (3435) | — | — |

(*) 88 copias de partidos que deja `medicion.sh` (incluye los 20 precargados) más las 16 de equipos de la muestra.

Respuesta de error con `noeviction`: `OOM command not allowed when used memory > 'maxmemory'`.

### 3.1 Cómo se interpreta

- Con `volatile-lru`, **ninguna escritura falló**: Redis eliminó claves con TTL para hacer lugar.
  Las claves que desaparecieron **no vencieron por tiempo** (todas tenían cientos de segundos): fueron
  **evictadas**. Es la diferencia entre expiración y evicción hecha visible.
- Una **sesión evictada se comporta como una sesión inexistente**: el usuario debe iniciar sesión
  otra vez. Una **copia de caché evictada** provoca un miss y se recarga desde la fuente.
- Con `noeviction`, Redis **no borró nada** y rechazó casi todas las escrituras: la aplicación
  debe manejar ese error, y con él no se aceptan sesiones nuevas.
- El experimento es **deliberadamente extremo**: 6 MB de datos nuevos contra 3 MB de margen, y todas
  las claves de la muestra estaban igual de inactivas, por lo que el LRU las descartó casi todas. No
  representa la proporción que se perdería en uso real (donde se evictan primero las claves menos
  usadas, es decir, las sesiones inactivas y las copias poco consultadas).
- Al terminar, el script restaura `maxmemory` y la política, borra las claves de prueba y recarga la
  muestra (idempotente), por lo que el ambiente queda como al empezar.

### 3.2 Efecto de cada mecanismo sobre cada tipo de dato

| Dato | Por TTL | Por evicción (`volatile-lru`) |
| :--- | :--- | :--- |
| Sesión | Vence tras 30 min inactiva: **esperado** | Desaparece antes de su TTL: el usuario debe reautenticar aunque estaba activo. **No deseado**: altera el ciclo de vida de la sesión (ver §3.3) |
| Copia de caché | Vence a los 300 s / 3600 s: se recarga | Desaparece antes: miss y recarga |
| Visitas y votos | No tienen TTL | **No se evictan** (sin TTL) |
| Datos de prueba | Vencen a los 600 s | Pueden evictarse |

### 3.3 Riesgo observado: la evicción alcanza sesiones vigentes (corrección del Hito 7)

La prueba de §3 muestra que, con `volatile-lru`, las sesiones vigentes pasaron de 200 a 2 por
presión de memoria. Ninguna había vencido por tiempo: fueron **expulsadas antes de su TTL de
inactividad**. El usuario pierde la sesión aunque la esté usando, y el ciclo de vida definido en
`ciclo_de_vida_e_invalidacion.md` (30 min sin actividad) deja de cumplirse.

**Por qué pasa.** `volatile-lru` elige entre **todas** las claves con TTL. Para Redis, una copia de
caché y una sesión son lo mismo: dos claves con vencimiento. La política no puede saber que perder
una copia de caché cuesta un *miss*, mientras que perder una sesión le cierra la sesión a un usuario
activo.

**Separación conceptual de los datos de este módulo:**

| Grupo | Claves | ¿Se puede evictar sin afectar al usuario? | Qué pasa si desaparece |
| :--- | :--- | :--- | :--- |
| Copias reconstruibles | `cache:partido:*`, `cache:equipo:*` | **Sí** | Un *miss*: se vuelve a leer la fuente de verdad (Neo4j, MongoDB) y se recarga la copia. El usuario solo nota más latencia |
| Datos de prueba | `prueba:*` | **Sí** | Ninguno: no forman parte del dominio |
| Estado del usuario | `sesion:*` | **No** | Se cierra la sesión de alguien que estaba activo. No se puede reconstruir desde otra fuente |
| Datos conservados | `partido:*:visitas`, `encuesta:*:figura` | **No** (ya protegidos: no tienen TTL) | Se pierden votos y contadores |

**Por qué esto no contradice el trade-off del Hito 2 y del Hito 3.** Allí se aceptó perder sesiones
ante la **caída de un nodo**, un evento excepcional. La presión de memoria es distinta: aparece
justamente en los picos de audiencia, cuando más usuarios están conectados. Si se aceptara, el
sistema cerraría sesiones en el peor momento y de forma rutinaria.

**Decisión.** La memoria para sesiones y la memoria para caché se separan:

- **Instancia de caché**, con `allkeys-lru`: todo lo que guarda es reconstruible, así que expulsar lo
  menos usado es correcto.
- **Instancia de sesiones**, con `noeviction`: al llenarse rechaza **nuevos** inicios de sesión con
  error, pero **nunca cierra una sesión vigente**. Se dimensiona con margen sobre la cantidad de
  sesiones esperada y se vigila `used_memory` contra `maxmemory` para ampliar antes de llegar al límite.
- Los votos y visitas quedan con las sesiones (sin TTL, no se evictan con ninguna de las dos políticas).

**Alcance en este laboratorio.** El módulo sigue corriendo en **una sola instancia** con
`volatile-lru`, porque la consigna pide un nodo único y los scripts de prueba operan sobre él. En ese
entorno el riesgo existe y está documentado: la prueba de §3 lo demuestra en condiciones extremas
(3 MB de margen). La separación de instancias es la decisión de diseño para un despliegue real y no se
implementó ni se midió en este hito.

**Alternativa descartada: `volatile-ttl` en una sola instancia.** Evicta primero lo que tiene menos TTL
restante. Protegería a las sesiones solo si todas las copias de caché vencieran antes que cualquier
sesión, y no es así: `cache:equipo:*` dura 3600 s y una sesión, 1800 s. Ajustar los TTL para forzar ese
orden mezclaría dos decisiones distintas (frescura de la caché y vida de la sesión).

## 4. Límites del nodo local

El ambiente es **un único nodo (standalone)**. Esto es un laboratorio de aprendizaje, **no una
topología de alta disponibilidad ni Redis Cluster**.

| Aspecto | Qué prueba el laboratorio | Qué NO prueba |
| :--- | :--- | :--- |
| Modelo de datos y comandos | Sí: estructuras, TTL, `MULTI/EXEC`, `INFO` | — |
| Atomicidad bajo concurrencia | Sí, en un nodo (los comandos se ejecutan de a uno) | Atomicidad entre nodos |
| Persistencia ante reinicio | Sí (`12_persistencia.log`) | Recuperación ante pérdida del disco o del equipo |
| Conmutación ante falla (*failover*) | No | Qué pasa si cae el nodo y otro lo reemplaza |
| Distribución de claves | No | Reparto en slots entre varios nodos |
| Consistencia entre réplicas | No | Retraso de réplicas, lecturas desactualizadas |
| Límite de RAM de una máquina | Solo el `maxmemory` de laboratorio | El techo real de una instancia grande |

## 5. Pasos futuros de escala

La Clase 8 distingue tres topologías; el camino natural, de menor a mayor complejidad:

| Paso | Qué agrega | Qué resuelve | Trade-off |
| :--- | :--- | :--- | :--- |
| 1. Primary + réplicas (con Sentinel para monitoreo y conmutación) | Copias para lectura y recuperación ante caída del primary | Continuidad del acceso; es la **réplica asincrónica regional** que fijó el Hito 3 para sesiones | Las réplicas pueden estar brevemente atrasadas; las escrituras siguen concentradas en el primary |
| 2. Redis Cluster | Reparte las claves en slots entre nodos | Capacidad de memoria y de escritura más allá de una máquina; es el **reparto por usuario** del Hito 3 | Una operación con varias claves exige que caigan en el mismo slot. Este modelo ya opera sobre una sola clave por unidad, así que no necesita *hash tags* |
| 3. Separar instancias de caché y de sesiones (**decisión de diseño**, §3.3) | Una instancia de caché con `allkeys-lru` y otra de sesiones con `noeviction` | Evita que la presión de la caché evicte sesiones vigentes | Más piezas que operar y dos límites de memoria que vigilar |

Medidas previas a escalar: medir los **bytes por sesión** para dimensionar la RAM, revisar la
frecuencia de snapshot y la política de sincronización de AOF según la pérdida tolerable, y
definir la consolidación de votos en una fuente durable. Ninguno de estos pasos se implementó ni se
probó en este hito.
