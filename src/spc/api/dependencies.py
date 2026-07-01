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


def obtener_cache_agnostico(request: Request) -> CacheModelosAgnosticos:
    """Devuelve la caché de modelos agnósticos auto-entrenados (ADR-0023), creada en el arranque.

    Lanza ``ServicioNoDisponible`` (→ 503) si no se inicializó. Es la vía por la que los
    endpoints ``/auto/*`` reusan o entrenan modelos por (cliente, esquema, datos).
    """
    cache = getattr(request.app.state, "cache_agnostico", None)
    if cache is None:
        raise ServicioNoDisponible("La predicción agnóstica no está disponible.")
    return cache


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
