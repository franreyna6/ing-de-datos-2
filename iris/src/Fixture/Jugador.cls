/// Hito 9 - Jugador de una seleccion. Especializa Persona.
/// Lado "muchos" de Equipo-Jugador y lado "uno" de Jugador-Evento (un jugador
/// protagoniza muchos eventos; mientras tenga eventos no se lo puede borrar).
Class Fixture.Jugador Extends Fixture.Persona
{

/// Codigo del Hito 5 (ej. ARG-10-emtxem). Unico.
Property Codigo As %String(MAXLEN = 30) [ Required ];

Property Posicion As %String(VALUELIST = ",Arquero,Defensor,Mediocampista,Delantero") [ Required ];

Property Dorsal As %Integer(MINVAL = 1, MAXVAL = 99) [ Required ];

Relationship Equipo As Fixture.Equipo [ Cardinality = one, Inverse = Jugadores, Required ];

Relationship Eventos As Fixture.Evento [ Cardinality = many, Inverse = Jugador ];

Index JugCodigoIdx On Codigo [ Unique ];

/// RNF3: indice sobre la propiedad relacional del lado "muchos". Lo usa IRIS
/// para cargar equipo.Jugadores sin recorrer todas las personas.
Index JugEquipoIdx On Equipo;

/// Regla del dominio: dos jugadores del mismo equipo no comparten dorsal.
Index JugDorsalIdx On (Equipo, Dorsal) [ Unique ];

}
