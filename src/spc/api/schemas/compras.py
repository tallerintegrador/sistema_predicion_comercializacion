"""Esquemas del campo COMPRAS — reposición (derivada del pronóstico).

Implementa el contrato de la seccion 3.2. COMPRAS **no tiene modelo propio**: el
cliente envia el mismo bloque `history` (de donde se calcula internamente el
pronostico de VENTAS) y los `replenishment_params` logisticos por producto
(`current_stock`, `lead_time_days`, `target_coverage_days`). La respuesta es la
cantidad sugerida a reponer y el punto de reorden, derivados por **lógica de
negocio** (capa de servicio), no por un modelo.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from spc.api.schemas.comunes import EJEMPLO_HISTORICO, HistoricoItem, IdContrato


class ParametroReposicion(BaseModel):
    """Parámetros logísticos de un producto en un punto de venta.

    Son **del cliente** (SPC no los inventa): el stock que tiene hoy, el tiempo de
    entrega del proveedor y los días de cobertura objetivo de su política.

    Validación **estricta** (``strict=True``): sin coerciones silenciosas de tipo.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    store_id: IdContrato
    product_id: IdContrato
    current_stock: float = Field(ge=0, description="Stock disponible hoy (unidades).")
    lead_time_days: int = Field(
        gt=0, description="Tiempo de entrega del proveedor (días, > 0)."
    )
    target_coverage_days: int = Field(
        gt=0, description="Días de demanda que se quiere cubrir (> 0)."
    )


class ComprasRequest(BaseModel):
    """Petición de reposición de COMPRAS.

    Validación **estricta** (``strict=True``): sin coerciones silenciosas de tipo.
    """

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        json_schema_extra={
            "example": {
                "history": EJEMPLO_HISTORICO,
                "replenishment_params": [
                    {
                        "store_id": "1",
                        "product_id": "BEVERAGES",
                        "current_stock": 900,
                        "lead_time_days": 3,
                        "target_coverage_days": 7,
                    }
                ],
            }
        },
    )

    history: list[HistoricoItem] = Field(
        min_length=1, description="Histórico para calcular el pronóstico de demanda."
    )
    replenishment_params: list[ParametroReposicion] = Field(
        min_length=1, description="Parámetros logísticos por producto a reponer."
    )


class RecomendacionItem(BaseModel):
    """Recomendación de reposición para un producto en un punto de venta."""

    store_id: str
    product_id: str
    expected_demand_horizon: float = Field(
        ge=0,
        description="Demanda pronosticada acumulada sobre la ventana de cobertura.",
    )
    reorder_point: float = Field(
        ge=0,
        description="Nivel de stock que dispara una nueva orden (demanda en lead time + seguridad).",
    )
    replenishment_quantity: float = Field(
        ge=0, description="Unidades sugeridas a pedir (≥ 0)."
    )
    justification: str = Field(description="Fórmula/razonamiento de la recomendación.")


class MetadatosCompras(BaseModel):
    """Metadatos informativos (supuestos de la derivación).

    Declara **todos** los campos que el servicio produce hoy (sin ``extra="allow"``),
    de modo que el catálogo derivado de este esquema describa la salida completa.
    """

    assumption: str = Field(
        default="demanda y lead time aproximados; revisar política del cliente",
        description="Supuestos de la lógica de reposición.",
    )
    policy: str = Field(
        default="coverage_days",
        description="Política de reposición aplicada (días de cobertura).",
    )


class ComprasResponse(BaseModel):
    """Respuesta del campo COMPRAS (coincide en forma con la sección 3.2)."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "field": "purchases",
                "recommendation": [
                    {
                        "store_id": "1",
                        "product_id": "BEVERAGES",
                        "expected_demand_horizon": 12200,
                        "reorder_point": 5400,
                        "replenishment_quantity": 11300,
                        "justification": "forecast_demand + safety_stock - current_stock",
                    }
                ],
                "metadata": {
                    "assumption": "demanda y lead time aproximados; revisar política del cliente"
                },
            }
        }
    )

    field: Literal["purchases"] = "purchases"
    recommendation: list[RecomendacionItem]
    metadata: MetadatosCompras = Field(default_factory=MetadatosCompras)
