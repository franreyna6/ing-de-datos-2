# Matriz de integridad

Reglas que la base debe cumplir, qué mecanismo las garantiza y dónde se demuestran. La pregunta del enunciado —**¿qué ocurre con los eventos si un partido se borra?**— se responde en la primera fila: se borran con él, porque son hijos en una relación padre-hijo.

## 1. Borrados

| Se borra | Efecto sobre los relacionados | Mecanismo | Demostración |
| :--- | :--- | :--- | :--- |
| Partido | Sus **Eventos** y **Designaciones** se borran en cascada. Los jugadores, árbitros, equipos y la sede no se tocan; sus colecciones dejan de incluir esos hijos. | Relación padre-hijo (`Cardinality = children` / `parent`) | Bloque 7, punto 1: conteo de hijos antes (2 y 3) y después (0 y 0) |
| Jugador con eventos | Se **rechaza** el borrado; el jugador y sus eventos quedan intactos. | Relación uno-a-muchos Jugador–Evento | Bloque 7, punto 2 |
| Sede con partidos | Se **rechaza**. | Relación uno-a-muchos Sede–Partido | Bloque 7, punto 2 |
| Árbitro con designaciones | Se **rechaza**. | Relación uno-a-muchos Árbitro–Designación | Bloque 7, punto 2 |
| Equipo con jugadores | Se **rechaza**. Como todo equipo cargado tiene jugadores, esto también protege las referencias `Partido.EquipoLocal`/`EquipoVisitante` y `Tecnico.Equipo`. | Relación uno-a-muchos Equipo–Jugador | Bloque 7, punto 2 |
| Evento suelto | No está bloqueado por el modelo (ver límites). | — | — |

Por qué la diferencia: en padre-hijo el hijo **depende** del padre, así que borrar al padre arrastra a los hijos. En uno-a-muchos las dos entidades son **independientes**; borrar el extremo "uno" dejaría a los "muchos" apuntando a nada, así que el borrado se rechaza mientras existan.

## 2. Altas y modificaciones

| Regla | Mecanismo | Demostración |
| :--- | :--- | :--- |
| Un partido y sus hijos se guardan juntos o no se guarda nada | `%Save()` guarda el grafo alcanzable en una transacción | Bloque 2 (se guarda todo) y Bloque 3 caso B (un hijo inválido impide guardar al padre y a su hermano válido) |
| Propiedades obligatorias y tipos | `[ Required ]`, `VALUELIST`, `MINVAL`/`MAXVAL`, `MAXLEN` | Bloque 3 caso A (falta `Fecha`) y caso B (falta `Minuto`) |
| El estado avanza solo `Programado → EnJuego → Finalizado` | `Iniciar()` y `Finalizar()` | Bloque 6 |
| No se registran eventos fuera de `EnJuego`; minuto 1..120; jugador de uno de los dos equipos | `RegistrarEvento()` y, para eventos creados con `%New()`, `Evento.%OnBeforeSave()` y el tipo de `Minuto` | Bloque 6 (gol en el minuto 0 sobre un partido Finalizado, gol de un jugador ajeno) |
| Un evento guardado no se modifica | `Evento.%OnBeforeSave()` rechaza toda actualización | Bloque 6: se cambia el minuto de `EV-0001`, el guardado se rechaza y SQL muestra el minuto original |
| Terna neutral, un rol por persona, cada rol una vez | `DesignarArbitro()` + índice único `PartidoRolIdx` | Bloque 6 |
| No se inicia sin árbitro Principal | `Iniciar()` + `Partido.%OnBeforeSave()` | Bloque 6 |
| El marcador coincide con los goles registrados | `RegistrarEvento()` lo mantiene; `Partido.%OnBeforeSave()` lo exige | Bloque 6 (`GolesLocal = 5` asignado a mano se rechaza) y control cruzado contra el CSV en la carga |
| Un equipo no juega contra sí mismo | `Partido.%OnBeforeSave()` | Bloque 6 (FRA vs FRA) |
| Claves de negocio únicas; dorsal único por equipo; un técnico por equipo | Índices únicos | Se aplican en cada guardado |

## 3. Límites conocidos (qué no protege el modelo)

Se dejan explícitos para no atribuirle al modelo garantías que no tiene.

1. **Escrituras SQL directas.** `%OnBeforeSave()` y los métodos de transición se ejecutan en el guardado **por objetos**. Un `UPDATE` o `DELETE` por SQL respeta tipos, obligatorios, índices únicos y relaciones, pero **no** pasa por esos métodos: por ejemplo, un `UPDATE Fixture.Partido SET Estado = 'Programado'` dejaría un partido con eventos en un estado que el modelo no permite. Por eso la **interfaz de escritura autorizada** para Partido, Evento y Designación son los métodos de la clase; SQL se usa para consultar, reportar e integrar, y para datos sin reglas de transición (el Bloque 5 cambia por SQL solo el nombre de una sede). Es el mismo criterio que dejó la corrección del Hito 7: un mecanismo que puede alterar el ciclo de vida de un dato antes de tiempo se separa conceptualmente de lo que sí puede tocar.
2. **Borrado de un evento suelto.** `Fixture.Evento.%DeleteId()` sobre un gol no está bloqueado y dejaría el marcador desalineado hasta el próximo guardado del partido (que lo rechazaría). Los eventos no se borran ni se corrigen fuera del borrado del partido completo; no forma parte de la interfaz autorizada.
3. **Referencias a Equipo.** `EquipoLocal`, `EquipoVisitante` y `Tecnico.Equipo` son referencias y no relaciones. Quedan protegidas en la práctica porque un equipo con jugadores no se puede borrar, pero un equipo sin jugadores sí podría borrarse aunque un partido lo referencie.
4. **Concurrencia.** No se probaron dos procesos modificando el mismo partido a la vez. La Clase 10 indica que IRIS permite fijar el nivel de concurrencia al abrir un objeto; elegir y probar esa estrategia queda fuera de este hito.
5. **Rendimiento.** Con 96 partidos y 437 eventos la demostración valida lógica, no rendimiento: los índices están justificados por el patrón de acceso, pero no se midieron tiempos.
