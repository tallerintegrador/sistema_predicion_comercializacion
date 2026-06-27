"""Trabajos de **entrenamiento por cliente** (ADR-0013): almacén in-process + worker.

Espeja a ``spc.api.jobs`` (modo lote) pero para entrenamientos, con un executor
**separado**: el entrenamiento es pesado y debe correr **desacoplado** del flujo de
predicción para no saturarlo (y para que, si el serving migra a la nube, el entrenamiento
pueda correr aparte). Cada trabajo lleva, además del estado, una **fase honesta**
(``validating`` → ``training`` → ``evaluating``) para que la UI muestre progreso real.

Mismas limitaciones honestas que el modo lote (ADR-0008): in-process, en memoria, se
pierde al reiniciar y solo es visible dentro de un proceso. El resultado de un trabajo es
el **experimento medido** (comparación candidato vs congelado vs baseline + veredicto de
adopción) que produce ``spc.training.cliente``.
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from spc.api.schemas.comunes import CuerpoError
from spc.service.errores import SolicitudInvalida
from spc.utils.logging import get_logger

log = get_logger("api.jobs_entrenamiento")

EstadoEntrenamiento = Literal["queued", "running", "done", "error"]
Fase = Literal["validating", "training", "evaluating"]

# Un trabajo recibe un callback para reportar su fase y devuelve el dict del experimento.
ReportarFase = Callable[[str], None]
TrabajoEntrenamiento = Callable[[ReportarFase], dict[str, Any]]


def _ahora() -> datetime:
    return datetime.now(UTC)


@dataclass
class JobEntrenamiento:
    """Estado de un trabajo de entrenamiento por cliente."""

    id: str
    client_id: str
    source: str
    domain: str = "sales"
    status: EstadoEntrenamiento = "queued"
    phase: Fase | None = None
    created_at: datetime = field(default_factory=_ahora)
    finished_at: datetime | None = None
    # Resultado (status == "done"): el experimento medido (comparación + veredicto).
    resultado: dict[str, Any] | None = None
    # Error (status == "error"): mismo cuerpo/criterio que la API en línea.
    error_status: int | None = None
    error_cuerpo: CuerpoError | None = None


class GestorEntrenamientos:
    """Almacén in-process de trabajos de entrenamiento + executor propio (separado del lote)."""

    def __init__(self, *, max_workers: int = 1) -> None:
        self._trabajos: dict[str, JobEntrenamiento] = {}
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="spc-train"
        )

    def crear(self, *, client_id: str, source: str) -> JobEntrenamiento:
        """Registra un trabajo nuevo en estado ``queued`` y lo devuelve."""
        job = JobEntrenamiento(id=uuid.uuid4().hex, client_id=client_id, source=source)
        with self._lock:
            self._trabajos[job.id] = job
        return job

    def obtener(self, job_id: str) -> JobEntrenamiento | None:
        with self._lock:
            return self._trabajos.get(job_id)

    def enviar(self, job_id: str, trabajo: TrabajoEntrenamiento) -> None:
        """Encola el entrenamiento en el executor propio (devuelve de inmediato)."""
        self._executor.submit(self._ejecutar, job_id, trabajo)

    def _ejecutar(self, job_id: str, trabajo: TrabajoEntrenamiento) -> None:
        """Corre el trabajo en segundo plano, reportando fases y guardando resultado/error."""
        job = self.obtener(job_id)
        if job is None:  # defensivo
            return
        job.status = "running"

        def reportar(fase: str) -> None:
            job.phase = fase  # type: ignore[assignment]

        try:
            job.resultado = trabajo(reportar)
            job.status = "done"
        except SolicitudInvalida as exc:
            job.status = "error"
            job.error_status = 400
            job.error_cuerpo = CuerpoError(type="invalid_request", message=str(exc))
        except Exception as exc:  # noqa: BLE001 - frontera: nada escapa del worker
            log.exception("Entrenamiento %s falló de forma inesperada: %s", job_id, exc)
            job.status = "error"
            job.error_status = 500
            job.error_cuerpo = CuerpoError(
                type="internal_error",
                message="Ocurrió un error interno durante el entrenamiento.",
            )
        finally:
            job.phase = None
            job.finished_at = _ahora()

    def cerrar(self) -> None:
        """Apaga el executor esperando a que terminen los entrenamientos en curso."""
        self._executor.shutdown(wait=True)
