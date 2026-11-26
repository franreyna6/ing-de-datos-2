# Envoltorio de PowerShell: ejecuta ejecutar_todo_h13.py con el Python del entorno de la API
# (api\.venv), que ya tiene los paquetes necesarios. Los argumentos se pasan tal cual.
# Uso, desde la raiz del repositorio:  .\monitoreo\scripts\ejecutar_todo_h13.ps1 [opciones]
$ErrorActionPreference = "Stop"
$raiz = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$py = Join-Path $raiz "api\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }
$env:PYTHONIOENCODING = "utf-8"
& $py (Join-Path $PSScriptRoot "ejecutar_todo_h13.py") @args
exit $LASTEXITCODE
