"""Fixtures de los tests de la API.

Los motores ``/auto/*`` (ADR-0023) y ``/v2/*`` (ADR-0024/0025) entrenan **en el momento**
sobre los datos que envía el cliente, así que la app se construye **sin artefactos**. El
control de acceso se desactiva por defecto; los tests de auth lo activan con su propia base
temporal.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from spc.api.main import crear_app
from spc.db.engine import crear_engine


@pytest.fixture(autouse=True)
def _auth_desactivada_por_defecto(monkeypatch) -> None:
    """Por defecto los tests de la API no exigen autenticación.

    ``SPC_AUTH_ENABLED=0``: los endpoints protegidos no piden credenciales, de modo que la
    suite de predicción corre sin tokens. ``test_auth.py`` activa la bandera y crea su propia
    app con un repositorio de auth temporal.
    """
    monkeypatch.setenv("SPC_AUTH_ENABLED", "0")


@pytest.fixture
def client(tmp_path) -> object:
    """`TestClient` sobre la app (motores en el momento; sin registro de artefactos).

    La carpeta de la caché de modelos agnósticos (ADR-0023) se apunta a un temporal por test,
    para que ningún test escriba en ``models/clientes`` del repo.
    """
    # Base de datos aislada por test (ADR-0026): un SQLite temporal para el corpus/modelos,
    # de modo que la persistencia no toque la base real del repo ni se filtre entre tests.
    engine = crear_engine(f"sqlite:///{(tmp_path / 'spc_test.db').as_posix()}")
    app = crear_app(
        engine=engine,
        client_models_dir=tmp_path / "clientes",
        cors_origins=["http://localhost:5173"],
    )
    with TestClient(app) as c:
        yield c
