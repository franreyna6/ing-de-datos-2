# Health, readiness y diagnóstico por dependencia

**Grupo 8** · Fixture 2030 · Hito 11 (sección 5.6, RNF5, RNF12)

## 1. Qué hay hoy en la API del Hito 10 (observado, sin modificar)

`GET /salud` ejecuta **en cada llamada** el `verificar()` de los seis adaptadores, uno detrás de
otro, y responde siempre **HTTP 200** con un booleano por fuente:

```json
{"api": "ok", "dependencias": [{"fuente": "mongodb", "disponible": true}, …]}
```

| Observación | Evidencia | Consecuencia |
| :--- | :--- | :--- |
| Siempre 200, aunque una fuente esté caída | Redis detenido: `200` con `redis=false` | Un balanceador no puede usarlo como readiness |
| Secuencial: el tiempo es la suma de las seis pruebas | 6.185 ms (inicial, con IPv6 lento e IRIS sin credencial), 2.188 ms (final), 6.013 ms (Redis detenido) | Costoso para consultarlo seguido; puede superar el timeout de un probe |
| Booleano sin causa | IRIS `false` por credencial expirada; InfluxDB `false` por H6 | No distingue caída, timeout, credencial, contexto ni defecto de la API |
| `verificar()` prueba otra cosa que el caso de uso | Final: `iris = true`, pero `/detalle` da 503 (H7). Inicial: `mongodb = true`, pero `/equipos/ARG` da 404 (H1) | “Verde” no garantiza el caso de uso |
| Abre conexiones en frío | La primera conexión del driver de Cassandra tarda ~1,6 s | El primer `/salud` tras un reinicio es el más lento |

La matriz de este hito ([`matriz_de_conectividad.md`](matriz_de_conectividad.md)) cubre ese hueco
desde afuera de la API. La propuesta siguiente lo cubriría desde adentro.

## 2. Propuesta (no implementada: el alcance acordado fue no modificar la API)

### Endpoints

| Endpoint | Pregunta | Qué consulta | Status | Uso |
| :--- | :--- | :--- | :--- | :--- |
| `GET /salud/liveness` | ¿El proceso de la API está vivo? | **Nada externo**: responde desde memoria | `200` siempre que el proceso atienda | Reiniciar el proceso si no responde |
| `GET /salud/readiness` | ¿Puede recibir tráfico? | El **último estado en caché** de las dependencias críticas (no las consulta en el request) | `200` si todas las críticas están `up`; `503` si alguna está `down` | Sacar la instancia del balanceador |
| `GET /salud/dependencias` | ¿Cómo está cada producto y por qué? | El estado en caché de las seis, con capa, causa resumida, latencia y antigüedad | `200` siempre (es diagnóstico, no decisión) | Operación y soporte |

### Estados (significado definido)

| Estado | Significado en la API |
| :--- | :--- |
| `up` | la prueba configurada para esa fuente terminó correctamente dentro de su timeout |
| `down` | se intentó la prueba y falló (red, protocolo, credencial, contexto u operación) |
| `degraded` | la API funciona, pero con una dependencia **no crítica** afectada (aplica al estado global) |
| `unknown` | todavía no hay resultado (arranque) o el último tiene más de 3 ciclos de antigüedad |
| `not_configured` | falta configuración obligatoria (p. ej. `INFLUXDB3_TOKEN`): no se intenta conectar |

Cada `down` lleva `capa` (`tcp`, `autenticacion`, `contexto`, `operacion`, …) y un `motivo`
corto sin detalle técnico (que va al log), igual que la matriz de este hito.

### Prueba por dependencia: la operación del caso de uso, acotada

Lección de H1 y H7: el chequeo debe ejecutar **la misma operación que el adaptador**, con un
parámetro fijo y un límite, no un `SELECT 1`.

| Fuente | Prueba propuesta | Costo medido de la lectura nativa equivalente (final) | Crítica para readiness |
| :--- | :--- | ---: | :---: |
| MongoDB | `find_one` del adaptador sobre un equipo fijo, con proyección | ~1 ms | sí |
| Neo4j | `MATCH (p:Partido {codigo:$c}) … LIMIT 1` | ~8 ms | sí |
| Cassandra | lectura de una partición fija con `LIMIT 1` (sesión ya abierta) | ~15 ms | no |
| Redis | `HMGET` de una clave de control con TTL largo (o `PING` + `TYPE`) | ~1 ms | sí (sesiones) |
| InfluxDB | consulta del adaptador sobre una ventana fija de 1 minuto | ~8 ms | no |
| IRIS | SQL del adaptador para un partido fijo | ~1 ms | no |

“Crítica” es una decisión de producto: sin sesiones (Redis) ni equipos o partidos (Mongo, Neo4j),
la aplicación no puede atender su flujo principal. Comentarios, estadísticas y detalle pueden
degradarse (503 en su ruta, como se vio en la falla controlada) sin sacar la instancia de servicio.

### Frecuencia, timeout y costo del chequeo profundo

- **Frecuencia:** una tarea en segundo plano cada **30 s**, que actualiza la caché. Ningún request
  normal consulta las bases para saber su estado (5.6: “no consultar indiscriminadamente”).
- **Timeout:** **1 s por dependencia**, las seis **en paralelo**: el ciclo dura como máximo ~1 s,
  en lugar de la suma secuencial que hoy llega a 6 s.
- **Costo:** seis lecturas acotadas cada 30 s, es decir 0,2 operaciones por segundo y por
  instancia. Con los costos medidos, menos de 40 ms de trabajo por ciclo en total. Despreciable
  frente al tráfico; aun así se registra como métrica (duración por dependencia y ciclo).
- **Arranque:** hasta el primer ciclo completo, las dependencias están en `unknown` y readiness
  devuelve `503` (la instancia no recibe tráfico antes de saber si puede atenderlo).
- **Sin reintentos dentro del ciclo:** si una prueba falla, se informa `down` hasta el próximo
  ciclo. Nada de reintentos ilimitados (RNF12).
- **Histeresis:** pasar de `up` a `down` en readiness solo después de **2 ciclos** fallidos
  seguidos, para no sacar la instancia del balanceador por un error aislado.

### Relación con los errores de las rutas (RF18)

El estado en caché permite responder antes y con más precisión:

| Situación | Hoy | Propuesto |
| :--- | :--- | :--- |
| Fuente `down` en caché | intenta conectar y falla tras el timeout | `503 DEPENDENCY_UNAVAILABLE` inmediato, con `detalles.fuente` y `detalles.capa` |
| Timeout durante la operación | `503` | `504 DEPENDENCY_TIMEOUT` |
| Error de modelo u operación (H1, H2, H6, H7) | `404`, `500` o `503` | `500 INTERNAL_ERROR` (no es una caída) y la fuente sigue `up` |
| `not_configured` | `503` | `503` con `detalles.motivo = "no_configurado"` |
