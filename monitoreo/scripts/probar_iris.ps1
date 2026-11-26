# Envoltorio de PowerShell: ejecuta probar_iris.py con el Python del entorno de la API
# (api\.venv), que ya tiene los paquetes necesarios. Los argumentos se pasan tal cual.
# Uso, desde la raiz del repositorio:  .\monitoreo\scripts\probar_iris.ps1 [opciones]
$ErrorActionPreference = "Stop"
$raiz = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$py = Join-Path $raiz "api\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }
$env:PYTHONIOENCODING = "utf-8"
& $py (Join-Path $PSScriptRoot "probar_iris.py") @args
exit $LASTEXITCODE
