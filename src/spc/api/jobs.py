"""Almacén de trabajos por lote **in-process** y su worker (Fase 3.4).

El modo por lote acepta envíos grandes, devuelve un ``job_id`` (202) y procesa en
segundo plano **llamando al MISMO flujo de predicción** que el modo en línea. Aquí
viven las dos piezas que lo sostienen:

- ``Job``: el estado de un trabajo (cola → corriendo → terminado/erróneo, con su
  resultado o su error).
- ``GestorTrabajos``: el almacén (``dict`` protegido por un lock) más un
  ``ThreadPoolExecutor`` que ejecuta los trabajos. Es **in-process** y **en memoria**
  (decisión P5/ADR-0008): cero dependencias externas (sin Celery/Redis).

**Limitaciones honestas (documentadas en ADR-0008):**

- Los trabajos se pierden al **reiniciar** el proceso (no hay persistencia).
- Solo sirven dentro de **un proceso**: con varios workers de uvicorn
  (``--workers > 1``) un trabajo creado por un proceso no es visible para otro. El
  modo lote exige **un solo proceso** o, a futuro, un almacén compartido (SQLite).

Este módulo es **agnóstico al dominio**: ejecuta una función ``trabajo()`` sin
argumentos que ya encapsula "predecir y serializar"; así no duplica la lógica de
predicción ni conoce VENTAS/COMPRAS/ALMACÉN. El ruteo (``spc.api.ruteo``) arma esa
función. El mapeo de errores reproduce el de la capa API en línea: una regla de
negocio incumplida es un **400** con el mismo cuerpo que daría el JSON síncrono.
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

log = get_logger("api.jobs")

EstadoTrabajo = Literal["queued", "running", "done", "error"]

# Una función "predecir + serializar" sin argumentos que devuelve el cuerpo JSON-safe
# (idéntico al de la respuesta en línea). La construye la capa de ruteo.
Trabajo = Callable[[], dict[str, Any]]


def _ahora() -> datetime:
    """Marca de tiempo en UTC (timezone-aware)."""
    return datetime.now(UTC)


@dataclass
class Job:
    """Estado de un trabajo por lote (un envío grande en proceso)."""

    id: str
    domain: str
    rows: int
    status: EstadoTrabajo = "queued"
    created_at: datetime = field(default_factory=_ahora)
    finished_at: datetime | None = None
    # Resultado (cuando status == "done"): el MISMO cuerpo que la respuesta en línea.
    resultado: dict[str, Any] | None = None
    # Error (cuando status == "error"): código y cuerpo idénticos a los del modo en línea.
    error_status: int | None = None
    error_cuerpo: CuerpoError | None = None


class GestorTrabajos:
    """Almacén in-process de trabajos por lote + executor que los procesa.

    Vive en ``app.state.jobs`` (como el ``registro`` de artefactos) para que sea
    inyectable y testeable sin tocar el disco ni levantar infraestructura.
    """

    def __init__(self, *, max_workers: int = 1) -> None:
        self._trabajos: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="spc-batch"
        )

    # -- Lectura/creación --------------------------------------------------
    def crear(self, *, domain: str, rows: int) -> Job:
        """Registra un trabajo nuevo en estado ``queued`` y devuelve su ``Job``."""
        job = Job(id=uuid.uuid4().hex, domain=domain, rows=rows)
        with self._lock:
            self._trabajos[job.id] = job
        return job

    def obtener(self, job_id: str) -> Job | None:
        """Devuelve el ``Job`` por id, o ``None`` si no existe."""
        with self._lock:
            return self._trabajos.get(job_id)

    # -- Ejecución asíncrona ----------------------------------------------
    def enviar(self, job_id: str, trabajo: Trabajo) -> None:
        """Encola la ejecución del trabajo en el executor (devuelve de inmediato)."""
        self._executor.submit(self._ejecutar, job_id, trabajo)

    def _ejecutar(self, job_id: str, trabajo: Trabajo) -> None:
        """Corre el trabajo en segundo plano y guarda su resultado o su error.

        Reproduce el mapeo de errores de la capa API en línea: ``SolicitudInvalida``
        (regla de negocio) → **400** con el mismo cuerpo; cualquier otro fallo → **500**
        controlado, sin filtrar detalles internos (se registra en el log).
        """
        job = self.obtener(job_id)
        if job is None:  # defensivo: no debería ocurrir (se crea antes de enviar)
            return
        job.status = "running"
        try:
            job.resultado = trabajo()
            job.status = "done"
        except SolicitudInvalida as exc:
            job.status = "error"
            job.error_status = 400
            job.error_cuerpo = CuerpoError(type="invalid_request", message=str(exc))
        except Exception as exc:  # noqa: BLE001 - frontera: nada debe escapar del worker
            log.exception("Trabajo %s falló de forma inesperada: %s", job_id, exc)
            job.status = "error"
            job.error_status = 500
            job.error_cuerpo = CuerpoError(
                type="internal_error",
                message="Ocurrió un error interno al procesar la solicitud.",
            )
        finally:
            job.finished_at = _ahora()

    # -- Ciclo de vida -----------------------------------------------------
    def cerrar(self) -> None:
        """Apaga el executor esperando a que terminen los trabajos en curso."""
        self._executor.shutdown(wait=True)
