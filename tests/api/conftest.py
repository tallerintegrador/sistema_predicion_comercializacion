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
    app = crear_app(
        client_models_dir=tmp_path / "clientes",
        cors_origins=["http://localhost:5173"],
    )
    with TestClient(app) as c:
        yield c
