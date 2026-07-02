"""Copia el control de acceso del SQLite anterior a la base configurada (ADR-0027).

Lee el archivo ``spc.db`` legado (esquema de ADR-0014: ``roles``, ``role_permissions``,
``users``, ``client_profiles``) y **vuelca** su contenido en la base destino que resuelve
``spc.config.database_url()`` (Postgres/Supabase o el SQLite nuevo), usando el ORM. Es
**idempotente**: no pisa filas ya existentes (por PK/único). El corpus y los modelos NO se
migran (el corpus antiguo fue retirado; los modelos se re-entrenan).

Uso:

    python scripts/migrar_sqlite_a_postgres.py --sqlite data/spc.db
    SPC_DATABASE_URL=postgresql+psycopg://... python scripts/migrar_sqlite_a_postgres.py
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

from sqlalchemy import select

from spc.db.engine import obtener_engine
from spc.db.orm import Role, RolePermission, Tenant, User
from spc.service.repositorio_auth import RepositorioAuth


def _filas(con: sqlite3.Connection, tabla: str) -> list[sqlite3.Row]:
    """Lee todas las filas de ``tabla`` si existe; lista vacía si la tabla no está."""
    existe = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (tabla,)
    ).fetchone()
    if not existe:
        return []
    return con.execute(f"SELECT * FROM {tabla}").fetchall()


def migrar(sqlite_path: Path) -> dict[str, int]:
    """Copia roles/permisos/usuarios/perfiles del SQLite legado a la base destino."""
    if not sqlite_path.exists():
        raise SystemExit(f"No existe el SQLite de origen: {sqlite_path}")

    origen = sqlite3.connect(str(sqlite_path))
    origen.row_factory = sqlite3.Row

    # Asegura el esquema destino (crea tablas si faltan) reutilizando la siembra de admins.
    engine = obtener_engine()
    RepositorioAuth.desde_engine(engine)

    contadores = {"roles": 0, "role_permissions": 0, "users": 0, "tenants": 0}
    from sqlalchemy.orm import Session

    with Session(engine) as s, s.begin():
        for r in _filas(origen, "roles"):
            if s.get(Role, int(r["id"])) is None:
                s.add(Role(id=int(r["id"]), name=r["name"], description=r["description"],
                           created_at=r["created_at"]))
                contadores["roles"] += 1
        s.flush()
        existentes_perm = {
            (rp.role_id, rp.permission) for rp in s.scalars(select(RolePermission))
        }
        for r in _filas(origen, "role_permissions"):
            clave = (int(r["role_id"]), r["permission"])
            if clave not in existentes_perm:
                s.add(RolePermission(role_id=clave[0], permission=clave[1]))
                contadores["role_permissions"] += 1
        for r in _filas(origen, "users"):
            if s.get(User, r["user_id"]) is None:
                s.add(User(
                    user_id=r["user_id"], password_hash=r["password_hash"],
                    role_id=int(r["role_id"]), client_id=r["client_id"],
                    is_active=bool(r["is_active"]), onboarding_done=bool(r["onboarding_done"]),
                    created_at=r["created_at"],
                ))
                contadores["users"] += 1
        for r in _filas(origen, "client_profiles"):
            if s.get(Tenant, r["client_id"]) is None:
                s.add(Tenant(
                    client_id=r["client_id"], business_name=r["business_name"],
                    sector=r["sector"], size=r["size"], region=r["region"],
                    currency=r["currency"], owner_user_id=r["owner_user_id"],
                    created_at=r["created_at"],
                ))
                contadores["tenants"] += 1

    origen.close()
    return contadores


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Migra el control de acceso del SQLite legado a la base configurada.")
    p.add_argument("--sqlite", default="data/spc.db", help="Ruta del SQLite de origen (default: data/spc.db).")
    args = p.parse_args(argv)

    contadores = migrar(Path(args.sqlite))
    print("Migración completada (filas nuevas insertadas):")
    for tabla, n in contadores.items():
        print(f"  {tabla}: {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
