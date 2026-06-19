"""Esquemas del **modo por lote** (Fase 3.4): acuse de envío y estado del trabajo.

El mismo endpoint de predicción decide por número de filas: si el envío es chico,
responde en línea (200 con el resultado); si es grande, lo acepta como trabajo por
lote y responde **202** con un ``JobAccepted`` (el "ticket"). El estado se consulta
en ``GET /jobs/{job_id}`` (``JobStatus``) y el resultado en
``GET /jobs/{job_id}/result`` (el MISMO cuerpo que la respuesta en línea).

Los campos van en **inglés**, igual que el resto del contrato de la API.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

EstadoTrabajo = Literal["queued", "running", "done", "error"]


class JobAccepted(BaseModel):
    """Acuse de un envío aceptado para procesarse por lote (respuesta **202**)."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "job_id": "9f1c2a7b4d8e4f0aa1b2c3d4e5f60718",
                "status": "queued",
                "mode": "batch",
                "domain": "sales",
                "rows": 42000,
                "status_url": "/jobs/9f1c2a7b4d8e4f0aa1b2c3d4e5f60718",
                "result_url": "/jobs/9f1c2a7b4d8e4f0aa1b2c3d4e5f60718/result",
            }
        }
    )

    job_id: str = Field(description="Identificador del trabajo por lote.")
    status: EstadoTrabajo = Field(description="Estado del trabajo en el momento del acuse.")
    mode: Literal["batch"] = Field(default="batch", description="Modo de ejecución elegido por volumen.")
    domain: str = Field(description="Dominio del envío (sales/purchases/inventory).")
    rows: int = Field(description="Número de filas de `history` que dispararon el modo por lote.")
    status_url: str = Field(description="Dónde consultar el estado del trabajo.")
    result_url: str = Field(description="Dónde recuperar el resultado cuando esté listo.")


class JobStatus(BaseModel):
    """Estado de un trabajo por lote (``GET /jobs/{job_id}``)."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "job_id": "9f1c2a7b4d8e4f0aa1b2c3d4e5f60718",
                "status": "done",
                "domain": "sales",
                "rows": 42000,
                "created_at": "2026-06-19T14:03:21Z",
                "finished_at": "2026-06-19T14:03:24Z",
                "result_url": "/jobs/9f1c2a7b4d8e4f0aa1b2c3d4e5f60718/result",
            }
        }
    )

    job_id: str = Field(description="Identificador del trabajo por lote.")
    status: EstadoTrabajo = Field(
        description="queued (en cola) · running (procesando) · done (listo) · error (falló)."
    )
    domain: str = Field(description="Dominio del envío (sales/purchases/inventory).")
    rows: int = Field(description="Número de filas de `history` del envío.")
    created_at: datetime = Field(description="Cuándo se aceptó el trabajo (UTC).")
    finished_at: datetime | None = Field(
        default=None, description="Cuándo terminó (UTC); ausente si sigue en curso."
    )
    result_url: str = Field(description="Dónde recuperar el resultado cuando status == 'done'.")
