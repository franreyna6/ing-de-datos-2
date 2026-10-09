# =============================================================================
# Hito 7 - Cache de usuarios y sesiones del Fixture 2030 (Grupo 8)
# ejecutar_todo.ps1 : version PowerShell de ejecutar_todo.sh (Windows)
# Corre TODOS los scripts del modulo contra el contenedor y guarda la salida de
# cada paso en docs/evidencia/logs/ (RF13, RNF3, RNF10).
#
# Uso (desde la carpeta redis/, con 'docker compose up -d' ya ejecutado):
#   powershell -ExecutionPolicy Bypass -File .\scripts\ejecutar_todo.ps1
#   $env:SIN_PRESION = 1   (antes de ejecutar) omite la prueba de presion de memoria
#
# La prueba de presion de memoria baja maxmemory temporalmente y evicta claves;
# al terminar restaura la configuracion y recarga la muestra (idempotente).
# =============================================================================
$ErrorActionPreference = "Continue"
Set-Location (Join-Path $PSScriptRoot "..")

$Contenedor = if ($env:CONTENEDOR) { $env:CONTENEDOR } else { "fixture2030-redis" }
$Logs = "docs/evidencia/logs"
New-Item -ItemType Directory -Force $Logs | Out-Null
$script:Fallos = 0

# Escribe el log en UTF-8 sin BOM (Tee-Object en Windows PowerShell 5 usaria UTF-16)
function Registrar($nombre, $lineas, [switch]$Agregar) {
    $texto = @($lineas | ForEach-Object { "$_" })
    $texto | ForEach-Object { Write-Host $_ }
    $ruta = Join-Path (Get-Location).Path "$Logs/$nombre.log"
    if ($Agregar) { [System.IO.File]::AppendAllLines($ruta, [string[]]$texto) }
    else { [System.IO.File]::WriteAllLines($ruta, [string[]]$texto) }
}

Write-Host "Esperando a que Redis responda PONG..."
$listo = $false
for ($i = 1; $i -le 30; $i++) {
    $r = docker exec $Contenedor redis-cli PING 2>$null
    if ("$r".Trim() -eq "PONG") { $listo = $true; break }
    Start-Sleep -Seconds 2
}
if (-not $listo) { throw "Redis no respondio. Revisar: docker compose ps / docker compose logs redis" }

# ---- 00. Ambiente (RF1, RNF1, RNF10): fecha, version observada de latest y recursos ----
$amb = @()
$amb += "Fecha de ejecucion (UTC): $((Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ'))"
$amb += "Equipo: $([System.Environment]::OSVersion.VersionString)"
$amb += (docker compose version 2>&1 | Select-Object -First 1)
$amb += (docker info --format "Docker: {{.ServerVersion}} | CPUs: {{.NCPU}} | Memoria total (bytes): {{.MemTotal}} | SO: {{.OperatingSystem}}" 2>&1)
$amb += (docker image inspect redis:latest --format "Imagen redis:latest: id {{.Id}} | creada {{.Created}}" 2>&1)
$amb += "Servidor: $(docker exec $Contenedor redis-server --version)"
$amb += "Cliente:  $(docker exec $Contenedor redis-cli --version)"
$amb += ""
$amb += (docker compose ps 2>&1)
Registrar "00_ambiente" $amb

function Paso($nombre, [string[]]$comando) {
    Write-Host "=== $nombre ($((Get-Date).ToUniversalTime().ToString('HH:mm:ssZ'))) ==="
    $salida = & docker exec $Contenedor @comando 2>&1
    if ($LASTEXITCODE -ne 0) { $script:Fallos++ }
    Registrar $nombre $salida
}

Paso "01_inicializacion"        @("sh", "/scripts/ejecutar_bloques.sh", "/scripts/inicializacion.redis")
Paso "02_carga_muestra"         @("sh", "/scripts/ejecutar_bloques.sh", "/scripts/carga_muestra.redis", "carga")
Paso "03_sesiones"              @("sh", "/scripts/ejecutar_bloques.sh", "/scripts/sesiones.redis")
Paso "04_cache"                 @("sh", "/scripts/ejecutar_bloques.sh", "/scripts/cache.redis")

# Servidor no disponible (simulado): un cliente apuntando a un puerto sin Redis (RF7)
$sinServidor = @(
    "",
    "# --- 7. Servidor no disponible (simulado) ---",
    "# Un cliente que apunta a un puerto sin Redis recibe un error de conexion. Comportamiento",
    "# esperado de la aplicacion: responder consultando la fuente de verdad (modo degradado).",
    "> redis-cli -p 6399 PING"
)
$sinServidor += (docker exec $Contenedor redis-cli -p 6399 PING 2>&1 | ForEach-Object { "  $_" })
Registrar "04_cache" $sinServidor -Agregar

Paso "05_concurrencia_comandos" @("sh", "/scripts/ejecutar_bloques.sh", "/scripts/concurrencia.redis")
Paso "06_concurrencia_paralela" @("sh", "/scripts/concurrencia_paralela.sh")
Paso "07_auditoria_ttl"         @("sh", "/scripts/auditoria_ttl.sh")
Paso "08_metricas"              @("sh", "/scripts/ejecutar_bloques.sh", "/scripts/metricas.redis")
Paso "09_medicion"              @("sh", "/scripts/medicion.sh")
if (-not $env:SIN_PRESION) {
    Paso "10_presion_memoria"   @("sh", "/scripts/presion_memoria.sh")
    Paso "11_metricas_final"    @("sh", "/scripts/ejecutar_bloques.sh", "/scripts/metricas.redis")
}

# ---- 12. Persistencia (RNF2): los datos y los TTL sobreviven al reinicio del contenedor ----
$per = @("=== ANTES del reinicio ($((Get-Date).ToUniversalTime().ToString('HH:mm:ssZ'))) ===")
$per += (docker exec $Contenedor sh /scripts/ejecutar_bloques.sh /scripts/persistencia.redis 2>&1)
$per += ""
$per += "=== docker compose restart redis ==="
$per += (docker compose restart redis 2>&1)
$volvio = $false
for ($i = 1; $i -le 30; $i++) {
    $r = docker exec $Contenedor redis-cli PING 2>$null
    if ("$r".Trim() -eq "PONG") { $volvio = $true; break }
    Start-Sleep -Seconds 2
}
$per += "Redis volvio a responder: $(if ($volvio) { 'si' } else { 'NO' })"
$per += ""
$per += "=== DESPUES del reinicio ($((Get-Date).ToUniversalTime().ToString('HH:mm:ssZ'))) ==="
$per += (docker exec $Contenedor sh /scripts/ejecutar_bloques.sh /scripts/persistencia.redis 2>&1)
Registrar "12_persistencia" $per

""
if ($script:Fallos -eq 0) { "Listo. Registros en $Logs/ (sin pasos fallidos)." }
else { "Listo con $($script:Fallos) paso(s) que devolvieron error. Revisar los logs en $Logs/." }
