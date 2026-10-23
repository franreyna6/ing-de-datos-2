# Matriz de conectividad — corrida `C2_antes_localhost`

- **Fecha (UTC):** 2026-10-23T19:41:53Z
- **Commit:** `82e1233`
- **Entorno de ejecución:** notebook Windows 10 | Python 3.11.9 (.venv) — mismo origen que la API del Hito 10
- **Docker:** Docker Engine 29.8.2
- **Modo:** `tcp` · **timeout por operación:** 3.0 s
- **Significado:** OK = esa prueba concreta funcionó en este momento; no garantiza rendimiento ni disponibilidad permanente (RNF17). SKIP = no se ejecutó por falta de herramienta o configuración, no producto caído.

## Estado por dependencia

| Dependencia | Host:puerto (desde la API) | Contexto | Estado | Capa con falla | OK/FALLA/SKIP | Rutas API según contrato | Diagnóstico automático |
| :--- | :--- | :--- | :--- | :--- | :---: | :---: | :--- |
| **influxdb** | `localhost:8181` (HTTP (API v3)) | database fixture2030_vivo / tabla estadisticas_equipo | **disponible** | - | 2/0/0 | - | todas las pruebas positivas OK |
| **iris** | `localhost:1972` (IRIS Superserver (protocolo propio)) | namespace USER / esquema SQL Fixture | **disponible** | - | 4/0/0 | - | todas las pruebas positivas OK |

## influxdb

| Capa | Prueba | Origen | Cliente | Resultado | ms | Detalle |
| :--- | :--- | :--- | :--- | :---: | ---: | :--- |
| resolucion | Resolver host (driver de la API) | notebook | socket.getaddrinfo | OK | - | localhost -> 127.0.0.1, ::1 |
| tcp | Conexion TCP (driver de la API) | notebook | socket.create_connection | OK | 2068 | exito: conexion establecida 127.0.0.1 -> 127.0.0.1:8181 |
| tcp | TCP por familia de direcciones (driver de la API) | notebook | socket.create_connection | INFO | - | 127.0.0.1 -> exito (15 ms); ::1 -> refused (2038 ms) / la conexion por nombre tardo 2068 ms: el primer intento va a una direccion sin listener |

## iris

| Capa | Prueba | Origen | Cliente | Resultado | ms | Detalle |
| :--- | :--- | :--- | :--- | :---: | ---: | :--- |
| resolucion | Resolver host (driver de la API (Superserver)) | notebook | socket.getaddrinfo | OK | - | localhost -> 127.0.0.1, ::1 |
| resolucion | Resolver host (Management Portal) | notebook | socket.getaddrinfo | OK | - | localhost -> 127.0.0.1, ::1 |
| tcp | Conexion TCP (driver de la API (Superserver)) | notebook | socket.create_connection | OK | 2058 | exito: conexion establecida 127.0.0.1 -> 127.0.0.1:1972 |
| tcp | TCP por familia de direcciones (driver de la API (Superserver)) | notebook | socket.create_connection | INFO | - | 127.0.0.1 -> exito (1 ms); ::1 -> refused (2050 ms) / la conexion por nombre tardo 2058 ms: el primer intento va a una direccion sin listener |
| tcp | Conexion TCP (Management Portal) | notebook | socket.create_connection | OK | 2057 | exito: conexion establecida 127.0.0.1 -> 127.0.0.1:52773 |
| tcp | TCP por familia de direcciones (Management Portal) | notebook | socket.create_connection | INFO | - | 127.0.0.1 -> exito (1 ms); ::1 -> refused (2052 ms) / la conexion por nombre tardo 2057 ms: el primer intento va a una direccion sin listener |

## Herramientas o pruebas no ejecutadas (SKIP)

- ninguna
