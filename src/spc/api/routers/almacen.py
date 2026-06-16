"""Router del campo ALMACEN — ``POST /inventory`` (riesgo de quiebre y stock)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from spc.api.dependencies import obtener_registro
from spc.api.schemas.almacen import AlmacenRequest, AlmacenResponse
from spc.api.schemas.comunes import ErrorResponse
from spc.service import almacen_service
from spc.service.artefactos import RegistroArtefactos

router = APIRouter(tags=["INVENTORY"])


@router.post(
    "/inventory",
    response_model=AlmacenResponse,
    response_model_exclude_none=True,
    summary="Riesgo de quiebre y stock recomendado (clasificación + perfilado)",
    responses={
        400: {"model": ErrorResponse, "description": "Producto sin histórico u otra regla de negocio"},
        422: {"model": ErrorResponse, "description": "Entrada mal formada"},
    },
)
def evaluar_almacen(
    peticion: AlmacenRequest,
    registro: Annotated[RegistroArtefactos, Depends(obtener_registro)],
) -> dict:
    """Devuelve, por producto, la clase de demanda, el riesgo de quiebre, el stock
    recomendado/seguridad y el ``store_segment`` del clustering/perfilado.
    """
    return almacen_service.alertas(
        historico=[h.model_dump() for h in peticion.history],
        estado_inventario=[e.model_dump() for e in peticion.inventory_status],
        registro=registro,
    )
