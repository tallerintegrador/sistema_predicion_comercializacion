"""Capa de base de datos del SPC (ADR-0026).

Toda la persistencia (control de acceso, corpus acumulativo por cliente y registro de
modelos entrenados) vive en UNA base de datos accedida vía **SQLAlchemy**. El mismo ORM
sirve a SQLite (tests/dev) y a Postgres/Supabase (producción); la URL se resuelve en
:func:`spc.config.database_url`.

- :mod:`spc.db.orm` — entidades declarativas (tablas) y la ``Base`` compartida.
- :mod:`spc.db.engine` — creación del engine y la fábrica de sesiones.
"""

from __future__ import annotations

from spc.db.engine import crear_engine, crear_todo, obtener_engine, obtener_sesion
from spc.db.orm import (
    Base,
    Dataset,
    ModeloEntrenado,
    Observation,
    Prediction,
    Role,
    RolePermission,
    Tenant,
    TrainingRun,
    User,
)

__all__ = [
    "Base",
    "Dataset",
    "ModeloEntrenado",
    "Observation",
    "Prediction",
    "Role",
    "RolePermission",
    "Tenant",
    "TrainingRun",
    "User",
    "crear_engine",
    "crear_todo",
    "obtener_engine",
    "obtener_sesion",
]
