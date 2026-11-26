// =============================================================================
// 05-agregacion.js
// -----------------------------------------------------------------------------
// Pipelines de agregacion pertinentes al modulo documental (RF11).
// Cada pipeline responde una pregunta de negocio concreta.
// =============================================================================

function titulo(t) {
  print("");
  print("--------------------------------------------------------------");
  print(" " + t);
  print("--------------------------------------------------------------");
}

// -----------------------------------------------------------------------------
// (1) Distribucion de plantilla por confederacion
// -----------------------------------------------------------------------------
// Pregunta: "cuantos jugadores y cuantos equipos hay convocados por
// confederacion, y cual es la edad promedio del plantel de cada una?"
// Necesita cruzar jugadores con equipos -> $lookup + $group.
titulo("1) Jugadores, equipos y edad promedio por confederacion");

db.jugadores.aggregate([
  { $match: { convocado: true } },
  {
    // JOIN documental: trae la confederacion del equipo asociado a cada jugador
    $lookup: {
      from: "equipos",
      localField: "equipoCodigo",
      foreignField: "codigo",
      as: "eq"
    }
  },
  { $unwind: "$eq" },
  {
    $group: {
      _id: "$eq.confederacion",
      totalJugadores: { $sum: 1 },
      equiposDistintos: { $addToSet: "$equipoCodigo" },
      edadPromedio: {
        $avg: {
          $dateDiff: {
            startDate: "$fechaNacimiento",
            endDate: "$$NOW",
            unit: "year"
          }
        }
      }
    }
  },
  {
    $project: {
      _id: 0,
      confederacion: "$_id",
      totalJugadores: 1,
      totalEquipos: { $size: "$equiposDistintos" },
      edadPromedio: { $round: ["$edadPromedio", 1] }
    }
  },
  { $sort: { totalJugadores: -1 } }
]).forEach(r => print(
  `  ${r.confederacion.padEnd(10)}  equipos=${String(r.totalEquipos).padStart(2)}  jugadores=${String(r.totalJugadores).padStart(4)}  edadProm=${r.edadPromedio}`
));

// -----------------------------------------------------------------------------
// (2) Top-10 equipos por valor de mercado total del plantel
// -----------------------------------------------------------------------------
// Pregunta: "cual es el plantel mas valioso?" -> suma de valorMercado de sus
// jugadores. Es un pipeline pesado en potencia; se resuelve indexando
// jugadores.equipoCodigo (idx_jugadores_equipo_posicion cubre el prefijo).
titulo("2) Top-10 selecciones por valor de mercado acumulado (M EUR)");

db.jugadores.aggregate([
  {
    $group: {
      _id: "$equipoCodigo",
      valorTotal: { $sum: "$valorMercado_millonesEUR" },
      cantidad: { $sum: 1 }
    }
  },
  {
    $lookup: {
      from: "equipos",
      localField: "_id",
      foreignField: "codigo",
      as: "eq"
    }
  },
  { $unwind: "$eq" },
  {
    $project: {
      _id: 0,
      codigo: "$eq.codigo",
      nombre: "$eq.nombre",
      confederacion: "$eq.confederacion",
      rankingFIFA: "$eq.rankingFIFA",
      cantidad: 1,
      valorTotal: { $round: ["$valorTotal", 1] }
    }
  },
  { $sort: { valorTotal: -1 } },
  { $limit: 10 }
]).forEach((r, i) => print(
  `  ${String(i+1).padStart(2)}. ${r.codigo}  ${r.nombre.padEnd(22)}  ${r.confederacion.padEnd(9)}  rank=${String(r.rankingFIFA).padStart(3)}  valor=${String(r.valorTotal).padStart(7)}M EUR  jugadores=${r.cantidad}`
));

// -----------------------------------------------------------------------------
// (3) Balance de posiciones por equipo (facetado)
// -----------------------------------------------------------------------------
// Pregunta: "cuantos arqueros/defensores/mediocampistas/delanteros lleva
// cada seleccion?" -> permite detectar planteles desbalanceados.
titulo("3) Composicion tactica por equipo (primeras 5 selecciones alfabeticas)");

db.jugadores.aggregate([
  {
    $group: {
      _id: { equipo: "$equipoCodigo", posicion: "$posicion" },
      n: { $sum: 1 }
    }
  },
  {
    $group: {
      _id: "$_id.equipo",
      composicion: {
        $push: { posicion: "$_id.posicion", cantidad: "$n" }
      },
      total: { $sum: "$n" }
    }
  },
  { $sort: { _id: 1 } },
  { $limit: 5 }
]).forEach(r => {
  const orden = { Arquero: 1, Defensor: 2, Mediocampista: 3, Delantero: 4 };
  r.composicion.sort((a, b) => orden[a.posicion] - orden[b.posicion]);
  const desglose = r.composicion.map(c => `${c.posicion.substr(0,3)}=${c.cantidad}`).join("  ");
  print(`  ${r._id}  total=${r.total}   ${desglose}`);
});

// -----------------------------------------------------------------------------
// (4) Estadistica de altura por posicion (min, max, promedio)
// -----------------------------------------------------------------------------
// Pregunta: "hay diferencia de altura significativa entre posiciones?"
titulo("4) Altura por posicion (cm)");

db.jugadores.aggregate([
  {
    $group: {
      _id: "$posicion",
      cantidad: { $sum: 1 },
      alturaMin: { $min: "$altura_cm" },
      alturaMax: { $max: "$altura_cm" },
      alturaProm: { $avg: "$altura_cm" }
    }
  },
  {
    $project: {
      _id: 0,
      posicion: "$_id",
      cantidad: 1,
      alturaMin: 1,
      alturaMax: 1,
      alturaProm: { $round: ["$alturaProm", 1] }
    }
  },
  { $sort: { alturaProm: -1 } }
]).forEach(r => print(
  `  ${r.posicion.padEnd(14)}  n=${String(r.cantidad).padStart(4)}   min=${r.alturaMin}   prom=${r.alturaProm}   max=${r.alturaMax}`
));

print("");
print("==============================================================");
