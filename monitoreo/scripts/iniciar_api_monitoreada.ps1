# Envoltorio de PowerShell: ejecuta iniciar_api_monitoreada.py con el Python del entorno de la API
# (api\.venv), que ya tiene los paquetes necesarios. Los argumentos se pasan tal cual.
# Uso, desde la raiz del repositorio:  .\monitoreo\scripts\iniciar_api_monitoreada.ps1 [opciones]
$ErrorActionPreference = "Stop"
$raiz = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$py = Join-Path $raiz "api\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }
$env:PYTHONIOENCODING = "utf-8"
& $py (Join-Path $PSScriptRoot "iniciar_api_monitoreada.py") @args
exit $LASTEXITCODE
