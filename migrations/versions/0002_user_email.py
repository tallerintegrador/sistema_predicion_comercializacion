"""Añade la columna ``email`` a ``users`` (canal para el restablecimiento de contraseña).

Nullable (las cuentas antiguas y las de demo no la tienen) e indexada para buscar por
correo. En SQLite (dev/tests) el ``create_all`` idempotente del arranque ya la crea; esta
migración cubre Postgres/Supabase, donde el esquema no se recrea en caliente.

Revision ID: 0002_user_email
Revises: 0001_esquema_inicial
Create Date: 2026-07-07
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_user_email"
down_revision: str | None = "0001_esquema_inicial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _tiene_columna(bind, tabla: str, columna: str) -> bool:
    """True si ``tabla`` ya tiene ``columna`` en la base actual."""
    insp = sa.inspect(bind)
    return columna in {c["name"] for c in insp.get_columns(tabla)}


def _tiene_indice(bind, tabla: str, indice: str) -> bool:
    insp = sa.inspect(bind)
    return indice in {i["name"] for i in insp.get_indexes(tabla)}


def upgrade() -> None:
    # Idempotente: 0001 crea el esquema con ``Base.metadata.create_all`` desde el ORM ACTUAL,
    # que ya incluye ``email``; en una migración desde cero la columna existe y no debe
    # re-agregarse (rompería con "duplicate column"). En un entorno que se quedó en 0001 sin
    # ``email`` (aplicado antes de añadirla al ORM), esta migración sí la crea.
    bind = op.get_bind()
    if not _tiene_columna(bind, "users", "email"):
        op.add_column("users", sa.Column("email", sa.String(length=255), nullable=True))
    if not _tiene_indice(bind, "users", "ix_users_email"):
        op.create_index("ix_users_email", "users", ["email"])


def downgrade() -> None:
    bind = op.get_bind()
    if _tiene_indice(bind, "users", "ix_users_email"):
        op.drop_index("ix_users_email", table_name="users")
    if _tiene_columna(bind, "users", "email"):
        op.drop_column("users", "email")
