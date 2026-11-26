// =============================================================================
// 06-analisis-rendimiento.js
// -----------------------------------------------------------------------------
// Analiza el efecto de un indice sobre una consulta critica (RF12, RNF4).
//
// Consulta bajo prueba: "plantel completo de Argentina, ordenado por posicion"
//   db.jugadores.find({ equipoCodigo: "ARG" }).sort({ posicion: 1 })
//
// Procedimiento:
//   1. Se dropea temporalmente el indice compuesto (equipoCodigo, posicion).
//   2. Se ejecuta explain("executionStats") -> se espera COLLSCAN.
//   3. Se re-crea el indice.
//   4. Se ejecuta explain("executionStats") de nuevo -> se espera IXSCAN.
//   5. Se comparan las metricas clave: docsExamined, keysExamined, executionTimeMillis.
//
// La comparacion queda impresa por consola; el README indica como capturarla.
// =============================================================================

print("==============================================================");
print(" Analisis de rendimiento con explain() antes/despues del indice");
print("==============================================================");

const NOMBRE_INDICE = "idx_jugadores_equipo_posicion";
const CONSULTA = { equipoCodigo: "ARG" };
const ORDEN = { posicion: 1 };

// -----------------------------------------------------------------------------
// Helpers de resumen
// -----------------------------------------------------------------------------
function resumenExec(explainOut, etiqueta) {
  const es = explainOut.executionStats || {};
  const stage = (es.executionStages && es.executionStages.stage) || "?";
  const innerStage = (es.executionStages && es.executionStages.inputStage && es.executionStages.inputStage.stage) || null;
  print("");
  print("--- " + etiqueta + " ---");
  print("  winning stage         : " + stage + (innerStage ? "  <- " + innerStage : ""));
  print("  nReturned             : " + es.nReturned);
  print("  totalKeysExamined     : " + es.totalKeysExamined);
  print("  totalDocsExamined     : " + es.totalDocsExamined);
  print("  executionTimeMillis   : " + es.executionTimeMillis);
  return {
    stage: stage,
    innerStage: innerStage,
    keysExamined: es.totalKeysExamined,
    docsExamined: es.totalDocsExamined,
    tiempoMs: es.executionTimeMillis,
    nReturned: es.nReturned
  };
}

// -----------------------------------------------------------------------------
// Estado inicial del indice
// -----------------------------------------------------------------------------
const indicesActuales = db.jugadores.getIndexes().map(i => i.name);
print("Indices actuales en jugadores: " + indicesActuales.join(", "));

// -----------------------------------------------------------------------------
// FASE 1: SIN indice
// -----------------------------------------------------------------------------
if (indicesActuales.includes(NOMBRE_INDICE)) {
  print("");
  print("Dropeando temporalmente '" + NOMBRE_INDICE + "' para la prueba SIN indice...");
  db.jugadores.dropIndex(NOMBRE_INDICE);
}

const explainSin = db.jugadores
  .find(CONSULTA)
  .sort(ORDEN)
  .explain("executionStats");

const rSin = resumenExec(explainSin, "SIN indice (esperado COLLSCAN + SORT)");

// -----------------------------------------------------------------------------
// FASE 2: CON indice
// -----------------------------------------------------------------------------
print("");
print("Re-creando '" + NOMBRE_INDICE + "'...");
db.jugadores.createIndex(
  { equipoCodigo: 1, posicion: 1 },
  { name: NOMBRE_INDICE }
);

const explainCon = db.jugadores
  .find(CONSULTA)
  .sort(ORDEN)
  .explain("executionStats");

const rCon = resumenExec(explainCon, "CON indice (esperado IXSCAN, sin SORT en memoria)");

// -----------------------------------------------------------------------------
// COMPARATIVA
// -----------------------------------------------------------------------------
print("");
print("==============================================================");
print(" COMPARATIVA");
print("==============================================================");
print(`  docsExamined : sin=${rSin.docsExamined}  con=${rCon.docsExamined}   (menor es mejor)`);
print(`  keysExamined : sin=${rSin.keysExamined}  con=${rCon.keysExamined}   (0 sin indice)`);
print(`  tiempo (ms)  : sin=${rSin.tiempoMs}  con=${rCon.tiempoMs}`);
print(`  nReturned    : sin=${rSin.nReturned}  con=${rCon.nReturned}   (identico -> resultado correcto)`);

const factor = rSin.docsExamined > 0 && rCon.docsExamined > 0
  ? (rSin.docsExamined / rCon.docsExamined).toFixed(1)
  : "n/d";
print("");
print(`  Reduccion de documentos examinados: ${factor}x`);
print("");
print("Interpretacion:");
print("  * SIN indice: MongoDB tuvo que recorrer TODOS los documentos de la");
print("    coleccion (COLLSCAN) y ordenar en memoria (SORT).");
print("  * CON indice: MongoDB uso IXSCAN sobre (equipoCodigo, posicion): las");
print("    16 filas del plantel ya vienen agrupadas y ordenadas por el indice,");
print("    evitando el SORT en memoria. Este es exactamente el patron ESR");
print("    (Equality, Sort) para el que se disenio el indice compuesto.");
print("==============================================================");
