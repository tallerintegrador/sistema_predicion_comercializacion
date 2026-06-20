"""Router del campo VENTAS — ``POST /sales`` (pronóstico de demanda)."""

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
from spc.api.schemas.comunes import ErrorResponse
from spc.api.schemas.jobs import JobAccepted
from spc.api.schemas.ventas import VentasRequest, VentasResponse
from spc.service.artefactos import RegistroArtefactos
from spc.service.repositorio import RepositorioPredicciones

router = APIRouter(tags=["SALES"])


@router.post(
    "/sales",
    response_model=VentasResponse,
    response_model_exclude_none=True,
    summary="Pronóstico de demanda (regresión)",
    responses={
        202: {"model": JobAccepted, "description": "Envío grande: aceptado como trabajo por lote"},
        400: {"model": ErrorResponse, "description": "Regla de negocio incumplida"},
        422: {"model": ErrorResponse, "description": "Entrada mal formada"},
    },
)
def pronosticar_ventas(
    peticion: VentasRequest,
    registro: Annotated[RegistroArtefactos, Depends(obtener_registro)],
    jobs: Annotated[GestorTrabajos, Depends(obtener_jobs)],
    repositorio: Annotated[RepositorioPredicciones | None, Depends(obtener_repositorio)],
    client_id: Annotated[str, Depends(obtener_client_id)],
) -> dict | JSONResponse:
    """Pronóstico de demanda por período, punto de venta y producto.

    **Entra:** el bloque ``history``, la ``granularity`` (``day``/``week``/``month``,
    diaria por defecto) y el ``horizon`` (períodos futuros, ``> 0`` y ``≤ 365``).
    **Sale:** por cada ``(date, store_id, product_id)`` futuro, ``forecast_demand``
    en unidades; ``model`` y ``metadata`` se leen del artefacto. ``interval_80`` está
    **diferido** (el modelo aún no lo produce, se omite hoy).

    **Modos de ejecución (Fase 3.4):** si ``len(history) ≤ SPC_ONLINE_MAX_ROWS`` se
    procesa **en línea** y se devuelve **200** con el resultado; si lo supera, se
    acepta como **trabajo por lote** y se devuelve **202** con un ``job_id`` (consulte
    estado y resultado en ``GET /jobs/{job_id}``). El motor pronostica a nivel diario;
    ``week``/``month`` agrega (suma) el resultado. El catálogo completo, en ``GET /catalog``.
    """
    return responder_segun_volumen(
        "sales", peticion, registro, jobs,
        repositorio=repositorio, canal="json", client_id=client_id,
    )
