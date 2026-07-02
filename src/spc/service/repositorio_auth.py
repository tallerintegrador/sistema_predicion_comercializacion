"""Persistencia del control de acceso por roles (ADR-0014) sobre **SQLAlchemy** (ADR-0026).

Antes usaba ``sqlite3`` directo; ahora se apoya en el ORM compartido de :mod:`spc.db`, de
modo que auth, corpus y modelos viven en **una sola base de datos** (SQLite en dev/tests,
Postgres/Supabase en producción). La **interfaz pública no cambia**: mismos métodos,
mismas dataclasses de salida (``Rol``, ``Usuario``, ``PerfilCliente``) y misma siembra
idempotente del rol administrador y las dos cuentas de DEMOSTRACIÓN (id 256317 y 256370,
contraseña = id, **hasheada**).

Dos formas de construir el repositorio:

- :meth:`RepositorioAuth.crear` (compatibilidad): abre una base propia en una ruta
  (SQLite) — la usan los tests con un archivo temporal.
- :meth:`RepositorioAuth.desde_engine`: reutiliza el engine global de la app para que todo
  comparta la misma base (lo usa el arranque en :mod:`spc.api.main`).
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import Engine, delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from spc.config import ADMIN_SEED_IDS
from spc.db.engine import crear_engine, crear_todo
from spc.db.orm import Role, RolePermission, Tenant, User
from spc.service import permisos
from spc.service.seguridad import hash_password
from spc.training.almacen import slug_cliente
from spc.utils.logging import get_logger

log = get_logger("service.repositorio_auth")

NOMBRE_ROL_ADMIN = "administrator"


def _ahora_iso() -> str:
    return datetime.now(UTC).isoformat()


# ---------------------------------------------------------------------------
# Vistas de solo lectura (sin la contraseña; lo que sale hacia la API)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Rol:
    """Un rol con su conjunto de permisos (claves del vocabulario controlado)."""

    id: int
    name: str
    description: str | None
    permissions: list[str]


@dataclass(frozen=True)
class Usuario:
    """Una cuenta SIN la contraseña (lo que la API entrega y usa para autorizar)."""

    user_id: str
    role_id: int
    client_id: str
    is_active: bool
    onboarding_done: bool
    created_at: str


@dataclass(frozen=True)
class PerfilCliente:
    """Perfil de negocio del onboarding, ligado al ``client_id``."""

    client_id: str
    business_name: str
    sector: str
    size: str
    region: str
    currency: str
    owner_user_id: str | None
    created_at: str


class RepositorioAuth:
    """Almacén (SQLAlchemy) de usuarios, roles, permisos y perfiles de cliente (ADR-0014)."""

    def __init__(self, engine: Engine, *, poseido: bool) -> None:
        self._engine = engine
        self._poseido = poseido  # ¿este repo es dueño del engine (debe cerrarlo)?
        self._Session: sessionmaker[Session] = sessionmaker(
            bind=engine, expire_on_commit=False, future=True
        )
        self._lock = threading.Lock()
        crear_todo(engine)
        self._sembrar_admins()

    # -- Construcción ------------------------------------------------------
    @classmethod
    def crear(cls, db_path: str | Path) -> RepositorioAuth:
        """Abre (o crea) una base SQLite propia en ``db_path`` (compat; usada por tests)."""
        ruta = str(db_path)
        url = "sqlite://" if ruta == ":memory:" else f"sqlite:///{Path(ruta).as_posix()}"
        return cls(crear_engine(url), poseido=True)

    @classmethod
    def desde_engine(cls, engine: Engine) -> RepositorioAuth:
        """Reutiliza un engine ya abierto (el global de la app); no lo cierra al terminar."""
        return cls(engine, poseido=False)

    @property
    def engine(self) -> Engine:
        """El engine subyacente (para que corpus/modelos compartan la misma base)."""
        return self._engine

    @contextmanager
    def _sesion(self) -> Iterator[Session]:
        """Abre una sesión, hace commit al salir sin error y siempre la cierra."""
        sesion = self._Session()
        try:
            yield sesion
            sesion.commit()
        except Exception:
            sesion.rollback()
            raise
        finally:
            sesion.close()

    # -- Siembra idempotente ----------------------------------------------
    def _sembrar_admins(self) -> None:
        """Crea el rol administrador (todos los permisos) y las cuentas de DEMO si faltan."""
        rol_id = self._asegurar_rol_admin()
        for user_id in ADMIN_SEED_IDS:
            self._asegurar_usuario_admin(user_id, rol_id)

    def _asegurar_rol_admin(self) -> int:
        with self._lock, self._sesion() as s:
            rol = s.scalar(select(Role).where(Role.name == NOMBRE_ROL_ADMIN))
            nuevo = rol is None
            if rol is None:
                rol = Role(
                    name=NOMBRE_ROL_ADMIN,
                    description="Acceso total a la plataforma.",
                    created_at=_ahora_iso(),
                )
                s.add(rol)
                s.flush()  # asigna rol.id
            # El administrador SIEMPRE tiene todos los permisos vigentes (si el catálogo creció).
            existentes = {
                p.permission
                for p in s.scalars(
                    select(RolePermission).where(RolePermission.role_id == rol.id)
                )
            }
            for clave in permisos.permisos_administrador():
                if clave not in existentes:
                    s.add(RolePermission(role_id=rol.id, permission=clave))
            rol_id = int(rol.id)
            if nuevo:
                log.info("Rol administrador sembrado (id=%s).", rol_id)
        return rol_id

    def _asegurar_usuario_admin(self, user_id: str, rol_id: int) -> None:
        with self._lock, self._sesion() as s:
            if s.get(User, user_id) is not None:
                return
            # Credencial de DEMO: contraseña inicial = id, almacenada HASHEADA (ADR-0014).
            s.add(
                User(
                    user_id=user_id,
                    password_hash=hash_password(user_id),
                    role_id=rol_id,
                    client_id=slug_cliente(user_id),
                    is_active=True,
                    onboarding_done=True,
                    created_at=_ahora_iso(),
                )
            )
            log.info("Cuenta administrador de DEMO sembrada (id=%s).", user_id)

    # -- Roles -------------------------------------------------------------
    def listar_roles(self) -> list[Rol]:
        with self._sesion() as s:
            filas = s.scalars(select(Role).order_by(Role.id)).all()
            return [self._rol_desde_orm(s, r) for r in filas]

    def obtener_rol(self, role_id: int) -> Rol | None:
        with self._sesion() as s:
            r = s.get(Role, role_id)
            return self._rol_desde_orm(s, r) if r else None

    def obtener_rol_por_nombre(self, name: str) -> Rol | None:
        with self._sesion() as s:
            r = s.scalar(select(Role).where(Role.name == name))
            return self._rol_desde_orm(s, r) if r else None

    @staticmethod
    def _rol_desde_orm(s: Session, r: Role) -> Rol:
        perms = s.scalars(
            select(RolePermission.permission)
            .where(RolePermission.role_id == r.id)
            .order_by(RolePermission.permission)
        ).all()
        return Rol(id=int(r.id), name=r.name, description=r.description, permissions=list(perms))

    def crear_rol(self, *, name: str, description: str | None, permissions: list[str]) -> Rol:
        with self._lock, self._sesion() as s:
            rol = Role(name=name, description=description, created_at=_ahora_iso())
            s.add(rol)
            s.flush()
            self._reemplazar_permisos(s, int(rol.id), permissions)
            rol_id = int(rol.id)
        return self.obtener_rol(rol_id)  # type: ignore[return-value]

    def actualizar_rol(
        self,
        role_id: int,
        *,
        description: str | None = None,
        permissions: list[str] | None = None,
    ) -> Rol | None:
        with self._lock, self._sesion() as s:
            rol = s.get(Role, role_id)
            if rol is None:
                return None
            if description is not None:
                rol.description = description
            if permissions is not None:
                self._reemplazar_permisos(s, role_id, permissions)
        return self.obtener_rol(role_id)

    @staticmethod
    def _reemplazar_permisos(s: Session, role_id: int, permissions: list[str]) -> None:
        s.execute(delete(RolePermission).where(RolePermission.role_id == role_id))
        for clave in dict.fromkeys(permissions):
            s.add(RolePermission(role_id=role_id, permission=clave))

    def eliminar_rol(self, role_id: int) -> None:
        with self._lock, self._sesion() as s:
            s.execute(delete(RolePermission).where(RolePermission.role_id == role_id))
            s.execute(delete(Role).where(Role.id == role_id))

    def contar_usuarios_de_rol(self, role_id: int) -> int:
        with self._sesion() as s:
            n = s.scalar(select(func.count()).select_from(User).where(User.role_id == role_id))
            return int(n or 0)

    # -- Usuarios ----------------------------------------------------------
    def listar_usuarios(self) -> list[Usuario]:
        with self._sesion() as s:
            filas = s.scalars(select(User).order_by(User.user_id)).all()
            return [self._usuario_desde_orm(u) for u in filas]

    def obtener_usuario(self, user_id: str) -> Usuario | None:
        with self._sesion() as s:
            u = s.get(User, user_id)
            return self._usuario_desde_orm(u) if u else None

    def obtener_password_hash(self, user_id: str) -> str | None:
        with self._sesion() as s:
            return s.scalar(select(User.password_hash).where(User.user_id == user_id))

    @staticmethod
    def _usuario_desde_orm(u: User) -> Usuario:
        return Usuario(
            user_id=u.user_id,
            role_id=int(u.role_id),
            client_id=u.client_id,
            is_active=bool(u.is_active),
            onboarding_done=bool(u.onboarding_done),
            created_at=u.created_at,
        )

    def crear_usuario(
        self, *, user_id: str, password: str, role_id: int, client_id: str | None = None
    ) -> Usuario:
        """Crea una cuenta con la contraseña HASHEADA. ``client_id`` deriva del id si falta."""
        cid = client_id or slug_cliente(user_id)
        with self._lock, self._sesion() as s:
            s.add(
                User(
                    user_id=user_id,
                    password_hash=hash_password(password),
                    role_id=role_id,
                    client_id=cid,
                    is_active=True,
                    onboarding_done=False,
                    created_at=_ahora_iso(),
                )
            )
        return self.obtener_usuario(user_id)  # type: ignore[return-value]

    def actualizar_usuario(
        self,
        user_id: str,
        *,
        role_id: int | None = None,
        password: str | None = None,
        is_active: bool | None = None,
        onboarding_done: bool | None = None,
    ) -> Usuario | None:
        with self._lock, self._sesion() as s:
            u = s.get(User, user_id)
            if u is None:
                return None
            if role_id is not None:
                u.role_id = role_id
            if password is not None:
                u.password_hash = hash_password(password)
            if is_active is not None:
                u.is_active = bool(is_active)
            if onboarding_done is not None:
                u.onboarding_done = bool(onboarding_done)
        return self.obtener_usuario(user_id)

    # -- Perfil de cliente (onboarding) -----------------------------------
    def obtener_perfil(self, client_id: str) -> PerfilCliente | None:
        with self._sesion() as s:
            t = s.get(Tenant, client_id)
            if t is None:
                return None
            return PerfilCliente(
                client_id=t.client_id,
                business_name=t.business_name,
                sector=t.sector,
                size=t.size,
                region=t.region,
                currency=t.currency,
                owner_user_id=t.owner_user_id,
                created_at=t.created_at,
            )

    def guardar_perfil(
        self,
        *,
        client_id: str,
        business_name: str,
        sector: str,
        size: str,
        region: str,
        currency: str,
        owner_user_id: str | None,
    ) -> PerfilCliente:
        """Inserta o reemplaza el perfil del cliente (onboarding idempotente)."""
        with self._lock, self._sesion() as s:
            t = s.get(Tenant, client_id)
            if t is None:
                t = Tenant(client_id=client_id, created_at=_ahora_iso())
                s.add(t)
            t.business_name = business_name
            t.sector = sector
            t.size = size
            t.region = region
            t.currency = currency
            t.owner_user_id = owner_user_id
        return self.obtener_perfil(client_id)  # type: ignore[return-value]

    # -- Ciclo de vida -----------------------------------------------------
    def cerrar(self) -> None:
        if not self._poseido:
            return  # el engine es compartido: no lo cerramos aquí
        try:
            self._engine.dispose()
        except Exception as exc:  # noqa: BLE001 - cierre best-effort
            log.warning("No se pudo cerrar la base de auth: %s", exc)
