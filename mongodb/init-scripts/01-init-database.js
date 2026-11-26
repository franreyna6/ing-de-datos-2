// =============================================================================
// 01-init-database.js
// -----------------------------------------------------------------------------
// Se ejecuta AUTOMATICAMENTE la primera vez que arranca el contenedor de
// MongoDB (cuando /data/db esta vacio). Su unica responsabilidad es dejar la
// base "fixture2030" preparada con:
//   - Colecciones creadas con validacion JSON Schema (RF7, RNF3)
//   - Un usuario de aplicacion con permisos acotados a esta base
//
// No carga datos. La carga (RF4, RF5, RF8) esta en scripts/01-cargar-datos.js
// para poder re-ejecutarse cuantas veces sea necesario sin borrar el volumen.
// =============================================================================

print("==============================================================");
print(" Inicializando base fixture2030 (validacion + usuario app)   ");
print("==============================================================");

// El usuario root (admin/admin) fue creado por Docker via env vars.
// Nos conectamos a la base de trabajo.
db = db.getSiblingDB("fixture2030");

// -----------------------------------------------------------------------------
// Coleccion: equipos
// -----------------------------------------------------------------------------
// 64 selecciones nacionales. Volumen fijo y chico, alta lectura.
// Modelado como documento autocontenido (no embebe jugadores; ver Decision #1
// en el documento de decisiones tecnicas).
// -----------------------------------------------------------------------------
db.createCollection("equipos", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      title: "Equipo del Fixture 2030",
      required: ["codigo", "nombre", "confederacion", "rankingFIFA"],
      additionalProperties: true,
      properties: {
        codigo: {
          bsonType: "string",
          description: "Codigo FIFA de 3 letras (ARG, BRA, ESP). Identificador de negocio unico.",
          pattern: "^[A-Z]{3}$"
        },
        nombre: {
          bsonType: "string",
          description: "Nombre oficial de la seleccion.",
          minLength: 2,
          maxLength: 80
        },
        confederacion: {
          enum: ["CONMEBOL", "UEFA", "CONCACAF", "CAF", "AFC", "OFC"],
          description: "Una de las 6 confederaciones de FIFA."
        },
        rankingFIFA: {
          bsonType: "int",
          minimum: 1,
          maximum: 250,
          description: "Posicion actual en el ranking mundial FIFA."
        },
        sedeBase: { bsonType: "string" },
        anfitrion: {
          bsonType: "bool",
          description: "true para las 6 sedes anfitrionas (ARG, URU, PAR, ESP, POR, MAR)."
        },
        colores: {
          bsonType: "array",
          items: { bsonType: "string" }
        },
        directorTecnico: {
          bsonType: "object",
          properties: {
            nombre: { bsonType: "string" },
            nacionalidad: { bsonType: "string" }
          }
        },
        fechaActualizacion: { bsonType: "date" }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
});
print("[OK] Coleccion 'equipos' creada con validacion JSON Schema");

// -----------------------------------------------------------------------------
// Coleccion: jugadores
// -----------------------------------------------------------------------------
// ~1.024 jugadores (16 por equipo). Colección separada (referencing) con
// campo equipoCodigo apuntando al codigo FIFA del equipo (ver Decision #1
// y Decision #3 en el documento de decisiones tecnicas).
// -----------------------------------------------------------------------------
db.createCollection("jugadores", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      title: "Jugador convocado al Fixture 2030",
      required: ["codigo", "equipoCodigo", "nombre", "posicion", "dorsal", "fechaNacimiento"],
      additionalProperties: true,
      properties: {
        codigo: {
          bsonType: "string",
          description: "Identificador de negocio del jugador (ej: ARG-10-abc123). Unico.",
          pattern: "^[A-Z]{3}-[0-9]{1,2}-[a-z0-9]{4,10}$"
        },
        equipoCodigo: {
          bsonType: "string",
          description: "Referencia al codigo FIFA del equipo. Debe existir en equipos.codigo.",
          pattern: "^[A-Z]{3}$"
        },
        nombre: {
          bsonType: "string",
          minLength: 2,
          maxLength: 80
        },
        posicion: {
          enum: ["Arquero", "Defensor", "Mediocampista", "Delantero"],
          description: "Posicion tactica principal."
        },
        dorsal: {
          bsonType: "int",
          minimum: 1,
          maximum: 99
        },
        fechaNacimiento: {
          bsonType: "date"
        },
        altura_cm: {
          bsonType: "int",
          minimum: 150,
          maximum: 220
        },
        peso_kg: {
          bsonType: "int",
          minimum: 50,
          maximum: 120
        },
        pieHabil: {
          enum: ["derecho", "izquierdo", "ambos"]
        },
        partidosInternacionales: {
          bsonType: "int",
          minimum: 0
        },
        goles: {
          bsonType: "int",
          minimum: 0
        },
        capitan: {
          bsonType: "bool"
        },
        convocado: {
          bsonType: "bool"
        },
        valorMercado_millonesEUR: {
          bsonType: ["double", "int"],
          minimum: 0
        },
        fechaActualizacion: { bsonType: "date" }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
});
print("[OK] Coleccion 'jugadores' creada con validacion JSON Schema");

// -----------------------------------------------------------------------------
// Usuario de aplicacion (least privilege) para la base fixture2030
// -----------------------------------------------------------------------------
db.createUser({
  user: "fixture_app",
  pwd: "fixture_app",
  roles: [
    { role: "readWrite", db: "fixture2030" }
  ]
});
print("[OK] Usuario de aplicacion 'fixture_app' creado (readWrite sobre fixture2030)");

print("==============================================================");
print(" Base fixture2030 lista. Proximo paso: cargar datos.         ");
print(" -> docker exec -i fixture2030-mongodb mongosh ... < scripts/01-cargar-datos.js");
print("==============================================================");
