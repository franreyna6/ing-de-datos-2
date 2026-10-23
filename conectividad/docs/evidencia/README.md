# Evidencia — Hito 11

Todo lo que hay acá se generó con los scripts de `conectividad/scripts/` en la notebook del
equipo, el 2026-10-23. Las salidas están **redactadas**: passwords, tokens y URI con credenciales
se reemplazan por `****` antes de escribir cualquier archivo (`lib_conectividad.redactar`). Se
verificó con una búsqueda del token real y de patrones `apiv3_…` / `usuario:password@` sobre
toda esta carpeta (sin coincidencias).

| Ruta | Contenido |
| :--- | :--- |
| `resultados_configuracion.*`, `resultados_tcp.*`, `resultados_clientes.*`, `resultados_api.*` | Última corrida completa (copia de `corridas/…_final/`), con los nombres que pide el enunciado. `.txt` para leer y `.json` con todos los campos (fecha, commit, origen, cliente, capa, resultado, ms, request_id, log, …) |
| `matriz_ultima_corrida.md` | Matriz generada de la última corrida |
| `corridas/20261023_031659_inicial/` | Corrida completa **antes** de las correcciones C1 y C2 |
| `corridas/20261023_031855_C1_iris_password/` | IRIS en modo nativo después de C1 |
| `corridas/20261023_031908_C2_antes_localhost/`, `…_C2_despues_127/` | TCP de InfluxDB e IRIS antes y después de C2 |
| `corridas/20261023_032545_final/` | Corrida completa final (commit `b6d4e88`) con `api_redactado.log` |
| `falla_controlada/` | Redis detenido, timeout bajo y token ausente, con los logs redactados de cada instancia de la API |
| `diagnostico/` | C0 (token de InfluxDB), H5 (esquema antes), C1, C2, C3 (recarga del Hito 8) y H8 (correlación en 500) |
| `capturas_redactadas/` | Nota: no hay capturas de pantalla; la evidencia es texto |
| `logs/crudos/` | **Excluido de Git**: logs de la API sin redactar, solo en la máquina local |

Cada archivo `resultados_*.txt` empieza con un encabezado de trazabilidad (RNF18):

```
# Evaluacion de conectividad - modo completo - final
# fecha UTC: 2026-10-23T06:25:45Z | commit: b6d4e88
# origen de las pruebas: notebook Windows 10 | Python 3.11.9 (.venv)
# docker: Docker Engine 29.8.2
# configuracion: configuracion.env presente
# timeout por operacion: 3.0 s
```

> `platform.release()` de Python informa “Windows 10” en Windows 11 (el kernel sigue siendo la
> versión 10.0, build 26200). La notebook usa Windows 11 Pro.

Las corridas `inicial` y anteriores registran el commit `c2502d1+cambios_locales`, porque se
ejecutaron con los scripts todavía sin commitear. La corrida `final` y las fallas controladas
corresponden al commit `b6d4e88`.
