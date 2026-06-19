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

from pydantic import BaseModel

from spc.api.schemas.almacen import AlertaItem, AlmacenRequest, AlmacenResponse, MetadatosAlmacen
from spc.api.schemas.catalog import (
    Availability,
    CatalogField,
    CatalogInput,
    CatalogResponse,
    DomainCatalog,
    OutputGroup,
)
from spc.api.schemas.compras import (
    ComprasRequest,
    ComprasResponse,
    MetadatosCompras,
    RecomendacionItem,
)
from spc.api.schemas.ventas import MetadatosVentas, PronosticoItem, VentasRequest, VentasResponse

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
        status="planned",
        description=(
            "Ajuste del modelo por cliente sobre el lote (opción B/híbrida): experimento "
            "futuro y medido. Hoy NO se implementa; el lote usa el modelo congelado (opción A)."
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
        ],
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
