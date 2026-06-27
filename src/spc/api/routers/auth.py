"""Router del **control de acceso por roles** (ADR-0014).

Endpoints operacionales (campos/params/enums en inglés, error uniforme del contrato):

- ``POST /auth/login`` — id + contraseña → token de sesión firmado.
- ``GET /auth/me`` — identidad y permisos del usuario autenticado.
- ``GET /permissions`` — catálogo de permisos para construir/editar roles.
- ``GET/POST/PATCH/DELETE /roles`` — administración de roles (permiso ``action:users_manage``).
- ``GET/POST/PATCH /users`` — administración de cuentas (permiso ``action:users_manage``).
- ``GET /profile`` · ``PUT /profile`` · ``GET /profile/options`` — onboarding del negocio.

La autorización se valida en el BACKEND vía :func:`spc.api.seguridad.requiere`; ocultar
elementos en la UI no basta.
"""

from __future__ import annotations

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, status

from spc.api.errors import (
    ConflictoRecurso,
    CredencialesInvalidas,
    RecursoNoEncontrado,
)
from spc.api.schemas.auth import (
    MONEDAS,
    REGIONES,
    SECTORES,
    TAMANOS,
    LoginRequest,
    LoginResponse,
    PermissionCatalog,
    PermissionOut,
    ProfileOptions,
    ProfileOut,
    ProfileUpdate,
    RoleCreate,
    RoleOut,
    RoleUpdate,
    SessionUser,
    UserCreate,
    UserOut,
    UserUpdate,
)
from spc.api.schemas.comunes import ErrorResponse
from spc.api.seguridad import (
    construir_sesion,
    obtener_repositorio_auth,
    requiere,
    sesion_actual,
)
from spc.config import auth_secret, auth_token_ttl
from spc.service import permisos
from spc.service.errores import SolicitudInvalida
from spc.service.repositorio_auth import NOMBRE_ROL_ADMIN, RepositorioAuth, Rol, Usuario
from spc.service.seguridad import crear_token, verify_password

router = APIRouter(tags=["auth"])

# Dependencia reutilizable: exige el permiso de administración de usuarios.
AdminDep = Annotated[SessionUser | None, Depends(requiere("action:users_manage"))]
RepoDep = Annotated[RepositorioAuth, Depends(obtener_repositorio_auth)]


# ---------------------------------------------------------------------------
# Conversión repo → contrato
# ---------------------------------------------------------------------------
def _user_out(repo: RepositorioAuth, usuario: Usuario) -> UserOut:
    rol = repo.obtener_rol(usuario.role_id)
    return UserOut(
        user_id=usuario.user_id,
        role_id=usuario.role_id,
        role=rol.name if rol else "",
        client_id=usuario.client_id,
        is_active=usuario.is_active,
        onboarding_done=usuario.onboarding_done,
        created_at=usuario.created_at,
    )


def _role_out(rol: Rol) -> RoleOut:
    return RoleOut(id=rol.id, name=rol.name, description=rol.description, permissions=rol.permissions)


def _validar_permisos(claves: list[str]) -> None:
    validas = permisos.claves_validas()
    desconocidas = [c for c in claves if c not in validas]
    if desconocidas:
        raise SolicitudInvalida("Permisos desconocidos: " + ", ".join(sorted(desconocidas)) + ".")


# ---------------------------------------------------------------------------
# Sesión
# ---------------------------------------------------------------------------
@router.post(
    "/auth/login",
    response_model=LoginResponse,
    summary="Iniciar sesión (id + contraseña)",
    responses={401: {"model": ErrorResponse, "description": "Credenciales inválidas"}},
)
def login(body: LoginRequest, repo: RepoDep) -> LoginResponse:
    """Verifica las credenciales contra el hash y emite un token de sesión firmado.

    Mensaje genérico ante fallo (no revela si el id existe). Una cuenta inactiva también
    se rechaza como credencial inválida.
    """
    usuario = repo.obtener_usuario(body.user_id)
    almacenado = repo.obtener_password_hash(body.user_id) if usuario else None
    if usuario is None or almacenado is None or not verify_password(body.password, almacenado):
        raise CredencialesInvalidas("Id o contraseña incorrectos.")
    if not usuario.is_active:
        raise CredencialesInvalidas("Id o contraseña incorrectos.")
    ttl = auth_token_ttl()
    token = crear_token(subject=usuario.user_id, secret=auth_secret(), ttl_segundos=ttl)
    return LoginResponse(token=token, expires_in=ttl, user=construir_sesion(repo, usuario))


@router.get(
    "/auth/me",
    response_model=SessionUser,
    summary="Identidad y permisos del usuario autenticado",
    responses={401: {"model": ErrorResponse, "description": "No autenticado"}},
)
def me(sesion: Annotated[SessionUser, Depends(sesion_actual)]) -> SessionUser:
    """Devuelve la identidad efectiva (rol y permisos) del token vigente."""
    return sesion


# ---------------------------------------------------------------------------
# Permisos (catálogo para el editor de roles)
# ---------------------------------------------------------------------------
@router.get(
    "/permissions",
    response_model=PermissionCatalog,
    summary="Catálogo de permisos disponibles (módulos + acciones)",
    responses={403: {"model": ErrorResponse, "description": "Sin permiso de administración"}},
)
def listar_permisos(_: AdminDep) -> PermissionCatalog:
    """Permisos para construir/editar roles. Los de módulo derivan del catálogo de dominios."""
    return PermissionCatalog(
        permissions=[
            PermissionOut(key=p.key, label=p.label, group=p.group)  # type: ignore[arg-type]
            for p in permisos.catalogo_permisos()
        ]
    )


# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------
@router.get("/roles", response_model=list[RoleOut], summary="Listar roles")
def listar_roles(_: AdminDep, repo: RepoDep) -> list[RoleOut]:
    return [_role_out(r) for r in repo.listar_roles()]


@router.post(
    "/roles",
    response_model=RoleOut,
    status_code=status.HTTP_201_CREATED,
    summary="Crear un rol",
    responses={
        400: {"model": ErrorResponse, "description": "Permisos desconocidos"},
        409: {"model": ErrorResponse, "description": "Ya existe un rol con ese nombre"},
    },
)
def crear_rol(body: RoleCreate, _: AdminDep, repo: RepoDep) -> RoleOut:
    _validar_permisos(body.permissions)
    if repo.obtener_rol_por_nombre(body.name) is not None:
        raise ConflictoRecurso(f"Ya existe un rol con el nombre '{body.name}'.")
    try:
        rol = repo.crear_rol(
            name=body.name, description=body.description, permissions=body.permissions
        )
    except sqlite3.IntegrityError as exc:  # carrera contra el UNIQUE de name
        raise ConflictoRecurso(f"Ya existe un rol con el nombre '{body.name}'.") from exc
    return _role_out(rol)


@router.patch(
    "/roles/{role_id}",
    response_model=RoleOut,
    summary="Editar un rol (descripción y/o permisos)",
    responses={
        400: {"model": ErrorResponse, "description": "Permisos desconocidos o rol protegido"},
        404: {"model": ErrorResponse, "description": "El rol no existe"},
    },
)
def actualizar_rol(role_id: int, body: RoleUpdate, _: AdminDep, repo: RepoDep) -> RoleOut:
    actual = repo.obtener_rol(role_id)
    if actual is None:
        raise RecursoNoEncontrado(f"No existe el rol con id {role_id}.")
    if actual.name == NOMBRE_ROL_ADMIN and body.permissions is not None:
        raise SolicitudInvalida("No se pueden modificar los permisos del rol administrador.")
    if body.permissions is not None:
        _validar_permisos(body.permissions)
    rol = repo.actualizar_rol(role_id, description=body.description, permissions=body.permissions)
    return _role_out(rol)  # type: ignore[arg-type]


@router.delete(
    "/roles/{role_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar un rol",
    responses={
        400: {"model": ErrorResponse, "description": "Rol protegido o con usuarios asignados"},
        404: {"model": ErrorResponse, "description": "El rol no existe"},
    },
)
def eliminar_rol(role_id: int, _: AdminDep, repo: RepoDep) -> None:
    actual = repo.obtener_rol(role_id)
    if actual is None:
        raise RecursoNoEncontrado(f"No existe el rol con id {role_id}.")
    if actual.name == NOMBRE_ROL_ADMIN:
        raise SolicitudInvalida("No se puede eliminar el rol administrador.")
    if repo.contar_usuarios_de_rol(role_id) > 0:
        raise SolicitudInvalida("No se puede eliminar un rol con usuarios asignados.")
    repo.eliminar_rol(role_id)


# ---------------------------------------------------------------------------
# Usuarios
# ---------------------------------------------------------------------------
@router.get("/users", response_model=list[UserOut], summary="Listar cuentas")
def listar_usuarios(_: AdminDep, repo: RepoDep) -> list[UserOut]:
    return [_user_out(repo, u) for u in repo.listar_usuarios()]


@router.post(
    "/users",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    summary="Crear una cuenta y asignarle un rol",
    responses={
        404: {"model": ErrorResponse, "description": "El rol no existe"},
        409: {"model": ErrorResponse, "description": "Ya existe un usuario con ese id"},
    },
)
def crear_usuario(body: UserCreate, _: AdminDep, repo: RepoDep) -> UserOut:
    if repo.obtener_rol(body.role_id) is None:
        raise RecursoNoEncontrado(f"No existe el rol con id {body.role_id}.")
    if repo.obtener_usuario(body.user_id) is not None:
        raise ConflictoRecurso(f"Ya existe un usuario con el id '{body.user_id}'.")
    try:
        usuario = repo.crear_usuario(
            user_id=body.user_id, password=body.password, role_id=body.role_id
        )
    except sqlite3.IntegrityError as exc:  # carrera contra la PK de user_id
        raise ConflictoRecurso(f"Ya existe un usuario con el id '{body.user_id}'.") from exc
    return _user_out(repo, usuario)


@router.patch(
    "/users/{user_id}",
    response_model=UserOut,
    summary="Editar una cuenta (rol, contraseña o estado)",
    responses={404: {"model": ErrorResponse, "description": "El usuario o el rol no existe"}},
)
def actualizar_usuario(user_id: str, body: UserUpdate, _: AdminDep, repo: RepoDep) -> UserOut:
    if repo.obtener_usuario(user_id) is None:
        raise RecursoNoEncontrado(f"No existe el usuario '{user_id}'.")
    if body.role_id is not None and repo.obtener_rol(body.role_id) is None:
        raise RecursoNoEncontrado(f"No existe el rol con id {body.role_id}.")
    usuario = repo.actualizar_usuario(
        user_id, role_id=body.role_id, password=body.password, is_active=body.is_active
    )
    return _user_out(repo, usuario)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Perfil de cliente (onboarding)
# ---------------------------------------------------------------------------
@router.get("/profile/options", response_model=ProfileOptions, summary="Opciones del onboarding")
def opciones_perfil(_: Annotated[SessionUser, Depends(sesion_actual)]) -> ProfileOptions:
    """Conjuntos de opciones (sector/tamaño/región/moneda) para poblar el formulario."""
    return ProfileOptions()


@router.get(
    "/profile",
    response_model=ProfileOut,
    summary="Perfil de negocio del cliente del usuario",
    responses={404: {"model": ErrorResponse, "description": "Onboarding no completado"}},
)
def obtener_perfil(sesion: Annotated[SessionUser, Depends(sesion_actual)], repo: RepoDep) -> ProfileOut:
    perfil = repo.obtener_perfil(sesion.client_id)
    if perfil is None:
        raise RecursoNoEncontrado("El perfil del negocio aún no se ha completado.")
    return ProfileOut(
        client_id=perfil.client_id,
        business_name=perfil.business_name,
        sector=perfil.sector,
        size=perfil.size,
        region=perfil.region,
        currency=perfil.currency,
    )


@router.put(
    "/profile",
    response_model=ProfileOut,
    summary="Guardar el onboarding del negocio",
    responses={400: {"model": ErrorResponse, "description": "Opción fuera del conjunto permitido"}},
)
def guardar_perfil(
    body: ProfileUpdate, sesion: Annotated[SessionUser, Depends(sesion_actual)], repo: RepoDep
) -> ProfileOut:
    """Persiste el perfil ligado al ``client_id`` del usuario y marca el onboarding como hecho."""
    if body.sector not in SECTORES:
        raise SolicitudInvalida(f"Sector inválido: '{body.sector}'.")
    if body.size not in TAMANOS:
        raise SolicitudInvalida(f"Tamaño inválido: '{body.size}'.")
    if body.region not in REGIONES:
        raise SolicitudInvalida(f"Región inválida: '{body.region}'.")
    if body.currency not in MONEDAS:
        raise SolicitudInvalida(f"Moneda inválida: '{body.currency}'.")
    perfil = repo.guardar_perfil(
        client_id=sesion.client_id,
        business_name=body.business_name,
        sector=body.sector,
        size=body.size,
        region=body.region,
        currency=body.currency,
        owner_user_id=sesion.user_id,
    )
    repo.actualizar_usuario(sesion.user_id, onboarding_done=True)
    return ProfileOut(
        client_id=perfil.client_id,
        business_name=perfil.business_name,
        sector=perfil.sector,
        size=perfil.size,
        region=perfil.region,
        currency=perfil.currency,
    )
