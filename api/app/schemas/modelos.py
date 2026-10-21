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
