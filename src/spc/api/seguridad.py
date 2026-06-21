"""Dependencias de **autenticación y autorización** de la capa API (ADR-0014).

La autorización se aplica en el **BACKEND**, no solo ocultando elementos en la UI: cada
endpoint protegido declara los permisos que exige con :func:`requiere`, y la dependencia
valida el token de sesión y el rol del usuario **en el servidor**.

Comportamiento según el knob ``SPC_AUTH_ENABLED``:

- **Activo (producción/tests de auth):** sin token válido → 401; con token pero sin el
  permiso → 403; en regla → se inyecta la sesión y se etiqueta ``request.state.usuario``.
- **Inactivo (tests de predicción heredados):** ``requiere`` deja pasar (``None``), de modo
  que la suite previa corre sin credenciales (igual criterio que la persistencia del corpus,
  desactivada por defecto en esos tests).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Header, Request

from spc.api.errors import AccesoDenegado, NoAutenticado, ServicioNoDisponible
from spc.api.schemas.auth import SessionUser
from spc.config import auth_enabled, auth_secret
from spc.service.repositorio_auth import RepositorioAuth, Usuario
from spc.service.seguridad import verificar_token


def obtener_repositorio_auth(request: Request) -> RepositorioAuth:
    """Repositorio de auth abierto en el arranque (``app.state.auth``).

    Lanza ``ServicioNoDisponible`` (→ 503) si no se inicializó: los endpoints de auth no
    pueden operar sin él.
    """
    repo = getattr(request.app.state, "auth", None)
    if repo is None:
        raise ServicioNoDisponible("El control de acceso no está disponible.")
    return repo


def _token_del_header(authorization: str | None) -> str | None:
    """Extrae el token de un encabezado ``Authorization: Bearer <token>``."""
    if not authorization:
        return None
    partes = authorization.split(" ", 1)
    if len(partes) == 2 and partes[0].lower() == "bearer":
        return partes[1].strip()
    return None


def construir_sesion(repo: RepositorioAuth, usuario: Usuario) -> SessionUser:
    """Arma la identidad efectiva (usuario + nombre de rol + permisos) desde la base.

    Los permisos se leen **frescos** en cada petición: un cambio de rol surte efecto sin
    re-emitir el token (que solo transporta el id del usuario).
    """
    rol = repo.obtener_rol(usuario.role_id)
    return SessionUser(
        user_id=usuario.user_id,
        role_id=usuario.role_id,
        role=rol.name if rol else "",
        permissions=list(rol.permissions) if rol else [],
        client_id=usuario.client_id,
        onboarding_done=usuario.onboarding_done,
    )


def usuario_opcional(
    request: Request,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> SessionUser | None:
    """Resuelve la sesión desde el token, o ``None`` si no hay/no es válida.

    Devuelve ``None`` cuando: el control de acceso está desactivado, falta el token, la
    firma/caducidad no validan, o el usuario no existe / está inactivo. Nunca lanza: la
    decisión de exigir credenciales la toma :func:`requiere`.
    """
    if not auth_enabled():
        return None
    token = _token_del_header(authorization)
    if not token:
        return None
    cuerpo = verificar_token(token, auth_secret())
    if cuerpo is None:
        return None
    repo = getattr(request.app.state, "auth", None)
    if repo is None:
        return None
    usuario = repo.obtener_usuario(str(cuerpo.get("sub", "")))
    if usuario is None or not usuario.is_active:
        return None
    sesion = construir_sesion(repo, usuario)
    request.state.usuario = sesion
    return sesion


def usuario_requerido(
    sesion: Annotated[SessionUser | None, Depends(usuario_opcional)],
) -> SessionUser | None:
    """Exige un usuario autenticado cuando el control de acceso está activo.

    Con el control activo y sin sesión válida → 401. Con el control inactivo → ``None``
    (sin enforcement). Es la base de :func:`requiere`.
    """
    if not auth_enabled():
        return None
    if sesion is None:
        raise NoAutenticado("Inicie sesión para continuar.")
    return sesion


def sesion_actual(
    sesion: Annotated[SessionUser | None, Depends(usuario_opcional)],
) -> SessionUser:
    """Exige SIEMPRE un usuario autenticado (independiente del knob).

    Lo usan los endpoints del propio usuario (``/auth/me``, ``/profile``): sin sesión
    válida → 401. A diferencia de :func:`usuario_requerido`, no deja pasar aunque el
    control esté desactivado (esos endpoints carecen de sentido sin identidad).
    """
    if sesion is None:
        raise NoAutenticado("Inicie sesión para continuar.")
    return sesion


def requiere(*permisos: str) -> Callable[..., SessionUser | None]:
    """Crea una dependencia que exige TODOS los ``permisos`` indicados sobre el endpoint.

    Uso: ``_: Annotated[SessionUser | None, Depends(requiere("module:sales", "action:forecast"))]``.
    Con el control de acceso inactivo no exige nada (deja pasar). Con él activo: 401 si no
    hay sesión, 403 si al rol le falta algún permiso.
    """
    requeridos = set(permisos)

    def dependencia(
        sesion: Annotated[SessionUser | None, Depends(usuario_requerido)],
    ) -> SessionUser | None:
        if not auth_enabled():
            return None
        assert sesion is not None  # usuario_requerido ya garantizó la sesión
        faltantes = requeridos - set(sesion.permissions)
        if faltantes:
            raise AccesoDenegado(
                "Su rol no tiene permiso para esta acción: " + ", ".join(sorted(faltantes)) + "."
            )
        return sesion

    return dependencia
