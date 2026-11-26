// =============================================================================
// 03-operaciones-crud.js
// -----------------------------------------------------------------------------
// Demuestra las operaciones de INSERCION y ACTUALIZACION exigidas por RF9,
// respetando la integridad documental (RNF3) y las validaciones del schema.
//
// Es idempotente: usa upsert por `codigo`, asi que dos ejecuciones dejan la
// base en el mismo estado.
// =============================================================================

print("==============================================================");
print(" Operaciones CRUD sobre equipos y jugadores                   ");
print("==============================================================");

// -----------------------------------------------------------------------------
// (1) INSERCION de un equipo nuevo
// -----------------------------------------------------------------------------
// Escenario: FIFA admite una repesca adicional. Ingresamos NORUEGA como
// equipo #65 de prueba. Usamos updateOne+upsert por `codigo` para que sea
// idempotente (no falla si ya existe de una corrida previa).
const nuevoEquipo = {
  codigo: "NOR",
  nombre: "Noruega",
  confederacion: "UEFA",
  rankingFIFA: 42,
  sedeBase: "Oslo",
  anfitrion: false,
  colores: ["rojo", "blanco", "azul"],
  directorTecnico: { nombre: "Stale Solbakken", nacionalidad: "Noruega" },
  fechaActualizacion: new Date()
};
const resInsEq = db.equipos.updateOne(
  { codigo: nuevoEquipo.codigo },
  { $set: nuevoEquipo },
  { upsert: true }
);
print(`[INSERT equipo] codigo=NOR  matched=${resInsEq.matchedCount}  upserted=${resInsEq.upsertedCount !== undefined ? resInsEq.upsertedCount : (resInsEq.upsertedId ? 1 : 0)}`);

// Verificacion: la validacion JSON Schema debe haber aceptado el documento.
printjson(db.equipos.findOne({ codigo: "NOR" }));

// -----------------------------------------------------------------------------
// (2) INSERCION de un jugador nuevo (vinculado al equipo insertado)
// -----------------------------------------------------------------------------
const nuevoJugador = {
  codigo: "NOR-9-hito4x",
  equipoCodigo: "NOR",
  nombre: "Erling Sintetico",   // nombre sintetico, no representa persona real
  posicion: "Delantero",
  dorsal: 9,
  fechaNacimiento: new Date("2000-07-21T00:00:00Z"),
  altura_cm: 194,
  peso_kg: 88,
  pieHabil: "izquierdo",
  partidosInternacionales: 40,
  goles: 35,
  capitan: false,
  convocado: true,
  valorMercado_millonesEUR: 180.0,
  fechaActualizacion: new Date()
};
const resInsJ = db.jugadores.updateOne(
  { codigo: nuevoJugador.codigo },
  { $set: nuevoJugador },
  { upsert: true }
);
print(`[INSERT jugador] codigo=NOR-9-hito4x  matched=${resInsJ.matchedCount}  upserted=${resInsJ.upsertedId ? 1 : 0}`);
printjson(db.jugadores.findOne({ codigo: "NOR-9-hito4x" }));

// -----------------------------------------------------------------------------
// (3) DEMOSTRACION de rechazo por validacion JSON Schema
// -----------------------------------------------------------------------------
// Intentamos insertar un equipo con confederacion invalida: el schema debe
// rechazarlo (validationAction: "error"). Se captura la excepcion para que
// el script no se corte.
print("");
print("Demostracion de validacion (se ESPERA un error controlado):");
try {
  db.equipos.insertOne({
    codigo: "XYZ",
    nombre: "Equipo Invalido",
    confederacion: "SUDAMERICANA",   // no esta en el enum
    rankingFIFA: 100
  });
  print("[FALLA] La validacion deberia haber rechazado el documento.");
} catch (e) {
  print("[OK] Validacion JSON Schema rechazo el documento como se esperaba.");
  print("     Motivo: " + (e.errInfo ? "confederacion fuera del enum" : e.message));
}

// -----------------------------------------------------------------------------
// (4) ACTUALIZACION de un equipo (cambio de DT y ranking)
// -----------------------------------------------------------------------------
// $set actualiza campos puntuales sin afectar los demas atributos del
// documento (RNF3: integridad documental).
const resUpdEq = db.equipos.updateOne(
  { codigo: "URU" },
  {
    $set: {
      "directorTecnico.nombre": "Marcelo Bielsa",
      rankingFIFA: 14,
      fechaActualizacion: new Date()
    }
  }
);
print("");
print(`[UPDATE equipo] URU  matched=${resUpdEq.matchedCount}  modified=${resUpdEq.modifiedCount}`);
printjson(db.equipos.findOne({ codigo: "URU" }, { nombre: 1, rankingFIFA: 1, directorTecnico: 1 }));

// -----------------------------------------------------------------------------
// (5) ACTUALIZACION masiva de jugadores (updateMany con $inc)
// -----------------------------------------------------------------------------
// Escenario: se disputo una fecha internacional. Todos los jugadores
// convocados suman +1 partido. Usamos $inc para no reescribir el valor entero.
const resIncr = db.jugadores.updateMany(
  { convocado: true },
  { $inc: { partidosInternacionales: 1 }, $set: { fechaActualizacion: new Date() } }
);
print(`[UPDATE MANY jugadores] convocados +1 partido  matched=${resIncr.matchedCount}  modified=${resIncr.modifiedCount}`);

// -----------------------------------------------------------------------------
// Cleanup opcional: NO borramos NOR/NOR-9-hito4x para que su presencia
// evidencie la insercion. Para removerlos:
//   db.jugadores.deleteMany({ equipoCodigo: "NOR" });
//   db.equipos.deleteOne({ codigo: "NOR" });
// -----------------------------------------------------------------------------
print("==============================================================");
