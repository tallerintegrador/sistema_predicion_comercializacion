"""Canal **Excel** — descarga de plantilla y carga de datos por dominio (Fase 3.3).

Por cada dominio expone dos endpoints:

- ``GET /{dominio}/template`` — descarga el ``.xlsx`` generado desde el contrato.
- ``POST /{dominio}/excel`` — sube el ``.xlsx``: convierte tipos explícitamente, valida
  con los **mismos modelos strict** y, tras validar, pasa por el **mismo ruteo por
  volumen** que el JSON (``spc.api.ruteo``). La respuesta es idéntica a la del JSON
  equivalente: **200** con el resultado si el Excel es chico, o **202** con un ``job_id``
  si supera ``SPC_ONLINE_MAX_ROWS`` filas (Fase 3.4).

El camino JSON (``POST /sales``, ``/purchases``, ``/inventory``) queda **intacto**: aquí
no hay lógica de predicción nueva, solo una puerta de entrada distinta. El tope de
tamaño del archivo (``SPC_EXCEL_MAX_BYTES``) es una guarda anti-abuso; la frontera real
en línea/lote se mide en **filas**, no en bytes.
"""

from __future__ import annotations

from typing import Annotated, cast

from fastapi import APIRouter, Depends, Form, UploadFile
from fastapi.responses import JSONResponse, Response

from spc.api.dependencies import (
    obtener_client_id,
    obtener_jobs,
    obtener_registro,
    obtener_repositorio,
    obtener_resolutor_cliente,
)
from spc.api.ingest import lector, plantilla
from spc.api.ingest.esquema_excel import plantilla_de
from spc.api.ingest.lector import ArchivoDemasiadoGrande
from spc.api.jobs import GestorTrabajos
from spc.api.ruteo import responder_segun_volumen
from spc.api.schemas.almacen import AlmacenRequest, AlmacenResponse
from spc.api.schemas.auth import SessionUser
from spc.api.schemas.compras import ComprasRequest, ComprasResponse
from spc.api.schemas.comunes import ErrorResponse
from spc.api.schemas.jobs import JobAccepted
from spc.api.schemas.ventas import VentasRequest, VentasResponse
from spc.api.seguridad import requiere
from spc.config import excel_max_bytes
from spc.service.artefactos import RegistroArtefactos
from spc.service.modelo_cliente import ResolutorModeloCliente
from spc.service.repositorio import RepositorioPredicciones

router = APIRouter(tags=["excel"])

_XLSX_MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

_RESPUESTAS_CARGA = {
    202: {"model": JobAccepted, "description": "Excel grande: aceptado como trabajo por lote"},
    400: {"model": ErrorResponse, "description": "Regla de negocio incumplida"},
    413: {"model": ErrorResponse, "description": "Archivo demasiado grande"},
    422: {"model": ErrorResponse, "description": "Excel mal formado o fuera del contrato"},
}


def _descarga(dominio: str) -> Response:
    """Construye la respuesta de descarga del ``.xlsx`` de un dominio."""
    contenido = plantilla.generar_bytes(dominio)
    nombre = plantilla_de(dominio).archivo
    return Response(
        content=contenido,
        media_type=_XLSX_MEDIA,
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )


async def _leer_contenido(archivo: UploadFile) -> bytes:
    """Lee el archivo subido respetando el tope de tamaño (sin cargar de más)."""
    tope = excel_max_bytes()
    datos = await archivo.read(tope + 1)
    if len(datos) > tope:
        mb = tope / (1024 * 1024)
        raise ArchivoDemasiadoGrande(
            f"El archivo supera el tamaño máximo permitido ({mb:.0f} MB)."
        )
    return datos


# ---------------------------------------------------------------------------
# SALES
# ---------------------------------------------------------------------------
@router.get("/sales/template", summary="Descargar plantilla Excel de SALES")
def plantilla_sales(
    _auth: Annotated[SessionUser | None, Depends(requiere("module:sales", "action:template_download"))],
) -> Response:
    """Descarga ``sales_template.xlsx`` (solo datos: hojas history + instructions)."""
    return _descarga("sales")


@router.post(
    "/sales/excel",
    response_model=VentasResponse,
    response_model_exclude_none=True,
    summary="Pronóstico de demanda a partir de un Excel",
    responses=_RESPUESTAS_CARGA,
)
async def cargar_sales(
    file: UploadFile,
    registro: Annotated[RegistroArtefactos, Depends(obtener_registro)],
    jobs: Annotated[GestorTrabajos, Depends(obtener_jobs)],
    repositorio: Annotated[RepositorioPredicciones | None, Depends(obtener_repositorio)],
    resolutor: Annotated[ResolutorModeloCliente | None, Depends(obtener_resolutor_cliente)],
    client_id: Annotated[str, Depends(obtener_client_id)],
    _auth: Annotated[SessionUser | None, Depends(requiere("module:sales", "action:template_upload"))],
    horizon: Annotated[int, Form(description="Períodos futuros a pronosticar (> 0).")],
    granularity: Annotated[str, Form(description="Granularidad: day/week/month.")] = "day",
) -> dict | JSONResponse:
    """Sube el Excel de SALES (solo datos) y pronostica con la configuración de pantalla.

    El archivo trae únicamente el bloque ``history``; la ``granularity`` y el
    ``horizon`` llegan como campos de formulario desde la petición en pantalla, que es
    la **única fuente** de la configuración del pronóstico (ADR-0022). Tipos y reglas se
    validan con el **mismo modelo strict** que el JSON; el resultado es idéntico al de
    ``POST /sales`` con esa configuración.
    """
    contenido = await _leer_contenido(file)
    peticion = cast(
        VentasRequest,
        lector.leer_peticion(
            contenido, "sales", extra={"granularity": granularity, "horizon": horizon}
        ),
    )
    return responder_segun_volumen(
        "sales", peticion, registro, jobs,
        repositorio=repositorio, resolutor=resolutor, canal="excel", client_id=client_id,
    )


# ---------------------------------------------------------------------------
# PURCHASES
# ---------------------------------------------------------------------------
@router.get("/purchases/template", summary="Descargar plantilla Excel de PURCHASES")
def plantilla_purchases(
    _auth: Annotated[SessionUser | None, Depends(requiere("module:purchases", "action:template_download"))],
) -> Response:
    """Descarga ``purchases_template.xlsx`` (history + replenishment_params + instructions)."""
    return _descarga("purchases")


@router.post(
    "/purchases/excel",
    response_model=ComprasResponse,
    response_model_exclude_none=True,
    summary="Reposición sugerida a partir de un Excel",
    responses=_RESPUESTAS_CARGA,
)
async def cargar_purchases(
    file: UploadFile,
    registro: Annotated[RegistroArtefactos, Depends(obtener_registro)],
    jobs: Annotated[GestorTrabajos, Depends(obtener_jobs)],
    repositorio: Annotated[RepositorioPredicciones | None, Depends(obtener_repositorio)],
    client_id: Annotated[str, Depends(obtener_client_id)],
    _auth: Annotated[SessionUser | None, Depends(requiere("module:purchases", "action:template_upload"))],
) -> dict | JSONResponse:
    """Sube el Excel de PURCHASES y devuelve el mismo resultado que ``POST /purchases``."""
    contenido = await _leer_contenido(file)
    peticion = cast(ComprasRequest, lector.leer_peticion(contenido, "purchases"))
    return responder_segun_volumen(
        "purchases", peticion, registro, jobs,
        repositorio=repositorio, canal="excel", client_id=client_id,
    )


# ---------------------------------------------------------------------------
# INVENTORY
# ---------------------------------------------------------------------------
@router.get("/inventory/template", summary="Descargar plantilla Excel de INVENTORY")
def plantilla_inventory(
    _auth: Annotated[SessionUser | None, Depends(requiere("module:inventory", "action:template_download"))],
) -> Response:
    """Descarga ``inventory_template.xlsx`` (history + inventory_status + instructions)."""
    return _descarga("inventory")


@router.post(
    "/inventory/excel",
    response_model=AlmacenResponse,
    response_model_exclude_none=True,
    summary="Riesgo de quiebre y stock a partir de un Excel",
    responses=_RESPUESTAS_CARGA,
)
async def cargar_inventory(
    file: UploadFile,
    registro: Annotated[RegistroArtefactos, Depends(obtener_registro)],
    jobs: Annotated[GestorTrabajos, Depends(obtener_jobs)],
    repositorio: Annotated[RepositorioPredicciones | None, Depends(obtener_repositorio)],
    client_id: Annotated[str, Depends(obtener_client_id)],
    _auth: Annotated[SessionUser | None, Depends(requiere("module:inventory", "action:template_upload"))],
) -> dict | JSONResponse:
    """Sube el Excel de INVENTORY y devuelve el mismo resultado que ``POST /inventory``."""
    contenido = await _leer_contenido(file)
    peticion = cast(AlmacenRequest, lector.leer_peticion(contenido, "inventory"))
    return responder_segun_volumen(
        "inventory", peticion, registro, jobs,
        repositorio=repositorio, canal="excel", client_id=client_id,
    )
