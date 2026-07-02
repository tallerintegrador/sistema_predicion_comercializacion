"""Router de **predicción agnóstica auto-entrenada** (ADR-0023).

Tres endpoints bajo ``/auto`` que aceptan el contrato agnóstico (`schema` + `rows`):
entrenan el algoritmo ganador al vuelo sobre la data declarada y predicen/mejoran.
A diferencia de ``/sales``·``/inventory``·``/purchases`` (esquema retail fijo), aquí el
cliente trae **columnas arbitrarias** de su propio rubro.

El entrenamiento corre **en línea** (síncrono): es la semántica "auto-aprende y predice
en una llamada". El modelo se cachea por (cliente, esquema, datos) para no reentrenar si
la misma data vuelve; si la data cambia, se reentrena solo (`spc.service.cache_agnostico`).
"""

from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Form, UploadFile
from fastapi.responses import Response
from pydantic import ValidationError

from spc.api.dependencies import (
    obtener_cache_agnostico,
    obtener_client_id,
    obtener_corpus_opcional,
)
from spc.api.ingest import agnostico_excel
from spc.api.ingest.errores_excel import ArchivoDemasiadoGrande
from spc.api.schemas.agnostico import (
    AutoInventoryRequest,
    AutoInventoryResponse,
    AutoPurchasesRequest,
    AutoPurchasesResponse,
    AutoSalesRequest,
    AutoSalesResponse,
    AutoTemplateRequest,
    SchemaSpec,
)
from spc.api.schemas.auth import SessionUser
from spc.api.schemas.comunes import ErrorResponse
from spc.api.seguridad import requiere
from spc.config import excel_max_bytes
from spc.service import agnostico as servicio
from spc.service import reentrenamiento
from spc.service.cache_agnostico import CacheModelosAgnosticos
from spc.service.errores import SolicitudInvalida
from spc.service.repositorio_corpus import RepositorioCorpus

router = APIRouter(prefix="/auto", tags=["AUTO"])

CorpusOpcDep = Annotated[RepositorioCorpus | None, Depends(obtener_corpus_opcional)]


def _acumular_auto(corpus: RepositorioCorpus | None, peticion: Any, campo: str, client_id: str) -> None:
    """Enganche best-effort del corpus para ``/auto/*`` (serie/fecha declaradas por el cliente)."""
    spec = peticion.schema_spec
    reentrenamiento.acumular_declarado(
        corpus,
        tenant_id=client_id,
        dominio=f"auto_{campo}",
        rows=peticion.rows,
        series_keys=list(spec.series_keys),
        date_col=spec.date,
        channel="json",
        schema_spec=spec.model_dump(mode="json"),
    )

_RESPUESTAS_ERR = {
    400: {"model": ErrorResponse, "description": "Esquema/datos inválidos o serie sin histórico"},
    422: {"model": ErrorResponse, "description": "Entrada mal formada"},
}
_XLSX_MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


async def _leer_contenido(file: UploadFile) -> bytes:
    """Lee el archivo subido respetando el tope de tamaño (anti-abuso)."""
    tope = excel_max_bytes()
    datos = await file.read(tope + 1)
    if len(datos) > tope:
        raise ArchivoDemasiadoGrande(
            f"El archivo supera el tamaño máximo permitido ({tope / (1024 * 1024):.0f} MB)."
        )
    return datos


def _parsear_schema(schema: str) -> SchemaSpec:
    """Valida el esquema declarado que llega como campo de formulario (JSON)."""
    try:
        return SchemaSpec.model_validate_json(schema)
    except ValidationError as exc:
        raise SolicitudInvalida(f"El esquema declarado no es válido: {exc.errors()[0]['msg']}.") from exc


def _parsear_json_lista(texto: str | None, campo: str) -> list[dict[str, Any]]:
    """Parsea un campo de formulario JSON que debe ser una lista de objetos."""
    if not texto:
        return []
    try:
        valor = json.loads(texto)
    except json.JSONDecodeError as exc:
        raise SolicitudInvalida(f"El campo '{campo}' no es JSON válido.") from exc
    if not isinstance(valor, list):
        raise SolicitudInvalida(f"El campo '{campo}' debe ser una lista.")
    return valor


def _plantilla(schema: SchemaSpec, dominio: str) -> Response:
    contenido = agnostico_excel.generar_plantilla(schema, dominio)
    nombre = f"plantilla_auto_{dominio}.xlsx"
    return Response(
        content=contenido,
        media_type=_XLSX_MEDIA,
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )


@router.post(
    "/sales",
    response_model=AutoSalesResponse,
    response_model_exclude_none=True,
    summary="Pronóstico de demanda auto-entrenado (esquema declarado por el cliente)",
    responses=_RESPUESTAS_ERR,
)
def auto_sales(
    peticion: AutoSalesRequest,
    cache: Annotated[CacheModelosAgnosticos, Depends(obtener_cache_agnostico)],
    client_id: Annotated[str, Depends(obtener_client_id)],
    corpus: CorpusOpcDep,
    _auth: Annotated[SessionUser | None, Depends(requiere("module:sales", "action:forecast"))],
) -> dict:
    """Entrena el ganador sobre ``rows`` (según ``schema``) y pronostica ``horizon`` períodos.

    **Entra:** ``schema`` (target, date, series_keys, features), ``rows`` (columnas libres),
    ``horizon`` y ``granularity``; opcional ``future`` con las features conocidas-a-futuro.
    **Sale:** ``forecast`` por (período, serie) + ``training`` (algoritmo ganador, métricas
    honestas de la ventana de prueba, candidatos).
    """
    _acumular_auto(corpus, peticion, "sales", client_id)
    return servicio.pronosticar_ventas(peticion, client_id=client_id, cache=cache)


@router.post(
    "/inventory",
    response_model=AutoInventoryResponse,
    response_model_exclude_none=True,
    summary="Riesgo de quiebre y stock auto-entrenado (esquema declarado)",
    responses=_RESPUESTAS_ERR,
)
def auto_inventory(
    peticion: AutoInventoryRequest,
    cache: Annotated[CacheModelosAgnosticos, Depends(obtener_cache_agnostico)],
    client_id: Annotated[str, Depends(obtener_client_id)],
    corpus: CorpusOpcDep,
    _auth: Annotated[SessionUser | None, Depends(requiere("module:inventory", "action:forecast"))],
) -> dict:
    """Deriva 'demanda alta' (target > P{q} de su serie), entrena el clasificador y evalúa stock.

    **Entra:** ``schema``, ``rows`` y ``items`` (claves de serie + ``current_stock`` y,
    opcional, ``lead_time_days``); ``high_demand_quantile`` (default 0.75).
    **Sale:** ``alerts`` por serie (clase de demanda, probabilidad, riesgo de quiebre,
    stock recomendado/seguridad, segmento de volumen) + ``training``.
    """
    _acumular_auto(corpus, peticion, "inventory", client_id)
    return servicio.alertas_inventario(peticion, client_id=client_id, cache=cache)


@router.post(
    "/purchases",
    response_model=AutoPurchasesResponse,
    response_model_exclude_none=True,
    summary="Reposición sugerida auto-entrenada (esquema declarado)",
    responses=_RESPUESTAS_ERR,
)
def auto_purchases(
    peticion: AutoPurchasesRequest,
    cache: Annotated[CacheModelosAgnosticos, Depends(obtener_cache_agnostico)],
    client_id: Annotated[str, Depends(obtener_client_id)],
    corpus: CorpusOpcDep,
    _auth: Annotated[SessionUser | None, Depends(requiere("module:purchases", "action:forecast"))],
) -> dict:
    """Entrena el ganador, pronostica y deriva la reposición por serie.

    **Entra:** ``schema``, ``rows`` y ``items`` (claves de serie + ``current_stock``,
    ``lead_time_days``, ``target_coverage_days``).
    **Sale:** ``recommendation`` por serie (demanda esperada, punto de reorden, cantidad
    a reponer) + ``training``.
    """
    _acumular_auto(corpus, peticion, "purchases", client_id)
    return servicio.reponer_compras(peticion, client_id=client_id, cache=cache)


# ===========================================================================
# Canal Excel: plantilla a medida del esquema + carga de datos
# ===========================================================================
@router.post("/sales/template", summary="Descargar plantilla Excel a medida (ventas)")
def plantilla_sales(
    peticion: AutoTemplateRequest,
    _auth: Annotated[SessionUser | None, Depends(requiere("module:sales", "action:forecast"))],
) -> Response:
    """Genera un ``.xlsx`` con las columnas de TU esquema (objetivo, fecha, series, features)."""
    return _plantilla(peticion.schema_spec, "sales")


@router.post("/inventory/template", summary="Descargar plantilla Excel a medida (almacén)")
def plantilla_inventory(
    peticion: AutoTemplateRequest,
    _auth: Annotated[SessionUser | None, Depends(requiere("module:inventory", "action:forecast"))],
) -> Response:
    """Plantilla con la hoja de datos + la hoja 'items' (stock y lead time por serie)."""
    return _plantilla(peticion.schema_spec, "inventory")


@router.post("/purchases/template", summary="Descargar plantilla Excel a medida (compras)")
def plantilla_purchases(
    peticion: AutoTemplateRequest,
    _auth: Annotated[SessionUser | None, Depends(requiere("module:purchases", "action:forecast"))],
) -> Response:
    """Plantilla con datos + 'items' (stock, lead time y días de cobertura por serie)."""
    return _plantilla(peticion.schema_spec, "purchases")


@router.post(
    "/sales/excel",
    response_model=AutoSalesResponse,
    response_model_exclude_none=True,
    summary="Pronóstico auto-entrenado a partir de un Excel",
    responses=_RESPUESTAS_ERR,
)
async def auto_sales_excel(
    file: UploadFile,
    cache: Annotated[CacheModelosAgnosticos, Depends(obtener_cache_agnostico)],
    client_id: Annotated[str, Depends(obtener_client_id)],
    _auth: Annotated[SessionUser | None, Depends(requiere("module:sales", "action:forecast"))],
    esquema: Annotated[str, Form(alias="schema", description="Esquema declarado (JSON).")],
    horizon: Annotated[int, Form(description="Períodos futuros a pronosticar (> 0).")],
    granularity: Annotated[str, Form(description="Granularidad: day/week/month.")] = "day",
    future: Annotated[str | None, Form(description="Filas futuras conocidas (JSON, opcional).")] = None,
) -> dict:
    """Sube el Excel con tus datos (hoja 'datos') y pronostica con el esquema de pantalla."""
    contenido = await _leer_contenido(file)
    schema_obj = _parsear_schema(esquema)
    rows, _ = agnostico_excel.leer_libro(contenido)
    peticion = AutoSalesRequest(
        schema_spec=schema_obj, horizon=horizon, granularity=granularity,  # type: ignore[arg-type]
        rows=rows, future=_parsear_json_lista(future, "future") or None,
    )
    return servicio.pronosticar_ventas(peticion, client_id=client_id, cache=cache)


@router.post(
    "/inventory/excel",
    response_model=AutoInventoryResponse,
    response_model_exclude_none=True,
    summary="Riesgo de quiebre y stock auto-entrenado a partir de un Excel",
    responses=_RESPUESTAS_ERR,
)
async def auto_inventory_excel(
    file: UploadFile,
    cache: Annotated[CacheModelosAgnosticos, Depends(obtener_cache_agnostico)],
    client_id: Annotated[str, Depends(obtener_client_id)],
    _auth: Annotated[SessionUser | None, Depends(requiere("module:inventory", "action:forecast"))],
    esquema: Annotated[str, Form(alias="schema", description="Esquema declarado (JSON).")],
    items: Annotated[str | None, Form(description="Items por serie (JSON). Si se omite, usa la hoja 'items'.")] = None,
    high_demand_quantile: Annotated[float, Form(description="Cuantil de demanda alta.")] = 0.75,
) -> dict:
    """Sube el Excel (hojas 'datos' + 'items') y evalúa riesgo de quiebre/stock."""
    contenido = await _leer_contenido(file)
    schema_obj = _parsear_schema(esquema)
    rows, items_xlsx = agnostico_excel.leer_libro(contenido)
    items_final = _parsear_json_lista(items, "items") or items_xlsx
    peticion = AutoInventoryRequest(
        schema_spec=schema_obj, rows=rows, items=items_final, high_demand_quantile=high_demand_quantile,
    )
    return servicio.alertas_inventario(peticion, client_id=client_id, cache=cache)


@router.post(
    "/purchases/excel",
    response_model=AutoPurchasesResponse,
    response_model_exclude_none=True,
    summary="Reposición auto-entrenada a partir de un Excel",
    responses=_RESPUESTAS_ERR,
)
async def auto_purchases_excel(
    file: UploadFile,
    cache: Annotated[CacheModelosAgnosticos, Depends(obtener_cache_agnostico)],
    client_id: Annotated[str, Depends(obtener_client_id)],
    _auth: Annotated[SessionUser | None, Depends(requiere("module:purchases", "action:forecast"))],
    esquema: Annotated[str, Form(alias="schema", description="Esquema declarado (JSON).")],
    items: Annotated[str | None, Form(description="Items por serie (JSON). Si se omite, usa la hoja 'items'.")] = None,
) -> dict:
    """Sube el Excel (hojas 'datos' + 'items') y deriva la reposición por serie."""
    contenido = await _leer_contenido(file)
    schema_obj = _parsear_schema(esquema)
    rows, items_xlsx = agnostico_excel.leer_libro(contenido)
    items_final = _parsear_json_lista(items, "items") or items_xlsx
    peticion = AutoPurchasesRequest(schema_spec=schema_obj, rows=rows, items=items_final)
    return servicio.reponer_compras(peticion, client_id=client_id, cache=cache)
