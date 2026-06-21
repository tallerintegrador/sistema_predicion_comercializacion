"""Router del campo COMPRAS — ``POST /purchases`` (reposición derivada)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from spc.api.dependencies import (
    obtener_client_id,
    obtener_jobs,
    obtener_registro,
    obtener_repositorio,
)
from spc.api.jobs import GestorTrabajos
from spc.api.ruteo import responder_segun_volumen
from spc.api.schemas.auth import SessionUser
from spc.api.schemas.compras import ComprasRequest, ComprasResponse
from spc.api.schemas.comunes import ErrorResponse
from spc.api.schemas.jobs import JobAccepted
from spc.api.seguridad import requiere
from spc.service.artefactos import RegistroArtefactos
from spc.service.repositorio import RepositorioPredicciones

router = APIRouter(tags=["PURCHASES"])


@router.post(
    "/purchases",
    response_model=ComprasResponse,
    response_model_exclude_none=True,
    summary="Reposición sugerida (derivada del pronóstico)",
    responses={
        202: {"model": JobAccepted, "description": "Envío grande: aceptado como trabajo por lote"},
        400: {"model": ErrorResponse, "description": "Producto sin histórico u otra regla de negocio"},
        422: {"model": ErrorResponse, "description": "Entrada mal formada"},
    },
)
def recomendar_compras(
    peticion: ComprasRequest,
    registro: Annotated[RegistroArtefactos, Depends(obtener_registro)],
    jobs: Annotated[GestorTrabajos, Depends(obtener_jobs)],
    repositorio: Annotated[RepositorioPredicciones | None, Depends(obtener_repositorio)],
    client_id: Annotated[str, Depends(obtener_client_id)],
    _auth: Annotated[SessionUser | None, Depends(requiere("module:purchases", "action:forecast"))],
) -> dict | JSONResponse:
    """Reposición sugerida por producto, derivada del pronóstico de ventas.

    **Entra:** el bloque ``history`` (de donde se deriva la demanda) y, por producto,
    ``replenishment_params`` (``current_stock``, ``lead_time_days``, ``target_coverage_days``).
    **Sale:** por producto, ``expected_demand_horizon``, ``reorder_point``,
    ``replenishment_quantity`` y su ``justification``.

    No hay modelo propio (la respuesta **no** incluye ``model``): es lógica de negocio
    que reutiliza el pronóstico de VENTAS y los parámetros logísticos del cliente. Un
    producto sin histórico devuelve ``400``. **Modo de ejecución (Fase 3.4):** por
    encima de ``SPC_ONLINE_MAX_ROWS`` filas se acepta como trabajo por lote (**202**
    con ``job_id``). El catálogo completo está en ``GET /catalog``.
    """
    return responder_segun_volumen(
        "purchases", peticion, registro, jobs,
        repositorio=repositorio, canal="json", client_id=client_id,
    )
