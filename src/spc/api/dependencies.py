"""Inyección de dependencias de la API.

Los motores de predicción (``/auto/*`` y ``/v2/*``) entrenan en el momento, así que no
hay artefactos que cargar por petición. Aquí viven las dependencias transversales: la
**caché** de modelos agnósticos auto-entrenados (ADR-0023) y el **identificador de
cliente** derivado de la sesión.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, Request

from spc.api.errors import ServicioNoDisponible
from spc.api.schemas.auth import SessionUser
from spc.api.seguridad import usuario_opcional
from spc.service.cache_agnostico import CacheModelosAgnosticos
from spc.service.repositorio_corpus import RepositorioCorpus
from spc.service.repositorio_modelos import RepositorioModelos


def obtener_cache_agnostico(request: Request) -> CacheModelosAgnosticos:
    """Devuelve la caché de modelos agnósticos auto-entrenados (ADR-0023), creada en el arranque.

    Lanza ``ServicioNoDisponible`` (→ 503) si no se inicializó. Es la vía por la que los
    endpoints ``/auto/*`` reusan o entrenan modelos por (cliente, esquema, datos).
    """
    cache = getattr(request.app.state, "cache_agnostico", None)
    if cache is None:
        raise ServicioNoDisponible("La predicción agnóstica no está disponible.")
    return cache


def obtener_corpus(request: Request) -> RepositorioCorpus:
    """Repositorio del corpus acumulativo (ADR-0026), creado al arranque. 503 si falta."""
    corpus = getattr(request.app.state, "corpus", None)
    if corpus is None:
        raise ServicioNoDisponible("La persistencia del corpus no está disponible.")
    return corpus


def obtener_corpus_opcional(request: Request) -> RepositorioCorpus | None:
    """Corpus si está disponible, o ``None`` (para el enganche best-effort que nunca rompe)."""
    return getattr(request.app.state, "corpus", None)


def obtener_modelos(request: Request) -> RepositorioModelos:
    """Registro de modelos entrenados (ADR-0026), creado al arranque. 503 si falta."""
    modelos = getattr(request.app.state, "modelos", None)
    if modelos is None:
        raise ServicioNoDisponible("El registro de modelos no está disponible.")
    return modelos


def obtener_client_id(
    sesion: Annotated[SessionUser | None, Depends(usuario_opcional)],
    x_client_id: Annotated[str | None, Header(alias="X-Client-Id")] = None,
) -> str:
    """Identificador del cliente para separar la caché de modelos por cuenta.

    Con el control de acceso activo, se **deriva del usuario autenticado** (``client_id``
    del token). Sin sesión (control inactivo o tests), cae al header ``X-Client-Id`` y, en
    su ausencia, a ``"default"``.
    """
    if sesion is not None:
        return sesion.client_id
    valor = (x_client_id or "").strip()
    return valor or "default"
