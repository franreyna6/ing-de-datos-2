# Envoltorio de PowerShell: ejecuta diagnosticar_bases.py con el Python del entorno de la API
# (api\.venv), que ya tiene los paquetes necesarios. Los argumentos se pasan tal cual.
# Uso, desde la raiz del repositorio:  .\monitoreo\scripts\diagnosticar_bases.ps1 [opciones]
$ErrorActionPreference = "Stop"
$raiz = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$py = Join-Path $raiz "api\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }
$env:PYTHONIOENCODING = "utf-8"
& $py (Join-Path $PSScriptRoot "diagnosticar_bases.py") @args
exit $LASTEXITCODE
