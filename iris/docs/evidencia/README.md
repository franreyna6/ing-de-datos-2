# Evidencia de ejecución

La evidencia principal es el **log de la corrida** que deja `scripts/ejecutar_todo.ps1` (o `.sh`) en `logs/ejecucion_<fecha>.log`. Contiene, en orden: equipo y versión de Docker, directorio durable, estado del contenedor y versión de IRIS (`$ZVersion`), compilación, carga y los siete bloques. Cada operación se imprime con `[ACEPTADO]` o `[RECHAZADO]` y el motivo que devuelve IRIS, y cada verificación se calcula consultando la base.

Además del log, el enunciado pide **capturas del Terminal de IRIS**. Guardarlas en esta carpeta con estos nombres:

| Archivo | Qué se ejecuta | Qué tiene que verse |
| :--- | :--- | :--- |
| `01_contenedor.png` | `docker compose ps` y el directorio durable: `ls ~/docker/data/iris` (Linux/WSL) o `docker volume inspect fixture2030-iris-durable` (Windows con `-VolumenDocker`) | Contenedor `fixture2030-iris` en ejecución y *healthy*, y dónde vive Durable %SYS |
| `02_compilacion.png` | Paso 2 (`$system.OBJ.LoadDir(...)`) | Las diez clases de dominio más `Carga` y `Demo` compiladas, `COMPILACION: OK` |
| `03_carga.png` | `Bloque1Carga()` | 12 sedes, 64 equipos, 64 técnicos, 1024 jugadores, 22 árbitros, 96 partidos, 437 eventos, 288 designaciones |
| `04_arbol_un_save.png` | `Bloque2ArbolAtomico()` | IDs vacíos antes del `%Save()`; ID del partido y de cada hijo después; reapertura con 3 eventos y 3 designaciones |
| `05_fallo_requerido.png` | `Bloque3FalloControlado()` | Los dos `[RECHAZADO]` por propiedad requerida (`Fecha`, `Minuto`) y las verificaciones en 0 |
| `06_navegacion.png` | `Bloque4Navegacion()` | Recorrido del partido F2030-001 por referencias, navegación inversa desde el jugador y el polimorfismo (`Fixture.Jugador`) |
| `07_sql.png` | `Bloque5ProyeccionSQL()` | El mismo ID que el objeto, eventos y designaciones por SQL, conteo por subclase de `Fixture.Persona` |
| `08_sql_portal.png` | Portal → System Explorer → SQL, namespace `USER`: `SELECT e.ID, e.Codigo, e.Tipo, e.Minuto, p.Codigo AS Partido FROM Fixture.Evento e JOIN Fixture.Partido p ON e.Partido = p.ID WHERE p.Codigo = 'DEMO-001' ORDER BY e.Minuto` | Los 3 eventos de DEMO-001 (minutos 12, 40 y 77), los mismos que creó el Bloque 2 por objetos. Se filtra por código porque el ID cambia cada vez que el Bloque 2 recrea el partido |
| `09_validaciones.png` | `Bloque6Validaciones()` | `[RECHAZADO]` del gol en el minuto 0 sobre un partido Finalizado y del resto de transiciones ilegales; evento inalterable |
| `10_integridad.png` | `Bloque7Integridad()` | Hijos 2/3 → 0/0 tras borrar el partido; borrados rechazados de jugador, sede, árbitro y equipo |
| `11_persistencia.png` | `Fixture.Demo.Conteo()`, `docker compose down`, `up -d`, `ps` hasta *healthy* y de nuevo `Conteo()` (o los pasos 10 a 10d de `-ProbarPersistencia`) | El mismo conteo antes y después; el `Node:` cambia porque el contenedor es otro |

**Antes de entregar, revisar que el log y las capturas digan lo mismo que el README y la matriz de integridad.** Si alguna operación no da el resultado esperado (por ejemplo, un borrado que se declara rechazado y aparece aceptado), se corrige el código o la documentación para que coincidan; no se deja una afirmación que la evidencia no muestra.
