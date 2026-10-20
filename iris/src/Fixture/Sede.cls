/// Hito 9 - Estadio donde se juegan los partidos.
/// Entidad independiente (identidad y ciclo de vida propios) que contiene su
/// Direccion por composicion. Relacion uno-a-muchos con Partido: una sede
/// tiene muchos partidos; cada partido tiene exactamente una sede.
Class Fixture.Sede Extends %Persistent
{

/// Clave de negocio (ej. MONU, CENT). Unica.
Property Codigo As %String(MAXLEN = 10) [ Required ];

Property Nombre As %String(MAXLEN = 120) [ Required ];

/// Composicion: la direccion forma parte de la sede.
Property Ubicacion As Fixture.Direccion [ Required ];

/// Extremo "uno" de la relacion Sede-Partido. El indice vive en Partido (lado "muchos").
Relationship Partidos As Fixture.Partido [ Cardinality = many, Inverse = Sede ];

/// Busqueda por codigo: genera CodigoIdxOpen() y CodigoIdxExists().
Index CodigoIdx On Codigo [ Unique ];

}
