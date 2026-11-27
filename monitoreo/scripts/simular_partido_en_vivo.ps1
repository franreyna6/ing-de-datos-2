# Envoltorio de PowerShell: ejecuta simular_partido_en_vivo.py con el Python del entorno de la API
# (api\.venv), que ya tiene los paquetes necesarios. Los argumentos se pasan tal cual.
# Uso, desde la raiz del repositorio:  .\monitoreo\scripts\simular_partido_en_vivo.ps1 [opciones]
$ErrorActionPreference = "Stop"
$raiz = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$py = Join-Path $raiz "api\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }
$env:PYTHONIOENCODING = "utf-8"
& $py (Join-Path $PSScriptRoot "simular_partido_en_vivo.py") @args
exit $LASTEXITCODE
