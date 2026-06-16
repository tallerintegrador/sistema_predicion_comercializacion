"""Router del campo VENTAS — ``POST /sales`` (pronóstico de demanda)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from spc.api.dependencies import obtener_registro
from spc.api.schemas.comunes import ErrorResponse
from spc.api.schemas.ventas import VentasRequest, VentasResponse
from spc.service import ventas_service
from spc.service.artefactos import RegistroArtefactos

router = APIRouter(tags=["SALES"])


@router.post(
    "/sales",
    response_model=VentasResponse,
    response_model_exclude_none=True,
    summary="Pronóstico de demanda (regresión)",
    responses={
        400: {"model": ErrorResponse, "description": "Regla de negocio incumplida"},
        422: {"model": ErrorResponse, "description": "Entrada mal formada"},
    },
)
def pronosticar_ventas(
    peticion: VentasRequest,
    registro: Annotated[RegistroArtefactos, Depends(obtener_registro)],
) -> dict:
    """Devuelve la demanda pronosticada por ``(date, store_id, product_id)``.

    El motor pronostica a nivel diario; ``granularity`` ``week``/``month`` agrega
    (suma) el resultado. La capa de servicio traduce el contrato al motor y de vuelta.
    """
    return ventas_service.pronosticar(
        historico=[h.model_dump() for h in peticion.history],
        horizonte=peticion.horizon,
        granularidad=peticion.granularity,
        registro=registro,
    )
