# Patrones de acceso — Caché de usuarios y sesiones (Hito 7)

**Grupo N.º 8** · Redis · Fixture 2030

Este documento cubre los apartados *Problema de concurrencia* y *Patrones de acceso* del análisis
(RF2). Se redactó **antes** de fijar las claves: el modelo de [`modelo_clave_valor.md`](modelo_clave_valor.md)
sale de estas preguntas, no al revés (RNF4).

## 1. Problema de concurrencia

### 1.1 Qué se necesita

La plataforma debe atender a millones de personas que consultan partidos, equipos y resultados al
mismo tiempo, y mantener una sesión viva mientras cada persona navega. Tres problemas distintos
caen sobre el mismo módulo:

1. **Sesiones.** Cada usuario conectado tiene un estado temporal que se valida en *cada* petición
   y que debe desaparecer solo cuando el usuario se queda inactivo. El Hito 1 lo diagnosticó como
   *Sesiones*: **2-3 M simultáneas**, crecimiento **explosivo** y con **TTL**, acceso de lectura y
   escritura (validar token). El Hito 2 asignó el modelo clave/valor (Redis, 4,15 en la matriz) y el
   Hito 3 fijó la postura **AP** con reparto por usuario.
2. **Lecturas repetidas.** Miles de personas piden la ficha del *mismo* partido o del *mismo* equipo.
   Esos datos viven en otro módulo (MongoDB para equipos, Hito 4; grafo de Neo4j para partidos,
   Hito 5). Si cada lectura llegara a la fuente de verdad, esa fuente absorbería un tráfico
   repetido e innecesario.
3. **Actualizaciones simultáneas.** Durante un partido muchas personas incrementan el mismo
   contador de visitas o votan al mismo jugador. Si dos clientes leen el mismo valor y escriben
   cada uno el suyo, se pierde una actualización.

### 1.2 Supuestos de carga

Estos valores **no están medidos en el laboratorio**: son los de la especificación y supuestos
del equipo para dimensionar el problema. Lo que sí se midió está en [`rendimiento.md`](rendimiento.md).

| Supuesto | Valor | Origen |
| :--- | :--- | :--- |
| Sesiones simultáneas | 2-3 M | Hito 1 |
| Solicitudes totales en picos | 100.000+ por segundo | Especificación (Hitos 2 y 3) |
| Objetivo de respuesta | p95 < 100 ms | Especificación (Hitos 2 y 3) |
| Frecuencia de actividad de un usuario conectado | Una petición autenticada cada ≈ 30 s | **Supuesto del equipo** |
| Renovaciones de sesión que se derivan | ≈ 67.000 a 100.000 por segundo (2-3 M ÷ 30 s) | Derivado del supuesto anterior |
| Equipos / partidos del laboratorio | 64 equipos / 96 partidos | CSV del Hito 5 (fase de grupos) |
| Relación lectura / escritura de sesiones | Lectura (validar) en cada petición; escritura (renovar) en cada petición válida | Diseño |

> Un detalle importante: validar una sesión es una lectura, pero **renovarla es una escritura**.
> Por eso las sesiones no son un caso de "mucha lectura, poca escritura": cada petición válida
> escribe. Esto condiciona la elección de estructura (ver §3 de `modelo_clave_valor.md`).

### 1.3 Qué NO resuelve este módulo

Redis aquí guarda **estado transitorio y copias de acceso rápido**. No reemplaza a los módulos
anteriores: el perfil persistente del usuario sigue en MongoDB (Hito 2), la ficha de equipos y
jugadores en MongoDB (Hito 4), las relaciones en Neo4j (Hito 5) y los comentarios masivos en
Cassandra (Hito 6). Toda copia en Redis debe poder reconstruirse desde su fuente de verdad.

## 2. Patrones de acceso

Cada patrón indica quién lo usa, con qué dato se localiza, qué respuesta recibe, cuánto se lee y
se escribe, qué es temporal y qué pertenece a una fuente externa, y por qué se eligió la estructura.

| ID | Pregunta | Quién | Entrada | Operación y respuesta | Frecuencia | Qué es temporal / fuente de verdad | Estructura y por qué |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **P1** | ¿Se puede abrir una sesión para este usuario? | Servicio de autenticación | `sesionId` nuevo + datos del usuario | Crear la sesión con su vencimiento. Responde "sesión creada" | Escritura baja-media (una por inicio de sesión) | **Toda la sesión es temporal.** El perfil permanente está en MongoDB | **Hash**: la sesión tiene varios atributos que se leen y cambian por separado |
| **P2** | ¿Esta sesión es válida? | API, en cada petición | `sesionId` | Leer `estado` y `usuario_id`. Responde válida / no válida | **Lectura muy alta** (cada petición) | Temporal | **Hash** + `HGET`: se leen solo los campos necesarios |
| **P3** | Registrar actividad y mantener viva la sesión | API, tras una petición válida | `sesionId` | Actualizar último acceso, sumar una acción y renovar el TTL, como una unidad | **Escritura muy alta** (una por petición válida) | Temporal | **Hash** + `HINCRBY` + `EXPIRE` en `MULTI/EXEC` |
| **P4** | Cerrar o suspender el acceso | Usuario (logout) o administración | `sesionId` | Eliminar la sesión, o cambiar su `estado` a suspendida | Baja | Temporal | **Hash**: `DEL` para cerrar; `HSET estado` para suspender sin borrar |
| **P5** | ¿Cuál es la ficha de este partido? | Aplicación web/móvil | código de partido (`F2030-001`) | Devolver la ficha completa. Responde el JSON del partido | **Lectura muy alta**; escritura solo en un miss; actualización cuando cambia el resultado (pocas veces por partido) | **Copia temporal.** Fuente: grafo de Neo4j (Hito 5) | **String** con JSON y TTL: se sirve completa, nunca se modifica por partes |
| **P6** | ¿Cuál es la ficha de este equipo? | Aplicación web/móvil | código de equipo (`ARG`) | Devolver la ficha del equipo | Lectura alta; casi nunca cambia | **Copia temporal.** Fuente: MongoDB (Hito 4) | **String** con JSON y TTL más largo |
| **P7** | ¿Cuántas visitas tiene este partido? | API (suma), portada (lee) | código de partido | Sumar 1 y devolver el total | **Escritura muy alta** en un partido popular | Dato derivado de la actividad; **se conserva** (ver `ciclo_de_vida_e_invalidacion.md` §4) | **String** entero + `INCR`: la suma es atómica en el servidor |
| **P8** | ¿Quién va ganando la votación "figura del partido"? | Usuarios (votan), pantalla del partido (lee el Top N) | código de partido, código de jugador | Sumar un voto y devolver el Top 5 ordenado | Escritura alta; lectura media | Dato de la actividad; **se conserva** | **Sorted Set**: `ZINCRBY` suma el voto y `ZREVRANGE` devuelve el Top N ya ordenado |

### 2.1 Cómo se localiza cada dato

Ninguna operación necesita buscar: la aplicación **construye la clave** con el contexto que ya tiene.

| Patrón | Contexto disponible | Clave que se construye |
| :--- | :--- | :--- |
| P1-P4 | Identificador de sesión que trae la petición | `sesion:<sesionId>` |
| P5 | Código de partido de la URL | `cache:partido:<codigo>` |
| P6 | Código de equipo de la URL | `cache:equipo:<codigo>` |
| P7 | Código de partido | `partido:<codigo>:visitas` |
| P8 | Código de partido | `encuesta:<codigo>:figura` |

### 2.2 Qué patrones se descartaron

No se usaron **Lists** ni **Sets**. Ningún patrón declarado necesita una secuencia por inserción
ni una pertenencia sin orden, y el enunciado exige que cada estructura esté justificada por una
operación concreta (RNF4). Por ejemplo, una lista de "actividad reciente del usuario" o un Set de
"usuarios conectados al partido" serían razonables, pero el equipo no los declaró como patrón, así
que no se incluyen.
