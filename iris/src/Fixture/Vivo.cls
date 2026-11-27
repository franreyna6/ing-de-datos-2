/// Hito 13 - Demo en vivo: interfaz de escritura del partido para la API.
///
/// La API (adaptador de IRIS) llama a estos metodos de clase por el Native API
/// de Python (iris.createIRIS(conexion).classMethodValue). Cada metodo usa la
/// interfaz autorizada del Hito 9 (Iniciar, RegistrarEvento, Finalizar y
/// %Save), asi que las MISMAS reglas que se defendieron en el Hito 9 deciden
/// si la operacion se acepta: un evento solo existe con el partido EnJuego, el
/// jugador tiene que pertenecer a uno de los dos equipos, no se inicia sin
/// arbitro Principal, etc. Si IRIS rechaza, la API responde 409 con el motivo.
///
/// Integridad (RNF5 del Hito 13): solo se crean y modifican partidos de
/// LABORATORIO, con codigo que empieza con H13-DEMO-. El fixture real cargado
/// en el Hito 9 no se toca. Lectura (Estado) admite cualquier codigo.
///
/// Todos los metodos devuelven un JSON (texto) con la misma forma:
///   {"ok":true|false, "codigo", "estado", "golesLocal", "golesVisitante",
///    "equipoLocal", "equipoVisitante", "sede", "cantidadEventos", "terna":[...],
///    "accion" (si ok) | "motivo" (si se rechazo)}
///
/// Compilar sin recargar datos:
///   docker exec -i fixture2030-iris iris session IRIS -U USER
///   USER> Do $system.OBJ.Load("/iris/src/Fixture/Vivo.cls","ck")
Class Fixture.Vivo
{

Parameter PREFIJO = "H13-DEMO-";

/// Crea (o recrea limpio) un partido de laboratorio Programado, con terna
/// arbitral neutral designada (DesignarArbitro rechaza arbitros del pais de
/// cualquiera de los dos equipos).
ClassMethod Crear(codigo As %String, local As %String, visitante As %String, sede As %String, fecha As %String) As %String
{
    If '..EsLaboratorio(codigo) Quit ..Rechazo(codigo, "Solo se crean partidos de laboratorio ("_..#PREFIJO_"...)")
    Do ##class(Fixture.Demo).Limpiar(codigo)
    Set p = ##class(Fixture.Demo).NuevoPartido(codigo, local, visitante, sede, fecha, "Grupos")
    If '$IsObject(p.EquipoLocal) Quit ..Rechazo(codigo, "Equipo inexistente en IRIS: "_local)
    If '$IsObject(p.EquipoVisitante) Quit ..Rechazo(codigo, "Equipo inexistente en IRIS: "_visitante)
    If '$IsObject(p.Sede) Quit ..Rechazo(codigo, "Sede inexistente en IRIS: "_sede)
    Set sc = ##class(Fixture.Demo).DesignarTerna(p, 1)
    If $$$ISOK(sc) Set sc = p.%Save()
    Quit ..Respuesta(p, sc, "Partido creado en estado Programado, con terna arbitral neutral")
}

/// Programado -> EnJuego (exige arbitro Principal).
ClassMethod Iniciar(codigo As %String) As %String
{
    Set p = ..Abrir(codigo, .sc)
    If '$IsObject(p) Quit ..Rechazo(codigo, $System.Status.GetErrorText(sc))
    Set sc = p.Iniciar()
    If $$$ISOK(sc) Set sc = p.%Save()
    If $$$ISERR(sc) Do p.%Reload()
    Quit ..Respuesta(p, sc, "Programado -> EnJuego")
}

/// Gol o tarjeta. Usa Partido.RegistrarEvento(): solo con el partido EnJuego,
/// minuto 1-120 y jugador de uno de los dos equipos. Si es gol, actualiza el
/// marcador; %OnBeforeSave() vuelve a verificar que coincida con los goles.
ClassMethod RegistrarEvento(codigo As %String, evento As %String, tipo As %String, minuto As %Integer, jugador As %String) As %String
{
    Set p = ..Abrir(codigo, .sc)
    If '$IsObject(p) Quit ..Rechazo(codigo, $System.Status.GetErrorText(sc))
    Set j = ##class(Fixture.Jugador).JugCodigoIdxOpen(jugador)
    Set sc = p.RegistrarEvento(evento, tipo, +minuto, j)
    If $$$ISOK(sc) Set sc = p.%Save()
    If $$$ISERR(sc) Do p.%Reload()
    Quit ..Respuesta(p, sc, tipo_" en el minuto "_minuto)
}

/// EnJuego -> Finalizado.
ClassMethod Finalizar(codigo As %String) As %String
{
    Set p = ..Abrir(codigo, .sc)
    If '$IsObject(p) Quit ..Rechazo(codigo, $System.Status.GetErrorText(sc))
    Set sc = p.Finalizar()
    If $$$ISOK(sc) Set sc = p.%Save()
    If $$$ISERR(sc) Do p.%Reload()
    Quit ..Respuesta(p, sc, "EnJuego -> Finalizado")
}

/// Lectura del objeto completo (cualquier partido, no solo de laboratorio).
ClassMethod Estado(codigo As %String) As %String
{
    Set p = ##class(Fixture.Partido).CodigoIdxOpen(codigo, , .sc)
    If '$IsObject(p) Quit ..Rechazo(codigo, "No existe el partido "_codigo)
    Quit ..Respuesta(p, $$$OK, "lectura")
}

// ------------------------------------------------------------- Utilidades

ClassMethod EsLaboratorio(codigo As %String) As %Boolean
{
    Quit ($Extract(codigo, 1, $Length(..#PREFIJO)) = ..#PREFIJO)
}

/// Abre un partido de laboratorio para modificarlo. Devuelve "" si no existe.
ClassMethod Abrir(codigo As %String, Output sc As %Status) As Fixture.Partido
{
    Set sc = $$$OK
    If '..EsLaboratorio(codigo) {
        Set sc = $$$ERROR($$$GeneralError, "Solo se modifican partidos de laboratorio ("_..#PREFIJO_"...)")
        Return ""
    }
    Set p = ##class(Fixture.Partido).CodigoIdxOpen(codigo, , .sc)
    If '$IsObject(p) {
        Set sc = $$$ERROR($$$GeneralError, "No existe el partido "_codigo)
        Return ""
    }
    Quit p
}

ClassMethod Respuesta(p As Fixture.Partido, sc As %Status, accion As %String) As %String
{
    Set r = {}
    Do r.%Set("ok", $$$ISOK(sc), "boolean")
    Do r.%Set("codigo", p.Codigo)
    Do r.%Set("estado", p.Estado)
    Do r.%Set("fecha", $Select(p.Fecha = "": "", 1: $ZDate(p.Fecha, 3)))
    Do r.%Set("golesLocal", p.GolesLocal, "number")
    Do r.%Set("golesVisitante", p.GolesVisitante, "number")
    Do r.%Set("equipoLocal", $Select($IsObject(p.EquipoLocal): p.EquipoLocal.Codigo, 1: ""))
    Do r.%Set("equipoVisitante", $Select($IsObject(p.EquipoVisitante): p.EquipoVisitante.Codigo, 1: ""))
    Do r.%Set("sede", $Select($IsObject(p.Sede): p.Sede.Nombre, 1: ""))
    Do r.%Set("cantidadEventos", p.Eventos.Count(), "number")
    Set terna = []
    Set key = ""
    For {
        Set d = p.Designaciones.GetNext(.key)
        Quit:key=""
        Do terna.%Push({"rol": (d.Rol), "arbitro": (d.Arbitro.Nombre), "nacionalidad": (d.Arbitro.Nacionalidad)})
    }
    Do r.%Set("terna", terna)
    If $$$ISOK(sc) {
        Do r.%Set("accion", accion)
    } Else {
        Do r.%Set("motivo", $System.Status.GetErrorText(sc))
    }
    Quit r.%ToJSON()
}

ClassMethod Rechazo(codigo As %String, motivo As %String) As %String
{
    Set r = {}
    Do r.%Set("ok", 0, "boolean")
    Do r.%Set("codigo", codigo)
    Do r.%Set("motivo", motivo)
    Quit r.%ToJSON()
}

}
