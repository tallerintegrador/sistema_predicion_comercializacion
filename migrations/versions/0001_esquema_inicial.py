"""Esquema inicial del SPC (ADR-0026): auth + corpus acumulativo + registro de modelos.

Crea TODO el esquema declarado en :data:`spc.db.orm.Base` directamente desde la metadata
del ORM. Es deliberado: garantiza que la base (SQLite o Postgres/Supabase) quede
**idéntica** a las entidades del código, sin re-describir cada tabla a mano (una sola
fuente de verdad). Las migraciones siguientes sí serán ``--autogenerate`` con diffs finos.

Revision ID: 0001_esquema_inicial
Revises:
Create Date: 2026-07-01
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

from spc.db.orm import Base

revision: str = "0001_esquema_inicial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
