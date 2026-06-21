"""Construye el **catálogo de predicciones** derivándolo de los esquemas reales.

La pieza clave de honestidad: las **entradas** y **salidas** que el catálogo declara
salen de los esquemas Pydantic de cada endpoint (`*Request` / `*Response`), no de
texto a mano. Si mañana cambia un campo de respuesta, el catálogo cambia con él y la
prueba de consistencia (tests/api) avisa si algo no calza.

`CONTRACT_VERSION` es la **única** fuente de la versión del contrato en el código
(alineada con el encabezado de `docs/contrato_datos.md`). Es distinta de la versión
de la *app* (`FastAPI(version=...)`), que versiona el despliegue, no el contrato.
"""

from __future__ import annotations

import types
import typing
from dataclasses import dataclass, field
from datetime import date as Date
from typing import Any

import annotated_types
from pydantic import BaseModel

from spc.api.schemas.almacen import AlertaItem, AlmacenRequest, AlmacenResponse, MetadatosAlmacen
from spc.api.schemas.catalog import (
    Availability,
    CatalogField,
    CatalogInput,
    CatalogResponse,
    DomainCatalog,
    ForecastDimension,
    ForecastTypology,
    GranularityOption,
    HorizonRange,
    OutputGroup,
    QueryOptions,
)
from spc.api.schemas.comunes import HistoricoItem
from spc.api.schemas.compras import (
    ComprasRequest,
    ComprasResponse,
    MetadatosCompras,
    RecomendacionItem,
)
from spc.api.schemas.ventas import (
    Granularidad,
    MetadatosVentas,
    PronosticoItem,
    VentasRequest,
    VentasResponse,
)

# Única fuente de la versión del contrato en el código (ver encabezado del contrato).
CONTRACT_VERSION = "1.0.1"

# Canales y modos: honestidad sobre lo disponible HOY vs. lo PLANIFICADO (contrato §7).
CHANNELS = [
    Availability(name="json", status="available", description="Entrada y salida en JSON (en línea)."),
    Availability(
        name="excel",
        status="available",
        description=(
            "Carga de los mismos campos por archivo Excel (Fase 3.3). Descargue la "
            "plantilla en GET /{dominio}/template y súbala en POST /{dominio}/excel; "
            "pasa por la misma validación y predicción que el JSON."
        ),
    ),
]
MODES = [
    Availability(name="online", status="available", description="Una petición en línea (síncrona)."),
    Availability(
        name="batch",
        status="available",
        description=(
            "Lote asíncrono para envíos grandes (Fase 3.4). El MISMO endpoint decide por "
            "número de filas (SPC_ONLINE_MAX_ROWS): si se supera, devuelve un job_id (202) y "
            "procesa en segundo plano con el modelo CONGELADO (opción A), reutilizando el "
            "mismo flujo de predicción que el modo en línea. Estado y resultado en "
            "GET /jobs/{job_id}. Almacén in-process (un solo proceso; ver ADR-0008)."
        ),
    ),
    Availability(
        name="client_adjustment",
        status="available",
        description=(
            "Ajuste del modelo por cliente BAJO DEMANDA (opt-in, ADR-0013). El cliente sube su "
            "plantilla Excel de SALES y dispara un entrenamiento LOCAL asíncrono (POST "
            "/training/sales/excel → job_id; estado en GET /training/jobs/{id}). Corre un "
            "experimento medido: compara el modelo por cliente contra el CONGELADO y un baseline "
            "ingenuo en validación temporal honesta (WAPE recursivo), y solo ADOPTA el modelo por "
            "cliente si supera al congelado; 'no mejora' se reporta y se sigue con el congelado. "
            "El modelo por cliente se sirve solo a ESE cliente (switch en POST /training/sales/"
            "serving). El camino por defecto (congelado) queda intacto para quien no opta. Hoy "
            "cubre SALES (regresión); el lote sigue usando el congelado (opción A)."
        ),
    ),
]


# ---------------------------------------------------------------------------
# Helpers de derivación desde los esquemas Pydantic
# ---------------------------------------------------------------------------
_BASES = {str: "str", int: "int", float: "float", bool: "bool", Date: "date"}


def _es_opcional(anotacion: Any) -> bool:
    """True si la anotación admite ``None`` (campo que puede **omitirse** en la salida).

    Con ``response_model_exclude_none=True``, un valor ``None`` se excluye de la
    respuesta; por eso "admite None" equivale a "puede estar ausente".
    """
    origen = typing.get_origin(anotacion)
    return origen in (typing.Union, types.UnionType) and type(None) in typing.get_args(anotacion)


def _nombre_tipo(anotacion: Any) -> str:
    """Nombre legible del tipo de un campo (sin ``NoneType`` ni ruido de typing)."""
    origen = typing.get_origin(anotacion)
    if origen in (typing.Union, types.UnionType):
        partes = [_nombre_tipo(a) for a in typing.get_args(anotacion) if a is not type(None)]
        return " | ".join(partes)
    if origen in (list, typing.List):  # noqa: UP006 - get_origin puede devolver list o typing.List
        args = typing.get_args(anotacion)
        return f"list[{_nombre_tipo(args[0]) if args else 'Any'}]"
    if origen is typing.Literal:
        return " | ".join(str(v) for v in typing.get_args(anotacion))
    if anotacion in _BASES:
        return _BASES[anotacion]
    return getattr(anotacion, "__name__", str(anotacion))


def _campos_salida(modelo: type[BaseModel], *, excluir: tuple[str, ...] = ()) -> list[CatalogField]:
    """Deriva los campos de **salida** de un modelo de respuesta.

    ``required`` = "la API siempre lo entrega" = el tipo **no** admite ``None``.
    """
    return [
        CatalogField(
            name=nombre,
            type=_nombre_tipo(info.annotation),
            required=not _es_opcional(info.annotation),
            description=info.description,
        )
        for nombre, info in modelo.model_fields.items()
        if nombre not in excluir
    ]


def _entradas(modelo: type[BaseModel]) -> list[CatalogInput]:
    """Deriva las **entradas** de nivel superior de un modelo de petición."""
    return [
        CatalogInput(
            name=nombre,
            type=_nombre_tipo(info.annotation),
            required=info.is_required(),
            description=info.description,
        )
        for nombre, info in modelo.model_fields.items()
    ]


# ---------------------------------------------------------------------------
# Opciones de consulta de la UI (R1 tipologías, R2 dimensiones, granularidad, horizonte)
#
# Honestidad por construcción, igual que inputs/outputs: cada opción se DERIVA del
# contrato y de las capacidades de agregación del servicio, nunca del motor de ML.
#   • granularidades: del Literal ``Granularidad`` del contrato (ventas.py).
#   • horizonte: de las restricciones (gt/le) del campo ``horizon`` de VentasRequest.
#   • dimensiones: de las columnas identificadoras del bloque ``history`` (comunes.py).
#   • tipologías: reflejan lo que el servicio puede agregar (serie temporal / por dimensión).
# La prueba anti-desync (tests/api/test_catalog.py) falla si alguna deja de calzar.
# ---------------------------------------------------------------------------

# Etiquetas en español de cada granularidad del contrato (en inglés -> formal en español).
_GRANULARITY_LABELS: dict[str, str] = {"day": "Día", "week": "Semana", "month": "Mes"}

# Sugerencia inicial del horizonte para la UI. El campo es OBLIGATORIO en el contrato (sin
# default): este valor solo da un punto de partida cómodo al formulario, acotado al rango real.
_HORIZON_DEFAULT_SUGGESTION = 7

# Tipologías de pronóstico que ofrece SALES (R1). No son modelos distintos: son formas de
# AGREGAR/PRESENTAR el mismo pronóstico por serie que produce el motor.
_SALES_TYPOLOGIES: list[ForecastTypology] = [
    ForecastTypology(
        name="time_series",
        label="Serie temporal (por período)",
        requires_dimension=False,
        description="Demanda total por período, sumando todas las series del histórico.",
    ),
    ForecastTypology(
        name="by_dimension",
        label="Por dimensión",
        requires_dimension=True,
        description="Desglosa el pronóstico por la columna elegida (p. ej. por tienda o por producto).",
    ),
]

# Columnas identificadoras del bloque ``history`` por las que tiene sentido desglosar/filtrar
# (R2). Los nombres deben existir en ``HistoricoItem``; la prueba anti-desync lo verifica, de
# modo que un cambio del contrato (renombrar/eliminar la columna) rompe la prueba.
_SALES_DIMENSIONS: list[ForecastDimension] = [
    ForecastDimension(
        name="store_id", label="Tienda", description="Local, sucursal o punto de venta."
    ),
    ForecastDimension(
        name="product_id",
        label="Producto / Categoría",
        description="Producto o familia/categoría.",
    ),
]


def _rango_horizonte(modelo: type[BaseModel], campo: str) -> HorizonRange:
    """Deriva ``min``/``max`` del horizonte de las restricciones del campo (gt/ge, le/lt).

    Lee los metadatos de ``annotated_types`` que Pydantic guarda en el campo (``Field(gt=0,
    le=365)`` → ``Gt(0)`` y ``Le(365)``), de modo que el rango de la UI **es** el del contrato:
    si mañana cambia el ``le``, el catálogo cambia con él.
    """
    info = modelo.model_fields[campo]
    minimo, maximo = 1, None
    for restriccion in info.metadata:
        if isinstance(restriccion, annotated_types.Gt):
            minimo = int(restriccion.gt) + 1
        elif isinstance(restriccion, annotated_types.Ge):
            minimo = int(restriccion.ge)
        elif isinstance(restriccion, annotated_types.Le):
            maximo = int(restriccion.le)
        elif isinstance(restriccion, annotated_types.Lt):
            maximo = int(restriccion.lt) - 1
    if maximo is None:
        raise ValueError(f"El campo '{campo}' no declara un máximo (le/lt) para el horizonte.")
    default = min(max(_HORIZON_DEFAULT_SUGGESTION, minimo), maximo)
    return HorizonRange(min=minimo, max=maximo, default=default)


def _granularidades() -> list[GranularityOption]:
    """Granularidades disponibles, derivadas del Literal ``Granularidad`` del contrato."""
    return [
        GranularityOption(name=valor, label=_GRANULARITY_LABELS.get(valor, valor))
        for valor in typing.get_args(Granularidad)
    ]


def _query_options_sales() -> QueryOptions:
    """Opciones de consulta de SALES (R1/R2 + granularidad + horizonte), derivadas del contrato.

    Las dimensiones se filtran contra ``HistoricoItem`` para no declarar una columna que el
    contrato no tenga (segunda red de seguridad además de la prueba anti-desync).
    """
    columnas = set(HistoricoItem.model_fields)
    dimensiones = [d for d in _SALES_DIMENSIONS if d.name in columnas]
    return QueryOptions(
        typologies=list(_SALES_TYPOLOGIES),
        dimensions=dimensiones,
        granularities=_granularidades(),
        horizon=_rango_horizonte(VentasRequest, "horizon"),
    )


# ---------------------------------------------------------------------------
# Especificación por dominio (lo "a mano" se limita a prosa y referencias honestas)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class _DomainSpec:
    domain: str
    endpoint: str
    summary: str
    description: str
    contract_reference: str
    request_model: type[BaseModel]
    response_model: type[BaseModel]
    item_field: str
    item_model: type[BaseModel]
    metadata_model: type[BaseModel]
    notes: list[str] = field(default_factory=list)
    pending_policy: list[str] = field(default_factory=list)
    query_options: QueryOptions | None = None


_SPECS: list[_DomainSpec] = [
    _DomainSpec(
        domain="sales",
        endpoint="POST /sales",
        summary="Pronóstico de demanda futura (regresión).",
        description=(
            "Estima la demanda esperada en unidades por cada período futuro, punto de "
            "venta y producto/familia, a partir del histórico de ventas."
        ),
        contract_reference="§3 SALES (bloque history compartido en §2)",
        request_model=VentasRequest,
        response_model=VentasResponse,
        item_field="forecast",
        item_model=PronosticoItem,
        metadata_model=MetadatosVentas,
        notes=[
            "horizon se cuenta en períodos de la granularity elegida (day/week/month) y está acotado a ≤ 365.",
            "week/month se obtienen agregando (sumando) el pronóstico diario; la fecha es el inicio del período.",
            "interval_80 NO está disponible aún (diferido): el modelo no lo produce, así que la respuesta lo omite.",
            "model se lee de la metadata del artefacto (no se clava en el código).",
            "metadata.scale y metadata.internal_transform también se leen de la metadata del artefacto.",
            "query_options (tipologías/dimensiones/granularidad/horizonte) son afordancias de UI "
            "derivadas del contrato y de las agregaciones del servicio; no cambian el motor ni la respuesta.",
        ],
        query_options=_query_options_sales(),
    ),
    _DomainSpec(
        domain="purchases",
        endpoint="POST /purchases",
        summary="Reposición sugerida (derivada del pronóstico de ventas).",
        description=(
            "Calcula, por producto, la demanda esperada en la ventana de cobertura, el "
            "punto de reorden y la cantidad a reponer. Es lógica de negocio: reutiliza el "
            "pronóstico de SALES y los parámetros logísticos del cliente."
        ),
        contract_reference="§4 PURCHASES (bloque history compartido en §2)",
        request_model=ComprasRequest,
        response_model=ComprasResponse,
        item_field="recommendation",
        item_model=RecomendacionItem,
        metadata_model=MetadatosCompras,
        notes=[
            "No tiene modelo propio: la respuesta NO incluye el campo 'model'.",
            "Un producto sin histórico no se puede pronosticar y devuelve un error 400 (invalid_request).",
            "No acepta granularity ni horizon: el horizonte sale de lead_time_days + target_coverage_days.",
            "El stock de seguridad usa un método configurable (SPC_PURCHASES_SAFETY_METHOD; default "
            "coverage_days) con factor configurable (SPC_PURCHASES_SAFETY_FACTOR; default 30%). El "
            "método y el factor efectivos se reportan en metadata.policy / metadata.assumption. "
            "Decidido en ADR-0010.",
        ],
        pending_policy=[],
    ),
    _DomainSpec(
        domain="inventory",
        endpoint="POST /inventory",
        summary="Riesgo de quiebre y stock recomendado (clasificación + perfilado).",
        description=(
            "Predice la clase de demanda (alta/baja) con su probabilidad, marca el riesgo "
            "de quiebre y recomienda un stock objetivo (con stock de seguridad), enriquecido "
            "con el segmento de la tienda."
        ),
        contract_reference="§5 INVENTORY (bloque history compartido en §2)",
        request_model=AlmacenRequest,
        response_model=AlmacenResponse,
        item_field="alerts",
        item_model=AlertaItem,
        metadata_model=MetadatosAlmacen,
        notes=[
            "No expone un campo 'model': combina clasificación y clustering bajo el contrato.",
            "demand_class, su probabilidad y el store_segment salen de los artefactos (umbral y centroides del meta).",
            "metadata.probability_threshold se lee del meta del artefacto; es null si el artefacto no lo expone.",
            "Un producto sin histórico devuelve un error 400 (invalid_request).",
            "Las constantes de política son configurables (ADR-0010): lead time por defecto "
            "(SPC_INVENTORY_LEAD_TIME_DEFAULT=7), ventana de demanda (SPC_INVENTORY_DEMAND_WINDOW=28), "
            "niveles de servicio z (SPC_INVENTORY_Z_BASE=1.28 / SPC_INVENTORY_Z_HIGH_VOLUME=1.65) y el "
            "método de stock (SPC_INVENTORY_SAFETY_METHOD; default service_level = z·σ·√lead, con σ de "
            "la demanda real). Unificar con PURCHASES = poner el método en coverage_days.",
        ],
        pending_policy=[
            "[PENDIENTE / model-adjacent] El nivel del cuantil de demanda alta (P75) aún no se expone "
            "como campo numérico en la metadata del artefacto: se usa un fallback documentado (0.75) y "
            "queda pendiente exponerlo en la metadata en la próxima reconstrucción (coordinación con el "
            "equipo de modelado). No es una constante de política sino una definición del modelo.",
        ],
    ),
]


def _catalogo_dominio(spec: _DomainSpec) -> DomainCatalog:
    """Arma el catálogo de un dominio derivando entradas y salidas de sus esquemas."""
    outputs = [
        OutputGroup(
            group="root",
            container=None,
            fields=_campos_salida(spec.response_model, excluir=(spec.item_field, "metadata")),
        ),
        OutputGroup(
            group="items",
            container=spec.item_field,
            fields=_campos_salida(spec.item_model),
        ),
        OutputGroup(
            group="metadata",
            container="metadata",
            fields=_campos_salida(spec.metadata_model),
        ),
    ]
    return DomainCatalog(
        domain=spec.domain,
        endpoint=spec.endpoint,
        has_model="model" in spec.response_model.model_fields,
        summary=spec.summary,
        description=spec.description,
        contract_reference=spec.contract_reference,
        inputs=_entradas(spec.request_model),
        outputs=outputs,
        query_options=spec.query_options,
        notes=list(spec.notes),
        pending_policy=list(spec.pending_policy),
    )


def construir_catalogo() -> CatalogResponse:
    """Construye el catálogo completo (versión del contrato + canales/modos + dominios)."""
    return CatalogResponse(
        contract_version=CONTRACT_VERSION,
        channels=list(CHANNELS),
        modes=list(MODES),
        domains=[_catalogo_dominio(spec) for spec in _SPECS],
    )
