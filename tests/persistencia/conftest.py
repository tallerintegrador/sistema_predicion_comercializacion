"""Fixtures de los tests de persistencia (ADR-0026).

Toda la capa de datos (auth + corpus + registro de modelos) corre sobre **SQLite temporal**,
nunca sobre la base real del repo ni sobre Supabase. Dos guardas:

- ``_storage_desactivado`` (autouse): borra las variables ``SUPABASE_*`` para que el registro
  de modelos caiga a **disco local** y jamás intente subir artefactos al bucket real.
- ``engine``: un engine SQLite de archivo temporal por test, con el esquema ya creado.
"""

from __future__ import annotations

import pytest
from sqlalchemy import Engine

from spc.db.engine import crear_engine, crear_todo


@pytest.fixture(autouse=True)
def _storage_desactivado(monkeypatch) -> None:
    """Fuerza el fallback a disco: sin ``SUPABASE_URL``/``SUPABASE_KEY`` no hay Storage."""
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)


@pytest.fixture
def engine(tmp_path) -> Engine:
    """Engine SQLite aislado por test (archivo temporal) con el esquema del ORM creado."""
    eng = crear_engine(f"sqlite:///{(tmp_path / 'persistencia.db').as_posix()}")
    crear_todo(eng)
    return eng
