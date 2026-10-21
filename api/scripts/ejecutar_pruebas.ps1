# Corre los tests (no requieren bases: validan contrato y manejo de errores).
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
python -m pytest tests/ -v
