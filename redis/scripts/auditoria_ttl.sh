#!/bin/sh
# =============================================================================
# auditoria_ttl.sh - Hito 7 (Grupo 8)
# Verifica la regla de ciclo de vida (RNF6): TODO dato temporal tiene TTL y solo
# las claves conservadas por decision explicita no lo tienen. Recorre las claves
# con SCAN (nunca KEYS *, RNF8) y consulta el TTL de cada una.
#
# Esto es lo que exige la politica volatile-lru: solo las claves con TTL son
# candidatas a eviccion; una clave temporal sin TTL quedaria fuera de ese control.
#
# Uso: sh /scripts/auditoria_ttl.sh        (sale con codigo distinto de 0 si la regla se viola)
# =============================================================================
. "$(dirname "$0")/lib_redis.sh"

echo "Fecha de ejecucion (UTC): $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo
printf '%-14s %8s %9s %9s   %s\n' "Prefijo" "Claves" "Con TTL" "Sin TTL" "Regla"

violaciones=0

# auditar <prefijo> <temporal|conservada> : las temporales no pueden tener claves sin TTL;
# las conservadas no deben tener TTL (su ciclo de vida es "conservar", ver docs).
auditar() {
  total=0; con=0; sin=0
  for k in $(listar_claves "$1*" | sort -u); do
    total=$((total + 1))
    ttl=$(redis-cli TTL "$k")
    if [ "$ttl" = "-1" ]; then sin=$((sin + 1)); else con=$((con + 1)); fi
  done
  if [ "$2" = "temporal" ]; then
    regla="temporal: sin TTL debe ser 0"
    [ "$sin" != "0" ] && violaciones=$((violaciones + 1))
  else
    regla="conservada por decision: con TTL debe ser 0"
    [ "$con" != "0" ] && violaciones=$((violaciones + 1))
  fi
  printf '%-14s %8d %9d %9d   %s\n' "$1" "$total" "$con" "$sin" "$regla"
}

auditar "sesion:"   temporal
auditar "cache:"    temporal
auditar "prueba:"   temporal
auditar "partido:"  conservada
auditar "encuesta:" conservada

echo
if [ "$violaciones" = "0" ]; then
  echo "Resultado: OK - ninguna clave temporal sin TTL y ninguna clave conservada con TTL."
else
  echo "Resultado: $violaciones prefijo(s) incumplen la regla de ciclo de vida."
  exit 1
fi
