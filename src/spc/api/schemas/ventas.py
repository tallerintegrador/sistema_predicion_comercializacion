"""Esquemas del campo VENTAS — pronóstico de demanda (regresión).

Implementa el contrato de la seccion 3.1: el cliente envia `granularity`,
`horizon` y el bloque `history`; recibe, por cada
`(store_id, product_id, periodo futuro)`, la demanda pronosticada en
**unidades**, con intervalo opcional.
"""

from __future__ import annotations

from datetime import date as Date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from spc.api.schemas.comunes import EJEMPLO_HISTORICO, HistoricoItem

# Granularidad temporal de la peticion (diaria por defecto; semana/mes por
# agregacion del pronostico diario en la capa de servicio).
Granularidad = Literal["day", "week", "month"]


class VentasRequest(BaseModel):
    """Petición de pronóstico de VENTAS."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "granularity": "day",
                "horizon": 7,
                "history": EJEMPLO_HISTORICO,
            }
        },
    )

    granularity: Granularidad = Field(
        default="day", description="Granularidad del pronóstico (diaria por defecto)."
    )
    horizon: int = Field(
        gt=0,
        le=365,
        description="Número de períodos futuros a pronosticar (> 0).",
    )
    history: list[HistoricoItem] = Field(
        min_length=1, description="Histórico de la(s) serie(s) a pronosticar."
    )


class PronosticoItem(BaseModel):
    """Demanda pronosticada para un período futuro de una serie."""

    date: Date
    store_id: str
    product_id: str
    forecast_demand: float = Field(
        ge=0, description="Demanda esperada en unidades (≥ 0)."
    )
    interval_80: list[float] | None = Field(
        default=None,
        description=(
            "Intervalo de predicción al 80% [inferior, superior]. Opcional; "
            "diferido en Fase 2 (el modelo aún no lo produce)."
        ),
    )


class MetadatosVentas(BaseModel):
    """Metadatos informativos del pronóstico (escala y transformación interna)."""

    model_config = ConfigDict(extra="allow")

    scale: str = Field(default="units", description="Escala de la salida.")
    internal_transform: str = Field(
        default="log1p",
        description="Transformación que el motor aplica internamente (informativo).",
    )


class VentasResponse(BaseModel):
    """Respuesta del campo VENTAS (coincide en forma con la sección 3.1)."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "field": "sales",
                "model": "regresion_v3",
                "forecast": [
                    {
                        "date": "2017-08-03",
                        "store_id": "1",
                        "product_id": "BEVERAGES",
                        "forecast_demand": 1742.5,
                    },
                    {
                        "date": "2017-08-04",
                        "store_id": "1",
                        "product_id": "BEVERAGES",
                        "forecast_demand": 1690.2,
                    },
                ],
                "metadata": {"scale": "units", "internal_transform": "log1p"},
            }
        }
    )

    field: Literal["sales"] = "sales"
    model: str = Field(description="Versión del artefacto que pronosticó (leída del meta).")
    forecast: list[PronosticoItem]
    metadata: MetadatosVentas = Field(default_factory=MetadatosVentas)
