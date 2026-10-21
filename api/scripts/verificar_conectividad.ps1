# Consulta /salud y muestra que fuentes estan disponibles (RF17, RNF11).
param([string]$Base = "http://localhost:8000")
Write-Host "Consultando $Base/salud ..."
Invoke-RestMethod "$Base/salud" | ConvertTo-Json -Depth 5
