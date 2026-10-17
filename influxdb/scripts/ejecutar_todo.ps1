<#
 Hito 8 - Ejecuta el flujo completo en Windows (PowerShell) y deja el log como
 evidencia en docs/evidencia/logs/. Requiere Docker Desktop y Python 3.8+.

 Uso (desde la carpeta influxdb/):
   .\scripts\ejecutar_todo.ps1                      # perfil local (~1,3 M puntos)
   .\scripts\ejecutar_todo.ps1 -Perfil muestra      # prueba rapida (22 mil)
   .\scripts\ejecutar_todo.ps1 -Perfil completo     # objetivo 10M+ (10,6 M)
   .\scripts\ejecutar_todo.ps1 -MedirLotes -ProbarPersistencia
#>
param(
  [ValidateSet("muestra","local","completo")][string]$Perfil = "local",
  [switch]$MedirLotes,
  [switch]$ProbarPersistencia
)
$ErrorActionPreference = "Continue"
Set-Location (Split-Path -Parent $PSScriptRoot)
if (-not $env:HOME) { $env:HOME = $env:USERPROFILE }     # lo usa docker-compose.yml
$py = if (Get-Command python -ErrorAction SilentlyContinue) { "python" } else { "py" }
$marca = Get-Date -Format "yyyyMMdd_HHmmss"
New-Item -ItemType Directory -Force -Path "docs\evidencia\logs" | Out-Null
$log = "docs\evidencia\logs\ejecucion_${Perfil}_$marca.log"
$fallos = 0

# Todo el log se escribe en UTF-8 (Tee-Object de Windows PowerShell 5.1 usaria
# UTF-16, que GitHub no muestra como texto) y Python tambien emite UTF-8.
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
$OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONUTF8 = "1"
$env:PYTHONUNBUFFERED = "1"      # que la salida de Python se vea en vivo
Set-Content -Path $log -Value $null -Encoding UTF8
function Registrar {
  param([Parameter(ValueFromPipeline = $true)]$Linea)
  process { $t = "$Linea"; Write-Host $t; Add-Content -Path $log -Value $t -Encoding UTF8 }
}

function Paso([string]$titulo, [scriptblock]$bloque) {
  "`n######## $titulo ########" | Registrar
  & $bloque 2>&1 | Registrar
  if ($LASTEXITCODE -ne 0) {
    "!! el paso termino con codigo $LASTEXITCODE" | Registrar
    $script:fallos++
  }
}

"Hito 8 - ejecucion $marca | perfil: $Perfil" | Registrar
"Fecha local: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')" | Registrar
$cs = Get-CimInstance Win32_ComputerSystem
$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
"Equipo: $($cpu.Name) | nucleos logicos: $($cs.NumberOfLogicalProcessors) | RAM: $([math]::Round($cs.TotalPhysicalMemory/1GB,1)) GB" | Registrar
"Python: $(& $py --version 2>&1) | Docker: $(docker --version)" | Registrar

Paso "1. Inicializacion (compose, token local, bases)" { & $py scripts\inicializacion.py }
if ($fallos -gt 0) {
  "SE DETIENE: fallo la inicializacion. Verificar que Docker Desktop este abierto (docker version) y repetir." | Registrar
  exit $fallos
}
Paso "2. Generacion de puntos ($Perfil)"              { & $py scripts\generacion_puntos.py --perfil $Perfil }
Paso "3. Carga por lotes"                             { & $py scripts\carga_lotes.py --perfil $Perfil }
if ($fallos -gt 0) {
  "SE DETIENE: la carga tuvo lotes rechazados o se aborto. Ver el detalle arriba." | Registrar
  exit $fallos
}
if ($MedirLotes) {
  Paso "3b. Medicion de tamano de lote y concurrencia" { & $py scripts\carga_lotes.py --perfil $Perfil --medir-lotes }
}
Paso "4. Consultas temporales"                        { & $py scripts\consultas_temporales.py }
Paso "5. Agregaciones y resumen de 1 minuto"          { & $py scripts\agregaciones.py }
Paso "6. Validacion"                                  { & $py scripts\validacion.py --perfil $Perfil }
if ($ProbarPersistencia) {
  Paso "7. Persistencia: conteo, reinicio del contenedor y nuevo conteo" { & $py scripts\persistencia.py }
}
"`nResumen: $fallos paso(s) con error. Log: $log" | Registrar
exit $fallos
