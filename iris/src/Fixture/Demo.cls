/// Hito 9 - Demostracion por bloques, invocable desde el Terminal de IRIS (RNF4).
///
///   Do ##class(Fixture.Demo).Bloque1Carga()          RF6  carga inicial (arbol por partido)
///   Do ##class(Fixture.Demo).Bloque2ArbolAtomico()   RF6  padre + hijos con un solo %Save
///   Do ##class(Fixture.Demo).Bloque3FalloControlado()RF5  falla por propiedad requerida omitida
///   Do ##class(Fixture.Demo).Bloque4Navegacion()     RF7  navegacion por referencias, sin SQL
///   Do ##class(Fixture.Demo).Bloque5ProyeccionSQL()  RF8  los mismos datos vistos y operados por SQL
///   Do ##class(Fixture.Demo).Bloque6Validaciones()   RF9  transiciones ilegales rechazadas
///   Do ##class(Fixture.Demo).Bloque7Integridad()     RF3  matriz de integridad (borrados)
///   Do ##class(Fixture.Demo).Conteo()                     conteo por SQL (persistencia)
///   Do ##class(Fixture.Demo).Todo()                       todos los bloques en orden
///
/// Cada operacion imprime [ACEPTADO] o [RECHAZADO] con el motivo que devuelve
/// IRIS, y cada verificacion se calcula consultando la base: la evidencia
/// muestra exactamente la operacion que se declara.
Class Fixture.Demo
{

ClassMethod Todo()
{
    Do ..Bloque1Carga()
    Do ..Bloque2ArbolAtomico()
    Do ..Bloque3FalloControlado()
    Do ..Bloque4Navegacion()
    Do ..Bloque5ProyeccionSQL()
    Do ..Bloque6Validaciones()
    Do ..Bloque7Integridad()
    Do ..Conteo()
}

// ---------------------------------------------------------------- Bloque 1

ClassMethod Bloque1Carga()
{
    Do ..Titulo("BLOQUE 1 - Carga inicial desde los CSV del Hito 5 (RF6)")
    Set sc = ##class(Fixture.Carga).Todo()
    Do ..Resultado("Fixture.Carga.Todo()", sc)
    Do ..Conteo()
}

// ---------------------------------------------------------------- Bloque 2

/// Padre e hijos se crean en memoria y se guardan con un unico %Save() del padre.
ClassMethod Bloque2ArbolAtomico()
{
    Do ..Titulo("BLOQUE 2 - Arbol de objetos guardado con un solo %Save() (RF6)")
    Do ..Limpiar("DEMO-001")
    Set p = ..NuevoPartido("DEMO-001", "ARG", "URU", "CENT", "2030-07-21", "Final")
    Do ..Resultado("Designar terna arbitral neutral", ..DesignarTerna(p, 4))
    Do ..Resultado("p.Iniciar()", p.Iniciar())
    Set jArg = ..PrimerJugador(p.EquipoLocal), jUru = ..PrimerJugador(p.EquipoVisitante)
    Do ..Resultado("p.RegistrarEvento(Gol, 12, "_jArg.Codigo_")", p.RegistrarEvento("DEMO-EV-01", "Gol", 12, jArg))
    Do ..Resultado("p.RegistrarEvento(Tarjeta, 40, "_jUru.Codigo_")", p.RegistrarEvento("DEMO-EV-02", "Tarjeta", 40, jUru))
    Do ..Resultado("p.RegistrarEvento(Gol, 77, "_jUru.Codigo_")", p.RegistrarEvento("DEMO-EV-03", "Gol", 77, jUru))
    Do ..Resultado("p.Finalizar()", p.Finalizar())
    Write !, "Antes de guardar (todo esta solo en memoria):", !
    Write "  partido ID = '", p.%Id(), "'   estado = ", p.Estado, "   marcador = ", p.GolesLocal, "-", p.GolesVisitante, !
    Do ..ListarHijos(p)
    Write !, ">>> Unica invocacion de guardado: p.%Save()", !
    Do ..Resultado("p.%Save()", p.%Save())
    Write !, "Despues de guardar (IRIS asigno identidad al padre y a cada hijo):", !
    Write "  partido ID = ", p.%Id(), !
    Do ..ListarHijos(p)
    // Verificacion independiente: se libera el objeto y se vuelve a abrir desde la base.
    Kill p, jArg, jUru
    Set q = ##class(Fixture.Partido).CodigoIdxOpen("DEMO-001")
    Write !, "Verificacion: se reabre DEMO-001 desde la base -> ", $Select($IsObject(q): "existe", 1: "NO existe"), !
    If $IsObject(q) Write "  eventos guardados: ", q.Eventos.Count(), "   designaciones guardadas: ", q.Designaciones.Count(), "   estado: ", q.Estado, !
}

// ---------------------------------------------------------------- Bloque 3

/// Una propiedad requerida omitida hace fallar el guardado y no queda nada a medias.
ClassMethod Bloque3FalloControlado()
{
    Do ..Titulo("BLOQUE 3 - Fallo controlado por propiedad requerida omitida (RF5 + atomicidad)")
    Do ..Limpiar("DEMO-002"), ..Limpiar("DEMO-003")

    Write !, "Caso A: al PADRE le falta Fecha (Required). Tiene una designacion y un evento validos.", !
    Set p = ..NuevoPartido("DEMO-002", "BRA", "COL", "MONU", "", "Final")
    Do ..DesignarTerna(p, 7), p.Iniciar()
    Set j = ..PrimerJugador(p.EquipoLocal)
    Do p.RegistrarEvento("DEMO-EV-21", "Tarjeta", 30, j)
    Do ..Resultado("p.%Save() sin Fecha", p.%Save())
    Kill p, j
    Write "  Verificacion: existe DEMO-002?    ", ##class(Fixture.Partido).CodigoIdxExists("DEMO-002"), "   (0 = no se guardo)", !
    Write "  Verificacion: existe DEMO-EV-21?  ", ##class(Fixture.Evento).CodigoIdxExists("DEMO-EV-21"), "   (0 = el hijo tampoco)", !

    Write !, "Caso B: el padre es valido, pero a un HIJO le falta Minuto (Required).", !
    Write "        El evento invalido se crea con %New(), salteando RegistrarEvento().", !
    Set p = ..NuevoPartido("DEMO-003", "MEX", "USA", "KEMP", "2030-07-22", "Final")
    Do ..DesignarTerna(p, 10), p.Iniciar()
    Set j = ..PrimerJugador(p.EquipoLocal)
    Do ..Resultado("p.RegistrarEvento(Tarjeta, 15) valido", p.RegistrarEvento("DEMO-EV-30", "Tarjeta", 15, j))
    Set ev = ##class(Fixture.Evento).%New()
    Set ev.Codigo = "DEMO-EV-31", ev.Tipo = "Tarjeta", ev.Jugador = j
    Do p.Eventos.Insert(ev)
    Do ..Resultado("p.%Save() con un hijo sin Minuto", p.%Save())
    Kill p, j, ev
    Write "  Verificacion: existe DEMO-003?    ", ##class(Fixture.Partido).CodigoIdxExists("DEMO-003"), "   (0 = el padre valido no se guardo)", !
    Write "  Verificacion: existe DEMO-EV-30?  ", ##class(Fixture.Evento).CodigoIdxExists("DEMO-EV-30"), "   (0 = el hijo valido no se guardo)", !
    Write "  => El arbol se guarda completo o no se guarda.", !
}

// ---------------------------------------------------------------- Bloque 4

/// Recorre el modelo solo con referencias de objetos: no se escribe SQL.
ClassMethod Bloque4Navegacion()
{
    Do ..Titulo("BLOQUE 4 - Navegacion por referencias de objetos, sin SQL (RF7)")
    Set p = ##class(Fixture.Partido).CodigoIdxOpen("F2030-001")
    If '$IsObject(p) { Write "No existe F2030-001: ejecutar primero el Bloque 1", ! Quit }
    Write "partido      ", p.Codigo, "  (", $ZDate(p.Fecha, 3), ", fase ", p.Fase, " ", p.Grupo, ", ", p.Estado, ")", !
    Write "  .Sede                  ", p.Sede.Nombre, !
    Write "  .Sede.Ubicacion        ", p.Sede.Ubicacion.Ciudad, ", ", p.Sede.Ubicacion.Pais, "   (componente embebido)", !
    Write "  .EquipoLocal           ", p.EquipoLocal.Nombre, "  ", p.GolesLocal, !
    Write "  .EquipoVisitante       ", p.EquipoVisitante.Nombre, "  ", p.GolesVisitante, !
    Set t = ##class(Fixture.Tecnico).TecEquipoIdxOpen(p.EquipoLocal.%Id())
    If $IsObject(t) Write "  tecnico local          ", t.Nombre, " (", t.Experiencia, " anios)", !
    Write "  .Designaciones (", p.Designaciones.Count(), ")", !
    Set key = ""
    For {
        Set d = p.Designaciones.GetNext(.key)
        Quit:key=""
        Write "     ", $Justify(d.Rol, 10), "  ", d.Arbitro.Nombre, " (", d.Arbitro.Nacionalidad, ", ", d.Arbitro.Licencia, ")", !
    }
    Write "  .Eventos (", p.Eventos.Count(), ")", !
    Set key = "", jug = ""
    For {
        Set ev = p.Eventos.GetNext(.key)
        Quit:key=""
        Write "     min ", $Justify(ev.Minuto, 3), "  ", $Justify(ev.Tipo, 7), "  ", ev.Jugador.Nombre, " #", ev.Jugador.Dorsal, " (", ev.Jugador.Equipo.Codigo, ")", !
        If jug = "" Set jug = ev.Jugador
    }
    If '$IsObject(jug) Quit
    Write !, "Navegacion inversa (bidireccional) desde el jugador ", jug.Nombre, ":", !
    Write "  .Equipo                ", jug.Equipo.Nombre, "  (el equipo tiene ", jug.Equipo.Jugadores.Count(), " jugadores)", !
    Write "  .Eventos (", jug.Eventos.Count(), ") en los partidos:", !
    Set key = ""
    For {
        Set ev = jug.Eventos.GetNext(.key)
        Quit:key=""
        Write "     ", ev.Partido.Codigo, "  min ", ev.Minuto, "  ", ev.Tipo, !
    }
    Write "  la sede ", p.Sede.Codigo, " tiene ", p.Sede.Partidos.Count(), " partidos (Sede.Partidos)", !
    // Polimorfismo: se abre como Persona y IRIS devuelve la subclase concreta.
    Set per = ##class(Fixture.Persona).%OpenId(jug.%Id())
    Write !, "Polimorfismo: Fixture.Persona.%OpenId(", jug.%Id(), ") devuelve un objeto de clase ", $ClassName(per), !
}

// ---------------------------------------------------------------- Bloque 5

/// Los objetos creados por codigo se ven y se operan como tablas SQL.
ClassMethod Bloque5ProyeccionSQL()
{
    Do ..Titulo("BLOQUE 5 - Proyeccion multimodelo: los mismos datos por SQL (RF8)")
    Set p = ##class(Fixture.Partido).CodigoIdxOpen("DEMO-001")
    If $IsObject(p) Write "Objeto: DEMO-001 tiene %Id() = ", p.%Id(), " -> debe coincidir con la columna ID de la consulta", !
    Kill p
    Do ..SQL("SELECT p.ID, p.Codigo, p.Fecha, p.Estado, el.Nombre AS NombreLocal, p.GolesLocal, p.GolesVisitante, ev.Nombre AS NombreVisitante, s.Nombre AS Sede, s.Ubicacion_Ciudad AS Ciudad FROM Fixture.Partido p JOIN Fixture.Equipo el ON p.EquipoLocal = el.ID JOIN Fixture.Equipo ev ON p.EquipoVisitante = ev.ID JOIN Fixture.Sede s ON p.Sede = s.ID WHERE p.Codigo = 'DEMO-001'")
    Do ..SQL("SELECT e.ID, e.Codigo, e.Tipo, e.Minuto, j.Nombre AS Jugador, q.Codigo AS Equipo FROM Fixture.Evento e JOIN Fixture.Partido p ON e.Partido = p.ID JOIN Fixture.Jugador j ON e.Jugador = j.ID JOIN Fixture.Equipo q ON j.Equipo = q.ID WHERE p.Codigo = 'DEMO-001' ORDER BY e.Minuto")
    Do ..SQL("SELECT d.ID, d.Rol, a.Nombre AS Arbitro, a.Nacionalidad FROM Fixture.Designacion d JOIN Fixture.Partido p ON d.Partido = p.ID JOIN Fixture.Arbitro a ON d.Arbitro = a.ID WHERE p.Codigo = 'DEMO-001'")
    Write !, "Herencia en SQL: Fixture.Persona contiene a las tres subclases.", !
    Do ..SQL("SELECT x__classname AS Subclase, COUNT(*) AS Personas FROM Fixture.Persona GROUP BY x__classname")
    Write !, "Consulta de reporte sobre los datos cargados como objetos: goleadores.", !
    Do ..SQL("SELECT TOP 5 %EXACT(j.Nombre) AS Nombre, q.Codigo AS Equipo, COUNT(*) AS Goles FROM Fixture.Evento e JOIN Fixture.Jugador j ON e.Jugador = j.ID JOIN Fixture.Equipo q ON j.Equipo = q.ID WHERE e.Tipo = 'Gol' GROUP BY j.ID, j.Nombre, q.Codigo ORDER BY Goles DESC, j.Nombre")

    Write !, "Operar por SQL y leer por objetos (mismo estado, no son dos copias):", !
    Set s = ##class(Fixture.Sede).CodigoIdxOpen("CENT")
    Set original = s.Nombre
    Kill s
    Do ..SQL("UPDATE Fixture.Sede SET Nombre = 'Estadio Centenario (renovado)' WHERE Codigo = 'CENT'")
    Set s = ##class(Fixture.Sede).CodigoIdxOpen("CENT")
    // %Reload() relee desde la base por si el objeto ya estaba abierto en este proceso.
    Do s.%Reload()
    Write "  Objeto: Sede CENT -> Nombre = ", s.Nombre, "   (cambio hecho por SQL, leido por objetos)", !
    Set s.Nombre = original
    Do ..Resultado("Restaurar el nombre por objetos: s.%Save()", s.%Save())
    Kill s
    Do ..SQL("SELECT ID, Codigo, Nombre FROM Fixture.Sede WHERE Codigo = 'CENT'")
}

// ---------------------------------------------------------------- Bloque 6

/// Operaciones encapsuladas que rechazan transiciones de estado ilegales.
ClassMethod Bloque6Validaciones()
{
    Do ..Titulo("BLOQUE 6 - Validaciones encapsuladas: transiciones ilegales (RF9)")
    Set p = ##class(Fixture.Partido).CodigoIdxOpen("F2030-001")
    If '$IsObject(p) { Write "No existe F2030-001: ejecutar primero el Bloque 1", ! Quit }
    Set j = ..PrimerJugador(p.EquipoLocal)
    Set antes = p.Eventos.Count()
    Write !, "Partido ", p.Codigo, " en estado ", p.Estado, " con ", antes, " eventos.", !
    Do ..Resultado("Gol en el minuto 0 sobre un partido Finalizado", p.RegistrarEvento("ILEGAL-01", "Gol", 0, j))
    Do ..Resultado("Gol en el minuto 30 sobre un partido Finalizado", p.RegistrarEvento("ILEGAL-02", "Gol", 30, j))
    Do ..Resultado("Iniciar() un partido Finalizado", p.Iniciar())
    Write "  Verificacion: eventos en memoria = ", p.Eventos.Count(), " (antes ", antes, "), marcador = ", p.GolesLocal, "-", p.GolesVisitante, !
    Kill p, j

    Write !, "Partido nuevo DEMO-004 (Programado, no se guarda):", !
    Set p = ..NuevoPartido("DEMO-004", "ESP", "ARG", "BERN", "2030-07-23", "Final")
    Set jEsp = ..PrimerJugador(p.EquipoLocal), jBra = ..PrimerJugador(##class(Fixture.Equipo).CodigoIdxOpen("BRA"))
    Do ..Resultado("Finalizar() un partido Programado", p.Finalizar())
    Do ..Resultado("RegistrarEvento() en un partido Programado", p.RegistrarEvento("ILEGAL-03", "Gol", 10, jEsp))
    Do ..Resultado("Iniciar() sin arbitro Principal", p.Iniciar())
    Set aEsp = ##class(Fixture.Arbitro).ArbLicenciaIdxOpen("ARB-005"), aArg = ##class(Fixture.Arbitro).ArbLicenciaIdxOpen("ARB-001")
    Do ..Resultado("Designar a "_aEsp.Nombre_" ("_aEsp.Nacionalidad_") en ESP vs ARG", p.DesignarArbitro(aEsp, "Principal"))
    Do ..Resultado("Designar a "_aArg.Nombre_" ("_aArg.Nacionalidad_") en ESP vs ARG", p.DesignarArbitro(aArg, "Principal"))
    Do ..Resultado("Designar terna neutral (Principal, Asistente1, Asistente2)", ..DesignarTerna(p, 15))
    Set aOtro = ##class(Fixture.Arbitro).ArbLicenciaIdxOpen("ARB-018")
    Do ..Resultado("Designar un segundo Principal ("_aOtro.Nombre_")", p.DesignarArbitro(aOtro, "Principal"))
    Do ..Resultado("Iniciar() con Principal designado", p.Iniciar())
    Do ..Resultado("Gol en el minuto 0 con el partido EnJuego", p.RegistrarEvento("ILEGAL-04", "Gol", 0, jEsp))
    Do ..Resultado("Gol de un jugador de BRA en ESP vs ARG", p.RegistrarEvento("ILEGAL-05", "Gol", 20, jBra))
    Do ..Resultado("DesignarArbitro() con el partido EnJuego", p.DesignarArbitro(aOtro, "Cuarto"))
    Kill p

    Write !, "Invariantes que %OnBeforeSave() controla aunque se asignen propiedades sin los metodos:", !
    Set p = ..NuevoPartido("DEMO-005", "FRA", "FRA", "LUZ", "2030-07-24", "Final")
    Do ..Resultado("%Save() de FRA vs FRA", p.%Save())
    Kill p
    Set p = ..NuevoPartido("DEMO-006", "ENG", "GER", "CART", "2030-07-24", "Final")
    Set p.Estado = "Finalizado"
    Do ..Resultado("%Save() con Estado = Finalizado asignado a mano y sin arbitros", p.%Save())
    Kill p
    Set p = ..NuevoPartido("DEMO-007", "ITA", "NED", "CAMP", "2030-07-24", "Final")
    Do ..DesignarTerna(p, 19), p.Iniciar()
    Set p.GolesLocal = 5
    Do ..Resultado("%Save() con GolesLocal = 5 asignado a mano y sin goles registrados", p.%Save())
    Kill p
    Write "  Verificacion: existen DEMO-004..007? ", ##class(Fixture.Partido).CodigoIdxExists("DEMO-004"), ##class(Fixture.Partido).CodigoIdxExists("DEMO-005"), ##class(Fixture.Partido).CodigoIdxExists("DEMO-006"), ##class(Fixture.Partido).CodigoIdxExists("DEMO-007"), "  (0000 = ninguno se guardo)", !

    Write !, "Evento inalterable: se intenta corregir el minuto de EV-0001.", !
    Set ev = ##class(Fixture.Evento).CodigoIdxOpen("EV-0001")
    Write "  minuto original = ", ev.Minuto, !
    Set ev.Minuto = 1
    Do ..Resultado("ev.%Save() con el minuto cambiado", ev.%Save())
    Kill ev
    Do ..SQL("SELECT Codigo, Tipo, Minuto FROM Fixture.Evento WHERE Codigo = 'EV-0001'")
}

// ---------------------------------------------------------------- Bloque 7

/// Que pasa con los objetos relacionados ante cada borrado (matriz de integridad).
ClassMethod Bloque7Integridad()
{
    Do ..Titulo("BLOQUE 7 - Integridad referencial ante borrados (RF3, matriz de integridad)")
    Write !, "1) Padre-hijo: borrar un partido borra sus eventos y designaciones.", !
    Do ..Limpiar("DEMO-008")
    Set p = ..NuevoPartido("DEMO-008", "POR", "MAR", "DRAG", "2030-07-25", "Final")
    Do ..DesignarTerna(p, 4), p.Iniciar()
    Do p.RegistrarEvento("DEMO-EV-81", "Gol", 10, ..PrimerJugador(p.EquipoLocal))
    Do p.RegistrarEvento("DEMO-EV-82", "Tarjeta", 50, ..PrimerJugador(p.EquipoVisitante))
    Do p.Finalizar()
    Do ..Resultado("Guardar DEMO-008 con 2 eventos y 3 designaciones", p.%Save())
    Set id = p.%Id()
    Kill p
    Do ..SQL("SELECT (SELECT COUNT(*) FROM Fixture.Evento WHERE Partido = "_id_") AS Eventos, (SELECT COUNT(*) FROM Fixture.Designacion WHERE Partido = "_id_") AS Designaciones")
    Do ..Resultado("Fixture.Partido.%DeleteId("_id_")", ##class(Fixture.Partido).%DeleteId(id))
    Do ..SQL("SELECT (SELECT COUNT(*) FROM Fixture.Evento WHERE Partido = "_id_") AS Eventos, (SELECT COUNT(*) FROM Fixture.Designacion WHERE Partido = "_id_") AS Designaciones")

    Write !, "2) Uno-a-muchos: no se borra el extremo 'uno' mientras tenga objetos asociados.", !
    Set ev = ##class(Fixture.Evento).CodigoIdxOpen("EV-0001")
    Set idJug = ev.Jugador.%Id(), idSede = ev.Partido.Sede.%Id(), idEq = ev.Jugador.Equipo.%Id()
    Set d = ev.Partido.Designaciones.GetNext("")
    Set idArb = d.Arbitro.%Id()
    Kill ev, d
    Do ..Resultado("Borrar el Jugador "_idJug_" (tiene eventos)", ##class(Fixture.Jugador).%DeleteId(idJug))
    Write "  Verificacion: el jugador sigue existiendo? ", ##class(Fixture.Jugador).%ExistsId(idJug), !
    Do ..Resultado("Borrar la Sede "_idSede_" (tiene partidos)", ##class(Fixture.Sede).%DeleteId(idSede))
    Write "  Verificacion: la sede sigue existiendo? ", ##class(Fixture.Sede).%ExistsId(idSede), !
    Do ..Resultado("Borrar el Arbitro "_idArb_" (tiene designaciones)", ##class(Fixture.Arbitro).%DeleteId(idArb))
    Write "  Verificacion: el arbitro sigue existiendo? ", ##class(Fixture.Arbitro).%ExistsId(idArb), !
    Do ..Resultado("Borrar el Equipo "_idEq_" (tiene jugadores)", ##class(Fixture.Equipo).%DeleteId(idEq))
    Write "  Verificacion: el equipo sigue existiendo? ", ##class(Fixture.Equipo).%ExistsId(idEq), !
    Write "  (1 = sigue existiendo; ver docs/matriz_de_integridad.md)", !
}

// ---------------------------------------------------------------- Utilidades

ClassMethod Conteo()
{
    Do ..SQL("SELECT (SELECT COUNT(*) FROM Fixture.Sede) AS Sedes, (SELECT COUNT(*) FROM Fixture.Equipo) AS Equipos, (SELECT COUNT(*) FROM Fixture.Persona) AS Personas, (SELECT COUNT(*) FROM Fixture.Jugador) AS Jugadores, (SELECT COUNT(*) FROM Fixture.Arbitro) AS Arbitros, (SELECT COUNT(*) FROM Fixture.Tecnico) AS Tecnicos, (SELECT COUNT(*) FROM Fixture.Partido) AS Partidos, (SELECT COUNT(*) FROM Fixture.Evento) AS Eventos, (SELECT COUNT(*) FROM Fixture.Designacion) AS Designaciones")
}

/// Crea un partido Programado en memoria (no lo guarda).
ClassMethod NuevoPartido(codigo As %String, local As %String, visitante As %String, sede As %String, fecha As %String, fase As %String) As Fixture.Partido
{
    Set p = ##class(Fixture.Partido).%New()
    Set p.Codigo = codigo
    If fecha '= "" Set p.Fecha = $ZDateH(fecha, 3)
    Set p.Fase = fase
    Set p.EquipoLocal = ##class(Fixture.Equipo).CodigoIdxOpen(local)
    Set p.EquipoVisitante = ##class(Fixture.Equipo).CodigoIdxOpen(visitante)
    Set p.Sede = ##class(Fixture.Sede).CodigoIdxOpen(sede)
    Quit p
}

/// Designa Principal, Asistente1 y Asistente2 con los primeros arbitros que
/// DesignarArbitro() acepte a partir de la licencia ARB-<desde> (salta los no
/// neutrales y los ya designados). Cada demo usa arbitros, equipos y sedes
/// distintos, para que un arbol rechazado que sigue en memoria no se mezcle
/// con el guardado de otro arbol dentro del mismo proceso.
ClassMethod DesignarTerna(p As Fixture.Partido, desde As %Integer = 1) As %Status
{
    Set roles = $ListBuild("Principal", "Asistente1", "Asistente2")
    Set r = 1, n = desde - 1
    For {
        Quit:r>3
        Set n = n + 1
        Set a = ##class(Fixture.Arbitro).ArbLicenciaIdxOpen("ARB-"_$Translate($Justify(n, 3), " ", "0"))
        Quit:'$IsObject(a)
        If p.TieneRol($List(roles, r)) { Set r = r + 1 Continue }
        If $$$ISOK(p.DesignarArbitro(a, $List(roles, r))) Set r = r + 1
    }
    If r <= 3 Quit $$$ERROR($$$GeneralError, "No se pudo completar la terna arbitral")
    Quit $$$OK
}

ClassMethod PrimerJugador(equipo As Fixture.Equipo) As Fixture.Jugador
{
    Quit equipo.Jugadores.GetNext("")
}

ClassMethod ListarHijos(p As Fixture.Partido)
{
    Set key = ""
    For {
        Set d = p.Designaciones.GetNext(.key)
        Quit:key=""
        Write "    designacion ID = '", d.%Id(), "'  ", d.Rol, " -> ", d.Arbitro.Nombre, !
    }
    Set key = ""
    For {
        Set ev = p.Eventos.GetNext(.key)
        Quit:key=""
        Write "    evento      ID = '", ev.%Id(), "'  ", ev.Codigo, "  min ", ev.Minuto, "  ", ev.Tipo, " (", ev.Jugador.Equipo.Codigo, ")", !
    }
}

/// Borra un partido de demostracion si quedo de una corrida anterior.
ClassMethod Limpiar(codigo As %String)
{
    If ##class(Fixture.Partido).CodigoIdxExists(codigo, .id) Do ##class(Fixture.Partido).%DeleteId(id)
}

ClassMethod Resultado(operacion As %String, sc As %Status)
{
    If $$$ISOK(sc) {
        Write "  [ACEPTADO]  ", operacion, !
    } Else {
        Write "  [RECHAZADO] ", operacion, !
        Write "              motivo: ", $System.Status.GetErrorText(sc), !
    }
}

ClassMethod Titulo(texto As %String)
{
    Write !, "==========================================================================", !
    Write texto, !
    Write "==========================================================================", !
}

/// Ejecuta una sentencia SQL e imprime el resultado (fechas en formato ODBC).
ClassMethod SQL(sql As %String)
{
    Write !, "SQL> ", sql, !
    Set st = ##class(%SQL.Statement).%New()
    Set st.%SelectMode = 1
    Set sc = st.%Prepare(sql)
    If $$$ISERR(sc) { Write "  error: ", $System.Status.GetErrorText(sc), ! Quit }
    Set rs = st.%Execute()
    If rs.%SQLCODE < 0 { Write "  SQLCODE ", rs.%SQLCODE, ": ", rs.%Message, ! Quit }
    If rs.%StatementType = 1 {
        Do rs.%Display()
        Write !
    } Else {
        Write "  filas afectadas: ", rs.%ROWCOUNT, !
    }
}

}
