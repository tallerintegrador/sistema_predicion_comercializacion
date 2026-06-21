"""Persistencia del control de acceso por roles (ADR-0014), sobre el **SQLite existente**.

Misma tecnología y patrón que ``RepositorioPredicciones`` (``sqlite3`` de la biblioteca
estándar + ``threading.Lock``, sin dependencias nuevas): conviven en el **mismo archivo
``spc.db``** pero en tablas distintas. Aquí viven cuatro tablas:

- ``roles`` + ``role_permissions``: roles y el conjunto de permisos de cada uno
  (vocabulario controlado en :mod:`spc.service.permisos`).
- ``users``: las cuentas (id de login, contraseña **hasheada**, rol, ``client_id`` y
  estado de onboarding).
- ``client_profiles``: el perfil de negocio del onboarding, ligado al ``client_id``.

Al abrirse, **siembra de forma idempotente** el rol administrador (con todos los permisos)
y las dos cuentas administrador de DEMOSTRACIÓN (id 256317 y 256370, contraseña = id,
**hasheada**). La siembra usa ``INSERT OR IGNORE``: repetir el arranque no la duplica ni
pisa cambios posteriores.
"""

from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from spc.config import ADMIN_SEED_IDS
from spc.service import permisos
from spc.service.seguridad import hash_password
from spc.training.almacen import slug_cliente
from spc.utils.logging import get_logger

log = get_logger("service.repositorio_auth")

NOMBRE_ROL_ADMIN = "administrator"

_DDL = """
CREATE TABLE IF NOT EXISTS roles (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT UNIQUE NOT NULL,
    description TEXT,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS role_permissions (
    role_id    INTEGER NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    permission TEXT NOT NULL,
    PRIMARY KEY (role_id, permission)
);

CREATE TABLE IF NOT EXISTS users (
    user_id         TEXT PRIMARY KEY,
    password_hash   TEXT NOT NULL,
    role_id         INTEGER NOT NULL REFERENCES roles(id),
    client_id       TEXT NOT NULL,
    is_active       INTEGER NOT NULL DEFAULT 1,
    onboarding_done INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS client_profiles (
    client_id     TEXT PRIMARY KEY,
    business_name TEXT NOT NULL,
    sector        TEXT NOT NULL,
    size          TEXT NOT NULL,
    region        TEXT NOT NULL,
    currency      TEXT NOT NULL,
    owner_user_id TEXT,
    created_at    TEXT NOT NULL
);
"""


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
    """Almacén SQLite de usuarios, roles, permisos y perfiles de cliente (ADR-0014)."""

    def __init__(self, conexion: sqlite3.Connection) -> None:
        self._con = conexion
        self._con.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._con.executescript(_DDL)
            self._con.commit()
        self._sembrar_admins()

    # -- Construcción ------------------------------------------------------
    @classmethod
    def crear(cls, db_path: str | Path) -> RepositorioAuth:
        """Abre (o crea) la base en ``db_path`` y garantiza el esquema + la siembra."""
        ruta = str(db_path)
        if ruta != ":memory:":
            Path(ruta).parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(ruta, check_same_thread=False)
        con.execute("PRAGMA foreign_keys = ON")
        return cls(con)

    # -- Siembra idempotente ----------------------------------------------
    def _sembrar_admins(self) -> None:
        """Crea el rol administrador (todos los permisos) y las cuentas de DEMO si faltan."""
        rol_id = self._asegurar_rol_admin()
        for user_id in ADMIN_SEED_IDS:
            self._asegurar_usuario_admin(user_id, rol_id)

    def _asegurar_rol_admin(self) -> int:
        with self._lock:
            cur = self._con.execute(
                "INSERT OR IGNORE INTO roles (name, description, created_at) VALUES (?, ?, ?)",
                (NOMBRE_ROL_ADMIN, "Acceso total a la plataforma.", _ahora_iso()),
            )
            fila = self._con.execute(
                "SELECT id FROM roles WHERE name = ?", (NOMBRE_ROL_ADMIN,)
            ).fetchone()
            rol_id = int(fila["id"])
            # Asegura que el rol administrador tenga SIEMPRE todos los permisos vigentes
            # (si el catálogo de permisos creció, el admin los recibe).
            for clave in permisos.permisos_administrador():
                self._con.execute(
                    "INSERT OR IGNORE INTO role_permissions (role_id, permission) VALUES (?, ?)",
                    (rol_id, clave),
                )
            self._con.commit()
            if cur.rowcount:
                log.info("Rol administrador sembrado (id=%s).", rol_id)
        return rol_id

    def _asegurar_usuario_admin(self, user_id: str, rol_id: int) -> None:
        with self._lock:
            existe = self._con.execute(
                "SELECT 1 FROM users WHERE user_id = ?", (user_id,)
            ).fetchone()
            if existe:
                return
            # Credencial de DEMO: contraseña inicial = id, almacenada HASHEADA (ADR-0014).
            self._con.execute(
                """
                INSERT INTO users
                    (user_id, password_hash, role_id, client_id, is_active, onboarding_done, created_at)
                VALUES (?, ?, ?, ?, 1, 1, ?)
                """,
                (user_id, hash_password(user_id), rol_id, slug_cliente(user_id), _ahora_iso()),
            )
            self._con.commit()
            log.info("Cuenta administrador de DEMO sembrada (id=%s).", user_id)

    # -- Roles -------------------------------------------------------------
    def listar_roles(self) -> list[Rol]:
        with self._lock:
            filas = self._con.execute("SELECT * FROM roles ORDER BY id").fetchall()
            return [self._rol_desde_fila(f) for f in filas]

    def obtener_rol(self, role_id: int) -> Rol | None:
        with self._lock:
            fila = self._con.execute("SELECT * FROM roles WHERE id = ?", (role_id,)).fetchone()
            return self._rol_desde_fila(fila) if fila else None

    def obtener_rol_por_nombre(self, name: str) -> Rol | None:
        with self._lock:
            fila = self._con.execute("SELECT * FROM roles WHERE name = ?", (name,)).fetchone()
            return self._rol_desde_fila(fila) if fila else None

    def _rol_desde_fila(self, fila: sqlite3.Row) -> Rol:
        perms = self._con.execute(
            "SELECT permission FROM role_permissions WHERE role_id = ? ORDER BY permission",
            (fila["id"],),
        ).fetchall()
        return Rol(
            id=int(fila["id"]),
            name=fila["name"],
            description=fila["description"],
            permissions=[p["permission"] for p in perms],
        )

    def crear_rol(self, *, name: str, description: str | None, permissions: list[str]) -> Rol:
        with self._lock:
            cur = self._con.execute(
                "INSERT INTO roles (name, description, created_at) VALUES (?, ?, ?)",
                (name, description, _ahora_iso()),
            )
            rol_id = int(cur.lastrowid or 0)
            self._reemplazar_permisos(rol_id, permissions)
            self._con.commit()
        return self.obtener_rol(rol_id)  # type: ignore[return-value]

    def actualizar_rol(
        self,
        role_id: int,
        *,
        description: str | None = None,
        permissions: list[str] | None = None,
    ) -> Rol | None:
        with self._lock:
            if self._con.execute("SELECT 1 FROM roles WHERE id = ?", (role_id,)).fetchone() is None:
                return None
            if description is not None:
                self._con.execute(
                    "UPDATE roles SET description = ? WHERE id = ?", (description, role_id)
                )
            if permissions is not None:
                self._reemplazar_permisos(role_id, permissions)
            self._con.commit()
        return self.obtener_rol(role_id)

    def _reemplazar_permisos(self, role_id: int, permissions: list[str]) -> None:
        self._con.execute("DELETE FROM role_permissions WHERE role_id = ?", (role_id,))
        self._con.executemany(
            "INSERT OR IGNORE INTO role_permissions (role_id, permission) VALUES (?, ?)",
            [(role_id, clave) for clave in dict.fromkeys(permissions)],
        )

    def eliminar_rol(self, role_id: int) -> None:
        with self._lock:
            self._con.execute("DELETE FROM role_permissions WHERE role_id = ?", (role_id,))
            self._con.execute("DELETE FROM roles WHERE id = ?", (role_id,))
            self._con.commit()

    def contar_usuarios_de_rol(self, role_id: int) -> int:
        with self._lock:
            fila = self._con.execute(
                "SELECT COUNT(*) AS n FROM users WHERE role_id = ?", (role_id,)
            ).fetchone()
            return int(fila["n"])

    # -- Usuarios ----------------------------------------------------------
    def listar_usuarios(self) -> list[Usuario]:
        with self._lock:
            filas = self._con.execute("SELECT * FROM users ORDER BY user_id").fetchall()
            return [self._usuario_desde_fila(f) for f in filas]

    def obtener_usuario(self, user_id: str) -> Usuario | None:
        with self._lock:
            fila = self._con.execute(
                "SELECT * FROM users WHERE user_id = ?", (user_id,)
            ).fetchone()
            return self._usuario_desde_fila(fila) if fila else None

    def obtener_password_hash(self, user_id: str) -> str | None:
        with self._lock:
            fila = self._con.execute(
                "SELECT password_hash FROM users WHERE user_id = ?", (user_id,)
            ).fetchone()
            return fila["password_hash"] if fila else None

    @staticmethod
    def _usuario_desde_fila(fila: sqlite3.Row) -> Usuario:
        return Usuario(
            user_id=fila["user_id"],
            role_id=int(fila["role_id"]),
            client_id=fila["client_id"],
            is_active=bool(fila["is_active"]),
            onboarding_done=bool(fila["onboarding_done"]),
            created_at=fila["created_at"],
        )

    def crear_usuario(
        self, *, user_id: str, password: str, role_id: int, client_id: str | None = None
    ) -> Usuario:
        """Crea una cuenta con la contraseña HASHEADA. ``client_id`` deriva del id si falta."""
        cid = client_id or slug_cliente(user_id)
        with self._lock:
            self._con.execute(
                """
                INSERT INTO users
                    (user_id, password_hash, role_id, client_id, is_active, onboarding_done, created_at)
                VALUES (?, ?, ?, ?, 1, 0, ?)
                """,
                (user_id, hash_password(password), role_id, cid, _ahora_iso()),
            )
            self._con.commit()
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
        sets: list[str] = []
        valores: list[object] = []
        if role_id is not None:
            sets.append("role_id = ?")
            valores.append(role_id)
        if password is not None:
            sets.append("password_hash = ?")
            valores.append(hash_password(password))
        if is_active is not None:
            sets.append("is_active = ?")
            valores.append(int(is_active))
        if onboarding_done is not None:
            sets.append("onboarding_done = ?")
            valores.append(int(onboarding_done))
        with self._lock:
            if self._con.execute(
                "SELECT 1 FROM users WHERE user_id = ?", (user_id,)
            ).fetchone() is None:
                return None
            if sets:
                valores.append(user_id)
                self._con.execute(
                    f"UPDATE users SET {', '.join(sets)} WHERE user_id = ?", valores
                )
                self._con.commit()
        return self.obtener_usuario(user_id)

    # -- Perfil de cliente (onboarding) -----------------------------------
    def obtener_perfil(self, client_id: str) -> PerfilCliente | None:
        with self._lock:
            fila = self._con.execute(
                "SELECT * FROM client_profiles WHERE client_id = ?", (client_id,)
            ).fetchone()
        if fila is None:
            return None
        return PerfilCliente(
            client_id=fila["client_id"],
            business_name=fila["business_name"],
            sector=fila["sector"],
            size=fila["size"],
            region=fila["region"],
            currency=fila["currency"],
            owner_user_id=fila["owner_user_id"],
            created_at=fila["created_at"],
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
        with self._lock:
            existente = self._con.execute(
                "SELECT created_at FROM client_profiles WHERE client_id = ?", (client_id,)
            ).fetchone()
            creado = existente["created_at"] if existente else _ahora_iso()
            self._con.execute(
                """
                INSERT OR REPLACE INTO client_profiles
                    (client_id, business_name, sector, size, region, currency, owner_user_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (client_id, business_name, sector, size, region, currency, owner_user_id, creado),
            )
            self._con.commit()
        return self.obtener_perfil(client_id)  # type: ignore[return-value]

    # -- Ciclo de vida -----------------------------------------------------
    def cerrar(self) -> None:
        with self._lock:
            try:
                self._con.close()
            except Exception as exc:  # noqa: BLE001 - cierre best-effort
                log.warning("No se pudo cerrar la base de auth: %s", exc)
