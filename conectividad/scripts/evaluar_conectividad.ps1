<#
 Hito 11 - Evaluacion de conectividad (Windows PowerShell).
 Usa el Python del entorno virtual de la API (api/.venv), que tiene los mismos
 drivers que la API del Hito 10. Si no existe, usa el Python del sistema y las
 pruebas con driver quedan en SKIP.

 Ejemplos (desde la carpeta conectividad/):
   .\scripts\evaluar_conectividad.ps1 --modo completo --iniciar-api --etiqueta final
   .\scripts\evaluar_conectividad.ps1 --modo tcp --producto redis,neo4j
   .\scripts\evaluar_conectividad.ps1 --modo nativos --producto influxdb
   .\scripts\evaluar_conectividad.ps1 falla        # fallas controladas (falla_controlada.py)
#>
$ErrorActionPreference = "Continue"
$scripts = $PSScriptRoot
$venv = Join-Path $scripts "..\..\api\.venv\Scripts\python.exe"
$py = if (Test-Path $venv) { (Resolve-Path $venv).Path } else { "python" }
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
$env:PYTHONIOENCODING = "utf-8"
if ($args.Count -gt 0 -and $args[0] -eq "falla") {
  & $py (Join-Path $scripts "falla_controlada.py") @($args | Select-Object -Skip 1)
} else {
  & $py (Join-Path $scripts "evaluar_conectividad.py") @args
}
