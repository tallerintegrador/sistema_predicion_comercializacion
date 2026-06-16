"""Router del campo COMPRAS — ``POST /purchases`` (reposición derivada)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from spc.api.dependencies import obtener_registro
from spc.api.schemas.compras import ComprasRequest, ComprasResponse
from spc.api.schemas.comunes import ErrorResponse
from spc.service import compras_service
from spc.service.artefactos import RegistroArtefactos

router = APIRouter(tags=["PURCHASES"])


@router.post(
    "/purchases",
    response_model=ComprasResponse,
    response_model_exclude_none=True,
    summary="Reposición sugerida (derivada del pronóstico)",
    responses={
        400: {"model": ErrorResponse, "description": "Producto sin histórico u otra regla de negocio"},
        422: {"model": ErrorResponse, "description": "Entrada mal formada"},
    },
)
def recomendar_compras(
    peticion: ComprasRequest,
    registro: Annotated[RegistroArtefactos, Depends(obtener_registro)],
) -> dict:
    """Devuelve, por producto, la demanda esperada, el punto de reorden y la cantidad a reponer.

    No hay modelo propio: reutiliza el pronóstico de VENTAS y los parámetros
    logísticos del cliente (lógica de negocio en la capa de servicio).
    """
    return compras_service.reponer(
        historico=[h.model_dump() for h in peticion.history],
        parametros_reposicion=[p.model_dump() for p in peticion.replenishment_params],
        registro=registro,
    )
