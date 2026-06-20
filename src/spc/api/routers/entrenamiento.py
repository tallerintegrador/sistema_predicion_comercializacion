"""Router del **entrenamiento por cliente bajo demanda** (ADR-0013).

OPT-IN y DESACOPLADO de la predicción. Endpoints:

- ``POST /training/sales/excel`` — sube la plantilla Excel de SALES (misma validación
  strict que la predicción) y dispara un entrenamiento LOCAL asíncrono → **202** con
  ``job_id``. ``?source=`` elige los datos: ``merged`` (Excel + corpus, por defecto),
  ``excel`` (solo lo subido) o ``corpus`` (solo lo acumulado).
- ``GET /training/jobs/{job_id}`` — estado + fase honesta del trabajo.
- ``GET /training/jobs/{job_id}/result`` — el experimento medido (comparación + veredicto).
- ``GET /training/sales/status`` — ¿este cliente tiene modelo adoptado? ¿se sirve?
- ``POST /training/sales/serving`` — switch para servir (o no) con el modelo por cliente.

El experimento (entrenar candidato, comparar contra el congelado y un baseline, adoptar
solo si mejora) vive en ``spc.training.cliente``; aquí solo se orquesta el trabajo.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request, UploadFile, status
from fastapi.responses import JSONResponse

from spc.api.dependencies import (
    obtener_client_id,
    obtener_entrenamientos,
    obtener_registro,
    obtener_repositorio,
    obtener_resolutor_cliente,
)
from spc.api.errors import TrabajoNoEncontrado
from spc.api.ingest import lector
from spc.api.ingest.lector import ArchivoDemasiadoGrande
from spc.api.jobs_entrenamiento import GestorEntrenamientos, JobEntrenamiento
from spc.api.schemas.comunes import ErrorResponse
from spc.api.schemas.training import (
    ServingStatus,
    ServingSwitchRequest,
    TrainingAccepted,
    TrainingJobStatus,
    TrainingResult,
)
from spc.api.schemas.ventas import VentasRequest
from spc.config import Settings, excel_max_bytes
from spc.service.artefactos import RegistroArtefactos
from spc.service.modelo_cliente import ResolutorModeloCliente
from spc.service.repositorio import RepositorioPredicciones
from spc.training import almacen, cliente
from spc.utils.logging import get_logger

log = get_logger("api.entrenamiento")

router = APIRouter(tags=["training"])

FuenteDatos = Literal["merged", "excel", "corpus"]


def _client_models_dir(request: Request) -> Path:
    """Carpeta raíz de los artefactos por cliente (de ``app.state``, inyectable en tests)."""
    return Path(request.app.state.client_models_dir)


async def _leer_contenido(archivo: UploadFile) -> bytes:
    """Lee el .xlsx respetando el tope de tamaño (misma guarda que el canal Excel)."""
    tope = excel_max_bytes()
    datos = await archivo.read(tope + 1)
    if len(datos) > tope:
        mb = tope / (1024 * 1024)
        raise ArchivoDemasiadoGrande(f"El archivo supera el tamaño máximo permitido ({mb:.0f} MB).")
    return datos


def _estado(job: JobEntrenamiento) -> TrainingJobStatus:
    return TrainingJobStatus(
        job_id=job.id,
        status=job.status,
        phase=job.phase,
        domain=job.domain,
        client_id=job.client_id,
        source=job.source,
        created_at=job.created_at,
        finished_at=job.finished_at,
        result_url=f"/training/jobs/{job.id}/result",
    )


@router.post(
    "/training/sales/excel",
    response_model=TrainingAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Entrenar un modelo de SALES con los datos del cliente (opt-in)",
    responses={
        400: {"model": ErrorResponse, "description": "Regla de negocio incumplida"},
        413: {"model": ErrorResponse, "description": "Archivo demasiado grande"},
        422: {"model": ErrorResponse, "description": "Excel mal formado o fuera del contrato"},
        503: {"model": ErrorResponse, "description": "Ajuste por cliente deshabilitado"},
    },
)
async def entrenar_sales(
    request: Request,
    file: UploadFile,
    registro: Annotated[RegistroArtefactos, Depends(obtener_registro)],
    entrenamientos: Annotated[GestorEntrenamientos, Depends(obtener_entrenamientos)],
    repositorio: Annotated[RepositorioPredicciones | None, Depends(obtener_repositorio)],
    resolutor: Annotated[ResolutorModeloCliente | None, Depends(obtener_resolutor_cliente)],
    client_id: Annotated[str, Depends(obtener_client_id)],
    source: Annotated[FuenteDatos, Query(description="Origen de datos: merged|excel|corpus")] = "merged",
) -> TrainingAccepted:
    """Valida el Excel (strict), arma la historia y encola el experimento de entrenamiento.

    Devuelve **202** con un ``job_id`` (como el modo lote). El entrenamiento corre en un
    executor **separado** del de predicción; el modelo congelado no se toca y solo se
    adopta el modelo por cliente si supera al congelado en validación honesta.
    """
    contenido = await _leer_contenido(file)
    # Misma validación strict y mismo lector que la predicción por Excel.
    peticion: VentasRequest = lector.leer_peticion(contenido, "sales")  # type: ignore[assignment]
    history_excel = [h.model_dump(mode="json") for h in peticion.history]

    root = _client_models_dir(request)
    settings = Settings()
    job = entrenamientos.crear(client_id=client_id, source=source)

    def trabajo(reportar: Callable[[str], None]) -> dict:
        # Fusión de datos según la fuente elegida (corpus deduplicado + Excel).
        history_corpus = None
        if source in ("merged", "corpus") and repositorio is not None:
            df = repositorio.leer_corpus(client_id=client_id, dedup=True)
            from spc.service import corpus as corpus_mod

            history_corpus = corpus_mod.a_contrato(df)
        if source == "excel":
            history = list(history_excel)
        elif source == "corpus":
            history = list(history_corpus or [])
        else:  # merged
            history = cliente.fundir_historico(history_excel, history_corpus)

        resultado = cliente.entrenar_para_cliente(
            client_id=client_id,
            history=history,
            frozen=registro.regresion,
            settings=settings,
            root=root,
            progreso=reportar,
        )
        # Tras entrenar, refresca el cache de serving (puede haber nueva versión adoptada).
        if resolutor is not None:
            resolutor.invalidar(client_id)
        return resultado

    entrenamientos.enviar(job.id, trabajo)
    return TrainingAccepted(
        job_id=job.id,
        status=job.status,
        client_id=client_id,
        source=source,
        status_url=f"/training/jobs/{job.id}",
        result_url=f"/training/jobs/{job.id}/result",
    )


def _buscar(job_id: str, entrenamientos: GestorEntrenamientos) -> JobEntrenamiento:
    job = entrenamientos.obtener(job_id)
    if job is None:
        raise TrabajoNoEncontrado(f"No existe un trabajo de entrenamiento con id '{job_id}'.")
    return job


@router.get(
    "/training/jobs/{job_id}",
    response_model=TrainingJobStatus,
    response_model_exclude_none=True,
    summary="Estado de un trabajo de entrenamiento por cliente",
    responses={404: {"model": ErrorResponse, "description": "El job_id no existe"}},
)
def estado_entrenamiento(
    job_id: str,
    entrenamientos: Annotated[GestorEntrenamientos, Depends(obtener_entrenamientos)],
) -> TrainingJobStatus:
    """Estado + fase honesta (validating/training/evaluating) del entrenamiento."""
    return _estado(_buscar(job_id, entrenamientos))


@router.get(
    "/training/jobs/{job_id}/result",
    response_model=None,
    summary="Resultado (experimento medido) de un entrenamiento por cliente",
    responses={
        200: {"model": TrainingResult, "description": "Terminado: comparación + veredicto de adopción."},
        202: {"model": TrainingJobStatus, "description": "Aún en cola o entrenando (reintente)."},
        400: {"model": ErrorResponse, "description": "El entrenamiento falló por una regla de negocio."},
        404: {"model": ErrorResponse, "description": "El job_id no existe"},
    },
)
def resultado_entrenamiento(
    job_id: str,
    entrenamientos: Annotated[GestorEntrenamientos, Depends(obtener_entrenamientos)],
) -> JSONResponse:
    """Recupera el experimento medido honesto cuando el trabajo terminó.

    - ``done`` → **200** con la comparación (candidato vs congelado vs baseline + veredicto).
    - ``error`` → mismo cuerpo/código que daría la API en línea (p. ej. **400**).
    - ``queued``/``running`` → **202** con el estado/fase.
    """
    job = _buscar(job_id, entrenamientos)
    if job.status == "done":
        return JSONResponse(status_code=200, content=job.resultado)
    if job.status == "error":
        cuerpo = ErrorResponse(error=job.error_cuerpo)  # type: ignore[arg-type]
        return JSONResponse(
            status_code=job.error_status or 500, content=cuerpo.model_dump(exclude_none=True)
        )
    return JSONResponse(
        status_code=202, content=_estado(job).model_dump(mode="json", exclude_none=True)
    )


def _serving_status(root: Path, client_id: str) -> ServingStatus:
    est = almacen.estado(root, client_id)
    return ServingStatus(
        client_id=client_id,
        has_client_model=bool(est["versiones_entrenadas"]),
        serving_client_model=bool(est["serving_cliente"]),
        adopted_version=est["version_adoptada"],
        model_version=est["model_version"] if est["serving_cliente"] else None,
        trained_versions=est["versiones_entrenadas"],
        last_comparison=est["ultima_comparacion"],
    )


@router.get(
    "/training/sales/status",
    response_model=ServingStatus,
    response_model_exclude_none=True,
    summary="Estado del modelo por cliente (adopción y serving)",
    responses={503: {"model": ErrorResponse, "description": "Ajuste por cliente deshabilitado"}},
)
def estado_serving(
    request: Request,
    _entrenamientos: Annotated[GestorEntrenamientos, Depends(obtener_entrenamientos)],
    client_id: Annotated[str, Depends(obtener_client_id)],
) -> ServingStatus:
    """¿Este cliente tiene modelo entrenado/adoptado? ¿Se le está sirviendo? Última comparación."""
    return _serving_status(_client_models_dir(request), client_id)


@router.post(
    "/training/sales/serving",
    response_model=ServingStatus,
    response_model_exclude_none=True,
    summary="Activar/desactivar servir con el modelo por cliente (switch)",
    responses={503: {"model": ErrorResponse, "description": "Ajuste por cliente deshabilitado"}},
)
def switch_serving(
    request: Request,
    body: ServingSwitchRequest,
    _entrenamientos: Annotated[GestorEntrenamientos, Depends(obtener_entrenamientos)],
    resolutor: Annotated[ResolutorModeloCliente | None, Depends(obtener_resolutor_cliente)],
    client_id: Annotated[str, Depends(obtener_client_id)],
) -> ServingStatus:
    """Conmuta el serving por cliente (reversible). El default congelado sigue disponible."""
    root = _client_models_dir(request)
    almacen.set_servir(root, client_id, body.enabled)
    if resolutor is not None:
        resolutor.invalidar(client_id)
    return _serving_status(root, client_id)
