# Datos de prueba (RF3)

## Qué son

El conjunto de datos de esta prueba es el **plan de operaciones**: la secuencia ordenada de lecturas y escrituras que van a ejecutar los usuarios virtuales. Cada línea de `plan.jsonl` es una operación:

```json
{"i": 7, "tipo": "escritura", "partido": "P1", "usuarioId": "u-01234",
 "contenido": "Que golazo, no lo puedo creer #7", "comentarioId": "6f1c...-...."}
{"i": 8, "tipo": "lectura", "partido": "P1"}
{"i": 9, "tipo": "reintento", "partido": "P2", "usuarioId": "...", "contenido": "...",
 "comentarioId": "<el mismo de una escritura previa>", "reintentoDe": 3}
```

## Cómo se generan

- Son **sintéticos**: los genera `scripts/preparar_datos.py`, con la semilla fija `2030` de `config/escenario.json`. No contienen datos personales ni sensibles (RNF7).
- Son **reproducibles**: la misma semilla y el mismo escenario producen exactamente el mismo archivo. El hash SHA-256 queda en `resumen_plan.json`, y cada corrida verifica antes de empezar que el plan coincida con ese hash.
- `plan.jsonl` no se versiona, porque se regenera idéntico. Sí se versiona `resumen_plan.json`.

## Distribución

| Aspecto | Valor | Por qué |
| :--- | :--- | :--- |
| Mezcla | 70 % lecturas, 28 % escrituras, 2 % reintentos | Después de un gol la mayoría lee, pero el volumen de escrituras es alto. Los reintentos simulan clientes que reenvían tras un timeout. |
| Partidos | P1 70 %, P2 20 %, P3 10 % | **Clave caliente** deliberada: P1 es el partido del gol. |
| Usuarios | 5.000 posibles, elegidos al azar de forma uniforme | Ningún usuario concentra la carga. Lo caliente es el partido, no el usuario. |
| Contenido | 10 frases + el sufijo `#i` | El sufijo hace único cada contenido, y así se detecta si un comentario se guardó alterado. |
| `comentarioId` | UUID v4 derivado de la semilla | Es único por escritura nueva. Un reintento reusa el id de la escritura original. |
| Timestamps | Los asigna la API al momento de escribir | Igual que en producción. La ventana de 5 minutos sale de ese instante. |

## Partidos de laboratorio (aislamiento, RNF7 y RNF11)

En el plan, los partidos se llaman `P1`, `P2` y `P3`. Al ejecutar, cada corrida los convierte en `H12-<etiqueta>-P1`, y así sucesivamente. Esos códigos no existen en el fixture real, de modo que:

- la prueba no altera los comentarios del Hito 6;
- dos corridas nunca escriben en la misma partición, y el conteo de integridad de cada una es exacto;
- la limpieza puede borrar solo lo de una corrida.

## Volumen probado y volumen proyectado

- **Volumen inicial**: la tabla `comentarios_por_partido` ya contiene el volumen masivo cargado en el Hito 6 (más de 1.000.000 de comentarios). Las particiones de la prueba empiezan vacías y crecen durante la corrida, como la ventana de un partido real.
- **Volumen de cada corrida**: el que efectivamente se consumió del plan (`operaciones_consumidas_del_plan` en `metadata.json`). Depende de la velocidad de la API, porque los usuarios trabajan en lazo cerrado.
- **Volumen proyectado** (Clase 13): más de 1.000.000 de comentarios potenciales por torneo y entre 2 y 3 millones de usuarios simultáneos en el escenario. La prueba usa como máximo **60 usuarios virtuales** en una notebook. Ver *Escalabilidad* en `docs/integridad_y_limitaciones.md`: no se extrapola un resultado medido a esa escala.
