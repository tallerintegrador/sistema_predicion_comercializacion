"""Esquemas del **entrenamiento por cliente bajo demanda** (ADR-0013).

OPT-IN: el cliente sube su Excel (la MISMA plantilla del contrato) y pulsa "entrenar".
El disparo devuelve **202** con un ``TrainingAccepted`` (job_id); el estado se consulta en
``GET /training/jobs/{job_id}`` (``TrainingJobStatus``, con la **fase** honesta) y el
resultado en ``GET /training/jobs/{job_id}/result`` (el experimento medido). El estado de
adopción/serving por cliente está en ``GET /training/sales/status`` (``ServingStatus``).

Campos en **inglés**, igual que el resto del contrato de la API.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

EstadoEntrenamiento = Literal["queued", "running", "done", "error"]
Fase = Literal["validating", "training", "evaluating"]
Outcome = Literal["adopted", "not_adopted", "insufficient_data", "inconclusive"]


class TrainingAccepted(BaseModel):
    """Acuse de un entrenamiento aceptado para correr en segundo plano (respuesta **202**)."""

    job_id: str = Field(description="Identificador del trabajo de entrenamiento.")
    status: EstadoEntrenamiento = Field(description="Estado del trabajo en el acuse.")
    domain: Literal["sales"] = Field(default="sales", description="Dominio del modelo a ajustar.")
    client_id: str = Field(description="Cliente para el que se entrena (header X-Client-Id).")
    source: str = Field(description="Origen de los datos: excel | corpus | merged.")
    status_url: str = Field(description="Dónde consultar el estado/fase del trabajo.")
    result_url: str = Field(description="Dónde recuperar el resultado (la comparación) al terminar.")


class TrainingJobStatus(BaseModel):
    """Estado de un trabajo de entrenamiento (``GET /training/jobs/{job_id}``)."""

    job_id: str = Field(description="Identificador del trabajo.")
    status: EstadoEntrenamiento = Field(
        description="queued · running · done · error."
    )
    phase: Fase | None = Field(
        default=None,
        description="Fase honesta mientras corre: validating · training · evaluating.",
    )
    domain: str = Field(description="Dominio (sales).")
    client_id: str = Field(description="Cliente del entrenamiento.")
    source: str = Field(description="Origen de los datos del entrenamiento.")
    created_at: datetime = Field(description="Cuándo se aceptó (UTC).")
    finished_at: datetime | None = Field(
        default=None, description="Cuándo terminó (UTC); ausente si sigue en curso."
    )
    result_url: str = Field(description="Dónde recuperar el resultado cuando status == 'done'.")


# ---------------------------------------------------------------------------
# Resultado del experimento (documentación de Swagger; el endpoint devuelve el dict
# honesto tal cual, sin recortar campos — igual que el resultado del modo lote).
# ---------------------------------------------------------------------------
class MetricTriple(BaseModel):
    """Las tres métricas guía (en unidades / %), recursivas honestas."""

    WAPE: float
    MAE: float
    RMSE: float


class BaselineMetric(MetricTriple):
    """Métrica de un baseline ingenuo, con su nombre."""

    name: str


class TrainingResult(BaseModel):
    """Resultado del experimento medido: comparación honesta + veredicto de adopción.

    Permisivo (``extra='allow'``) porque el cuerpo varía por ``outcome`` (p. ej.
    ``insufficient_data`` trae ``missing``/``requirements`` en vez de las métricas). El
    endpoint devuelve el dict completo; este modelo documenta los campos principales.
    """

    model_config = ConfigDict(extra="allow")

    domain: Literal["sales"] = "sales"
    outcome: Outcome = Field(description="adopted · not_adopted · insufficient_data · inconclusive.")
    message: str = Field(description="Explicación honesta del resultado.")
    metric: str | None = Field(default=None, description="Métrica de comparación (WAPE recursivo).")
    window_days: int | None = Field(default=None, description="Días por holdout temporal (adaptativo).")
    candidate: MetricTriple | None = Field(default=None, description="Métricas del modelo por cliente.")
    frozen: MetricTriple | None = Field(default=None, description="Métricas del modelo congelado.")
    baseline: BaselineMetric | None = Field(default=None, description="Mejor baseline ingenuo.")
    improvement_wape_points: float | None = Field(
        default=None, description="Puntos de WAPE que el candidato mejora al congelado (>0 = mejor)."
    )
    model_version: str | None = Field(
        default=None, description="Versión del modelo por cliente (si se entrenó/adoptó)."
    )


# ---------------------------------------------------------------------------
# Estado de adopción/serving por cliente
# ---------------------------------------------------------------------------
class ServingStatus(BaseModel):
    """Estado del modelo por cliente (``GET /training/sales/status``)."""

    domain: Literal["sales"] = "sales"
    client_id: str = Field(description="Cliente consultado.")
    has_client_model: bool = Field(description="True si el cliente tiene algún modelo entrenado.")
    serving_client_model: bool = Field(
        description="True si HOY se sirve el modelo por cliente (adoptado y switch activo)."
    )
    adopted_version: int | None = Field(default=None, description="Versión adoptada (o null).")
    model_version: str | None = Field(
        default=None, description="Etiqueta del modelo servido por cliente (o null = congelado)."
    )
    trained_versions: list[int] = Field(
        default_factory=list, description="Versiones entrenadas (historial)."
    )
    last_comparison: dict[str, Any] | None = Field(
        default=None, description="Último experimento medido (comparación + veredicto)."
    )


class ServingSwitchRequest(BaseModel):
    """Switch para servir (o no) con el modelo por cliente (``POST /training/sales/serving``)."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(description="True = servir el modelo por cliente; False = volver al congelado.")
