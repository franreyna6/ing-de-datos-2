# =============================================================================
# Hito 6 - Comentarios masivos del Fixture 2030 (Grupo 8)
# carga_o_prueba.ps1 : version PowerShell de carga_o_prueba.sh (Windows)
# Carga masiva (1.100.000 comentarios, > 1.000.000) y medicion de escrituras con COPY.
#
# Uso (desde la carpeta cassandra/):
#   powershell -ExecutionPolicy Bypass -File .\scripts\carga_o_prueba.ps1
#   $env:TOTAL = 20000; .\scripts\carga_o_prueba.ps1      # prueba rapida
# Registrar solo la PRIMERA corrida sobre tablas vacias (ver carga_o_prueba.sh).
# =============================================================================
$ErrorActionPreference = "Continue"
Set-Location (Join-Path $PSScriptRoot "..")

$Contenedor   = if ($env:CONTENEDOR)   { $env:CONTENEDOR }   else { "fixture2030-cassandra" }
$Total        = if ($env:TOTAL)        { $env:TOTAL }        else { "1100000" }
$NumProcesses = if ($env:NUMPROCESSES) { $env:NUMPROCESSES } else { "2" }
$ChunkSize    = if ($env:CHUNKSIZE)    { $env:CHUNKSIZE }    else { "1000" }
$KS = "fixture2030_comentarios"
$Stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMdd_HHmmss")
$Log = "docs/evidencia/logs/carga_$Stamp.log"
New-Item -ItemType Directory -Force docs/evidencia/logs, data/generado | Out-Null

function Cqlsh($sql) { docker exec -i $Contenedor cqlsh -e $sql }

if (-not ((Test-Path data/generado/comentarios_por_partido.csv) -and (Test-Path data/generado/comentarios_por_usuario.csv))) {
    python scripts/generar_datos.py --total $Total
}
$Filas = (Get-Content data/generado/comentarios_por_partido.csv | Measure-Object -Line).Lines - 1

& {
    "=== PRUEBA DE CARGA - HITO 6 (Cassandra) ==="
    "Fecha de ejecucion (UTC): $((Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ'))"
    "Host: $([System.Environment]::OSVersion.VersionString) | procesadores logicos: $([Environment]::ProcessorCount)"
    "Recursos visibles para Docker: $(docker info --format '{{.NCPU}} CPUs, {{.MemTotal}} bytes de memoria')"
    "Contenedor: $Contenedor"
    "--- Version de Cassandra (SHOW VERSION) ---"
    Cqlsh "SHOW VERSION"
    "--- Estado del nodo (nodetool status) ---"
    docker exec $Contenedor nodetool status
    "--- Parametros ---"
    "Filas por CSV: $Filas | NUMPROCESSES=$NumProcesses | CHUNKSIZE=$ChunkSize"

    ""
    "--- COPY 1/2: comentarios_por_partido ---"
    $sw1 = [Diagnostics.Stopwatch]::StartNew()
    Cqlsh "COPY $KS.comentarios_por_partido (partido_id, ventana, creado_en, comentario_id, usuario_id, contenido, estado, likes) FROM '/data/generado/comentarios_por_partido.csv' WITH HEADER = TRUE AND NUMPROCESSES = $NumProcesses AND CHUNKSIZE = $ChunkSize;"
    $sw1.Stop()

    ""
    "--- COPY 2/2: comentarios_por_usuario ---"
    $sw2 = [Diagnostics.Stopwatch]::StartNew()
    Cqlsh "COPY $KS.comentarios_por_usuario (usuario_id, creado_en, comentario_id, partido_id, ventana, contenido, estado) FROM '/data/generado/comentarios_por_usuario.csv' WITH HEADER = TRUE AND NUMPROCESSES = $NumProcesses AND CHUNKSIZE = $ChunkSize;"
    $sw2.Stop()

    ""
    "--- RESULTADO DE LA MEDICION ---"
    $d1 = $sw1.Elapsed.TotalSeconds; $d2 = $sw2.Elapsed.TotalSeconds
    "comentarios_por_partido : {0} filas en {1,8:N1} s -> {2,10:N0} filas/s" -f $Filas, $d1, ($Filas / $d1)
    "comentarios_por_usuario : {0} filas en {1,8:N1} s -> {2,10:N0} filas/s" -f $Filas, $d2, ($Filas / $d2)
    "Total                   : {0} escrituras fisicas en {1,8:N1} s -> {2,10:N0} escrituras/s" -f (2 * $Filas), ($d1 + $d2), (2 * $Filas / ($d1 + $d2))
    "Objetivo del hito: 10.000 escrituras/s o mas (si el hardware lo permite)."

    ""
    "--- VERIFICACION DE LA CARGA (conteo esperado segun el CSV vs. conteo en Cassandra) ---"
    $esp1 = (Select-String -Path data/generado/comentarios_por_partido.csv -Pattern '^F2030-063,2030-06-22 20:35:00' | Measure-Object).Count
    $obs1 = (Cqlsh "SELECT COUNT(*) FROM $KS.comentarios_por_partido WHERE partido_id='F2030-063' AND ventana='2030-06-22 20:35:00+0000';" | Select-String '^\s*\d+\s*$' | Select-Object -First 1).Line.Trim()
    "Particion (F2030-063, ventana 20:35): esperado=$esp1 observado=$obs1"
    $esp2 = (Select-String -Path data/generado/comentarios_por_usuario.csv -Pattern '^U000001,' | Measure-Object).Count
    $obs2 = (Cqlsh "SELECT COUNT(*) FROM $KS.comentarios_por_usuario WHERE usuario_id='U000001';" | Select-String '^\s*\d+\s*$' | Select-Object -First 1).Line.Trim()
    "Particion (usuario U000001)         : esperado=$esp2 observado=$obs2"
} *>&1 | Tee-Object -FilePath $Log

"Registro guardado en $Log"
