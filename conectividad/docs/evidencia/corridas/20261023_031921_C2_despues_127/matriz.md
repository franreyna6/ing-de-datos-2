# Matriz de conectividad — corrida `C2_despues_127`

- **Fecha (UTC):** 2026-10-23T06:19:22Z
- **Commit:** `fc5d50a+cambios_locales`
- **Entorno de ejecución:** notebook Windows 10 | Python 3.11.9 (.venv) — mismo origen que la API del Hito 10
- **Docker:** Docker Engine 29.8.2
- **Modo:** `tcp` · **timeout por operación:** 3.0 s
- **Significado:** OK = esa prueba concreta funcionó en este momento; no garantiza rendimiento ni disponibilidad permanente (RNF17). SKIP = no se ejecutó por falta de herramienta o configuración, no producto caído.

## Estado por dependencia

| Dependencia | Host:puerto (desde la API) | Contexto | Estado | Capa con falla | OK/FALLA/SKIP | Rutas API según contrato | Diagnóstico automático |
| :--- | :--- | :--- | :--- | :--- | :---: | :---: | :--- |
| **influxdb** | `127.0.0.1:8181` (HTTP (API v3)) | database fixture2030_vivo / tabla estadisticas_equipo | **disponible** | - | 2/0/0 | - | todas las pruebas positivas OK |
| **iris** | `127.0.0.1:1972` (IRIS Superserver (protocolo propio)) | namespace USER / esquema SQL Fixture | **disponible** | - | 4/0/0 | - | todas las pruebas positivas OK |

## influxdb

| Capa | Prueba | Origen | Cliente | Resultado | ms | Detalle |
| :--- | :--- | :--- | :--- | :---: | ---: | :--- |
| resolucion | Resolver host (driver de la API) | notebook | socket.getaddrinfo | OK | - | 127.0.0.1 -> 127.0.0.1 |
| tcp | Conexion TCP (driver de la API) | notebook | socket.create_connection | OK | 1 | exito: conexion establecida 127.0.0.1 -> 127.0.0.1:8181 |

## iris

| Capa | Prueba | Origen | Cliente | Resultado | ms | Detalle |
| :--- | :--- | :--- | :--- | :---: | ---: | :--- |
| resolucion | Resolver host (driver de la API (Superserver)) | notebook | socket.getaddrinfo | OK | - | 127.0.0.1 -> 127.0.0.1 |
| resolucion | Resolver host (Management Portal) | notebook | socket.getaddrinfo | OK | - | 127.0.0.1 -> 127.0.0.1 |
| tcp | Conexion TCP (driver de la API (Superserver)) | notebook | socket.create_connection | OK | 15 | exito: conexion establecida 127.0.0.1 -> 127.0.0.1:1972 |
| tcp | Conexion TCP (Management Portal) | notebook | socket.create_connection | OK | 0 | exito: conexion establecida 127.0.0.1 -> 127.0.0.1:52773 |

## Herramientas o pruebas no ejecutadas (SKIP)

- ninguna
