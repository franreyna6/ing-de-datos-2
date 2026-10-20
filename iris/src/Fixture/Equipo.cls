/// Hito 9 - Seleccion participante del Fixture 2030.
/// Relacion uno-a-muchos con Jugador: un equipo tiene muchos jugadores; las
/// dos entidades son independientes (borrar un equipo no borra jugadores: el
/// borrado se rechaza mientras tenga jugadores asociados).
Class Fixture.Equipo Extends %Persistent
{

/// Codigo FIFA de tres letras (ej. ARG). Unico.
Property Codigo As %String(MAXLEN = 3) [ Required ];

Property Nombre As %String(MAXLEN = 80) [ Required ];

Property Confederacion As %String(VALUELIST = ",AFC,CAF,CONCACAF,CONMEBOL,OFC,UEFA") [ Required ];

Property RankingFIFA As %Integer(MINVAL = 1);

Property EsAnfitrion As %Boolean [ InitialExpression = 0, Required ];

Property Grupo As %String(MAXLEN = 1);

/// Extremo "uno" de la relacion Equipo-Jugador. El indice vive en Jugador.
Relationship Jugadores As Fixture.Jugador [ Cardinality = many, Inverse = Equipo ];

Index CodigoIdx On Codigo [ Unique ];

}
