# =============================================================================
# Hito 6 - Comentarios masivos del Fixture 2030 (Grupo 8)
# ejecutar_todo.ps1 : version PowerShell de ejecutar_todo.sh (Windows)
# Ejecuta esquema -> muestra -> CRUD -> consultas y guarda cada salida en
# docs/evidencia/logs/.
#
# Uso (desde la carpeta cassandra/):
#   powershell -ExecutionPolicy Bypass -File .\scripts\ejecutar_todo.ps1
# =============================================================================
$ErrorActionPreference = "Continue"
Set-Location (Join-Path $PSScriptRoot "..")

$Contenedor = if ($env:CONTENEDOR) { $env:CONTENEDOR } else { "fixture2030-cassandra" }
$Logs = "docs/evidencia/logs"
New-Item -ItemType Directory -Force $Logs | Out-Null

Write-Host "Esperando a que Cassandra acepte conexiones CQL (el primer inicio puede tardar)..."
$listo = $false
for ($i = 1; $i -le 40; $i++) {
    docker exec $Contenedor cqlsh -e "DESCRIBE KEYSPACES" *> $null
    if ($LASTEXITCODE -eq 0) { $listo = $true; break }
    Start-Sleep -Seconds 10
}
if (-not $listo) { throw "Cassandra no respondio. Revisar: docker compose logs cassandra" }

& {
    "Fecha de ejecucion (UTC): $((Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ'))"
    docker exec $Contenedor nodetool status
} *>&1 | Tee-Object -FilePath "$Logs/00_estado_nodo.log"

function Paso($nombre, $archivo) {
    "=== $archivo ==="
    docker exec -i $Contenedor cqlsh -f "/scripts/$archivo" *>&1 | Tee-Object -FilePath "$Logs/$nombre.log"
}
Paso "01_esquema"        "esquema.cql"
Paso "02_carga_muestra"  "carga_muestra.cql"
Paso "03_crud"           "crud.cql"
Paso "04_consultas"      "consultas.cql"

"Listo. Registros en $Logs/"
