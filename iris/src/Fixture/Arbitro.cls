/// Hito 9 - Arbitro del torneo. Especializa Persona.
/// Lado "uno" de Arbitro-Designacion: un arbitro tiene muchas designaciones;
/// mientras tenga designaciones no se lo puede borrar.
Class Fixture.Arbitro Extends Fixture.Persona
{

/// Licencia del arbitro (ej. ARB-001). Unica.
Property Licencia As %String(MAXLEN = 20) [ Required ];

Property Categoria As %String(VALUELIST = ",FIFA,Nacional") [ InitialExpression = "FIFA", Required ];

Relationship Designaciones As Fixture.Designacion [ Cardinality = many, Inverse = Arbitro ];

Index ArbLicenciaIdx On Licencia [ Unique ];

}
