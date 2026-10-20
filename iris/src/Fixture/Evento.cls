/// Hito 9 - Gol o tarjeta de un partido.
/// Hijo de Partido (padre-hijo): no existe sin su partido y se borra con el.
/// Lado "muchos" de Jugador-Evento. Una vez guardado es inalterable.
/// La forma autorizada de crearlo es partido.RegistrarEvento().
Class Fixture.Evento Extends %Persistent
{

/// Codigo del Hito 5 (ej. EV-0001). Unico.
Property Codigo As %String(MAXLEN = 20) [ Required ];

Property Tipo As %String(VALUELIST = ",Gol,Tarjeta") [ Required ];

/// El minuto 0 o mayor a 120 se rechaza por el propio tipo de dato.
Property Minuto As %Integer(MINVAL = 1, MAXVAL = 120) [ Required ];

Relationship Partido As Fixture.Partido [ Cardinality = parent, Inverse = Eventos ];

Relationship Jugador As Fixture.Jugador [ Cardinality = one, Inverse = Eventos, Required ];

/// RNF3: indice sobre la propiedad relacional del lado hijo (Partido.Eventos).
Index PartidoIdx On Partido;

/// RNF3: indice sobre la propiedad relacional del lado "muchos" (Jugador.Eventos).
Index JugadorIdx On Jugador;

Index CodigoIdx On Codigo [ Unique ];

/// Un evento se inserta una sola vez y nunca se modifica. Tambien se comprueba
/// aqui (y no solo en RegistrarEvento) que el partido haya comenzado y que el
/// jugador sea de uno de los dos equipos, para cubrir eventos creados con %New().
Method %OnBeforeSave(insert As %Boolean) As %Status [ Private, ServerOnly = 1 ]
{
    If 'insert Quit $$$ERROR($$$GeneralError, "Evento inalterable: "_..Codigo_" ya fue registrado y no se puede modificar")
    If '$IsObject(..Partido) Quit $$$ERROR($$$GeneralError, "El evento "_..Codigo_" no tiene partido")
    If ..Partido.Estado = "Programado" Quit $$$ERROR($$$GeneralError, "El partido "_..Partido.Codigo_" no comenzo: no admite eventos")
    If ..Partido.LadoDe(..Jugador) = "" Quit $$$ERROR($$$GeneralError, "El jugador del evento "_..Codigo_" no pertenece a los equipos del partido")
    Quit $$$OK
}

}
