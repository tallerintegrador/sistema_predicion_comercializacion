"""Fixtures sinteticas que imitan el esquema real con pocas filas.

Permiten testear logica de calidad/integracion/temporal sin depender de los CSV
pesados de `data/raw`. Los builders viven en `tests/sintetico.py` (modulo de nombre
unico, reutilizable desde otros conftests sin colision).
"""

from __future__ import annotations

import pandas as pd
import pytest

from sintetico import (
    construir_analitico_clasificacion,
    construir_analitico_clustering,
    construir_analitico_sintetico,
)
from spc.config import Settings


@pytest.fixture
def settings(tmp_path) -> Settings:
    """Settings apuntando a un directorio temporal (las escrituras no tocan el repo)."""
    return Settings(base_dir=tmp_path)


@pytest.fixture
def analitico_sintetico() -> pd.DataFrame:
    """Dataset analitico sintetico aprendible para los tests de regresion."""
    return construir_analitico_sintetico()


@pytest.fixture
def analitico_clasificacion() -> pd.DataFrame:
    """Dataset analitico sintetico desbalanceado (con familia degenerada) para 2b."""
    return construir_analitico_clasificacion()


@pytest.fixture
def analitico_clustering() -> pd.DataFrame:
    """Dataset analitico sintetico separable (16 tiendas / 6 familias) para 2c."""
    return construir_analitico_clustering()


@pytest.fixture
def synthetic_data() -> dict[str, pd.DataFrame]:
    """Dataset minimo coherente: 2 tiendas, 2 familias, 3 dias, 1 feriado nacional."""
    dates = pd.to_datetime(["2014-01-01", "2014-01-02", "2014-01-03"])

    rows = []
    rid = 0
    for d in dates:
        for store in (1, 2):
            for fam in ("A", "B"):
                rows.append(
                    {
                        "id": rid,
                        "date": d,
                        "store_nbr": store,
                        "family": fam,
                        "sales": float(rid),  # 0..11, da variedad para P75
                        "onpromotion": rid % 3,
                    }
                )
                rid += 1
    train = pd.DataFrame(rows)
    train["family"] = train["family"].astype("category")

    test = pd.DataFrame(
        {
            "id": [100, 101],
            "date": pd.to_datetime(["2014-01-04", "2014-01-04"]),
            "store_nbr": [1, 2],
            "family": pd.Series(["A", "B"], dtype="category"),
            "onpromotion": [0, 1],
        }
    )

    stores = pd.DataFrame(
        {
            "store_nbr": [1, 2],
            "city": pd.Series(["Quito", "Guayaquil"], dtype="category"),
            "state": pd.Series(["Pichincha", "Guayas"], dtype="category"),
            "type": pd.Series(["A", "B"], dtype="category"),
            "cluster": [1, 2],
        }
    )

    # transactions: falta el dia 3 de la tienda 2 (para probar la bandera de faltante)
    transactions = pd.DataFrame(
        {
            "date": pd.to_datetime(
                ["2014-01-01", "2014-01-01", "2014-01-02", "2014-01-02", "2014-01-03"]
            ),
            "store_nbr": [1, 2, 1, 2, 1],
            "transactions": [100, 200, 110, 210, 120],
        }
    )

    # oil: falta el dia 2 (para probar el reindex + ffill)
    oil = pd.DataFrame(
        {
            "date": pd.to_datetime(["2014-01-01", "2014-01-03"]),
            "dcoilwtico": [90.0, 92.0],
        }
    )

    holidays = pd.DataFrame(
        {
            "date": pd.to_datetime(["2014-01-01", "2014-01-02"]),
            "type": pd.Series(["Holiday", "Holiday"], dtype="category"),
            "locale": pd.Series(["National", "National"], dtype="category"),
            "locale_name": pd.Series(["Ecuador", "Ecuador"], dtype="category"),
            "description": pd.Series(["Anio Nuevo", "Transferido"], dtype="category"),
            "transferred": [False, True],
        }
    )

    sample_submission = pd.DataFrame({"id": [100, 101], "sales": [0.0, 0.0]})

    return {
        "train": train,
        "test": test,
        "stores": stores,
        "transactions": transactions,
        "oil": oil,
        "holidays_events": holidays,
        "sample_submission": sample_submission,
    }
