<#
 Hito 9 - Flujo completo en Windows (PowerShell): levanta IRIS, compila las
 clases, carga los datos y ejecuta los bloques de demostracion. Deja el log
 como evidencia en docs/evidencia/logs/. Requiere Docker Desktop.

 Uso (desde la carpeta iris/):
   .\scripts\ejecutar_todo.ps1                         # flujo normal
   .\scripts\ejecutar_todo.ps1 -Reiniciar              # borra el dominio y recarga desde cero
   .\scripts\ejecutar_todo.ps1 -ProbarPersistencia     # ademas recrea el contenedor y recuenta
   .\scripts\ejecutar_todo.ps1 -VolumenDocker -ProbarPersistencia   # Windows sin WSL

 Cada bloque corre en una sesion nueva del Terminal de IRIS (proceso limpio).

 ATENCION: con Docker Desktop en Windows, si ~/docker/data/iris esta en el
 disco de Windows, IRIS no puede hacer chown sobre /durable y no arranca.
 En ese caso agregar -VolumenDocker (o usar scripts/ejecutar_todo.sh desde WSL).
#>
param(
  [switch]$VolumenDocker,
  [switch]$Reiniciar,
  [switch]$ProbarPersistencia
)
$ErrorActionPreference = "Continue"
Set-Location (Split-Path -Parent $PSScriptRoot)
if (-not $env:HOME) { $env:HOME = $env:USERPROFILE }     # lo usa docker-compose.yml
$contenedor = "fixture2030-iris"
# -VolumenDocker: /durable en un volumen de Docker (docker-compose.windows.yml),
# para Windows, donde la carpeta del disco NTFS no admite el chown de IRIS.
$archivos = @("-f", "docker-compose.yml")
if ($VolumenDocker) { $archivos += @("-f", "docker-compose.windows.yml") }
function Compose { docker compose @archivos @args }
$marca = Get-Date -Format "yyyyMMdd_HHmmss"
New-Item -ItemType Directory -Force -Path "docs\evidencia\logs" | Out-Null
$log = "docs\evidencia\logs\ejecucion_$marca.log"

# El log se escribe en UTF-8 (Tee-Object de Windows PowerShell 5.1 usaria UTF-16).
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
# Lo que se envia por tuberia a "iris session" va en UTF-8 SIN BOM: un BOM al
# inicio haria fallar el primer comando ObjectScript.
$OutputEncoding = New-Object System.Text.UTF8Encoding $false
Set-Content -Path $log -Value $null -Encoding UTF8
function Registrar {
  param([Parameter(ValueFromPipeline = $true)]$Linea)
  process { $t = "$Linea"; Write-Host $t; Add-Content -Path $log -Value $t -Encoding UTF8 }
}
function Paso([string]$titulo, [scriptblock]$bloque) {
  "`n######## $titulo ########" | Registrar
  & $bloque 2>&1 | Registrar
}
# Ejecuta comandos ObjectScript en una sesion nueva del Terminal (namespace USER).
function Iris([string]$comandos) {
  "$comandos`nHalt`n" | docker exec -i $contenedor iris session IRIS -U USER
}
function EsperarIris {
  "Esperando a que IRIS arranque (el primer inicio copia Durable %SYS y tarda)..."
  $salida = ""
  for ($i = 0; $i -lt 120; $i++) {
    $estado = docker inspect -f "{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{end}}" $contenedor 2>&1
    $qlist = docker exec $contenedor iris qlist 2>&1
    if ("$qlist" -match "running") {
      $salida = Iris 'Write "IRIS-LISTO",!' 2>&1
      if ("$salida" -match "IRIS-LISTO") { "IRIS listo (contenedor: $estado)."; return }
    }
    if ($i % 6 -eq 0) { "  ... $([int]($i * 5 / 60)) min | contenedor: $estado" }
    Start-Sleep -Seconds 5
  }
  "IRIS no respondio en 10 minutos."
  "Estado del contenedor: $estado"
  "iris qlist: $qlist"
  "Ultima respuesta de iris session:"
  $salida
  "Ultimas lineas del log de IRIS:"
  Compose logs --tail 40 iris 2>&1
  if ("$(Compose logs iris 2>&1)" -match "Error executing chown") {
    "DIAGNOSTICO: IRIS no puede hacer chown sobre $env:HOME\docker\data\iris (disco de Windows)."
    "Solucion: docker compose down y volver a ejecutar con -VolumenDocker (o el .sh desde WSL). Ver README, nota de Windows."
  }
}

"Hito 9 - ejecucion $marca" | Registrar
"Fecha local: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')" | Registrar
$cs = Get-CimInstance Win32_ComputerSystem
$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
"Equipo: $($cpu.Name) | nucleos logicos: $($cs.NumberOfLogicalProcessors) | RAM: $([math]::Round($cs.TotalPhysicalMemory/1GB,1)) GB | Docker: $(docker --version)" | Registrar

if ($VolumenDocker) {
  Paso "0. Durable %SYS en el volumen de Docker fixture2030-iris-durable" {
    "Modo -VolumenDocker: /durable se monta en un volumen de Docker (docker-compose.windows.yml)."
    docker volume inspect fixture2030-iris-durable --format "{{.Name}} existe desde {{.CreatedAt}}" 2>&1
  }
} else {
  Paso "0. Directorio durable ~/docker/data/iris" {
    $dir = Join-Path $env:HOME "docker\data\iris"
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    Get-Item $dir | Select-Object FullName, LastWriteTime | Format-List | Out-String
  }
}
Paso "1. docker compose up -d"                    { Compose up -d }
Paso "1b. Espera del servicio"                    { EsperarIris }
if (-not (Select-String -Path $log -Pattern "IRIS listo" -SimpleMatch -Quiet)) {
  "SE DETIENE: IRIS no esta disponible. Verificar que Docker Desktop este abierto." | Registrar
  exit 1
}
Paso "1c. Version de IRIS y contenedor"           { Compose ps; Iris 'Write $ZVersion,!' }

Paso "2. Carga y compilacion de las clases .cls"  { Iris 'Set sc=$system.OBJ.LoadDir("/iris/src","ck",.err,1) Write !,"COMPILACION: ",$Select($System.Status.IsOK(sc):"OK",1:$System.Status.GetErrorText(sc)),!' }
if (-not (Select-String -Path $log -Pattern "COMPILACION: OK" -SimpleMatch -Quiet)) {
  "SE DETIENE: las clases no compilaron (ver el detalle arriba)." | Registrar
  exit 1
}
if ($Reiniciar) { Paso "2b. Reinicio del dominio" { Iris 'Do ##class(Fixture.Carga).Reiniciar()' } }
Paso "3. Bloque 1 - Carga inicial (RF6)"             { Iris 'Do ##class(Fixture.Demo).Bloque1Carga()' }
Paso "4. Bloque 2 - Arbol con un solo %Save (RF6)"   { Iris 'Do ##class(Fixture.Demo).Bloque2ArbolAtomico()' }
Paso "5. Bloque 3 - Fallo controlado (RF5)"          { Iris 'Do ##class(Fixture.Demo).Bloque3FalloControlado()' }
Paso "6. Bloque 4 - Navegacion por objetos (RF7)"    { Iris 'Do ##class(Fixture.Demo).Bloque4Navegacion()' }
Paso "7. Bloque 5 - Proyeccion SQL (RF8)"            { Iris 'Do ##class(Fixture.Demo).Bloque5ProyeccionSQL()' }
Paso "8. Bloque 6 - Validaciones (RF9)"              { Iris 'Do ##class(Fixture.Demo).Bloque6Validaciones()' }
Paso "9. Bloque 7 - Integridad ante borrados (RF3)"  { Iris 'Do ##class(Fixture.Demo).Bloque7Integridad()' }

if ($ProbarPersistencia) {
  Paso "10. Persistencia: conteo antes de recrear el contenedor" { Iris 'Do ##class(Fixture.Demo).Conteo()' }
  Paso "10b. docker compose down + up -d"                        { Compose down; Compose up -d }
  Paso "10c. Espera del servicio"                                { EsperarIris }
  Paso "10d. Persistencia: conteo despues de recrear el contenedor" { Iris 'Do ##class(Fixture.Demo).Conteo()' }
}
"`nFin. Log: $log" | Registrar
