// =============================================================================
// 02-crear-indices.js
// -----------------------------------------------------------------------------
// Crea los indices del modulo documental (RF12). Cada indice esta justificado
// por una consulta concreta del modulo. NO se crean indices "por las dudas":
// cada indice cuesta almacenamiento y penaliza la escritura.
//
// La operacion es idempotente: createIndex es un no-op si el indice con esa
// especificacion ya existe (misma clave, mismas opciones).
// =============================================================================

print("==============================================================");
print(" Creacion de indices sobre equipos y jugadores                ");
print("==============================================================");

// -----------------------------------------------------------------------------
// EQUIPOS
// -----------------------------------------------------------------------------

// (1) codigo UNIQUE
// Sostiene: findOne({codigo:"ARG"}), $lookup por codigo, upsert idempotente.
// Garantia adicional: unicidad del identificador de negocio (evita duplicados
// aun ante bugs de carga). Es el indice mas frecuente en toda la aplicacion.
db.equipos.createIndex(
  { codigo: 1 },
  { unique: true, name: "idx_equipos_codigo_unique" }
);
print("[OK] equipos.idx_equipos_codigo_unique  (unique)");

// (2) confederacion + rankingFIFA
// Sostiene: "top N equipos de una confederacion" (find + sort). El orden de las
// claves respeta la regla ESR (Equality, Sort, Range): primero el campo de
// igualdad (confederacion), despues el de orden (rankingFIFA).
db.equipos.createIndex(
  { confederacion: 1, rankingFIFA: 1 },
  { name: "idx_equipos_confederacion_ranking" }
);
print("[OK] equipos.idx_equipos_confederacion_ranking");

// (3) anfitrion parcial
// Sostiene: listar las 6 selecciones anfitrionas. Indice PARCIAL: solo indexa
// los documentos con anfitrion:true (6 de 64) -> ocupa mucho menos y es mas
// selectivo para esa consulta.
db.equipos.createIndex(
  { anfitrion: 1 },
  { name: "idx_equipos_anfitrion_partial",
    partialFilterExpression: { anfitrion: true } }
);
print("[OK] equipos.idx_equipos_anfitrion_partial  (parcial)");

// -----------------------------------------------------------------------------
// JUGADORES
// -----------------------------------------------------------------------------

// (4) codigo UNIQUE
// Sostiene: findOne({codigo:...}), upsert idempotente. Mismo criterio que en
// equipos: es el identificador de negocio, debe ser unico y siempre buscable.
db.jugadores.createIndex(
  { codigo: 1 },
  { unique: true, name: "idx_jugadores_codigo_unique" }
);
print("[OK] jugadores.idx_jugadores_codigo_unique  (unique)");

// (5) equipoCodigo + posicion
// Sostiene la consulta MAS FRECUENTE del modulo: "plantel de un equipo",
// opcionalmente filtrando por posicion ("delanteros de Argentina"). El orden
// (equipoCodigo, posicion) respeta ESR y ademas cubre solo la consulta por
// equipoCodigo (prefijo del indice).
db.jugadores.createIndex(
  { equipoCodigo: 1, posicion: 1 },
  { name: "idx_jugadores_equipo_posicion" }
);
print("[OK] jugadores.idx_jugadores_equipo_posicion  (compuesto)");

// (6) equipoCodigo + dorsal UNIQUE
// Sostiene: findOne({equipoCodigo:"ARG", dorsal:10}). Ademas asegura que no
// puedan existir dos jugadores con el mismo dorsal en el mismo equipo.
db.jugadores.createIndex(
  { equipoCodigo: 1, dorsal: 1 },
  { unique: true, name: "idx_jugadores_equipo_dorsal_unique" }
);
print("[OK] jugadores.idx_jugadores_equipo_dorsal_unique  (unique compuesto)");

// (7) valorMercado_millonesEUR descendente
// Sostiene: rankings globales/paginados por valor de mercado (find + sort).
db.jugadores.createIndex(
  { valorMercado_millonesEUR: -1 },
  { name: "idx_jugadores_valorMercado_desc" }
);
print("[OK] jugadores.idx_jugadores_valorMercado_desc");

// -----------------------------------------------------------------------------
// Inventario final
// -----------------------------------------------------------------------------
print("");
print("INDICES EN equipos:");
db.equipos.getIndexes().forEach(i => print("  - " + i.name + "  keys=" + JSON.stringify(i.key)));
print("");
print("INDICES EN jugadores:");
db.jugadores.getIndexes().forEach(i => print("  - " + i.name + "  keys=" + JSON.stringify(i.key)));
print("==============================================================");
