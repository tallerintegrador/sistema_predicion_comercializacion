"""Router del **modo por lote** — consulta de estado y resultado de un trabajo.

El *envío* no vive aquí: lo hace el mismo endpoint de predicción
(``POST /sales`` …), que al superar el umbral de filas devuelve **202** con un
``job_id``. Este router expone las dos consultas:

- ``GET /jobs/{job_id}`` — estado del trabajo (``JobStatus``).
- ``GET /jobs/{job_id}/result`` — resultado cuando está listo. Devuelve el **mismo
  cuerpo y código** que daría la petición en línea: **200** con la respuesta del
  dominio si terminó bien; **400** (u otro) con el cuerpo de error uniforme si una
  regla de negocio falló; **202** si aún se está procesando.

Un ``job_id`` inexistente devuelve **404** (``TrabajoNoEncontrado``), con el mismo
cuerpo de error que el resto de la API.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from spc.api.dependencies import obtener_jobs
from spc.api.errors import TrabajoNoEncontrado
from spc.api.jobs import GestorTrabajos, Job
from spc.api.schemas.comunes import ErrorResponse
from spc.api.schemas.jobs import JobStatus

router = APIRouter(tags=["batch"])

_RESPUESTAS_TRABAJO = {404: {"model": ErrorResponse, "description": "El job_id no existe"}}


def _estado(job: Job) -> JobStatus:
    """Proyecta el ``Job`` interno al esquema público ``JobStatus``."""
    return JobStatus(
        job_id=job.id,
        status=job.status,
        domain=job.domain,
        rows=job.rows,
        created_at=job.created_at,
        finished_at=job.finished_at,
        result_url=f"/jobs/{job.id}/result",
    )


def _buscar(job_id: str, jobs: GestorTrabajos) -> Job:
    """Devuelve el trabajo o lanza ``TrabajoNoEncontrado`` (→ 404) si no existe."""
    job = jobs.obtener(job_id)
    if job is None:
        raise TrabajoNoEncontrado(f"No existe un trabajo por lote con id '{job_id}'.")
    return job


@router.get(
    "/jobs/{job_id}",
    response_model=JobStatus,
    response_model_exclude_none=True,
    summary="Estado de un trabajo por lote",
    responses=_RESPUESTAS_TRABAJO,
)
def estado_trabajo(
    job_id: str,
    jobs: Annotated[GestorTrabajos, Depends(obtener_jobs)],
) -> JobStatus:
    """Devuelve el estado del trabajo: ``queued``/``running``/``done``/``error``."""
    return _estado(_buscar(job_id, jobs))


@router.get(
    "/jobs/{job_id}/result",
    response_model=None,
    summary="Resultado de un trabajo por lote",
    responses={
        200: {"description": "Trabajo terminado: el MISMO cuerpo que la respuesta en línea."},
        202: {"model": JobStatus, "description": "Aún en cola o procesando (reintente)."},
        400: {"model": ErrorResponse, "description": "El trabajo falló por una regla de negocio"},
        404: {"model": ErrorResponse, "description": "El job_id no existe"},
    },
)
def resultado_trabajo(
    job_id: str,
    jobs: Annotated[GestorTrabajos, Depends(obtener_jobs)],
) -> JSONResponse:
    """Recupera el resultado del trabajo, fiel a "el mismo dato da el mismo resultado".

    - ``done`` → **200** con la respuesta del dominio (idéntica a la del modo en línea).
    - ``error`` → el **mismo cuerpo y código** que daría la petición síncrona
      (p. ej. **400** ``invalid_request`` para una regla de negocio incumplida).
    - ``queued``/``running`` → **202** con el estado (el resultado aún no está listo).
    """
    job = _buscar(job_id, jobs)

    if job.status == "done":
        return JSONResponse(status_code=200, content=job.resultado)
    if job.status == "error":
        cuerpo = ErrorResponse(error=job.error_cuerpo)  # type: ignore[arg-type]
        return JSONResponse(
            status_code=job.error_status or 500,
            content=cuerpo.model_dump(exclude_none=True),
        )
    # queued / running: todavía no hay resultado.
    return JSONResponse(
        status_code=202,
        content=_estado(job).model_dump(mode="json", exclude_none=True),
    )
