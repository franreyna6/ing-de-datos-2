/// Hito 9 - Designacion de un arbitro en un rol dentro de un partido.
/// Hijo de Partido (padre-hijo) y lado "muchos" de Arbitro-Designacion.
/// Resuelve la relacion muchos-a-muchos Partido-Arbitro con una clase propia
/// que guarda el dato de la relacion (el rol).
/// La forma autorizada de crearla es partido.DesignarArbitro().
Class Fixture.Designacion Extends %Persistent
{

Property Rol As %String(VALUELIST = ",Principal,Asistente1,Asistente2,Cuarto") [ Required ];

Relationship Partido As Fixture.Partido [ Cardinality = parent, Inverse = Designaciones ];

Relationship Arbitro As Fixture.Arbitro [ Cardinality = one, Inverse = Designaciones, Required ];

/// RNF3: indice sobre la propiedad relacional del lado hijo (Partido.Designaciones).
Index PartidoIdx On Partido;

/// RNF3: indice sobre la propiedad relacional del lado "muchos" (Arbitro.Designaciones).
Index ArbitroIdx On Arbitro;

/// Cada rol se cubre una sola vez por partido (tambien lo valida DesignarArbitro()).
Index PartidoRolIdx On (Partido, Rol) [ Unique ];

}
