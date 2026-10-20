/// Hito 9 - Director tecnico de una seleccion. Especializa Persona.
/// Cada equipo tiene un solo tecnico: lo garantiza el indice unico sobre Equipo.
Class Fixture.Tecnico Extends Fixture.Persona
{

/// Anios de experiencia como entrenador.
Property Experiencia As %Integer(MINVAL = 0, MAXVAL = 60) [ Required ];

/// Referencia al equipo que dirige.
Property Equipo As Fixture.Equipo [ Required ];

/// Un tecnico por equipo. Genera TecEquipoIdxOpen(idEquipo) para la busqueda.
Index TecEquipoIdx On Equipo [ Unique ];

}
