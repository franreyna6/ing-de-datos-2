# Ciclo de vida e invalidación — Caché de usuarios y sesiones (Hito 7)

**Grupo N.º 8** · Redis · Fixture 2030

Cubre los apartados *Ciclo de vida* y *Fuente de verdad y caché* del análisis (RF4, RF6, RF7,
RNF6). Cada dato temporal tiene una decisión explícita de expiración, renovación, invalidación o
conservación. La evidencia está en `docs/evidencia/logs/` (se cita en cada sección).

## 1. Sesiones

### 1.1 Reglas

| Pregunta | Decisión |
| :--- | :--- |
| ¿Cuándo es válida una sesión? | Cuando **la clave existe** (`TTL` distinto de -2) **y** el campo `estado` vale `activa`. |
| ¿Qué evento renueva la actividad? | Cualquier petición autenticada y válida de la sesión (consultar un partido, votar). Una petición con sesión suspendida o inexistente **no** renueva. |
| ¿Qué se hace al renovar? | Una unidad `MULTI/EXEC`: `HSET ultimo_acceso`, `HINCRBY acciones 1` y `EXPIRE 1800`. |
| ¿Cuánto dura? | **1800 s (30 minutos) de inactividad**, contados desde la última renovación. |
| ¿Hay una vida máxima absoluta? | No en el laboratorio. Una sesión activa se renueva indefinidamente. Si se pidiera un tope, se compararía `creada_en` en la aplicación; es una decisión pendiente, no implementada. |
| ¿Cómo se elimina una sesión vencida? | Por el **mecanismo nativo de expiración de Redis**. No existe ningún proceso que recorra las sesiones (el enunciado lo prohíbe). |

### 1.2 Por qué 1800 s

La duración se justifica con cuatro criterios, no con un valor copiado:

1. **Ritmo de uso.** Quien sigue un partido interactúa con frecuencia; una ventana de 30 minutos
   tolera pausas razonables (por ejemplo un entretiempo de unos 15 minutos) sin obligar a iniciar
   sesión de nuevo.
2. **Memoria.** Con 2-3 M de sesiones simultáneas (Hito 1), cada minuto extra de retención de una
   sesión inactiva ocupa RAM sin aportar nada. Una ventana corta libera el estado rápido.
3. **Seguridad.** Una sesión abandonada en un dispositivo ajeno queda expuesta solo mientras
   no vence.
4. **Costo de equivocarse.** Si una sesión vence antes de tiempo, la consecuencia es una
   reautenticación, que el Hito 2 ya aceptó como trade-off frente al costo de la latencia.

### 1.3 Ciclo completo

| Etapa | Operación | Resultado esperado | Evidencia (`03_sesiones.log`) |
| :--- | :--- | :--- | :--- |
| Crear | `MULTI` · `HSET` · `EXPIRE 1800` · `EXEC` | Hash creado con TTL 1800. Es atómico: nunca queda una sesión sin vencimiento | Bloque 1 |
| Recuperar / validar | `HGET usuario_id`, `HGET estado`, `TTL` | Campos y TTL restante | Bloque 2 |
| Actualizar un atributo | `HSET rol ...` | El contenido cambia y el **TTL no se renueva** | Bloques 3 y 4 |
| Renovar | `MULTI` · `HSET` · `HINCRBY` · `EXPIRE 1800` · `EXEC` | TTL vuelve a 1800 | Bloque 5 |
| Suspender | `HSET estado suspendida` | Se conserva la clave; la aplicación niega el acceso y no renueva | Bloque 6 |
| Vencer | (nada: lo hace Redis) | `TTL` = -2 y lecturas vacías | Bloque 7 |
| Cerrar / invalidar | `DEL sesion:<id>` | Devuelve 1; repetir devuelve 0 (es inocuo) | Bloque 8 |
| Sesión inexistente | `HGETALL`, `TTL` | Respuesta vacía y `TTL` = -2 | Bloque 9 |

Un detalle que el log demuestra: actualizar un campo con `HSET` **no extiende la vida de la
sesión** (bloque 4), por eso la renovación es una operación explícita y separada.

### 1.4 Comportamiento ante una sesión ausente o un servidor caído

| Situación | Qué ve la aplicación | Qué debe hacer |
| :--- | :--- | :--- |
| La sesión venció o se cerró | `TTL` = -2, `HGETALL` vacío | Tratar la petición como **no autenticada** y pedir un nuevo inicio de sesión. **No se reconstruye** la sesión desde otra fuente: una sesión es estado temporal |
| La sesión fue **evictada** por presión de memoria | Igual que una sesión vencida | Igual: reautenticar (ver `memoria_y_escalabilidad.md`) |
| La sesión está suspendida | Existe, con `estado` ≠ `activa` | Negar el acceso, informar la causa y no renovar |
| Redis no está disponible | Error de conexión (se muestra en `04_cache.log`, bloque 7) | No se pueden validar sesiones: las operaciones protegidas se niegan y se pide reintentar. Es la consecuencia de la postura AP del Hito 3: se prioriza continuar sobre garantizar sesiones |

### 1.5 Qué pasa con las sesiones si se reinicia el nodo

El Compose activa **AOF** (`--appendonly yes`) y **snapshot RDB** (`--save 60 1`) con los datos en
`~/docker/data/redis`. En un reinicio normal las sesiones **se conservan y su TTL sigue corriendo**
(no se reinicia ni se pierde). Se comprobó con `docker compose restart redis`
(`12_persistencia.log`). Una caída abrupta puede perder los últimos segundos de escrituras
(política de sincronización de AOF, Clase 8). Esto responde la pregunta que dejó abierta el Hito 2
sobre la política ante la caída de un nodo de sesiones: en el laboratorio se **persiste para
sobrevivir a un reinicio**, y se **acepta** perder lo que no llegó a disco, con reautenticación
como costo. La réplica asincrónica regional del Hito 3 queda como paso futuro (no se prueba en un
solo nodo).

## 2. Caché de la ficha de partido (Cache-Aside)

| Aspecto | Decisión |
| :--- | :--- |
| Fuente de verdad | Grafo de **Neo4j** (Hito 5, nodo `Partido`). En el laboratorio la fuente se simula leyendo `data/origen/partidos.csv`, de donde salió |
| Clave y valor | `cache:partido:<codigo>` → String con el JSON de la ficha |
| Condición de **cache hit** | La clave existe: `GET` devuelve un valor |
| Camino ante un **cache miss** | 1) `GET` devuelve vacío. 2) La aplicación lee la fuente de verdad. 3) Guarda la copia con `SET ... EX 300`. 4) Responde |
| Momento de actualizar / invalidar | **Justo después** de que cambia la fuente de verdad (por ejemplo, se corrige el acta de un partido): el flujo de escritura ejecuta `DEL cache:partido:<codigo>`. El siguiente lector provoca un miss y recarga el valor nuevo |
| Período máximo de permanencia de una copia | **300 s**. Es el tope si una invalidación fallara, no la estrategia principal |
| Si Redis no tiene la clave | Es un miss normal: se consulta la fuente |
| Si Redis no está disponible | Se consulta directamente la fuente de verdad (modo degradado: más lento, pero correcto) |

### 2.1 Coherencia: por qué el TTL solo no alcanza

Si solo se confiara en el TTL, tras corregir un resultado los usuarios podrían ver el valor
viejo hasta 5 minutos. Por eso la estrategia es **invalidar al escribir** (`DEL`) y dejar el TTL
como límite del peor caso. El log `04_cache.log` (bloque 4) muestra el flujo completo: `DEL`,
`GET` vacío, recarga con el valor corregido (2-1) y nuevo TTL de 300 s.

### 2.2 Riesgo residual (documentado, no eliminado)

Existe una carrera inevitable con este patrón. Un lector A provoca un miss y lee la fuente
(valor viejo); justo entonces el escritor actualiza la fuente y ejecuta `DEL` (que no encuentra
nada que borrar); después A guarda el valor viejo en la caché. Resultado: una copia obsoleta que
dura **como máximo 300 s**. Se acepta porque la ventana es muy estrecha, el dato se corrige solo
al vencer el TTL y el costo es ver un resultado desactualizado por pocos minutos. Mitigaciones:
ejecutar siempre el `DEL` **después** de actualizar la fuente (nunca antes) y, si se necesitara
menos tolerancia durante un partido en juego, usar un TTL más corto en esos partidos (no
implementado).

### 2.3 Regla: toda copia se escribe con `EX`

`SET` sin `EX` elimina el TTL anterior y deja una copia eterna. El bloque 6 de `04_cache.log` lo
demuestra con una clave de prueba (`TTL` pasa de 100 a -1). Por eso el módulo escribe **siempre**
`SET ... EX`, y `auditoria_ttl.sh` verifica que ninguna clave temporal quede sin TTL.

## 3. Caché de la ficha de equipo

| Aspecto | Decisión |
| :--- | :--- |
| Fuente de verdad | Colección `equipos` de **MongoDB** (Hito 4); simulada con `equipos.csv` |
| Clave | `cache:equipo:<codigo>` (String JSON) |
| TTL | **3600 s**: nombre, confederación, ranking y grupo casi no cambian durante el torneo |
| Invalidación | `DEL cache:equipo:<codigo>` cuando se edita el equipo en MongoDB. El TTL de 1 hora es el tope |
| Miss / Redis caído | Igual que el partido: se consulta MongoDB |

## 4. Datos que se conservan (sin TTL) y por qué

El enunciado acepta "conservación" como decisión de ciclo de vida siempre que sea explícita (RNF6).

| Clave | Decisión | Razón |
| :--- | :--- | :--- |
| `partido:<codigo>:visitas` | Conservar | Hay un solo contador por partido (96 en el laboratorio). El volumen está **acotado por el dominio**: no crece con el número de usuarios |
| `encuesta:<codigo>:figura` | Conservar | Una votación por partido, con pocos candidatos. También acotada por el dominio |

Dos consecuencias que se asumen:

- Las claves sin TTL **no son candidatas a evicción** bajo `volatile-lru`: la presión de memoria
  nunca descarta votos ni visitas (ver `memoria_y_escalabilidad.md`).
- En este laboratorio Redis es el **único** lugar donde viven esos contadores. Son métricas de
  participación, no datos de negocio con integridad exigida. En un despliegue real, el resultado
  final de una votación se consolidaría en una fuente durable al cerrar el partido; esa
  consolidación queda fuera del alcance del hito.

## 5. Resumen: decisión de ciclo de vida por clave (RNF6)

| Clave | Expiración | Renovación | Invalidación | Conservación |
| :--- | :--- | :--- | :--- | :--- |
| `sesion:<id>` | TTL 1800 s | Con cada actividad válida | `DEL` (cierre), `HSET estado` (suspensión) | No |
| `cache:partido:<c>` | TTL 300 s | No (se recarga tras un miss) | `DEL` al cambiar la fuente | No |
| `cache:equipo:<c>` | TTL 3600 s | No | `DEL` al cambiar la fuente | No |
| `partido:<c>:visitas` | Sin TTL | — | — | **Sí** (acotado) |
| `encuesta:<c>:figura` | Sin TTL | — | — | **Sí** (acotado) |
| `prueba:*` | TTL 600 s | No | `limpieza.sh` | No |

`07_auditoria_ttl.log` verifica esta tabla con `SCAN`: 0 claves temporales sin TTL y 0 claves
conservadas con TTL.

## 6. Clave ausente: qué hace la aplicación según el tipo

| Clave | Si no está | Efecto |
| :--- | :--- | :--- |
| `sesion:<id>` | Reautenticar | Pérdida de estado temporal, aceptada |
| `cache:*` | Miss: leer la fuente y recargar | Solo una lectura más lenta |
| `partido:<c>:visitas` | `INCR` crea la clave en 1 | El conteo empieza de cero |
| `encuesta:<c>:figura` | `ZINCRBY` crea el miembro; el Top N queda vacío | La votación empieza de cero |
