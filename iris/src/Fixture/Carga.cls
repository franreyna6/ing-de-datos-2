/// Hito 9 - Carga inicial del dominio a partir de los CSV del Hito 5 (RF6).
///
/// Orden: sedes, equipos, tecnicos, jugadores, arbitros y partidos.
/// Cada partido se construye como un arbol de objetos en memoria (partido +
/// designaciones + eventos), recorriendo la maquina de estados con los metodos
/// del dominio, y se guarda con UN SOLO partido.%Save().
///
/// Los arbitros y tecnicos no existen en los CSV del Hito 5: se generan de forma
/// determinista (datos simulados) para poder poblar la jerarquia de Persona.
///
/// Uso desde el Terminal (namespace USER):
///   Do ##class(Fixture.Carga).Todo()             // carga si la base esta vacia
///   Do ##class(Fixture.Carga).Reiniciar()        // borra todo el dominio (laboratorio)
Class Fixture.Carga
{

/// Carpeta donde docker-compose.yml monta data/origen (solo lectura).
Parameter DIRECTORIO = "/iris/data";

ClassMethod Todo(dir As %String = {..#DIRECTORIO}) As %Status
{
    Write !, "=== Carga inicial desde ", dir, " ===", !
    If ##class(Fixture.Partido).CodigoIdxExists("F2030-001") {
        Write "Los datos ya estan cargados: no se duplica nada (carga idempotente).", !
        Write "Para empezar de cero: Do ##class(Fixture.Carga).Reiniciar()", !
        Quit $$$OK
    }
    Set sc = ..Sedes(dir)
    If $$$ISOK(sc) Set sc = ..Equipos(dir)
    If $$$ISOK(sc) Set sc = ..Tecnicos(dir)
    If $$$ISOK(sc) Set sc = ..Jugadores(dir)
    If $$$ISOK(sc) Set sc = ..Arbitros()
    If $$$ISOK(sc) Set sc = ..Partidos(dir)
    If $$$ISERR(sc) {
        Write "CARGA INTERRUMPIDA: ", $System.Status.GetErrorText(sc), !
    } Else {
        Write "Carga completa.", !
    }
    Quit sc
}

/// Lee un CSV (sin la fila de encabezado) en filas(1..n); filas = n.
ClassMethod Leer(archivo As %String, ByRef filas) As %Status
{
    Kill filas
    Set filas = 0
    Set stream = ##class(%Stream.FileCharacter).%New()
    Set sc = stream.LinkToFile(archivo)
    If $$$ISERR(sc) Quit sc
    Set stream.TranslateTable = "UTF8"
    If stream.AtEnd Quit $$$ERROR($$$GeneralError, "No se encontro o esta vacio: "_archivo)
    Do stream.ReadLine()
    While 'stream.AtEnd {
        // $ZStrip quita el fin de linea de Windows (CR) si el archivo lo trae.
        Set linea = $ZStrip(stream.ReadLine(), "*C")
        Continue:linea=""
        Set filas = filas + 1
        Set filas(filas) = linea
    }
    Quit $$$OK
}

ClassMethod Sedes(dir As %String) As %Status
{
    Set sc = ..Leer(dir_"/sedes.csv", .filas)
    If $$$ISERR(sc) Quit sc
    For i = 1:1:filas {
        Set f = filas(i)
        Set s = ##class(Fixture.Sede).%New()
        Set s.Codigo = $Piece(f, ",", 1)
        Set s.Nombre = $Piece(f, ",", 2)
        Set s.Ubicacion.Ciudad = $Piece(f, ",", 3)
        Set s.Ubicacion.Pais = $Piece(f, ",", 4)
        Set sc = s.%Save()
        If $$$ISERR(sc) Return sc
    }
    Write "Sedes:      ", filas, !
    Quit $$$OK
}

ClassMethod Equipos(dir As %String) As %Status
{
    Set sc = ..Leer(dir_"/equipos.csv", .filas)
    If $$$ISERR(sc) Quit sc
    For i = 1:1:filas {
        Set f = filas(i)
        Set e = ##class(Fixture.Equipo).%New()
        Set e.Codigo = $Piece(f, ",", 1)
        Set e.Nombre = $Piece(f, ",", 2)
        Set e.Confederacion = $Piece(f, ",", 3)
        Set e.RankingFIFA = $Piece(f, ",", 4)
        Set e.EsAnfitrion = ($Piece(f, ",", 5) = "true")
        Set e.Grupo = $Piece(f, ",", 6)
        Set sc = e.%Save()
        If $$$ISERR(sc) Return sc
    }
    Write "Equipos:    ", filas, !
    Quit $$$OK
}

/// Un tecnico simulado por equipo, de la misma nacionalidad que el equipo.
ClassMethod Tecnicos(dir As %String) As %Status
{
    Set nombres = $ListBuild("Ricardo","Marcelo","Jorge","Luis","Carlos","Diego","Fernando","Pablo","Andres","Hugo","Sergio","Martin")
    Set apellidos = $ListBuild("Gareca","Bielsa","Sampaoli","Pekerman","Tabarez","Bauza","Pizzi","Lopez","Garcia","Rossi","Silva","Mendez","Ortiz")
    Set sc = ..Leer(dir_"/equipos.csv", .filas)
    If $$$ISERR(sc) Quit sc
    For i = 1:1:filas {
        Set cod = $Piece(filas(i), ",", 1)
        Set eq = ##class(Fixture.Equipo).CodigoIdxOpen(cod)
        Set t = ##class(Fixture.Tecnico).%New()
        Set t.Nombre = $List(nombres, (i # $ListLength(nombres)) + 1)_" "_$List(apellidos, (i # $ListLength(apellidos)) + 1)
        Set t.Nacionalidad = cod
        Set t.Experiencia = 5 + (i # 20)
        Set t.Equipo = eq
        Set sc = t.%Save()
        If $$$ISERR(sc) Return sc
    }
    Write "Tecnicos:   ", filas, " (simulados)", !
    Quit $$$OK
}

ClassMethod Jugadores(dir As %String) As %Status
{
    Set sc = ..Leer(dir_"/jugadores.csv", .filas)
    If $$$ISERR(sc) Quit sc
    For i = 1:1:filas {
        Set f = filas(i)
        Set codEq = $Piece(f, ",", 5)
        If '$Data(eqs(codEq)) Set eqs(codEq) = ##class(Fixture.Equipo).CodigoIdxOpen(codEq)
        Set j = ##class(Fixture.Jugador).%New()
        Set j.Codigo = $Piece(f, ",", 1)
        Set j.Nombre = $Piece(f, ",", 2)
        Set j.Posicion = $Piece(f, ",", 3)
        Set j.Dorsal = $Piece(f, ",", 4)
        Set j.Nacionalidad = codEq
        Set j.Equipo = eqs(codEq)
        Set sc = j.%Save()
        If $$$ISERR(sc) Return sc
    }
    Write "Jugadores:  ", filas, !
    Quit $$$OK
}

/// 22 arbitros simulados. Sus nacionalidades son de equipos del torneo, para que
/// la regla de neutralidad de DesignarArbitro() tenga efecto real.
ClassMethod Arbitros() As %Status
{
    Set nacs = $ListBuild("ARG","BRA","URU","COL","ESP","FRA","ENG","POR","ITA","GER","NED","MEX","USA","MAR","SEN","EGY","JPN","KOR","AUS","KSA","NZL","CRO")
    Set nombres = $ListBuild("Nestor Pitana","Wilton Sampaio","Andres Matonte","Wilmar Roldan","Antonio Mateu","Clement Turpin","Michael Oliver","Artur Soares","Daniele Orsato","Felix Brych","Danny Makkelie","Cesar Ramos","Ismail Elfath","Redouane Jiyed","Maguette Ndiaye","Mohamed Adel","Yoshimi Yamashita","Kim Jong-hyeok","Chris Beath","Mohammed Al-Hoaish","Matthew Conger","Ivan Bebek")
    For i = 1:1:$ListLength(nacs) {
        Set a = ##class(Fixture.Arbitro).%New()
        Set a.Nombre = $List(nombres, i)
        Set a.Nacionalidad = $List(nacs, i)
        Set a.Licencia = "ARB-"_$Translate($Justify(i, 3), " ", "0")
        Set a.Categoria = "FIFA"
        Set sc = a.%Save()
        If $$$ISERR(sc) Return sc
    }
    Write "Arbitros:   ", $ListLength(nacs), " (simulados)", !
    Quit $$$OK
}

/// Construye y guarda cada partido como un arbol: designaciones + eventos.
ClassMethod Partidos(dir As %String) As %Status
{
    // Participaciones: quien es local y quien visitante en cada partido.
    Set sc = ..Leer(dir_"/participaciones.csv", .filas)
    If $$$ISERR(sc) Quit sc
    For i = 1:1:filas {
        Set f = filas(i)
        Set lados($Piece(f, ",", 1), $Piece(f, ",", 3)) = $Piece(f, ",", 2)
    }
    // Eventos agrupados por partido.
    Set sc = ..Leer(dir_"/eventos.csv", .filas)
    If $$$ISERR(sc) Quit sc
    For i = 1:1:filas {
        Set f = filas(i)
        Set p = $Piece(f, ",", 4)
        Set evs(p) = $Get(evs(p)) + 1
        Set evs(p, evs(p)) = f
    }
    // Arbitros disponibles, en orden de licencia.
    Set narb = 0
    For {
        Set a = ##class(Fixture.Arbitro).ArbLicenciaIdxOpen("ARB-"_$Translate($Justify(narb + 1, 3), " ", "0"))
        Quit:'$IsObject(a)
        Set narb = narb + 1
        Set arbs(narb) = a
    }
    Set roles = $ListBuild("Principal", "Asistente1", "Asistente2")
    Set sc = ..Leer(dir_"/partidos.csv", .filas)
    If $$$ISERR(sc) Quit sc
    Set nev = 0
    For i = 1:1:filas {
        Set f = filas(i)
        Set cod = $Piece(f, ",", 1)
        Set p = ##class(Fixture.Partido).%New()
        Set p.Codigo = cod
        Set p.Fecha = $ZDateH($Piece(f, ",", 2), 3)
        Set p.Fase = $Piece(f, ",", 3)
        Set p.Grupo = $Piece(f, ",", 4)
        Set p.EquipoLocal = ##class(Fixture.Equipo).CodigoIdxOpen($Get(lados(cod, "local")))
        Set p.EquipoVisitante = ##class(Fixture.Equipo).CodigoIdxOpen($Get(lados(cod, "visitante")))
        Set p.Sede = ##class(Fixture.Sede).CodigoIdxOpen($Piece(f, ",", 7))
        // Terna arbitral: rota entre los arbitros; DesignarArbitro() rechaza los no neutrales.
        Set r = 1, intento = 0
        While (r <= 3) && (intento < narb) {
            Set arb = arbs(((i + intento) # narb) + 1)
            Set intento = intento + 1
            If $$$ISOK(p.DesignarArbitro(arb, $List(roles, r))) Set r = r + 1
        }
        If r <= 3 Return $$$ERROR($$$GeneralError, "No hay arbitros neutrales suficientes para "_cod)
        Set sc = p.Iniciar()
        If $$$ISERR(sc) Return sc
        For k = 1:1:$Get(evs(cod)) {
            Set e = evs(cod, k)
            Set jug = ##class(Fixture.Jugador).JugCodigoIdxOpen($Piece(e, ",", 5))
            Set sc = p.RegistrarEvento($Piece(e, ",", 1), $Piece(e, ",", 2), $Piece(e, ",", 3), jug)
            If $$$ISERR(sc) Return sc
            Set nev = nev + 1
        }
        Set sc = p.Finalizar()
        If $$$ISERR(sc) Return sc
        // Control cruzado: el marcador calculado desde los eventos debe coincidir con el CSV.
        If (p.GolesLocal '= $Piece(f, ",", 5)) || (p.GolesVisitante '= $Piece(f, ",", 6)) {
            Return $$$ERROR($$$GeneralError, "El marcador de "_cod_" no coincide con el CSV")
        }
        // UN SOLO guardado: partido + designaciones + eventos en una transaccion.
        Set sc = p.%Save()
        If $$$ISERR(sc) Return sc
    }
    Write "Partidos:   ", filas, " (cada uno con un solo %Save del arbol)", !
    Write "Eventos:    ", nev, !
    Write "Designaciones: ", filas * 3, !
    Quit $$$OK
}

/// Borra todo el dominio (uso de laboratorio). Primero los partidos, que borran
/// en cascada sus eventos y designaciones; despues personas, equipos y sedes.
ClassMethod Reiniciar() As %Status
{
    Write !, "=== Reinicio del dominio ===", !
    For clase = "Fixture.Partido", "Fixture.Persona", "Fixture.Equipo", "Fixture.Sede" {
        Set sc = $ClassMethod(clase, "%DeleteExtent")
        Write clase, ": ", $Select($$$ISOK(sc): "vaciada", 1: $System.Status.GetErrorText(sc)), !
        If $$$ISERR(sc) Return sc
    }
    Quit $$$OK
}

}
