"""Router del campo ALMACEN — ``POST /inventory`` (riesgo de quiebre y stock)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from spc.api.dependencies import obtener_jobs, obtener_registro
from spc.api.jobs import GestorTrabajos
from spc.api.ruteo import responder_segun_volumen
from spc.api.schemas.almacen import AlmacenRequest, AlmacenResponse
from spc.api.schemas.comunes import ErrorResponse
from spc.api.schemas.jobs import JobAccepted
from spc.service.artefactos import RegistroArtefactos

router = APIRouter(tags=["INVENTORY"])


@router.post(
    "/inventory",
    response_model=AlmacenResponse,
    response_model_exclude_none=True,
    summary="Riesgo de quiebre y stock recomendado (clasificación + perfilado)",
    responses={
        202: {"model": JobAccepted, "description": "Envío grande: aceptado como trabajo por lote"},
        400: {"model": ErrorResponse, "description": "Producto sin histórico u otra regla de negocio"},
        422: {"model": ErrorResponse, "description": "Entrada mal formada"},
    },
)
def evaluar_almacen(
    peticion: AlmacenRequest,
    registro: Annotated[RegistroArtefactos, Depends(obtener_registro)],
    jobs: Annotated[GestorTrabajos, Depends(obtener_jobs)],
) -> dict | JSONResponse:
    """Riesgo de quiebre y stock recomendado por producto (clasificación + perfilado).

    **Entra:** el bloque ``history`` (para clasificar demanda alta/baja) y, por
    producto, ``inventory_status`` (``current_stock`` y ``lead_time_days`` opcional).
    **Sale:** por producto, ``demand_class`` con su ``high_demand_probability``,
    ``stockout_risk``, ``recommended_stock``, ``safety_stock`` y el ``store_segment``
    del clustering/perfilado.

    No expone ``model``: combina clasificación y clustering bajo el contrato. Un
    producto sin histórico devuelve ``400``. **Modo de ejecución (Fase 3.4):** por
    encima de ``SPC_ONLINE_MAX_ROWS`` filas se acepta como trabajo por lote (**202**
    con ``job_id``). El catálogo completo está en ``GET /catalog``.
    """
    return responder_segun_volumen("inventory", peticion, registro, jobs)
