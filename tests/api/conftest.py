"""Fixtures de los tests de la API (Fase 3).

Entrena **artefactos diminutos** con las mismas funciones de entrenamiento del
motor sobre los fixtures sintéticos ya existentes (`construir_analitico_*` del
conftest raíz), los serializa en un ``models/`` temporal y construye la app
inyectando ese registro. Así los tests ejercitan la **ruta real de carga**
(`cargar_artefacto`) y predicción **sin GPU ni `data/raw`**.

La sesión entrena una sola vez (fixture *session-scoped*) para amortizar el costo.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

# Builders sintéticos compartidos (módulo de nombre único, sin colisión de conftests).
from sintetico import (
    construir_analitico_clasificacion,
    construir_analitico_clustering,
    construir_analitico_sintetico,
)
from spc.api.main import crear_app
from spc.config import Settings
from spc.service.artefactos import RegistroArtefactos


@pytest.fixture(scope="session")
def directorio_modelos(tmp_path_factory) -> object:
    """Entrena y serializa los tres artefactos diminutos en un ``models/`` temporal."""
    base = tmp_path_factory.mktemp("spc_artefactos")
    settings = Settings(base_dir=base)

    # --- Regresión (VENTAS/COMPRAS) ---
    from spc.models.regresion import entrenar_y_comparar as entrenar_reg
    from spc.models.regresion import serializar_artefacto as guardar_reg

    res_reg = entrenar_reg(
        construir_analitico_sintetico(), settings, max_train_rows=None, con_cv=False
    )
    guardar_reg(res_reg, settings)

    # --- Clasificación (ALMACÉN) ---
    from spc.models.clasificacion import entrenar_y_comparar as entrenar_clf
    from spc.models.clasificacion import serializar_artefacto as guardar_clf

    res_clf = entrenar_clf(
        construir_analitico_clasificacion(),
        settings,
        max_train_rows=None,
        con_cv=False,
        usar_gpu=False,
    )
    guardar_clf(res_clf, settings)

    # --- Clustering de tiendas (segmento_tienda de ALMACÉN) ---
    from spc.models.clustering import CONFIGS, entrenar_tarea, serializar_artefactos

    res_clu = {
        "tiendas": entrenar_tarea(construir_analitico_clustering(), CONFIGS["tiendas"], seed=42)
    }
    serializar_artefactos(res_clu, settings)

    return base / "models"


@pytest.fixture(scope="session")
def registro(directorio_modelos) -> RegistroArtefactos:
    """Carga el registro de artefactos diminutos (ruta real de carga)."""
    return RegistroArtefactos.cargar(directorio_modelos)


@pytest.fixture
def client(registro) -> object:
    """`TestClient` sobre la app con el registro inyectado (sin tocar el disco real)."""
    app = crear_app(registro=registro, cors_origins=["http://localhost:5173"])
    with TestClient(app) as c:
        yield c


@pytest.fixture
def historico_contrato() -> list[dict]:
    """Histórico en **forma de contrato** (nombres genéricos): 2 puntos de venta, 1 producto.

    120 días con un AR(1) + efecto de promoción, suficiente para los rezagos del
    pronóstico. El producto ``BEVERAGES`` coincide con las familias sintéticas, de
    modo que la categórica del motor no degrada en los tests.
    """
    rng = np.random.default_rng(7)
    fechas = [d.date().isoformat() for d in pd.date_range("2017-04-01", periods=120, freq="D")]
    filas: list[dict] = []
    for pv in ("1", "2"):
        prev = rng.uniform(800, 1200)
        for f in fechas:
            promo = int(rng.integers(0, 8))
            val = max(0.0, 0.8 * prev + 20 * promo + rng.normal(0, 40))
            prev = val
            filas.append(
                {
                    "date": f,
                    "store_id": pv,
                    "product_id": "BEVERAGES",
                    "units_sold": round(val, 1),
                    "on_promotion": promo,
                    "transactions": round(val * 1.5, 0),
                }
            )
    return filas
