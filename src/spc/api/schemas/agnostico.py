"""Contrato **agnóstico al rubro** (predicción auto-entrenada, ADR-0023) — re-export.

Los modelos viven en la capa neutral ``spc.service.esquemas_agnostico`` para que el motor de
servicio no dependa de la capa de API (se rompió el import invertido en la auditoría
2026-07-03). Este módulo los re-exporta para no cambiar el contrato ni los importadores de la
capa API/legacy.
"""

from __future__ import annotations

from spc.service.esquemas_agnostico import (  # noqa: F401
    EJEMPLO_ROWS,
    AutoInventoryRequest,
    AutoInventoryResponse,
    AutoPurchasesRequest,
    AutoPurchasesResponse,
    AutoSalesRequest,
    AutoSalesResponse,
    AutoTemplateRequest,
    FeatureSpec,
    Granularidad,
    InfoEntrenamiento,
    SchemaSpec,
    TipoFeature,
)

__all__ = [
    "EJEMPLO_ROWS",
    "AutoInventoryRequest",
    "AutoInventoryResponse",
    "AutoPurchasesRequest",
    "AutoPurchasesResponse",
    "AutoSalesRequest",
    "AutoSalesResponse",
    "AutoTemplateRequest",
    "FeatureSpec",
    "Granularidad",
    "InfoEntrenamiento",
    "SchemaSpec",
    "TipoFeature",
]
