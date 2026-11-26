// =============================================================================
// 04-consultas.js
// -----------------------------------------------------------------------------
// Consultas de recuperacion exigidas por RF10:
//   (A) por identificador directo
//   (B) filtrado por condiciones de negocio
//   (C) proyeccion (solo campos necesarios)
//   (D) ordenamiento y paginacion
//
// Cada consulta declara su OBJETIVO FUNCIONAL. Todas fueron pensadas para
// aprovechar los indices creados en 02-crear-indices.js.
// =============================================================================

function titulo(t) {
  print("");
  print("--------------------------------------------------------------");
  print(" " + t);
  print("--------------------------------------------------------------");
}

// -----------------------------------------------------------------------------
// (A) RECUPERACION POR IDENTIFICADOR DIRECTO
// -----------------------------------------------------------------------------
titulo("A.1) Consultar el equipo Argentina por su codigo FIFA");
// Objetivo: pantalla de ficha de equipo. Indice: idx_equipos_codigo_unique.
printjson(db.equipos.findOne({ codigo: "ARG" }));

titulo("A.2) Consultar el jugador con dorsal 10 de Argentina");
// Objetivo: ficha de jugador desde el numero del dorsal. Indice:
// idx_jugadores_equipo_dorsal_unique.
printjson(db.jugadores.findOne({ equipoCodigo: "ARG", dorsal: 10 }));

// -----------------------------------------------------------------------------
// (B) RECUPERACION FILTRADA POR CONDICIONES DE NEGOCIO
// -----------------------------------------------------------------------------
titulo("B.1) Equipos anfitriones del Mundial 2030");
// Objetivo: destacar en la home a las 6 sedes. Indice parcial:
// idx_equipos_anfitrion_partial (solo indexa los 6 documentos).
db.equipos.find({ anfitrion: true }).forEach(e => print(`  ${e.codigo} - ${e.nombre} (sede: ${e.sedeBase})`));

titulo("B.2) Equipos top-10 de CONMEBOL");
// Objetivo: filtro por confederacion. Indice: idx_equipos_confederacion_ranking.
db.equipos.find(
  { confederacion: "CONMEBOL", rankingFIFA: { $lte: 50 } }
).forEach(e => print(`  #${e.rankingFIFA}  ${e.codigo}  ${e.nombre}`));

titulo("B.3) Delanteros de Brasil convocados");
// Objetivo: armar linea de ataque. Indice: idx_jugadores_equipo_posicion.
db.jugadores.find({
  equipoCodigo: "BRA",
  posicion: "Delantero",
  convocado: true
}).forEach(j => print(`  #${j.dorsal}  ${j.nombre}  goles=${j.goles}`));

titulo("B.4) Jugadores altos que juegan de defensor (>=190cm)");
// Objetivo: scouting fisico. Sin indice especifico -> collection scan;
// util para comparar performance en 06-analisis-rendimiento.js.
const altosDef = db.jugadores.countDocuments({ posicion: "Defensor", altura_cm: { $gte: 190 } });
print(`  Total defensores >=190cm: ${altosDef}`);

// -----------------------------------------------------------------------------
// (C) PROYECCION (devolver solo lo necesario)
// -----------------------------------------------------------------------------
titulo("C.1) Solo nombre y ranking de cada equipo de UEFA");
// Objetivo: listado ligero para dropdown en UI. La proyeccion reduce el
// payload de red y permite un covered query si combinamos indice + proyeccion.
db.equipos.find(
  { confederacion: "UEFA" },
  { _id: 0, codigo: 1, nombre: 1, rankingFIFA: 1 }
).sort({ rankingFIFA: 1 }).limit(5).forEach(e => print(`  #${e.rankingFIFA}  ${e.codigo}  ${e.nombre}`));

titulo("C.2) Capitanes de todas las selecciones");
// Objetivo: reporte de capitanes.
db.jugadores.find(
  { capitan: true },
  { _id: 0, equipoCodigo: 1, nombre: 1, posicion: 1, dorsal: 1 }
).sort({ equipoCodigo: 1 }).limit(10).forEach(c => print(`  ${c.equipoCodigo}  #${c.dorsal}  ${c.nombre} (${c.posicion})`));

// -----------------------------------------------------------------------------
// (D) ORDENAMIENTO Y PAGINACION
// -----------------------------------------------------------------------------
titulo("D.1) Ranking global de valor de mercado - paginado, 5 por pagina");
// Objetivo: pagina "Top jugadores" con navegacion. Justificacion en UI: la
// lista completa (1024) satura la vista; se muestra en paginas de 5.
// Indice: idx_jugadores_valorMercado_desc.
const PAGE_SIZE = 5;

function mostrarPagina(nPage) {
  print(`  --- Pagina ${nPage} ---`);
  db.jugadores.find(
    {},
    { _id: 0, nombre: 1, equipoCodigo: 1, posicion: 1, valorMercado_millonesEUR: 1 }
  )
  .sort({ valorMercado_millonesEUR: -1 })
  .skip((nPage - 1) * PAGE_SIZE)
  .limit(PAGE_SIZE)
  .forEach(j => print(`  ${String(j.valorMercado_millonesEUR).padStart(6," ")} MEUR  ${j.equipoCodigo}  ${j.nombre}  (${j.posicion})`));
}

mostrarPagina(1);
mostrarPagina(2);

// -----------------------------------------------------------------------------
// Nota sobre la paginacion:
//   skip+limit es adecuado hasta paginas pequenas/medias, pero degrada en
//   paginas muy profundas (skip debe descartar N documentos previos). Para
//   listados muy grandes conviene "keyset pagination" (usar el ultimo
//   valorMercado como cursor). Se documenta en el archivo de decisiones.
// -----------------------------------------------------------------------------

print("");
print("==============================================================");
