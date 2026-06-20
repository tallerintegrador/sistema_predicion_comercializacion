"""Inyección de dependencias de la API.

Los artefactos se cargan **una sola vez** al arranque (lifespan en `main.py`) y se
guardan en ``app.state.registro``. Los routers reciben ese registro vía
``Depends(obtener_registro)``: no cargan nada por petición. En los tests, el
registro se inyecta directamente (artefactos diminutos) sin tocar el disco real.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Header, Request

from spc.api.errors import ServicioNoDisponible
from spc.api.jobs import GestorTrabajos
from spc.service.artefactos import RegistroArtefactos
from spc.service.repositorio import RepositorioPredicciones


def obtener_registro(request: Request) -> RegistroArtefactos:
    """Devuelve el registro de artefactos cargado en el arranque.

    Lanza ``ServicioNoDisponible`` (→ HTTP 503) si el motor no se cargó (arranque
    incompleto). Es la única vía por la que los routers acceden al motor.
    """
    registro = getattr(request.app.state, "registro", None)
    if registro is None:
        raise ServicioNoDisponible("El motor de ML no está cargado.")
    return registro


def obtener_jobs(request: Request) -> GestorTrabajos:
    """Devuelve el gestor de trabajos por lote (in-process) creado en el arranque.

    Lanza ``ServicioNoDisponible`` (→ HTTP 503) si no se inicializó. Es la única vía
    por la que los routers acceden al almacén/executor de trabajos.
    """
    jobs = getattr(request.app.state, "jobs", None)
    if jobs is None:
        raise ServicioNoDisponible("El gestor de trabajos por lote no está disponible.")
    return jobs


def obtener_repositorio(request: Request) -> RepositorioPredicciones | None:
    """Devuelve el repositorio de corpus (persistencia incremental) o ``None``.

    A diferencia del motor o el gestor de lote, la persistencia es **opcional y
    best-effort** (Fase A MEJORADO, ADR-0011): si está desactivada
    (``SPC_PERSIST_ENABLED=0``) o no se inicializó, devuelve ``None`` y el ruteo
    simplemente no acumula corpus — la predicción no se ve afectada.
    """
    return getattr(request.app.state, "repositorio", None)


def obtener_client_id(
    x_client_id: Annotated[str | None, Header(alias="X-Client-Id")] = None,
) -> str:
    """Identificador del cliente para etiquetar el corpus (header ``X-Client-Id``).

    Es **metadato de transporte**, no parte del cuerpo del contrato (no lo toca). Si el
    cliente no lo envía, cae a ``"default"``. Habilita corpus/ajuste por cliente a futuro.
    """
    valor = (x_client_id or "").strip()
    return valor or "default"
