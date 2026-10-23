# Matriz de conectividad — corrida `C1_iris_password`

- **Fecha (UTC):** 2026-10-23T06:19:00Z
- **Commit:** `fc5d50a+cambios_locales`
- **Entorno de ejecución:** notebook Windows 10 | Python 3.11.9 (.venv) — mismo origen que la API del Hito 10
- **Docker:** Docker Engine 29.8.2
- **Modo:** `nativos` · **timeout por operación:** 3.0 s
- **Significado:** OK = esa prueba concreta funcionó en este momento; no garantiza rendimiento ni disponibilidad permanente (RNF17). SKIP = no se ejecutó por falta de herramienta o configuración, no producto caído.

## Estado por dependencia

| Dependencia | Host:puerto (desde la API) | Contexto | Estado | Capa con falla | OK/FALLA/SKIP | Rutas API según contrato | Diagnóstico automático |
| :--- | :--- | :--- | :--- | :--- | :---: | :---: | :--- |
| **iris** | `localhost:1972` (IRIS Superserver (protocolo propio)) | namespace USER / esquema SQL Fixture | **disponible** | - | 9/0/0 | - | todas las pruebas positivas OK |

## iris

| Capa | Prueba | Origen | Cliente | Resultado | ms | Detalle |
| :--- | :--- | :--- | :--- | :---: | ---: | :--- |
| protocolo | Management Portal HTTP | notebook | HTTP GET | OK | 2064 | HTTP 200 (pagina de login) |
| autenticacion | Conexion al Superserver como '_SYSTEM' en 'USER' | notebook | intersystems-irispython | OK | 22 | sesion abierta (autenticacion y seleccion de namespace en el mismo paso) |
| autorizacion | Permiso SELECT sobre Fixture.Partido | notebook | intersystems-irispython | OK | 17 | 96 partidos visibles |
| contexto | Metadato: tablas del esquema Fixture (proyeccion SQL de las clases) | notebook | intersystems-irispython | OK | 25 | 9 tablas en el esquema Fixture |
| contexto | [negativo] Namespace incorrecto | notebook | intersystems-irispython | OK | 2019 | RuntimeError: <COMMUNICATION LINK ERROR> Failed to connect to server; Details: <COMMUNICATION ERROR> Invalid Message received; Details: Access Denied |
| contexto | [negativo] Terminal con namespace incorrecto | contenedor | iris session | OK | 108 | Node: ac4fc74fb0a5, Instance: IRIS Access Denied |
| lectura | Lectura de la entidad Partido F2030-001 | notebook | intersystems-irispython | OK | 15 | ('F2030-001', 'Finalizado', 1, 1) |
| lectura | [negativo] Objeto inexistente (F2030-999) | notebook | intersystems-irispython | OK | 13 | sin filas y sin error (404 en la API) |
| lectura | Terminal (iris session): existe F2030-001 por indice CodigoIdx | contenedor | iris session | OK | 106 | NS=USER EXISTE=1 / VERSION=IRIS for UNIX (Ubuntu Server LTS for x86-64 Containers) 2026.2 (Build 221U) Fri Jun 26 2026 09:58:52 EDT |

## Herramientas o pruebas no ejecutadas (SKIP)

- ninguna
