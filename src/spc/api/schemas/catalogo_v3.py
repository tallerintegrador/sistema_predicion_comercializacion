"""Esquemas Pydantic para la API v3 del catálogo.

Define las estructuras de respuesta para los endpoints /v3/{modulo}, /v3/catalogo,
y /v3/{modulo}/plantilla.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class FilaComparacion(BaseModel):
    """Fila de la tabla de comparación de modelos (solo detalle técnico)."""

    modelo: str
    metrica: str
    valor: float
    ganador: bool = False


class DetalleTecnico(BaseModel):
    """Información técnica de un reporte: modelo ganador, métricas, competencia."""

    modelo_ganador: str
    metrica: str
    valor_metrica: float
    tabla_comparacion: list[FilaComparacion]
    fecha_entrenamiento: datetime
    nota_tecnica: str | None = Field(
        default=None, description="Nota honesta (p. ej. etiqueta por regla determinística)"
    )


class ReporteConsulta(BaseModel):
    """Un reporte de una consulta ejecutada del catálogo."""

    consulta_id: str
    modulo: str
    tipo: str  # "regresion", "clasificacion", "clustering"
    pregunta: str
    descripcion: str | None = None
    unidad: str = Field(default="", description="Unidad de la magnitud predicha (unidades/S/./días/%/índice)")
    resultado: dict[str, Any] = Field(
        description="Predicciones/agrupación del reporte (estructura variable por tipo)"
    )
    advertencia: str | None = Field(
        default=None, description="Advertencia de calidad baja (umbrales no bloqueantes)"
    )
    detalle_tecnico: DetalleTecnico


class PuntoSerie(BaseModel):
    """Un punto de la serie temporal (fecha + valor agregado)."""

    fecha: str
    valor: float


class BloqueAnalisisTendencia(BaseModel):
    """Bloque de análisis/tendencia: la ÚNICA sección con línea temporal.

    Claves en ASCII (sin tildes/ñ) para un contrato JSON limpio.
    """

    campo: str = "tendencia"
    titulo: str = "Análisis / Tendencia"
    descripcion: str = "Evolución temporal del negocio (histórico) y pronóstico referencial."
    unidad: str = ""
    metodo: str = ""
    historico: list[PuntoSerie] = Field(default_factory=list)
    pronostico: list[PuntoSerie] = Field(default_factory=list)


class RespuestaModulo(BaseModel):
    """Respuesta completa de POST /v3/{modulo}."""

    modulo: str
    reportes: list[ReporteConsulta] = Field(
        min_length=10, max_length=10, description="Exactamente 10 reportes (4R+3C+3K)"
    )
    analisis_tendencia: BloqueAnalisisTendencia | None = None
    fecha_ejecución: datetime


class ConsultaInfo(BaseModel):
    """Información de una consulta para GET /v3/catalogo."""

    id: str
    modulo: str
    tipo: str
    pregunta: str
    descripcion: str | None = None


class RespuestaCatalogo(BaseModel):
    """Respuesta de GET /v3/catalogo."""

    total_consultas: int = 30
    consultas: list[ConsultaInfo]


class SolicitudAnalisisModulo(BaseModel):
    """Solicitud de POST /v3/{modulo} — datos a analizar."""

    rows: list[dict[str, Any]] = Field(min_length=1, description="Filas de datos del módulo")
