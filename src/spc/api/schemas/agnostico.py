"""Esquemas del contrato **agnóstico al rubro** (predicción auto-entrenada, ADR-0023).

A diferencia del contrato retail fijo (`comunes.HistoricoItem`: ``store_id``,
``product_id``, ``units_sold``...), aquí el cliente **declara su propio esquema**
(`SchemaSpec`) y envía **filas con columnas arbitrarias** (``rows``). El sistema
entrena en el momento el **algoritmo ganador** sobre esa data (`spc.models.automl`) y
predice/mejora, de modo que sirve a cualquier sector sin reentrenar el motor a mano.

Tres dominios, el mismo bloque `schema` + `rows`:

- **/auto/sales** — pronóstico de demanda (regresión auto-entrenada).
- **/auto/inventory** — riesgo de quiebre y stock recomendado (clasificación + política).
- **/auto/purchases** — reposición sugerida (sobre el pronóstico genérico).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Granularidad = Literal["day", "week", "month"]
TipoFeature = Literal["numeric", "categorical"]


class FeatureSpec(BaseModel):
    """Declaración de una columna-feature del esquema del cliente.

    - ``type``: ``numeric`` (continua/contable) o ``categorical`` (etiqueta/segmento).
    - ``known_future``: ``true`` si su valor del período a pronosticar **se conoce de
      antemano** (calendario, promoción/precio planificados): se usa tal cual. ``false``
      si solo se conoce a posteriori (tráfico, transacciones): se usan solo sus rezagos
      (evita la fuga). Las categóricas se tratan siempre como conocidas.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, description="Nombre de la columna en ``rows``.")
    type: TipoFeature = Field(description="Tipo de la feature: numeric | categorical.")
    known_future: bool = Field(
        default=True,
        description="¿Se conoce su valor del período a predecir? (false → solo rezagos).",
    )


class SchemaSpec(BaseModel):
    """Esquema declarado por el cliente: qué columna es el objetivo, la fecha, las series
    y qué features extra trae. Es lo que hace al sistema **agnóstico al rubro**."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "target": "units_sold",
                "date": "date",
                "series_keys": ["store_id", "product_id"],
                "features": [
                    {"name": "on_promotion", "type": "numeric", "known_future": True},
                    {"name": "transactions", "type": "numeric", "known_future": False},
                    {"name": "region", "type": "categorical", "known_future": True},
                ],
            }
        },
    )

    target: str = Field(min_length=1, description="Columna a predecir (numérica para ventas).")
    date: str | None = Field(
        default=None, description="Columna de fecha (ISO). Ausente → modo tabular sin rezagos."
    )
    series_keys: list[str] = Field(
        default_factory=list,
        description="Columnas que identifican cada serie (generaliza tienda×producto).",
    )
    features: list[FeatureSpec] = Field(
        default_factory=list, description="Features extra declaradas (numéricas/categóricas)."
    )


class AutoTemplateRequest(BaseModel):
    """Petición para generar la plantilla Excel a medida del esquema declarado."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_spec: SchemaSpec = Field(alias="schema", description="Esquema declarado.")


EJEMPLO_ROWS: list[dict[str, Any]] = [
    {
        "date": "2024-01-01",
        "store_id": "L1",
        "product_id": "CAFE",
        "units_sold": 120.0,
        "on_promotion": 0,
        "transactions": 168.0,
        "region": "norte",
    },
    {
        "date": "2024-01-02",
        "store_id": "L1",
        "product_id": "CAFE",
        "units_sold": 98.0,
        "on_promotion": 1,
        "transactions": 137.0,
        "region": "norte",
    },
]


# ---------------------------------------------------------------------------
# Información de entrenamiento (común a las tres respuestas)
# ---------------------------------------------------------------------------
class InfoEntrenamiento(BaseModel):
    """Resumen honesto del modelo entrenado al vuelo para esta petición."""

    winner_algorithm: str = Field(description="Algoritmo ganador elegido en validación.")
    trained_rows: int = Field(description="Filas usadas tras descartar el calentamiento.")
    honest_metrics: dict[str, float] = Field(
        default_factory=dict,
        description="Métricas en la ventana de prueba temporal (WAPE/MAE o PR-AUC/Recall).",
    )
    candidates: dict[str, float] | None = Field(
        default=None, description="MAE de validación por algoritmo candidato (regresión)."
    )
    reused_cached_model: bool = Field(
        default=False,
        description="¿Se reusó un modelo ya entrenado para este (cliente, esquema)?",
    )
    schema_signature: str = Field(description="Firma del esquema declarado (clave de caché).")
    seleccion: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Veredicto de la comparación candidato-vs-campeón persistido del cliente "
            "(quédate-con-el-mejor): métrica, valores y cuál se adoptó. Ausente la primera vez."
        ),
    )


# ---------------------------------------------------------------------------
# SALES (regresión)
# ---------------------------------------------------------------------------
class AutoSalesRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "schema": SchemaSpec.model_config["json_schema_extra"]["example"],
                "horizon": 7,
                "granularity": "day",
                "rows": EJEMPLO_ROWS,
            }
        },
    )

    schema_spec: SchemaSpec = Field(alias="schema", description="Esquema declarado.")
    horizon: int = Field(gt=0, le=365, description="Períodos futuros a pronosticar.")
    granularity: Granularidad = Field(default="day", description="Granularidad de salida.")
    rows: list[dict[str, Any]] = Field(min_length=1, description="Datos históricos (columnas libres).")
    future: list[dict[str, Any]] | None = Field(
        default=None,
        description=(
            "Filas futuras opcionales con las features conocidas-a-futuro ya fijadas "
            "(p. ej. promoción planificada). Si se omite, se asume sin promoción."
        ),
    )


class AutoSalesResponse(BaseModel):
    field: Literal["sales"] = "sales"
    training: InfoEntrenamiento
    forecast: list[dict[str, Any]] = Field(
        description="Por (período futuro, serie): forecast_demand y las claves de serie."
    )
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# INVENTORY (clasificación + política)
# ---------------------------------------------------------------------------
class AutoInventoryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_spec: SchemaSpec = Field(alias="schema", description="Esquema declarado.")
    rows: list[dict[str, Any]] = Field(min_length=1, description="Datos históricos (columnas libres).")
    items: list[dict[str, Any]] = Field(
        min_length=1,
        description=(
            "Estado de inventario por serie: las claves de serie + ``current_stock`` y, "
            "opcional, ``lead_time_days``."
        ),
    )
    high_demand_quantile: float = Field(
        default=0.75, gt=0.0, lt=1.0,
        description="Cuantil por serie que define 'demanda alta' (default P75).",
    )


class AutoInventoryResponse(BaseModel):
    field: Literal["inventory"] = "inventory"
    training: InfoEntrenamiento
    alerts: list[dict[str, Any]]
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# PURCHASES (reposición sobre el pronóstico)
# ---------------------------------------------------------------------------
class AutoPurchasesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_spec: SchemaSpec = Field(alias="schema", description="Esquema declarado.")
    rows: list[dict[str, Any]] = Field(min_length=1, description="Datos históricos (columnas libres).")
    items: list[dict[str, Any]] = Field(
        min_length=1,
        description=(
            "Parámetros de reposición por serie: claves de serie + ``current_stock``, "
            "``lead_time_days`` y ``target_coverage_days``."
        ),
    )


class AutoPurchasesResponse(BaseModel):
    field: Literal["purchases"] = "purchases"
    training: InfoEntrenamiento
    recommendation: list[dict[str, Any]]
    metadata: dict[str, Any] = Field(default_factory=dict)
