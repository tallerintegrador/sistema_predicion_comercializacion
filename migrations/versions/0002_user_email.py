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


def upgrade() -> None:
    op.add_column("users", sa.Column("email", sa.String(length=255), nullable=True))
    op.create_index("ix_users_email", "users", ["email"])


def downgrade() -> None:
    op.drop_index("ix_users_email", table_name="users")
    op.drop_column("users", "email")
