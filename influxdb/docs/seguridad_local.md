# Seguridad local

El módulo corre solo en la máquina del integrante. Nada de lo que sigue es un secreto real publicado (RNF7).

| Aspecto | Decisión |
| :--- | :--- |
| Token de InfluxDB | `inicializacion.py` lo crea con `influxdb3 create token --admin` y lo guarda en `.influxdb3-token`, archivo **excluido** por `.gitignore`. No se imprime en ningún log ni en pantalla |
| Cómo viaja el token | Hacia el CLI del contenedor por la variable de entorno `INFLUXDB3_AUTH_TOKEN` (no por la línea de comandos, para que no quede en el listado de procesos). Hacia la API HTTP, en el encabezado `Authorization: Bearer` |
| Alternativa | Si existe la variable `INFLUXDB3_TOKEN`, los scripts la usan en lugar del archivo |
| Exposición de red | El compose publica `127.0.0.1:8181`: el servicio es accesible solo desde la propia máquina |
| Archivos excluidos del repositorio | `.influxdb3-token`, `*.token`, `.env`, `data/generado/` y la caché de Python (ver `.gitignore`) |
| Datos del repositorio | Los CSV de `data/origen/` son los datos simulados del Hito 5; no contienen datos personales reales |

## Cómo comprobar que no hay secretos en el repositorio

```bash
# Ningun archivo versionado debe llamarse como un token (debe quedar vacio)
git ls-files | grep -i token
# Ningun archivo versionado debe contener un token real (debe quedar vacio)
git grep -nE "apiv3_[A-Za-z0-9_-]{20,}"
```

## Si se pierde el token

El token de administración solo se muestra al crearlo. Si se borra `.influxdb3-token` y el servidor conserva sus datos, no se puede crear otro con `--admin`. Hay que empezar de cero: `docker compose down`, borrar `~/docker/data/influxdb` y volver a ejecutar `inicializacion.py`. Los datos se regeneran con la misma semilla.
