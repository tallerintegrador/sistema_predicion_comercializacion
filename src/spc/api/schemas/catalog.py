"""Esquema del **catálogo de predicciones** (`GET /catalog`).

El catálogo es la "lista de servicios" del producto: por dominio (`sales`,
`purchases`, `inventory`) describe **qué entra, qué sale y qué limitaciones tiene**,
más la versión del contrato y la disponibilidad de canales/modos.

**Honestidad por construcción.** Las *salidas* (`outputs`) y las *entradas*
(`inputs`) declaradas se **derivan de los esquemas Pydantic reales** de cada
endpoint (ver `spc.api.catalog`), no se escriben a mano. Así el catálogo no puede
desincronizarse de lo que la API entrega: una prueba de consistencia falla si el
catálogo afirma un campo que la API no produce.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CatalogField(BaseModel):
    """Un campo de **salida** del dominio (derivado del esquema de respuesta)."""

    name: str = Field(description="Nombre canónico del campo (en inglés, igual que la API).")
    type: str = Field(description="Tipo del campo (legible).")
    required: bool = Field(
        description="True si la API siempre lo entrega; False si puede omitirse (opcional/diferido)."
    )
    description: str | None = Field(
        default=None, description="Significado del campo (en español)."
    )


class CatalogInput(BaseModel):
    """Una **entrada** de la petición (derivada del esquema de request)."""

    name: str = Field(description="Nombre del parámetro de entrada.")
    type: str = Field(description="Tipo del parámetro (legible).")
    required: bool = Field(description="True si es obligatorio en la petición.")
    description: str | None = Field(
        default=None, description="Qué representa el parámetro (en español)."
    )


class OutputGroup(BaseModel):
    """Un grupo de campos de salida: la raíz, los ítems de la lista o la metadata."""

    group: Literal["root", "items", "metadata"] = Field(
        description="Ubicación de los campos en la respuesta."
    )
    container: str | None = Field(
        default=None,
        description="Nombre del contenedor en la respuesta (p. ej. 'forecast' para los ítems).",
    )
    fields: list[CatalogField] = Field(description="Campos del grupo.")


class ForecastTypology(BaseModel):
    """Una **tipología** de pronóstico que la UI ofrece (recomendación R1 del profesor).

    Describe *cómo* se presenta/agrega el pronóstico que el motor produce por serie, **no**
    un modelo distinto: ``time_series`` agrega por período; ``by_dimension`` desglosa por una
    columna. Es una afordancia de presentación, derivada de las capacidades de agregación del
    servicio (``ventas_service``); el motor de ML no interviene.
    """

    name: str = Field(description="Identificador de la tipología (en inglés, p. ej. 'time_series').")
    label: str = Field(description="Etiqueta para mostrar (en español).")
    requires_dimension: bool = Field(
        description="True si la tipología necesita elegir una dimensión de desglose (R2)."
    )
    description: str = Field(description="Qué hace la tipología (en español).")


class ForecastDimension(BaseModel):
    """Una **columna** del histórico por la que desglosar/filtrar el pronóstico (R2).

    Sale de las columnas IDENTIFICADORAS del bloque ``history`` del contrato (§2): son las
    únicas por las que tiene sentido agrupar (la fecha es el eje temporal y ``units_sold`` es
    la medida). Los **valores** concretos de la columna no salen del catálogo, sino del
    histórico real que cargue el cliente (no se fabrican).
    """

    name: str = Field(description="Nombre de la columna del contrato (en inglés, p. ej. 'store_id').")
    label: str = Field(description="Etiqueta para mostrar (en español).")
    description: str | None = Field(
        default=None, description="Qué representa la columna (en español)."
    )


class GranularityOption(BaseModel):
    """Una granularidad temporal disponible (derivada del Literal del contrato)."""

    name: str = Field(description="Valor del contrato (en inglés: 'day' | 'week' | 'month').")
    label: str = Field(description="Etiqueta para mostrar (en español: Día | Semana | Mes).")


class HorizonRange(BaseModel):
    """Rango permitido del horizonte (derivado de las restricciones del esquema de request)."""

    min: int = Field(description="Mínimo de períodos a pronosticar.")
    max: int = Field(description="Máximo de períodos a pronosticar.")
    default: int = Field(
        description="Sugerencia inicial para la UI (el campo es obligatorio en el contrato)."
    )
    unit: str = Field(
        default="periods", description="Unidad del horizonte (períodos de la granularidad)."
    )


class QueryOptions(BaseModel):
    """Opciones de consulta que la UI ofrece para un dominio (afordancias, **no** contrato).

    Centraliza —**derivadas del contrato y de las capacidades de agregación del servicio**—
    las opciones que antes la UI clavaba a mano: tipologías (R1), dimensiones (R2),
    granularidades y rango de horizonte. Así la UI no hardcodea nada y el motor de ML no se
    toca. Una prueba anti-desync verifica que cada opción sigue alineada con el contrato.
    """

    typologies: list[ForecastTypology] = Field(description="Tipologías de pronóstico (R1).")
    dimensions: list[ForecastDimension] = Field(description="Columnas de desglose/filtro (R2).")
    granularities: list[GranularityOption] = Field(
        description="Granularidades temporales disponibles."
    )
    horizon: HorizonRange = Field(description="Rango permitido del horizonte.")


class DomainCatalog(BaseModel):
    """El catálogo de un dominio: descripción, entradas, salidas y notas honestas."""

    domain: str = Field(description="Identificador del dominio (sales/purchases/inventory).")
    endpoint: str = Field(description="Endpoint que lo expone (p. ej. 'POST /sales').")
    has_model: bool = Field(
        description="True si la respuesta expone un campo 'model' (solo SALES hoy)."
    )
    summary: str = Field(description="Descripción corta del servicio (en español).")
    description: str = Field(description="Descripción ampliada (en español).")
    contract_reference: str = Field(description="Sección del contrato que define el dominio.")
    inputs: list[CatalogInput] = Field(description="Entradas requeridas (derivadas del request).")
    outputs: list[OutputGroup] = Field(description="Salidas reales (derivadas de la respuesta).")
    query_options: QueryOptions | None = Field(
        default=None,
        description=(
            "Opciones de consulta que la UI ofrece para el dominio (tipologías, dimensiones, "
            "granularidades, horizonte). Presente en los dominios que las exponen (hoy SALES); "
            "se omite (None) en los demás."
        ),
    )
    notes: list[str] = Field(
        default_factory=list, description="Notas y limitaciones honestas del servicio."
    )
    pending_policy: list[str] = Field(
        default_factory=list,
        description=(
            "Items de política/definición todavía PENDIENTES (no resueltos). Tras ADR-0010, "
            "las constantes de política son configurables (ver 'notes'); aquí solo quedan los "
            "pendientes reales, como definiciones model-adjacent que la metadata aún no expone."
        ),
    )


class Availability(BaseModel):
    """Disponibilidad honesta de un canal o modo: lo de HOY vs. lo PLANIFICADO."""

    name: str = Field(description="Nombre del canal o modo.")
    status: Literal["available", "planned"] = Field(
        description="'available' = disponible hoy; 'planned' = planificado (no implementado)."
    )
    description: str = Field(description="Detalle (en español).")


class CatalogResponse(BaseModel):
    """Catálogo de predicciones completo que devuelve `GET /catalog`."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "contract_version": "1.0.1",
                "channels": [
                    {"name": "json", "status": "available", "description": "Entrada/salida JSON."},
                    {"name": "excel", "status": "planned", "description": "Carga por Excel (Fase 3.3)."},
                ],
                "modes": [
                    {"name": "online", "status": "available", "description": "Una petición en línea."},
                    {"name": "batch", "status": "planned", "description": "Lote de series (futuro)."},
                ],
                "domains": [
                    {
                        "domain": "sales",
                        "endpoint": "POST /sales",
                        "has_model": True,
                        "summary": "Pronóstico de demanda futura (regresión).",
                        "description": "Demanda esperada por período, punto de venta y producto/familia.",
                        "contract_reference": "§3 SALES (bloque history en §2)",
                        "inputs": [
                            {"name": "horizon", "type": "int", "required": True,
                             "description": "Número de períodos futuros a pronosticar (> 0)."}
                        ],
                        "outputs": [
                            {"group": "items", "container": "forecast", "fields": [
                                {"name": "forecast_demand", "type": "float", "required": True,
                                 "description": "Demanda esperada en unidades (≥ 0)."}
                            ]}
                        ],
                        "notes": ["interval_80 no disponible aún (diferido)."],
                        "pending_policy": [],
                    }
                ],
            }
        }
    )

    contract_version: str = Field(description="Versión del contrato de datos vigente.")
    channels: list[Availability] = Field(description="Canales de entrada/salida (hoy vs. planificado).")
    modes: list[Availability] = Field(description="Modos de ejecución (hoy vs. planificado).")
    domains: list[DomainCatalog] = Field(description="Catálogo por dominio implementado.")
