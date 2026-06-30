"""Esquemas del contrato **3×3 por dominio** (rediseño: un formato, tres modelos).

El cliente envía las ``rows`` en el **formato único** del dominio
(``spc.synthetic.esquemas``) y recibe los tres bloques —regresión, clasificación y
clustering— en una sola respuesta. La salida se devuelve como objeto libre (``dict``)
porque combina tres modelos heterogéneos; cada bloque se documenta en el endpoint.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# Ejemplo mínimo de filas de VENTAS (formato único del dominio).
_EJEMPLO_VENTAS: list[dict[str, Any]] = [
    {
        "fecha": "2023-01-01", "id_tienda": "T01", "sku": "SKU-001", "categoria": "Bebidas",
        "unidades_vendidas": 120, "precio_unitario": 3.5, "ingreso": 420.0,
        "en_promocion": 0, "descuento_pct": 0.0, "metodo_pago": "efectivo",
        "canal_venta": "tienda", "es_fin_de_semana": 0, "dias_a_proximo_feriado": 5,
    },
]
_EJEMPLO_SCHEMA: dict[str, Any] = {"example": {"rows": _EJEMPLO_VENTAS, "horizon": 14}}


class Analisis3x3Request(BaseModel):
    """Petición del análisis 3×3: filas en el formato del dominio + horizonte de pronóstico."""

    model_config = ConfigDict(extra="forbid", json_schema_extra=_EJEMPLO_SCHEMA)

    rows: list[dict[str, Any]] = Field(
        min_length=1, description="Filas en el formato único del dominio (ventas/compras/almacén)."
    )
    horizon: int = Field(
        default=14, gt=0, le=90, description="Períodos futuros a pronosticar en regresión (1–90)."
    )
