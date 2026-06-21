"""Inyección de dependencias de la API.

Los artefactos se cargan **una sola vez** al arranque (lifespan en `main.py`) y se
guardan en ``app.state.registro``. Los routers reciben ese registro vía
``Depends(obtener_registro)``: no cargan nada por petición. En los tests, el
registro se inyecta directamente (artefactos diminutos) sin tocar el disco real.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, Request

from spc.api.errors import ServicioNoDisponible
from spc.api.jobs import GestorTrabajos
from spc.api.jobs_entrenamiento import GestorEntrenamientos
from spc.api.schemas.auth import SessionUser
from spc.api.seguridad import usuario_opcional
from spc.service.artefactos import RegistroArtefactos
from spc.service.modelo_cliente import ResolutorModeloCliente
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


def obtener_resolutor_cliente(request: Request) -> ResolutorModeloCliente | None:
    """Devuelve el resolutor de modelos por cliente (ADR-0013) o ``None``.

    ``None`` si el ajuste por cliente está desactivado (``SPC_CLIENT_ADJ_ENABLED=0``) o no
    se inicializó: en ese caso el serving usa siempre el congelado (default intacto).
    """
    return getattr(request.app.state, "resolutor_cliente", None)


def obtener_entrenamientos(request: Request) -> GestorEntrenamientos:
    """Devuelve el gestor de trabajos de entrenamiento por cliente (executor separado).

    Lanza ``ServicioNoDisponible`` (→ 503) si el ajuste por cliente está desactivado o no
    se inicializó (los endpoints de entrenamiento no están disponibles entonces).
    """
    gestor = getattr(request.app.state, "entrenamientos", None)
    if gestor is None:
        raise ServicioNoDisponible(
            "El entrenamiento por cliente no está disponible (deshabilitado por configuración)."
        )
    return gestor


def obtener_client_id(
    sesion: Annotated[SessionUser | None, Depends(usuario_opcional)],
    x_client_id: Annotated[str | None, Header(alias="X-Client-Id")] = None,
) -> str:
    """Identificador del cliente para etiquetar el corpus y el ajuste por cliente.

    Con el control de acceso activo, se **deriva del usuario autenticado** (``client_id``
    del token), de modo que el corpus/entrenamiento quedan ligados a la cuenta y no a un
    header que cualquiera podría falsificar. Sin sesión (control inactivo o tests previos),
    cae al header ``X-Client-Id`` (metadato de transporte) y, en su ausencia, a ``"default"``.
    """
    if sesion is not None:
        return sesion.client_id
    valor = (x_client_id or "").strip()
    return valor or "default"
