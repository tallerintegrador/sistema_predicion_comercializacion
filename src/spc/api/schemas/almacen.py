"""Esquemas del campo ALMACEN — riesgo de quiebre y stock recomendado.

Implementa el contrato de la seccion 3.3 (clasificación + perfilado). El cliente
envia el bloque `history` (para clasificar demanda alta) y el `inventory_status`
por producto (`current_stock`, `lead_time_days` opcional). La respuesta combina la
**clase de demanda** (high/low con probabilidad), la bandera de **riesgo de
quiebre** (`stockout_risk`), el **stock recomendado** (incluye stock de seguridad)
y el **store_segment** que sale del clustering/perfilado.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from spc.api.schemas.comunes import EJEMPLO_HISTORICO, HistoricoItem, IdContrato


class EstadoInventarioItem(BaseModel):
    """Estado de inventario de un producto en un punto de venta."""

    model_config = ConfigDict(extra="forbid")

    store_id: IdContrato
    product_id: IdContrato
    current_stock: float = Field(ge=0, description="Stock disponible hoy (unidades).")
    lead_time_days: int | None = Field(
        default=None,
        gt=0,
        description="Tiempo de entrega del proveedor (días, opcional; afina el riesgo).",
    )


class AlmacenRequest(BaseModel):
    """Petición del campo ALMACEN."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "history": EJEMPLO_HISTORICO,
                "inventory_status": [
                    {
                        "store_id": "1",
                        "product_id": "BEVERAGES",
                        "current_stock": 300,
                        "lead_time_days": 3,
                    }
                ],
            }
        },
    )

    history: list[HistoricoItem] = Field(
        min_length=1, description="Histórico de demanda por producto."
    )
    inventory_status: list[EstadoInventarioItem] = Field(
        min_length=1, description="Stock actual (y lead time opcional) por producto."
    )


class AlertaItem(BaseModel):
    """Alerta de almacén para un producto en un punto de venta."""

    store_id: str
    product_id: str
    demand_class: Literal["high", "low"] = Field(
        description="Clase de demanda predicha por el clasificador."
    )
    high_demand_probability: float = Field(
        ge=0, le=1, description="Probabilidad de demanda alta (0–1)."
    )
    stockout_risk: bool = Field(description="True si el stock no cubre la demanda esperada.")
    recommended_stock: float = Field(
        ge=0, description="Stock objetivo (demanda en lead time + seguridad)."
    )
    safety_stock: float = Field(
        ge=0, description="Colchón ante variabilidad de la demanda."
    )
    store_segment: int = Field(
        description="Segmento del punto de venta (clustering/perfilado de tiendas)."
    )


class MetadatosAlmacen(BaseModel):
    """Metadatos informativos (definición del umbral de demanda alta)."""

    model_config = ConfigDict(extra="allow")

    threshold: str = Field(
        default="high_demand = sales > P75 of its family",
        description="Definición del umbral de demanda alta.",
    )


class AlmacenResponse(BaseModel):
    """Respuesta del campo ALMACEN (coincide en forma con la sección 3.3)."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "field": "inventory",
                "alerts": [
                    {
                        "store_id": "1",
                        "product_id": "BEVERAGES",
                        "demand_class": "high",
                        "high_demand_probability": 0.87,
                        "stockout_risk": True,
                        "recommended_stock": 1600,
                        "safety_stock": 420,
                        "store_segment": 1,
                    }
                ],
                "metadata": {"threshold": "high_demand = sales > P75 of its family"},
            }
        }
    )

    field: Literal["inventory"] = "inventory"
    alerts: list[AlertaItem]
    metadata: MetadatosAlmacen = Field(default_factory=MetadatosAlmacen)
