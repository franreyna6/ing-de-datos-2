/// Hito 9 - Partido del Fixture 2030: la entidad compleja del modulo.
///
/// Es una maquina de estados: Programado -> EnJuego -> Finalizado.
/// Es el padre de dos colecciones dependientes (relaciones padre-hijo):
///   - Eventos      (goles y tarjetas; inalterables una vez registrados)
///   - Designaciones (terna arbitral: Principal, Asistente1, Asistente2, Cuarto)
/// Un unico partido.%Save() guarda el partido y todos sus hijos en una sola
/// transaccion; si un hijo es invalido, no se guarda nada.
///
/// Interfaz de escritura autorizada: los metodos DesignarArbitro(), Iniciar(),
/// RegistrarEvento() y Finalizar(). Cada uno valida la transicion antes de
/// aplicarla. Ademas, %OnBeforeSave() vuelve a comprobar las invariantes del
/// objeto entero, por si alguien asigna propiedades sin pasar por los metodos.
Class Fixture.Partido Extends %Persistent
{

/// Codigo del Hito 5 (ej. F2030-001). Unico.
Property Codigo As %String(MAXLEN = 20) [ Required ];

Property Fecha As %Date [ Required ];

Property Fase As %String(VALUELIST = ",Grupos,Dieciseisavos,Octavos,Cuartos,Semifinal,TercerPuesto,Final") [ Required ];

Property Grupo As %String(MAXLEN = 1);

/// Estado del partido. Solo cambia mediante Iniciar() y Finalizar().
Property Estado As %String(VALUELIST = ",Programado,EnJuego,Finalizado") [ InitialExpression = "Programado", Required ];

Property EquipoLocal As Fixture.Equipo [ Required ];

Property EquipoVisitante As Fixture.Equipo [ Required ];

/// Marcador. Lo actualiza RegistrarEvento(); %OnBeforeSave() exige que coincida
/// con los eventos de gol registrados.
Property GolesLocal As %Integer(MINVAL = 0) [ InitialExpression = 0, Required ];

Property GolesVisitante As %Integer(MINVAL = 0) [ InitialExpression = 0, Required ];

/// Lado "muchos" de Sede-Partido.
Relationship Sede As Fixture.Sede [ Cardinality = one, Inverse = Partidos, Required ];

/// Padre-hijo: los eventos no existen sin su partido (borrado en cascada).
Relationship Eventos As Fixture.Evento [ Cardinality = children, Inverse = Partido ];

/// Padre-hijo: las designaciones arbitrales no existen sin su partido.
Relationship Designaciones As Fixture.Designacion [ Cardinality = children, Inverse = Partido ];

Index CodigoIdx On Codigo [ Unique ];

/// RNF3: indice sobre la propiedad relacional del lado "muchos" de Sede-Partido.
Index SedeIdx On Sede;

/// Designa un arbitro en un rol. Reglas:
///  - solo con el partido Programado;
///  - el arbitro debe ser neutral (nacionalidad distinta de los dos equipos);
///  - cada rol se cubre una sola vez y un arbitro no ocupa dos roles.
Method DesignarArbitro(arbitro As Fixture.Arbitro, rol As %String) As %Status
{
    If ..Estado '= "Programado" Quit $$$ERROR($$$GeneralError, "Transicion ilegal: solo se designan arbitros con el partido Programado (estado actual: "_..Estado_")")
    If '$IsObject(arbitro) Quit $$$ERROR($$$GeneralError, "Arbitro inexistente")
    If ('$IsObject(..EquipoLocal)) || ('$IsObject(..EquipoVisitante)) Quit $$$ERROR($$$GeneralError, "Antes de designar arbitros hay que asignar los dos equipos")
    If (",Principal,Asistente1,Asistente2,Cuarto,") '[ (","_rol_",") Quit $$$ERROR($$$GeneralError, "Rol arbitral desconocido: "_rol)
    If (arbitro.Nacionalidad = ..EquipoLocal.Codigo) || (arbitro.Nacionalidad = ..EquipoVisitante.Codigo) {
        Quit $$$ERROR($$$GeneralError, "Arbitro no neutral: "_arbitro.Nombre_" ("_arbitro.Nacionalidad_") no puede dirigir "_..EquipoLocal.Codigo_" vs "_..EquipoVisitante.Codigo)
    }
    Set key = ""
    For {
        Set d = ..Designaciones.GetNext(.key)
        Quit:key=""
        If d.Rol = rol Return $$$ERROR($$$GeneralError, "El rol "_rol_" ya esta cubierto en el partido "_..Codigo)
        If d.Arbitro.%Id() = arbitro.%Id() Return $$$ERROR($$$GeneralError, "El arbitro "_arbitro.Nombre_" ya tiene el rol "_d.Rol_" en este partido")
    }
    Set d = ##class(Fixture.Designacion).%New()
    Set d.Rol = rol
    Set d.Arbitro = arbitro
    Do ..Designaciones.Insert(d)
    Quit $$$OK
}

/// Programado -> EnJuego. Requiere arbitro Principal designado.
Method Iniciar() As %Status
{
    If ..Estado '= "Programado" Quit $$$ERROR($$$GeneralError, "Transicion ilegal: "_..Estado_" -> EnJuego (solo se inicia un partido Programado)")
    If '..TieneRol("Principal") Quit $$$ERROR($$$GeneralError, "No se puede iniciar el partido "_..Codigo_" sin arbitro Principal designado")
    Set ..Estado = "EnJuego"
    Quit $$$OK
}

/// Registra un gol o una tarjeta. Reglas:
///  - solo con el partido EnJuego (un partido Programado o Finalizado no admite eventos);
///  - minuto entre 1 y 120;
///  - el jugador pertenece a uno de los dos equipos.
/// Si es gol, actualiza el marcador del lado del jugador.
Method RegistrarEvento(codigo As %String, tipo As %String, minuto As %Integer, jugador As Fixture.Jugador) As %Status
{
    If ..Estado '= "EnJuego" Quit $$$ERROR($$$GeneralError, "Transicion ilegal: el partido "_..Codigo_" esta "_..Estado_" y no admite eventos (se intento "_tipo_" en el minuto "_minuto_")")
    If (minuto < 1) || (minuto > 120) Quit $$$ERROR($$$GeneralError, "Minuto invalido: "_minuto_" (debe estar entre 1 y 120)")
    If (tipo '= "Gol") && (tipo '= "Tarjeta") Quit $$$ERROR($$$GeneralError, "Tipo de evento desconocido: "_tipo)
    If '$IsObject(jugador) Quit $$$ERROR($$$GeneralError, "Jugador inexistente")
    Set lado = ..LadoDe(jugador)
    If lado = "" Quit $$$ERROR($$$GeneralError, "El jugador "_jugador.Codigo_" no pertenece a "_..EquipoLocal.Codigo_" ni a "_..EquipoVisitante.Codigo)
    Set ev = ##class(Fixture.Evento).%New()
    Set ev.Codigo = codigo
    Set ev.Tipo = tipo
    Set ev.Minuto = minuto
    Set ev.Jugador = jugador
    Do ..Eventos.Insert(ev)
    If tipo = "Gol" {
        If lado = "L" { Set ..GolesLocal = ..GolesLocal + 1 } Else { Set ..GolesVisitante = ..GolesVisitante + 1 }
    }
    Quit $$$OK
}

/// EnJuego -> Finalizado.
Method Finalizar() As %Status
{
    If ..Estado '= "EnJuego" Quit $$$ERROR($$$GeneralError, "Transicion ilegal: "_..Estado_" -> Finalizado (solo se finaliza un partido EnJuego)")
    Set ..Estado = "Finalizado"
    Quit $$$OK
}

/// Devuelve 1 si el rol ya esta cubierto en este partido.
Method TieneRol(rol As %String) As %Boolean
{
    Set key = ""
    For {
        Set d = ..Designaciones.GetNext(.key)
        Quit:key=""
        If d.Rol = rol Return 1
    }
    Quit 0
}

/// "L" si el jugador es del equipo local, "V" si es del visitante, "" si de ninguno.
Method LadoDe(jugador As Fixture.Jugador) As %String
{
    If '$IsObject(jugador) Quit ""
    If '$IsObject(jugador.Equipo) Quit ""
    If $IsObject(..EquipoLocal) && (jugador.Equipo.%Id() = ..EquipoLocal.%Id()) Quit "L"
    If $IsObject(..EquipoVisitante) && (jugador.Equipo.%Id() = ..EquipoVisitante.%Id()) Quit "V"
    Quit ""
}

/// Validacion del objeto entero antes de cada guardado por objetos (%Save).
/// Comprueba invariantes que no dependen de por donde se modifico el objeto.
Method %OnBeforeSave(insert As %Boolean) As %Status [ Private, ServerOnly = 1 ]
{
    If $IsObject(..EquipoLocal) && $IsObject(..EquipoVisitante) {
        If ..EquipoLocal.Codigo = ..EquipoVisitante.Codigo Quit $$$ERROR($$$GeneralError, "Un equipo no puede jugar contra si mismo ("_..EquipoLocal.Codigo_")")
    }
    If (..Estado '= "Programado") && ('..TieneRol("Principal")) Quit $$$ERROR($$$GeneralError, "El partido "_..Codigo_" esta "_..Estado_" sin arbitro Principal designado")
    If (..Estado = "Programado") && (..Eventos.Count() > 0) Quit $$$ERROR($$$GeneralError, "El partido "_..Codigo_" esta Programado y no puede tener eventos")
    Set gl = 0, gv = 0, key = ""
    For {
        Set ev = ..Eventos.GetNext(.key)
        Quit:key=""
        Continue:ev.Tipo'="Gol"
        Set lado = ..LadoDe(ev.Jugador)
        If lado = "L" { Set gl = gl + 1 } ElseIf lado = "V" { Set gv = gv + 1 }
    }
    If (gl '= ..GolesLocal) || (gv '= ..GolesVisitante) {
        Quit $$$ERROR($$$GeneralError, "Marcador inconsistente en "_..Codigo_": "_..GolesLocal_"-"_..GolesVisitante_" pero los goles registrados suman "_gl_"-"_gv)
    }
    Quit $$$OK
}

}
