# Evidencia — consultas y visualización (RF11)

Capturas de Neo4j Browser correspondientes a la carga, la verificación de idempotencia,
las operaciones CRUD, los recorridos de grafo, el análisis relacional (RF9) y la
visualización del subgrafo.

## 1. Carga (queries/carga.cypher)
Conteo final esperado: equipos=64, jugadores=1024, sedes=12, partidos=96, eventos=437.
Total de nodos y relaciones: 1633 nodos, 2186 relaciones.

![Carga inicial - conteo de nodos y relaciones](01_carga.png)

## 2. Idempotencia (RNF4)
Se volvió a ejecutar `carga.cypher` por segunda vez. Los conteos se mantienen exactamente
iguales (1633 nodos, 2186 relaciones), lo que confirma que el uso de `MERGE` evita duplicados.

![Segunda ejecución de la carga - mismos conteos](02_idempotencia.png)

## 3. CRUD (queries/crud.cypher)

**CREATE** — alta de un evento de prueba (asistencia) vinculado a un partido y un jugador:

![CRUD - Create](03_crud_create.png)

**READ** — recuperación del evento recién creado con su contexto:

![CRUD - Read](04_crud_read.png)

**UPDATE** — corrección del minuto del evento de prueba:

![CRUD - Update minuto](05_crud_update1.png)

**UPDATE** — lectura de una propiedad de relación (condición local/visitante):

![CRUD - Update condicion](06_crud_update2.png)

**DELETE** — eliminación acotada de la relación del evento de prueba:

![CRUD - Delete relacion](07_crud_delete_relacion.png)

**DELETE** — eliminación acotada del nodo de prueba (DETACH DELETE por código):

![CRUD - Delete nodo](08_crud_delete_nodo.png)

**Verificación** — el evento de prueba ya no existe (0 resultados, como se esperaba):

![CRUD - Verificacion post-borrado](09_crud_verificacion.png)

## 4. Recorridos de 2+ saltos (queries/consultas_grafo.cypher, sección B)

**A.1** — Plantel de una selección (Argentina), ordenado por dorsal:

![Consulta A.1 - Plantel](10_consulta_a1.png)

**A.2** — Partidos de un grupo con su sede:

![Consulta A.2 - Partidos por grupo](11_consulta_a2.png)

**B.1** — Recorrido de 4 relaciones: goles con autor, selección, partido y sede:

![Consulta B.1 - Goles con contexto completo](12_consulta_b1.png)

**B.2** — Recorrido de 2 relaciones: máximos goleadores del torneo:

![Consulta B.2 - Goleadores](13_consulta_b2.png)

**B.3** — Recorrido de 2 relaciones: rivales de Argentina en la fase de grupos:

![Consulta B.3 - Rivales de Argentina](14_consulta_b3.png)

## 5. Análisis RF9 — centralidad de sedes y conectividad (sección C)

**C.1** — Centralidad por grado: sede que concentra más partidos:

![Análisis C.1 - Centralidad de sedes](15_analisis_c1.png)

**C.2** — Conectividad indirecta: equipos vinculados a Argentina por sede compartida:

![Análisis C.2 - Conectividad por sede compartida](16_analisis_c2.png)

## 6. Visualización del subgrafo (RF11)

Vista de grafo (nodos + relaciones) de los equipos del Grupo A, sus partidos, sedes y
planteles. Panel de resultados: 50 nodos, 49 relaciones (DISPUTA, PERTENECE_A, SE_JUEGA_EN).

![Visualización del subgrafo - Grupo A](17_visualizacion.png)