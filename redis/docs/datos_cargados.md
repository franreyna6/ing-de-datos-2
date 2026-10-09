# Datos cargados — Caché de usuarios y sesiones (Hito 7)

**Grupo N.º 8** · Redis · Fixture 2030

Cubre el apartado *Datos cargados* del análisis (RF11): origen o generación de los datos, alcance,
cantidad y distribución de usuarios, sesiones y claves de caché.

## 1. Origen

| Dato | Origen | Real o sintético |
| :--- | :--- | :--- |
| Fichas de partido (copias de caché) | `data/origen/partidos.csv` (los mismos CSV del Hito 5) | **Real** del proyecto |
| Fichas de equipo (copias de caché) | `data/origen/equipos.csv` | **Real** del proyecto |
| Candidatos de las encuestas | `data/origen/jugadores.csv` y `participaciones.csv` | **Real** del proyecto |
| Sesiones y usuarios | Generados por `scripts/generar_datos.py` | **Sintético** (los usuarios no existen en hitos previos) |
| Contadores de visitas y votos | Generados por `scripts/generar_datos.py` | **Sintético** |

No hay datos personales, contraseñas ni tokens reales (RNF7): los usuarios son `U0001`..., las
sesiones `S0001`..., y no se guarda ningún token.

## 2. Reproducibilidad

- **Semilla fija (2030).** La misma semilla y los mismos argumentos producen exactamente el
  mismo `carga_muestra.redis` (se comprobó generándolo varias veces con el mismo resultado).
- **Carga idempotente.** Usa `HSET`, `SET` y `ZADD` con claves fijas: repetirla sobrescribe las mismas
  claves y no duplica datos.
- **Solo biblioteca estándar de Python.**

```
python scripts/generar_datos.py                          # regenera carga_muestra.redis y la distribución
python scripts/generar_datos.py --sesiones 500 --semilla 2030   # otro tamaño
```

## 3. Alcance y distribución

(Resumen completo en [`evidencia/distribucion_generada.txt`](evidencia/distribucion_generada.txt).)

| Qué | Clave | Cantidad | TTL |
| :--- | :--- | ---: | :--- |
| Sesiones | `sesion:S0001`...`S0200` | 200 (177 `fan`, 16 `periodista`, 7 `admin`; todas `activa`) | 1800 s |
| Copias de ficha de partido | `cache:partido:F2030-001`...`020` | 20 de 96 partidos | 300 s |
| Copias de ficha de equipo | `cache:equipo:<codigo>` | 16 de 64 equipos | 3600 s |
| Contadores de visitas | `partido:<codigo>:visitas` | 96 (mín. 2.434, máx. 59.829) | sin TTL |
| Encuestas "figura del partido" | `encuesta:F2030-001`...`012:figura` | 12 (6 candidatos cada una: 3 jugadores por equipo) | sin TTL |
| **Total de claves** | | **344** (236 con TTL, 108 sin TTL por decisión) | |

Se precargan **solo una parte** de las fichas (20 partidos y 16 equipos) para que existan **hits y
misses reales**: el resto queda sin copia y provoca un miss cuando se lo pide.

Cada sesión tiene este aspecto (ver `modelo_clave_valor.md` §2.1):

```
sesion:S0001 → usuario_id=U0001 rol=fan estado=activa
               creada_en=2030-06-14T17:35:19Z ultimo_acceso=2030-06-14T19:33:43Z acciones=14   (TTL 1800 s)
```

## 4. Cómo leer el resumen de la carga

`ejecutar_bloques.sh ... carga` envía los **944 comandos** por una sola conexión y resume las
respuestas. Los números se pueden verificar a mano (`02_carga_muestra.log`):

| Respuesta | Cantidad | De dónde sale |
| :--- | ---: | :--- |
| `QUEUED` | 400 | 2 comandos encolados (`HSET`, `EXPIRE`) × 200 sesiones |
| `OK` | 332 | 200 `MULTI` + 20 + 16 + 96 `SET` |
| `6` | 212 | 200 `HSET` (6 campos nuevos cada uno) + 12 `ZADD` (6 candidatos cada uno) |
| `1` | 200 | 200 `EXPIRE` aplicados dentro de `EXEC` |

Total: 800 comandos de sesiones + 144 de caché, contadores y encuestas = 944. "Respuestas con
error: 0".

> **Nota.** Si se repite la carga sobre claves ya existentes, `HSET` devuelve 0 (los campos ya
> existían) en lugar de 6, y `ZADD` también: el resumen cambia, los datos no.
