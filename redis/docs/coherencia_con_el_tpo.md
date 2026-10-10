# Coherencia con el TPO — Caché de usuarios y sesiones (Hito 7)

**Grupo N.º 8** · Redis · Fixture 2030

Cubre el apartado *Coherencia con el TPO*: la relación del módulo con los requisitos de
rendimiento y con los módulos implementados en hitos anteriores.

## 1. Relación con los hitos anteriores

| Hito | Qué definió | Cómo se relaciona con este módulo |
| :--- | :--- | :--- |
| 1 — Análisis | *Sesiones*: 2-3 M simultáneas, crecimiento explosivo con TTL, lectura y escritura | Es el problema que resuelve el módulo (`patrones_de_acceso.md` §1) |
| 2 — Matriz de decisión | Sesiones → clave/valor (Redis, 4,15). Trade-off aceptado: se pueden perder sesiones activas y se reautentica. Pregunta abierta: política ante la caída de un nodo de sesiones | Se respeta el trade-off (`ciclo_de_vida_e_invalidacion.md` §1.4) y se responde la pregunta para el laboratorio: persistir con AOF + RDB para sobrevivir a reinicios y aceptar la pérdida de lo no persistido (§1.5) |
| 3 — Arquitectura distribuida | Sesiones: postura **AP**, reparto por usuario, réplica asincrónica regional; validación por tasa de reautenticación y disponibilidad | El modelo opera sobre una sola clave por unidad, compatible con el reparto por usuario; ante un servidor caído se niega el acceso protegido y se sirve el contenido público desde su fuente de verdad (modo degradado). La réplica regional queda como paso futuro (`memoria_y_escalabilidad.md` §5) |
| 4 — MongoDB | Perfiles de usuario y fichas de equipos/jugadores | **Fuente de verdad** de la ficha de equipo (`cache:equipo:`) y del perfil asociado a `usuario_id`. La caché no la reemplaza |
| 5 — Neo4j | Grafo de partidos, equipos y participaciones; CSV de origen | **Fuente de verdad** de la ficha de partido (`cache:partido:`); sus CSV son la fuente simulada y el origen de los candidatos de las encuestas |
| 6 — Cassandra | Comentarios masivos | No se cachean ni se duplican aquí: Redis no guarda comentarios. Las visitas y votos son métricas distintas de los comentarios |

Redis queda como **capa de estado transitorio y de lectura rápida delante** de las demás. Ninguna
clave de Redis es la única fuente de un dato de negocio, salvo los contadores de participación
declarados en `ciclo_de_vida_e_invalidacion.md` §4.

## 2. Requisitos de rendimiento del TPO: qué se demuestra y qué no

Los objetivos de la especificación (citados en los Hitos 2 y 3) son 2-3 M de usuarios simultáneos,
más de 100.000 solicitudes por segundo, p95 < 100 ms y disponibilidad de 99,99 %.

| Requisito | ¿Lo demuestra este módulo? | Qué sí aporta |
| :--- | :--- | :--- |
| 2-3 M de sesiones simultáneas | **No.** Se cargaron 200 sesiones | Un modelo de sesión que libera su estado por inactividad con expiración nativa, y la política de memoria que se aplica al llegar al límite |
| 100.000+ solicitudes por segundo | **No.** Se midió un cliente simple en un nodo (≈ 930-8.400 comandos/s según la operación, dominado por el cliente) | Evidencia de que las operaciones críticas son comandos únicos o unidades `MULTI/EXEC` sobre una clave, sin recorridos ni uniones |
| p95 < 100 ms | **No se midieron percentiles** | El camino de un hit es una sola lectura por clave conocida |
| Disponibilidad 99,99 % | **No.** Un solo nodo, sin réplicas | Qué pasa cuando el servidor no está (modo degradado) y cuál es el siguiente paso (réplicas y Sentinel) |
| Consistencia de datos replicados | **No** (no hay réplicas) | La estrategia de coherencia entre caché y fuente de verdad (invalidar al escribir, TTL como tope) |

Lo que el laboratorio **sí** valida es la **corrección** del diseño: ciclo de vida de sesiones,
caché con invalidación, atomicidad bajo concurrencia y comportamiento ante límite de memoria, todo
con evidencia reproducible. La **escala** solo se puede afirmar con una prueba de carga sobre una
topología distribuida, que está fuera del alcance de este hito.
