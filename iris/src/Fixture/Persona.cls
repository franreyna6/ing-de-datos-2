/// Hito 9 - Clase base de la jerarquia de personas (herencia).
/// Concentra los atributos que comparten Jugador, Arbitro y Tecnico. Las tres
/// subclases representan tipos estables del dominio (un jugador no pasa a ser
/// arbitro); los estados que cambian (lesionado, suspendido) NO se modelan como
/// subclases. Las subclases comparten la extension de Persona, por lo que
/// SELECT ... FROM Fixture.Persona devuelve a todas (polimorfismo).
Class Fixture.Persona Extends %Persistent
{

Property Nombre As %String(MAXLEN = 120) [ Required ];

/// Codigo de tres letras del pais (mismo formato que Equipo.Codigo).
Property Nacionalidad As %String(MAXLEN = 3) [ Required ];

Property FechaNacimiento As %Date;

}
