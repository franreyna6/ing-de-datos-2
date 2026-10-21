# Inicia la API localmente (Windows PowerShell). Requiere el entorno creado (ver README).
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
if (Test-Path .env) {
  Get-Content .env | Where-Object { $_ -and $_ -notmatch '^\s*#' } | ForEach-Object {
    $k, $v = $_ -split '=', 2
    if ($k) { [Environment]::SetEnvironmentVariable($k.Trim(), $v.Trim()) }
  }
}
$puerto = if ($env:API_PORT) { $env:API_PORT } else { "8000" }
python -m uvicorn app.main:app --host "0.0.0.0" --port $puerto --reload
