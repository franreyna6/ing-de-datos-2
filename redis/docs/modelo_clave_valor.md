# Modelo clave/valor — Caché de usuarios y sesiones (Hito 7)

**Grupo N.º 8** · Redis · Fixture 2030

Derivado de [`patrones_de_acceso.md`](patrones_de_acceso.md). Cada clave responde a uno o más
patrones y a operaciones concretas de lectura, escritura, actualización o vencimiento (RNF4).

## 1. Convención de nomenclatura (RNF5)

```
<dominio>:<identificador>[:<atributo>]
```

| Regla | Detalle |
| :--- | :--- |
| Separador | `:`. Es una convención humana; Redis no crea carpetas ni jerarquías. |
| Minúsculas | Todos los prefijos van en minúsculas y sin acentos. |
| Identificadores estables | Se usan los **códigos** del Fixture (`F2030-001`, `ARG`), que no cambian si se edita un nombre. |
| Alcance explícito | El nombre dice a qué contexto pertenece: `partido:F2030-001:visitas` es de ese partido, no global. |
| Sin secretos | Ninguna clave contiene un token ni datos personales. El identificador de sesión es opaco (en el laboratorio `S0001`...; en producción sería aleatorio y se trataría como dato sensible). |
| Sin `KEYS *` | Para inspeccionar se usa `SCAN` con cursor (RNF8). |
| Instancia dedicada | No se antepone `fixture2030:` porque esta instancia es exclusiva del módulo. Si se compartiera con otros sistemas, se antepondría ese prefijo. |

### 1.1 Prefijos y alcance

| Prefijo | Qué contiene | Alcance | Ciclo de vida |
| :--- | :--- | :--- | :--- |
| `sesion:` | Estado de una sesión de usuario | Una clave por sesión | **Temporal**, TTL 1800 s con renovación |
| `cache:partido:` | Copia de la ficha de un partido | Una clave por partido | **Temporal**, TTL 300 s + invalidación |
| `cache:equipo:` | Copia de la ficha de un equipo | Una clave por equipo | **Temporal**, TTL 3600 s + invalidación |
| `partido:` | Contadores de un partido (`:visitas`) | Una clave por partido | **Conservar** (acotado por el dominio) |
| `encuesta:` | Votación de un partido (`:figura`) | Una clave por partido | **Conservar** (acotado por el dominio) |
| `prueba:` | Claves de las pruebas de concurrencia, medición y presión | Solo pruebas | **Temporal**, TTL 600 s |

## 2. Claves, estructuras y operaciones

| Clave | Estructura | Contenido | Patrón | Operaciones | TTL |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `sesion:<sesionId>` | **Hash** | Atributos de la sesión (§2.1) | P1-P4 | Crear: `HSET` + `EXPIRE` (en `MULTI/EXEC`). Leer: `HGET`/`HGETALL`. Renovar: `HSET`, `HINCRBY`, `EXPIRE` (en `MULTI/EXEC`). Suspender: `HSET estado`. Cerrar: `DEL` | 1800 s (se renueva) |
| `cache:partido:<codigo>` | **String** (JSON) | Ficha del partido: código, fecha, fase, grupo, goles y sede | P5 | Leer: `GET`. Cargar tras un miss: `SET ... EX 300`. Invalidar: `DEL` | 300 s |
| `cache:equipo:<codigo>` | **String** (JSON) | Ficha del equipo: nombre, confederación, ranking, anfitrión, grupo | P6 | `GET`, `SET ... EX 3600`, `DEL` | 3600 s |
| `partido:<codigo>:visitas` | **String** (entero) | Contador de visitas | P7 | `INCR`, `INCRBY`, `GET` | sin TTL |
| `encuesta:<codigo>:figura` | **Sorted Set** | Miembro = código de jugador; puntaje = votos | P8 | `ZINCRBY`, `ZADD`, `ZREVRANGE ... WITHSCORES` | sin TTL |

### 2.1 Atributos de la sesión (RF5)

| Campo | Ejemplo | Qué es | Quién lo cambia |
| :--- | :--- | :--- | :--- |
| `usuario_id` | `U0001` | Usuario asociado a la sesión (referencia al perfil en MongoDB) | Solo al crear |
| `rol` | `fan` | Rol de acceso: `fan`, `periodista` o `admin` | Al crear (y administración) |
| `estado` | `activa` | Estado de acceso: `activa` o `suspendida` | Administración |
| `creada_en` | `2030-06-14T17:35:19Z` | Momento de creación (UTC) | Solo al crear |
| `ultimo_acceso` | `2030-06-14T19:33:43Z` | Momento de la última actividad válida (UTC) | Cada renovación |
| `acciones` | `14` | Contador de acciones realizadas en la sesión | Cada renovación (`HINCRBY`) |

La **regla de validez** (qué hace a una sesión válida) está en
[`ciclo_de_vida_e_invalidacion.md`](ciclo_de_vida_e_invalidacion.md) §1.1. El TTL **no es un campo**:
es un metadato de la clave completa.

## 3. Por qué cada estructura

**Sesión → Hash, no String con JSON.** Una petición válida cambia dos cosas de la sesión: el
último acceso y el contador de acciones. Con un String JSON habría que leer todo, modificarlo en la
aplicación y volver a escribirlo, y dos peticiones simultáneas de la misma sesión se pisarían
(es el antipatrón leer-modificar-escribir que se mide en `concurrencia.md`). Con un Hash, `HSET`
y `HINCRBY` modifican un campo dentro del servidor, y el TTL se asocia a la clave completa, no a
cada campo.

**Caché de fichas → String JSON, no Hash.** La ficha se pide siempre completa, se reemplaza
entera cuando cambia la fuente y nunca se modifica por partes. Un String con el JSON es lo más
simple y evita reconstruir un objeto campo a campo en cada lectura.

**Visitas → String entero.** `INCR` suma sobre el valor dentro del servidor, sin leerlo antes.

**Votos → Sorted Set.** Cada voto es un `ZINCRBY` sobre el candidato, y el Top N se recupera ya
ordenado con `ZREVRANGE`. Con otra estructura habría que traer todos los votos y ordenarlos en la
aplicación en cada lectura.

## 4. Todas las operaciones de una unidad tocan una sola clave

Cada `MULTI/EXEC` del módulo opera sobre **una única clave** (el Hash de una sesión). Esto importa
porque, en una topología con Redis Cluster, una operación con varias claves solo es posible si
todas caen en el mismo slot (los *hash tags* de la Clase 8 sirven para eso). Con este modelo no
hace falta: el reparto por usuario del Hito 3 es compatible con el diseño sin forzar claves al
mismo slot. El laboratorio es de un solo nodo y no prueba Cluster (ver
[`memoria_y_escalabilidad.md`](memoria_y_escalabilidad.md)).
