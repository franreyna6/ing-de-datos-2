"""Schemas de request y response (RF10, RNF3, RNF17).

Pydantic valida los cuerpos y las queries ANTES de tocar una base: un parametro
mal formado se rechaza con 422/400 sin consultar la fuente. Tambien definen la
forma de las respuestas que documenta OpenAPI, de modo que el contrato y el
servidor coinciden (RNF2).

Las respuestas conservan identificadores, timestamps y estados necesarios para
interpretar el dato (RNF17): no se recorta informacion que el consumidor precise.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


# --- Error comun (documentado en OpenAPI) ---
class ErrorDetalle(BaseModel):
    code: str = Field(..., examples=["NOT_FOUND"])
    message: str = Field(..., examples=["El recurso solicitado no existe"])
    request_id: str = Field(..., examples=["a1b2c3d4"])
    detalles: dict | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetalle


# --- MongoDB ---
class Equipo(BaseModel):
    codigo: str = Field(..., examples=["ARG"])
    nombre: str = Field(..., examples=["Argentina"])
    confederacion: str | None = Field(None, examples=["CONMEBOL"])
    rankingFIFA: int | None = Field(None, examples=[1])
    grupo: str | None = Field(None, examples=["A"])
    ciudadSede: str | None = Field(None, examples=["Buenos Aires"])


class Jugador(BaseModel):
    codigo: str = Field(..., examples=["ARG-10"])
    nombre: str | None = None
    apellido: str | None = None
    posicion: str | None = Field(None, examples=["Delantero"])
    dorsal: int | None = Field(None, examples=[10])
    equipoCodigo: str | None = Field(None, examples=["ARG"])


class ListaJugadores(BaseModel):
    equipoCodigo: str
    total: int
    jugadores: list[Jugador]


# --- Neo4j ---
class EventoPartido(BaseModel):
    evento: str | None = None
    tipo: str | None = Field(None, examples=["Gol"])
    minuto: int | None = Field(None, examples=[23])
    jugadorCodigo: str | None = None
    jugadorNombre: str | None = None


class EventosDePartido(BaseModel):
    partido: str = Field(..., examples=["F2030-001"])
    fecha: str | None = None
    eventos: list[EventoPartido]


# --- Cassandra ---
class Comentario(BaseModel):
    comentarioId: str
    creadoEn: str | None = None
    usuarioId: str | None = None
    contenido: str | None = None
    estado: str | None = None
    likes: int | None = None


class PaginaComentarios(BaseModel):
    partido: str
    ventana: str = Field(..., description="Inicio UTC de la ventana de 5 minutos leida")
    comentarios: list[Comentario]


class NuevoComentario(BaseModel):
    usuarioId: str = Field(..., min_length=1, max_length=64, examples=["u-00042"])
    contenido: str = Field(..., min_length=1, max_length=500,
                           examples=["Gran jugada en el minuto 15"])
    comentarioId: str | None = Field(
        None, description="Clave de idempotencia opcional (UUID). Reusarla reescribe la misma fila.")


class ComentarioCreado(BaseModel):
    partido: str
    ventana: str
    comentarioId: str
    creadoEn: str


# --- Redis ---
class Sesion(BaseModel):
    sesionId: str
    usuarioId: str | None = None
    estado: str = Field(..., examples=["activa"])
    ttlSegundos: int | None = Field(None, examples=[1800])


# --- InfluxDB ---
class PuntoEstadistica(BaseModel):
    time: str | None = None
    equipoId: str | None = None
    posesionPct: float | None = None
    pasesAcum: int | None = None
    tirosAcum: int | None = None
    recuperacionesAcum: int | None = None


class Estadisticas(BaseModel):
    partido: str
    desde: str
    hasta: str
    puntos: list[PuntoEstadistica]


# --- IRIS ---
class SedeRef(BaseModel):
    codigo: str | None = None
    nombre: str | None = None


class DetallePartido(BaseModel):
    codigo: str
    fecha: str | None = None
    fase: str | None = None
    estado: str | None = Field(None, examples=["Finalizado"])
    golesLocal: int | None = None
    golesVisitante: int | None = None
    equipoLocal: str | None = None
    equipoVisitante: str | None = None
    sede: SedeRef | None = None
    cantidadEventos: int | None = None


# --- Health ---
class EstadoDependencia(BaseModel):
    fuente: str
    disponible: bool


class Salud(BaseModel):
    api: str = "ok"
    dependencias: list[EstadoDependencia]


# --- Hito 13: demo en vivo (un partido que atraviesa las seis bases) ---
class NuevoPartidoVivo(BaseModel):
    codigo: str | None = Field(
        None, description="Codigo de laboratorio. Debe empezar con H13-DEMO-. "
                          "Si se omite: H13-DEMO-<LOCAL><VISITANTE>.",
        examples=["H13-DEMO-URUARG"])
    local: str = Field(..., min_length=3, max_length=3, examples=["URU"])
    visitante: str = Field(..., min_length=3, max_length=3, examples=["ARG"])
    sede: str = Field(..., min_length=2, max_length=10, examples=["CENT"])
    fecha: str = Field(..., description="AAAA-MM-DD", examples=["2030-06-08"])


class NuevoEventoVivo(BaseModel):
    tipo: str = Field(..., examples=["Gol"], description="Gol | Tarjeta")
    minuto: int = Field(..., ge=1, le=120, examples=[23])
    jugadorCodigo: str = Field(..., min_length=3, max_length=30, examples=["URU-4-blpv45"])


class RelojVivo(BaseModel):
    minuto: int = Field(..., ge=0, le=130, examples=[37])


class PuntoEstadisticaVivo(BaseModel):
    equipoId: str = Field(..., min_length=3, max_length=3, examples=["URU"])
    posesionPct: float = Field(..., ge=0, le=100, examples=[54.5])
    pasesAcum: int = Field(..., ge=0, examples=[212])
    tirosAcum: int = Field(..., ge=0, examples=[7])
    recuperacionesAcum: int = Field(..., ge=0, examples=[31])
    ts: int | None = Field(None, description="Epoch en segundos (UTC). Si se omite, ahora.")


class LoteEstadisticasVivo(BaseModel):
    sede: str = Field(..., examples=["CENT"])
    grupo: str | None = Field(None, examples=["-"])
    puntos: list[PuntoEstadisticaVivo] = Field(..., min_length=1, max_length=500)


class PasoTraza(BaseModel):
    fuente: str = Field(..., examples=["iris"])
    operacion: str = Field(..., examples=["Fixture.Vivo.RegistrarEvento"])
    ok: bool
    ms: float
    error: str | None = None
    sincronizado: bool | None = Field(
        None, description="false si la propagacion a esta base fallo (sin transacciones "
                          "entre motores: queda a la vista).")


class PartidoIris(BaseModel):
    ok: bool
    codigo: str
    estado: str | None = Field(None, examples=["EnJuego"])
    fecha: str | None = None
    golesLocal: int | None = None
    golesVisitante: int | None = None
    equipoLocal: str | None = None
    equipoVisitante: str | None = None
    sede: str | None = None
    cantidadEventos: int | None = None
    terna: list[dict] | None = None
    accion: str | None = None
    motivo: str | None = None


class OperacionVivo(BaseModel):
    partido: PartidoIris
    grafo: dict | None = None
    traza: list[PasoTraza]


class EventoVivoRegistrado(OperacionVivo):
    evento: str = Field(..., examples=["EVD-1A2B3C4D"])
    tipo: str
    minuto: int
    jugador: str


class EstadisticasEscritas(BaseModel):
    partido: str
    puntosEscritos: int


class SeccionTablero(BaseModel):
    fuente: str = Field(..., examples=["cassandra"])
    ok: bool
    http: int = Field(..., examples=[200])
    ms: float = Field(..., description="Tiempo de ESA base, medido dentro de la API")
    datos: dict | None = None
    error: dict | None = None


class TableroVivo(BaseModel):
    partido: str
    generado: str
    msTotal: float = Field(..., description="Las bases se consultan en paralelo: el total "
                                            "se acerca a la mas lenta, no a la suma.")
    secciones: dict[str, SeccionTablero]


class NuevaSesion(BaseModel):
    usuarioId: str = Field(..., min_length=1, max_length=64, examples=["u-00042"])
    rol: str = Field("hincha", examples=["hincha"])
    partido: str | None = Field(None, description="Si se indica, el hincha cuenta como "
                                                  "conectado a ese partido (HyperLogLog).",
                                examples=["H13-DEMO-URUARG"])


class SesionActiva(Sesion):
    acciones: int | None = None
