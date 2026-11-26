// =============================================================================
// 01-cargar-datos.js
// -----------------------------------------------------------------------------
// Carga reproducible e idempotente de 64 equipos y 1024 jugadores (RF4, RF5,
// RF8, RNF2).
//
// Estrategia (Decision #5 del documento de decisiones tecnicas):
//   - Se leen los JSON precomputados (data/equipos.json y data/jugadores.json)
//     que fueron generados por data/generar_datos.py con semilla fija.
//   - Se cargan via bulkWrite con updateOne + upsert, matcheando por el
//     identificador de negocio (`codigo`). Efecto:
//       * Primera ejecucion  -> inserta.
//       * Ejecuciones N > 1  -> actualiza campos sin crear duplicados.
//   - Los strings ISO 8601 se convierten a Date antes de la carga, para que
//     el JSON Schema (que exige bsonType: "date") los acepte.
//
// Ejecucion:
//   docker exec -i fixture2030-mongodb mongosh \
//     -u admin -p admin --authenticationDatabase admin \
//     fixture2030 --file /scripts/01-cargar-datos.js
// =============================================================================

const fs = require("fs");

print("==============================================================");
print(" Carga reproducible de equipos y jugadores (Fixture 2030)     ");
print("==============================================================");

// --- Leer JSON generados con semilla fija ------------------------------------
const equipos = JSON.parse(fs.readFileSync("/data-fixture/equipos.json", "utf-8"));
const jugadores = JSON.parse(fs.readFileSync("/data-fixture/jugadores.json", "utf-8"));

print(`Origen: /data-fixture/equipos.json   -> ${equipos.length} documentos`);
print(`Origen: /data-fixture/jugadores.json -> ${jugadores.length} documentos`);

// --- Conversion de fechas ISO string -> Date ---------------------------------
// El JSON Schema exige bsonType:"date" para fechaNacimiento y fechaActualizacion.
// Los JSON traen ISO strings; se transforman a Date antes del upsert.
for (const e of equipos) {
  if (typeof e.fechaActualizacion === "string") e.fechaActualizacion = new Date(e.fechaActualizacion);
}
for (const j of jugadores) {
  if (typeof j.fechaNacimiento === "string") j.fechaNacimiento = new Date(j.fechaNacimiento);
  if (typeof j.fechaActualizacion === "string") j.fechaActualizacion = new Date(j.fechaActualizacion);
}

// --- Upsert de equipos -------------------------------------------------------
// bulkWrite con updateOne + upsert:true garantiza idempotencia: si el
// documento ya existe (match por `codigo`), se actualiza; si no, se inserta.
const opsEquipos = equipos.map(e => ({
  updateOne: {
    filter: { codigo: e.codigo },
    update: { $set: e },
    upsert: true
  }
}));
const resEq = db.equipos.bulkWrite(opsEquipos, { ordered: false });
print(`[EQUIPOS] insertados=${resEq.upsertedCount}  actualizados=${resEq.modifiedCount}  matcheados=${resEq.matchedCount}`);

// --- Upsert de jugadores -----------------------------------------------------
const opsJugadores = jugadores.map(j => ({
  updateOne: {
    filter: { codigo: j.codigo },
    update: { $set: j },
    upsert: true
  }
}));
const resJug = db.jugadores.bulkWrite(opsJugadores, { ordered: false });
print(`[JUGADORES] insertados=${resJug.upsertedCount}  actualizados=${resJug.modifiedCount}  matcheados=${resJug.matchedCount}`);

// --- Verificacion post-carga (RNF3: integridad documental) -------------------
const totalEq = db.equipos.countDocuments({});
const totalJug = db.jugadores.countDocuments({});
print("");
print("VERIFICACION POST-CARGA:");
print(`  equipos.count()   = ${totalEq}   (esperado 64)`);
print(`  jugadores.count() = ${totalJug}   (esperado >= 1000)`);

// Integridad referencial: cada jugador.equipoCodigo debe existir en equipos.codigo
const codigosEquipo = new Set(db.equipos.distinct("codigo"));
const codigosReferenciados = db.jugadores.distinct("equipoCodigo");
const huerfanos = codigosReferenciados.filter(c => !codigosEquipo.has(c));
print(`  jugadores huerfanos (equipoCodigo inexistente) = ${huerfanos.length}   (esperado 0)`);
if (huerfanos.length > 0) {
  print("  !! Codigos huerfanos: " + huerfanos.join(", "));
}

// Duplicados de codigo: no deberia haber ninguno
const dupEquipos = db.equipos.aggregate([
  { $group: { _id: "$codigo", n: { $sum: 1 } } },
  { $match: { n: { $gt: 1 } } }
]).toArray();
const dupJugadores = db.jugadores.aggregate([
  { $group: { _id: "$codigo", n: { $sum: 1 } } },
  { $match: { n: { $gt: 1 } } }
]).toArray();
print(`  duplicados de equipos.codigo   = ${dupEquipos.length}   (esperado 0)`);
print(`  duplicados de jugadores.codigo = ${dupJugadores.length}   (esperado 0)`);

print("");
print("[OK] Carga finalizada. Puede re-ejecutarse sin producir duplicados.");
print("==============================================================");
