"""Esquemas del **control de acceso por roles** (ADR-0014).

Igual que el resto del contrato de la API, los **campos, parámetros y enums van en
inglés** (``user_id``, ``password``, ``role``, ``permissions``, ``business_name`` …); las
*descripciones* y las etiquetas de la UI van en español. Estos endpoints son
**operacionales** (autenticación, usuarios, perfil), no forman parte del contrato de datos
de predicción v1.0.1, pero respetan su mismo estilo de nombres y de error uniforme.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# Conjuntos de opciones del onboarding servidos por el backend (la UI NO los clava): el
# endpoint GET /profile/options los expone para poblar los desplegables. Son metadatos de
# negocio, no parámetros del modelo.
SECTORES: tuple[str, ...] = (
    "retail",
    "wholesale",
    "supermarket",
    "pharmacy",
    "hardware",
    "food_service",
    "other",
)
TAMANOS: tuple[str, ...] = ("micro", "small", "medium")
REGIONES: tuple[str, ...] = (
    "north_america",
    "central_america",
    "south_america",
    "europe",
    "africa",
    "asia",
    "oceania",
)
MONEDAS: tuple[str, ...] = ("USD", "EUR", "PEN", "COP", "MXN", "CLP", "ARS", "BRL")


# ---------------------------------------------------------------------------
# Sesión / identidad
# ---------------------------------------------------------------------------
class LoginRequest(BaseModel):
    """Credenciales de ingreso: id de usuario y contraseña."""

    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(min_length=1, description="Identificador de inicio de sesión.")
    password: str = Field(min_length=1, description="Contraseña (se verifica contra el hash).")


class SessionUser(BaseModel):
    """Identidad efectiva del usuario autenticado (lo que la UI usa para filtrar acceso)."""

    user_id: str = Field(description="Id del usuario.")
    role_id: int = Field(description="Id del rol asignado.")
    role: str = Field(description="Nombre del rol asignado.")
    permissions: list[str] = Field(description="Claves de permiso efectivas del rol.")
    client_id: str = Field(description="Cliente asociado (clave de corpus/entrenamiento).")
    onboarding_done: bool = Field(description="¿Completó el onboarding del negocio?")


class LoginResponse(BaseModel):
    """Token de sesión emitido tras un login correcto."""

    token: str = Field(description="Token de sesión firmado (enviar como 'Authorization: Bearer').")
    token_type: Literal["bearer"] = Field(default="bearer", description="Esquema del token.")
    expires_in: int = Field(description="Vida útil del token en segundos.")
    user: SessionUser = Field(description="Identidad y permisos del usuario.")


# ---------------------------------------------------------------------------
# Permisos
# ---------------------------------------------------------------------------
class PermissionOut(BaseModel):
    """Una entrada del catálogo de permisos (clave en inglés + etiqueta en español)."""

    key: str = Field(description="Clave del permiso (p. ej. 'module:sales', 'action:forecast').")
    label: str = Field(description="Etiqueta legible (español) para la UI.")
    group: Literal["module", "action"] = Field(description="Grupo del permiso.")


class PermissionCatalog(BaseModel):
    """Catálogo de permisos disponibles para construir/editar roles."""

    permissions: list[PermissionOut] = Field(description="Permisos disponibles (módulos + acciones).")


# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------
class RoleOut(BaseModel):
    """Un rol con su conjunto de permisos."""

    id: int
    name: str
    description: str | None = None
    permissions: list[str] = Field(default_factory=list)


class RoleCreate(BaseModel):
    """Alta de un rol."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=60, description="Nombre único del rol.")
    description: str | None = Field(default=None, max_length=200)
    permissions: list[str] = Field(default_factory=list, description="Claves de permiso del rol.")


class RoleUpdate(BaseModel):
    """Edición de un rol (campos omitidos no se tocan)."""

    model_config = ConfigDict(extra="forbid")

    description: str | None = Field(default=None, max_length=200)
    permissions: list[str] | None = Field(default=None, description="Reemplaza los permisos del rol.")


# ---------------------------------------------------------------------------
# Usuarios
# ---------------------------------------------------------------------------
class UserOut(BaseModel):
    """Una cuenta (sin la contraseña)."""

    user_id: str
    role_id: int
    role: str = Field(description="Nombre del rol asignado.")
    client_id: str
    is_active: bool
    onboarding_done: bool
    created_at: str


class UserCreate(BaseModel):
    """Alta de una cuenta por un administrador."""

    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(min_length=1, max_length=60, description="Id de inicio de sesión.")
    password: str = Field(min_length=4, max_length=128, description="Contraseña inicial.")
    role_id: int = Field(description="Rol a asignar.")


class UserUpdate(BaseModel):
    """Edición de una cuenta (rol, contraseña o estado)."""

    model_config = ConfigDict(extra="forbid")

    role_id: int | None = None
    password: str | None = Field(default=None, min_length=4, max_length=128)
    is_active: bool | None = None


# ---------------------------------------------------------------------------
# Perfil de cliente (onboarding)
# ---------------------------------------------------------------------------
class ProfileOptions(BaseModel):
    """Opciones disponibles para el onboarding (servidas por el backend, sin hardcode en UI)."""

    sectors: list[str] = Field(default_factory=lambda: list(SECTORES))
    sizes: list[str] = Field(default_factory=lambda: list(TAMANOS))
    regions: list[str] = Field(default_factory=lambda: list(REGIONES))
    currencies: list[str] = Field(default_factory=lambda: list(MONEDAS))


class ProfileOut(BaseModel):
    """Perfil de negocio del cliente (resultado del onboarding)."""

    client_id: str
    business_name: str
    sector: str
    size: str
    region: str
    currency: str


class ProfileUpdate(BaseModel):
    """Datos del onboarding del negocio (primer ingreso de un usuario no administrador)."""

    model_config = ConfigDict(extra="forbid")

    business_name: str = Field(min_length=1, max_length=120, description="Nombre del negocio/empresa.")
    sector: str = Field(description="Rubro/sector del negocio.")
    size: str = Field(description="Tamaño aproximado.")
    region: str = Field(description="Región.")
    currency: str = Field(description="Moneda.")
