"""REPETICION OPTIMIZADA (RF9): mismo escenario, misma carga, API CON cache.

Requisito: reiniciar la API con CACHE_COMENTARIOS_TTL_S=2. El script lo
verifica antes de empezar (primera lectura MISS, segunda HIT) y se niega a
correr si la API no esta en ese modo.

Usar el MISMO --escala que en la linea base (si se uso alguno): de lo
contrario la comparacion no es valida y comparar_resultados.py lo marca.

Uso:
  python scripts/ejecutar_prueba_optimizada.py
Luego:
  python scripts/validar_integridad.py <etiqueta que imprime>
  python scripts/comparar_resultados.py <etiqueta_base> <etiqueta_opt>
"""
import sys

import ejecutar_carga

if __name__ == "__main__":
    ejecutar_carga.main(["--modo", "opt", "--cache-esperada", "ON", *sys.argv[1:]])
