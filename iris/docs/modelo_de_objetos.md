# Modelo de objetos — decisiones de diseño

Para cada concepto del Fixture se respondió la pregunta de cierre de la Clase 10: **¿tiene identidad y ciclo de vida propios, es parte de otra entidad, o es una variante estable de una clase existente?** La respuesta decide entre objeto persistente, componente embebido, relación o herencia.

## 1. Por qué el Partido es la entidad compleja

En los módulos anteriores el partido era un dato más: un documento, un nodo del grafo, una clave de partición o un tag de una serie. Ninguno de esos modelos guarda **reglas** junto al dato. El partido las necesita:

- cambia de estado y no cualquier cambio es válido (no se finaliza un partido que no empezó);
- sus eventos dependen de él y no pueden quedar sueltos;
- un evento ya registrado no se corrige;
- el marcador tiene que coincidir con los goles registrados;
- la terna arbitral es un grupo acotado (cuatro roles como máximo) y neutral.

Con objetos persistentes, esas reglas quedan en los métodos de la clase y la base las aplica en cada guardado, sin repetirlas en cada aplicación que escriba un partido.

## 2. Decisión por concepto

| Concepto | Decisión | Motivo |
| :--- | :--- | :--- |
| Partido | Clase persistente | Identidad propia (`Codigo`), referenciada por eventos y designaciones, con ciclo de vida y reglas. |
| Evento (gol, tarjeta) | Clase persistente, **hijo** de Partido | No existe sin su partido y se borra con él (padre-hijo). Se guarda como objeto propio y no como lista dentro del partido porque también lo referencia el Jugador y se consulta por SQL. |
| Designación (árbitro + rol) | Clase persistente, **hijo** de Partido | Resuelve la relación muchos-a-muchos Partido–Árbitro guardando el dato de la relación (el rol). Pertenece al partido: sin partido no tiene sentido. |
| Sede | Clase persistente | Identidad propia; muchos partidos la referencian. |
| Dirección de la sede | `%SerialObject` embebido en Sede (**composición**) | No tiene identidad ni se referencia desde otro objeto; se guarda con la sede en el mismo `%Save()`. |
| Equipo | Clase persistente | Identidad propia; lo referencian jugadores, técnico y partidos. |
| Persona | Clase persistente base (**herencia**) | Agrupa nombre, nacionalidad y fecha de nacimiento, comunes a los tres tipos de persona. |
| Jugador, Árbitro, Técnico | Subclases de Persona | Son **tipos estables**: un jugador no se convierte en árbitro durante el torneo. Cada uno agrega solo lo que lo distingue. |
| Lesionado, suspendido, titular | **No** son subclases | Son estados que cambian; si hicieran falta serían propiedades o reglas del Jugador, no clases (nota del enunciado). Quedan fuera del alcance de este hito. |
| Estado del partido | Propiedad con `VALUELIST` + métodos de transición | El estado cambia; la estructura del Partido no. Por eso es una propiedad y no una jerarquía `PartidoProgramado`/`PartidoFinalizado`. |

## 3. Relaciones

| Relación | Tipo | Extremos (propiedad / inversa) | Índice en el lado muchos/hijo |
| :--- | :--- | :--- | :--- |
| Partido – Evento | padre-hijo | `Partido.Eventos` (children) / `Evento.Partido` (parent) | `Evento.PartidoIdx` |
| Partido – Designación | padre-hijo | `Partido.Designaciones` (children) / `Designacion.Partido` (parent) | `Designacion.PartidoIdx` |
| Sede – Partido | uno-a-muchos | `Sede.Partidos` (many) / `Partido.Sede` (one) | `Partido.SedeIdx` |
| Equipo – Jugador | uno-a-muchos | `Equipo.Jugadores` (many) / `Jugador.Equipo` (one) | `Jugador.JugEquipoIdx` |
| Jugador – Evento | uno-a-muchos | `Jugador.Eventos` (many) / `Evento.Jugador` (one) | `Evento.JugadorIdx` |
| Árbitro – Designación | uno-a-muchos | `Arbitro.Designaciones` (many) / `Designacion.Arbitro` (one) | `Designacion.ArbitroIdx` |

- **Padre-hijo** se usó solo donde hay dependencia de ciclo de vida (el hijo no sobrevive al padre).
- **Uno-a-muchos** se usó entre entidades independientes: borrar el extremo "uno" no borra a los "muchos"; se rechaza mientras existan (ver la matriz de integridad).
- `Partido.EquipoLocal`, `Partido.EquipoVisitante` y `Tecnico.Equipo` son **referencias** (propiedad de tipo objeto) y no relaciones: un partido apunta a dos equipos con papeles distintos y el equipo no necesita navegar hacia sus partidos en este hito. Su integridad se cubre en la matriz.
- **RNF3:** al abrir `partido.Eventos`, IRIS busca los eventos que apuntan a ese partido; el índice sobre la propiedad relacional evita recorrer todos los eventos. Lo mismo para las otras colecciones.

## 4. Tipos y propiedades obligatorias (RF5)

| Clase | Obligatorias (`[ Required ]`) | Restricciones de tipo |
| :--- | :--- | :--- |
| Persona | Nombre, Nacionalidad | `MAXLEN = 3` en Nacionalidad; FechaNacimiento `%Date` |
| Jugador | Codigo, Posicion, Dorsal, Equipo | Posicion con `VALUELIST`; Dorsal `%Integer` 1..99 |
| Arbitro | Licencia, Categoria | Categoria con `VALUELIST` (FIFA, Nacional) |
| Tecnico | Experiencia, Equipo | Experiencia `%Integer` 0..60 |
| Equipo | Codigo, Nombre, Confederacion, EsAnfitrion | Confederacion con `VALUELIST`; EsAnfitrion `%Boolean`; RankingFIFA `%Integer` ≥ 1 |
| Sede / Direccion | Codigo, Nombre, Ubicacion / Ciudad, Pais | — |
| Partido | Codigo, Fecha, Fase, Estado, EquipoLocal, EquipoVisitante, GolesLocal, GolesVisitante, Sede | Fecha `%Date`; Fase y Estado con `VALUELIST`; goles `%Integer` ≥ 0 |
| Evento | Codigo, Tipo, Minuto, Jugador | Tipo con `VALUELIST` (Gol, Tarjeta); Minuto `%Integer` 1..120 |
| Designacion | Rol, Arbitro | Rol con `VALUELIST` (Principal, Asistente1, Asistente2, Cuarto) |

Todos los tipos son tipos de datos de IRIS (`%String`, `%Integer`, `%Date`, `%Boolean`), así que cada propiedad aparece en SQL como columna con su tipo (nota "Multimodelo real" del enunciado).

## 5. Índices y su motivo

Un índice se agregó solo cuando lo justifica una relación, una búsqueda o una regla.

| Índice | Motivo |
| :--- | :--- |
| `CodigoIdx` único en Partido, Equipo, Sede y Evento; `JugCodigoIdx` en Jugador; `ArbLicenciaIdx` en Árbitro | Clave de negocio: unicidad y búsqueda por código. IRIS genera `CodigoIdxOpen()` y `CodigoIdxExists()`, que la carga y la navegación usan sin escribir SQL. |
| `PartidoIdx`, `JugadorIdx`, `ArbitroIdx`, `JugEquipoIdx`, `SedeIdx` | RNF3: lado muchos/hijo de cada relación. |
| `JugDorsalIdx` único sobre (Equipo, Dorsal) | Regla del dominio: dos jugadores de un equipo no comparten dorsal. |
| `PartidoRolIdx` único sobre (Partido, Rol) | Cada rol arbitral se cubre una vez por partido (respaldo en la base de la regla de `DesignarArbitro`). |
| `TecEquipoIdx` único sobre Equipo | Un técnico por equipo. |

## 6. Máquina de estados del Partido (RF9)

```
            DesignarArbitro()                       RegistrarEvento()
           ┌──────────────┐                        ┌──────────────┐
           ▼              │                        ▼              │
     ┌────────────┐  Iniciar()   ┌──────────┐      │   Finalizar() ┌────────────┐
     │ Programado │ ───────────▶ │ EnJuego  │ ─────┴─────────────▶ │ Finalizado │
     └────────────┘  (requiere   └──────────┘                      └────────────┘
                      Principal)                                    (no admite cambios
                                                                     de estado ni eventos)
```

| Operación | Permitida desde | Reglas adicionales | Si no se cumple |
| :--- | :--- | :--- | :--- |
| `DesignarArbitro(arbitro, rol)` | Programado | Árbitro neutral (nacionalidad distinta de ambos equipos); rol válido y libre; un árbitro no ocupa dos roles | `%Status` de error, no se agrega nada |
| `Iniciar()` | Programado | Debe haber árbitro Principal | Error, el estado no cambia |
| `RegistrarEvento(codigo, tipo, minuto, jugador)` | EnJuego | Minuto 1..120; tipo Gol o Tarjeta; jugador de uno de los dos equipos. Un gol suma al marcador de su lado | Error, no se crea el evento |
| `Finalizar()` | EnJuego | — | Error, el estado no cambia |

`%OnBeforeSave()` vuelve a verificar, en cada `%Save()`, las invariantes del objeto completo: un equipo no juega contra sí mismo, un partido iniciado o finalizado tiene Principal, un partido Programado no tiene eventos y el marcador coincide con los goles registrados. Así, aunque alguien asigne `Estado` o `GolesLocal` sin pasar por los métodos, el guardado por objetos lo rechaza (Bloque 6).

## 7. Carga (RF6)

`Fixture.Carga` lee los CSV del Hito 5 con la clase de archivos de IRIS (`%Stream.FileCharacter`), que se usa únicamente para leer el texto de los archivos. Cada partido se arma en memoria con los mismos métodos de dominio que usaría cualquier aplicación (designar terna, iniciar, registrar cada evento, finalizar) y se guarda con **un solo `%Save()`**. Al terminar cada partido se compara el marcador calculado desde los eventos con el del CSV; los 96 coinciden en los datos del Hito 5.

Árbitros (22) y técnicos (uno por equipo) se generan de forma determinista porque los CSV no los traen. Las nacionalidades de los árbitros son de equipos del torneo, para que la regla de neutralidad tenga efecto real en la asignación.
