"""Esquemas Pydantic para la API v3 del catálogo.

Define las estructuras de respuesta para los endpoints /v3/{modulo}, /v3/catalogo,
y /v3/{modulo}/plantilla.

Convención de contrato (ADR-0028): las CLAVES del cuerpo JSON y los enums (``type``) están
en inglés. Los VALORES de negocio en español (preguntas, avisos, etiquetas legibles) y los
identificadores de datos del cliente (columnas de la plantilla, valores de módulo en la ruta)
se mantienen en español porque son los datos reales del PYME.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ComparisonRow(BaseModel):
    """Fila de la tabla de comparación de modelos (solo detalle técnico)."""

    model: str
    metric: str
    value: float
    winner: bool = False


class TechnicalDetail(BaseModel):
    """Información técnica de un reporte: modelo ganador, métricas, competencia."""

    winner_model: str
    metric: str
    metric_value: float
    quality: str = Field(
        default="limitada", description="Calidad honesta según umbrales del catálogo: 'buena' | 'limitada'"
    )
    comparison_table: list[ComparisonRow]
    trained_at: datetime
    technical_note: str | None = Field(
        default=None, description="Nota honesta (p. ej. etiqueta por regla determinística)"
    )


class RegressionSummary(BaseModel):
    """Recuadro resumen de una regresión (A2): suma para extensivas, promedio para intensivas."""

    aggregation: str  # "sum" | "mean"
    value: float
    label: str  # "Total estimado" | "Promedio estimado"
    unit: str = ""
    magnitude: str  # "extensiva" | "intensiva"


class ColumnUsed(BaseModel):
    """Una columna que usa la consulta, con su rol e interpretación para el popup ⓘ."""

    name: str
    label: str
    role: str = Field(description="'objetivo' (lo que predice) | 'feature' (entrada) | 'dimension'")
    description: str = Field(default="", description="Interpretación de negocio; vacío = sin ⓘ")


class QueryReport(BaseModel):
    """Un reporte de una consulta ejecutada del catálogo."""

    query_id: str
    module: str
    type: str  # "regression", "classification", "clustering"
    question: str
    description: str | None = None
    unit: str = Field(default="", description="Unidad de la magnitud predicha (unidades/S/./días/%/índice)")
    result: dict[str, Any] = Field(
        description="Predicciones/agrupación del reporte (estructura variable por tipo)"
    )
    summary: RegressionSummary | None = Field(
        default=None, description="Recuadro resumen (solo regresión): suma/promedio según magnitud"
    )
    warning: str | None = Field(
        default=None, description="Advertencia de calidad baja (umbrales no bloqueantes)"
    )
    columns_used: list[ColumnUsed] = Field(
        default_factory=list,
        description="Columnas en que se basa la predicción (objetivo/features/dimensiones)",
    )
    technical_detail: TechnicalDetail


class SeriesPoint(BaseModel):
    """Un punto de la serie temporal (fecha + valor agregado)."""

    date: str
    value: float


class TrendSummary(BaseModel):
    """Resumen interpretativo del pronóstico (A3)."""

    projection: float  # suma proyectada en el horizonte
    change_pct: float  # variación % del pronóstico vs. período reciente
    direction: str  # "creciente" | "estable" | "decreciente"


class TrendBreakdown(BaseModel):
    """Serie por dimensión (p. ej. categoría) para el filtro del frontend (A3)."""

    label: str
    history: list[SeriesPoint] = Field(default_factory=list)
    forecast: list[SeriesPoint] = Field(default_factory=list)


class TrendAnalysis(BaseModel):
    """Bloque de análisis/tendencia: la ÚNICA sección con línea temporal.

    Claves en inglés/ASCII para un contrato JSON limpio.
    """

    field: str = "trend"
    title: str = "Análisis / Tendencia"
    description: str = "Evolución temporal del negocio (histórico) y pronóstico referencial."
    unit: str = ""
    method: str = ""
    horizon: int = 14  # días de pronóstico (del catálogo)
    history: list[SeriesPoint] = Field(default_factory=list)
    forecast: list[SeriesPoint] = Field(default_factory=list)
    summary: TrendSummary | None = None
    breakdowns: list[TrendBreakdown] = Field(default_factory=list)


class DatasetInfo(BaseModel):
    """Retroalimentación de validación de la carga (A8): qué se reconoció y qué se descartó."""

    recognized_columns: list[str] = Field(default_factory=list)
    missing_columns: list[str] = Field(default_factory=list)
    rows_received: int = 0
    rows_discarded: int = 0


class ModuleResponse(BaseModel):
    """Respuesta completa de POST /v3/{modulo}."""

    module: str
    reports: list[QueryReport] = Field(
        min_length=10, max_length=10, description="Exactamente 10 reportes (4R+3C+3K)"
    )
    trend_analysis: TrendAnalysis | None = None
    dataset_info: DatasetInfo | None = None
    executed_at: datetime


class QueryInfo(BaseModel):
    """Información de una consulta para GET /v3/catalogo."""

    id: str
    module: str
    type: str
    question: str
    description: str | None = None


class CatalogResponse(BaseModel):
    """Respuesta de GET /v3/catalogo."""

    total_queries: int = 30
    queries: list[QueryInfo]
    column_labels: dict[str, str] = Field(
        default_factory=dict,
        description="Etiquetas legibles por columna (fuente única del catálogo, para la UI)",
    )


class ModuleAnalysisRequest(BaseModel):
    """Solicitud de POST /v3/{modulo} — datos a analizar."""

    rows: list[dict[str, Any]] = Field(min_length=1, description="Filas de datos del módulo")


# ---------------------------------------------------------------------------
# Historial de predicciones (GET /v3/{modulo}/historial, GET /v3/historial/{id})
# ---------------------------------------------------------------------------
class PrediccionHistorialItem(BaseModel):
    """Una entrada del historial: metadatos de un análisis ejecutado (sin el payload pesado)."""

    id: int
    module: str = Field(description="Categoría: ventas | compras | almacen")
    created_at: str = Field(description="Marca de tiempo ISO de cuándo se ejecutó el análisis")
    rows: int = Field(default=0, description="Nº de filas de datos analizadas")
    reports: int = Field(default=0, description="Nº de reportes generados")


class HistorialResponse(BaseModel):
    """Respuesta de GET /v3/{modulo}/historial — lista paginable de análisis pasados."""

    module: str | None = None
    total: int = 0
    items: list[PrediccionHistorialItem] = Field(default_factory=list)


class PrediccionDetalle(BaseModel):
    """Detalle completo de una predicción del historial (para re-ver los valores pronosticados)."""

    id: int
    module: str
    created_at: str
    request: dict[str, Any] | None = None
    response: dict[str, Any] | None = None
