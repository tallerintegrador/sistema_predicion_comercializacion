"""Tests de las migraciones Alembic (ADR-0026).

Verifican que ``alembic upgrade head`` sobre una base SQLite temporal cree el esquema que el
ORM declara: todas las tablas de ``Base.metadata`` deben existir tras migrar, y la tabla de
control ``alembic_version`` debe quedar sellada. Así el despliegue (Postgres) y el desarrollo
(SQLite) parten del mismo esquema versionado, no de un ``create_all`` a ciegas.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, inspect

from spc.db.orm import Base


@pytest.fixture
def _url_temporal(tmp_path, monkeypatch) -> str:
    """Apunta la base de Alembic a un SQLite temporal (env.py lee SPC_DATABASE_URL)."""
    url = f"sqlite:///{(tmp_path / 'migrada.db').as_posix()}"
    monkeypatch.setenv("SPC_DATABASE_URL", url)
    return url


def test_upgrade_head_crea_todas_las_tablas(_url_temporal) -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")

    engine = create_engine(_url_temporal)
    tablas = set(inspect(engine).get_table_names())
    engine.dispose()

    # Toda tabla declarada por el ORM quedó creada por las migraciones.
    esperadas = set(Base.metadata.tables)
    assert esperadas <= tablas, f"Faltan tablas tras migrar: {esperadas - tablas}"
    # Alembic dejó su sello de versión.
    assert "alembic_version" in tablas
