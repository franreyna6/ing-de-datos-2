# Concurrencia — Caché de usuarios y sesiones (Hito 7)

**Grupo N.º 8** · Redis · Fixture 2030

Cubre el apartado *Concurrencia* del análisis (RF8, RF9): qué operaciones reciben
actualizaciones simultáneas, qué riesgo se evita y la evidencia del comportamiento implementado.

## 1. Operaciones que requieren atomicidad

| Operación | Quién actualiza a la vez | Riesgo si no fuera atómica | Mecanismo elegido |
| :--- | :--- | :--- | :--- |
| Sumar una visita al partido | Miles de clientes sobre la misma clave | Dos clientes leen el mismo valor y escriben cada uno el suyo: **se pierde una visita** | `INCR` (comando nativo) |
| Votar a un jugador | Miles de votantes sobre el mismo Sorted Set | Se pierden votos | `ZINCRBY` (comando nativo) |
| Registrar actividad de una sesión | Varias peticiones de la misma sesión | Actualizar `ultimo_acceso` y `acciones` pero **no renovar el TTL** (estado parcial), o perder un incremento | `MULTI` · `HSET` · `HINCRBY` · `EXPIRE` · `EXEC` |

### 1.1 Por qué es atómico

- **Comandos nativos** (`INCR`, `HINCRBY`, `ZINCRBY`): Redis ejecuta cada comando como una
  unidad, sin intercalarse con otro. El servidor lee, suma y escribe sin que otro cliente pueda
  meterse en el medio.
- **`MULTI/EXEC`**: encola los comandos y los ejecuta **consecutivamente**; ningún otro cliente se
  intercala entre ellos. Además, si el cliente se cae antes de `EXEC`, no se aplica **ninguno**:
  nunca queda una sesión a medio actualizar.
- **Límite que se asume:** Redis no ofrece *rollback* general. Si un comando dentro de
  `MULTI/EXEC` fallara en tiempo de ejecución, los demás igual se aplican. Se mitiga porque los
  comandos usados (`HSET`, `HINCRBY`, `EXPIRE`) no fallan sobre una clave de tipo Hash.
- **Todas las unidades tocan una sola clave**, así que la atomicidad no depende de que varias
  claves compartan nodo (ver `modelo_clave_valor.md` §4).

## 2. Ranking temporal (RF9)

La votación "figura del partido" se resuelve con un Sorted Set: cada voto es un `ZINCRBY` y el
Top N se recupera ya ordenado con `ZREVRANGE ... WITHSCORES`, sin ordenar en la aplicación. Se
muestra en `05_concurrencia_comandos.log` (bloques 2 y 3), tanto con una clave de prueba como con
el ranking real de la muestra (Top 3 de la encuesta del partido `F2030-001`).

## 3. Evidencia: prueba con clientes en paralelo

`scripts/concurrencia_paralela.sh` lanza **4 clientes `redis-cli` simultáneos** sobre la **misma
clave** y compara cuatro formas de actualizar. Resultado de la corrida registrada
(`06_concurrencia_paralela.log`):

| Prueba | Esperado | Obtenido | Resultado |
| :--- | ---: | ---: | :--- |
| `INCR` (atómico) | 2000 | 2000 | correcto |
| `ZINCRBY` (atómico) | 2000 | 2000 | correcto |
| `MULTI/EXEC` (acciones de sesión) | 2000 | 2000 | correcto |
| `GET` + suma + `SET` (**antipatrón**) | 400 | 141 | **perdió 259 actualizaciones** |

Además, tras 2000 renovaciones concurrentes con `MULTI/EXEC`, el TTL de la sesión quedó en
**1800 s**: ninguna renovación dejó la sesión sin vencimiento (`-1`) ni la eliminó (`-2`).

### 3.1 Cómo se interpreta

- Los tres mecanismos atómicos dan **exactamente** el total esperado: no se pierde ninguna
  actualización.
- El antipatrón pierde la mayor parte porque, entre el `GET` de un cliente y su `SET`, otros
  clientes ya escribieron. **La cantidad perdida cambia en cada corrida** (en la corrida de validación sin Docker dio 139 y en la del grupo 141); lo que no cambia es que siempre es menor que el esperado.
- El antipatrón se corre con menos iteraciones (100 por cliente) porque cada una lanza dos
  procesos; la comparación válida es "obtenido contra esperado", no entre filas.

### 3.2 Límites de la prueba

- Los clientes son procesos del mismo equipo que el servidor, sin red de por medio.
- Con 4 clientes el intercalado es real pero acotado; con más clientes la pérdida del antipatrón
  sería igual o mayor, pero no se midió.
- Es una prueba de **corrección bajo concurrencia**, no de capacidad (para tiempos ver
  [`rendimiento.md`](rendimiento.md)).

## 4. Cómo repetirla

```
docker exec fixture2030-redis sh /scripts/concurrencia_paralela.sh
# otros tamaños:
docker exec -e CLIENTES=8 -e N=1000 -e M=200 fixture2030-redis sh /scripts/concurrencia_paralela.sh
```
