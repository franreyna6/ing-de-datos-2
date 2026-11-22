"""LINEA BASE (RF4): corre el escenario con la API SIN cache.

Requisito: la API tiene que estar levantada con CACHE_COMENTARIOS_TTL_S=0 (o sin
esa variable). El script lo verifica antes de empezar (header X-Cache: OFF) y
se niega a correr si la API no esta en ese modo.

Uso:
  python scripts/ejecutar_linea_base.py              # escenario completo
  python scripts/ejecutar_linea_base.py --escala 0.5 # mitad de usuarios
Luego:
  python scripts/validar_integridad.py <etiqueta que imprime>
"""
import sys

import ejecutar_carga

if __name__ == "__main__":
    ejecutar_carga.main(["--modo", "base", "--cache-esperada", "OFF", *sys.argv[1:]])
