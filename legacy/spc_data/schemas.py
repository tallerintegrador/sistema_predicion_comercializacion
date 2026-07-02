"""Esquemas de tipos y fechas por archivo.

Centraliza los `dtype` eficientes y las columnas de fecha que antes estaban
incrustados en `load_data`. Tenerlos como datos permite reutilizarlos en tests
y validar el contrato de cada CSV en un solo lugar.
"""

from __future__ import annotations

# dtype por columna para cada archivo (memoria eficiente).
DTYPES: dict[str, dict[str, str]] = {
    "train": {
        "id": "int32",
        "store_nbr": "int16",
        "family": "category",
        "sales": "float32",
        "onpromotion": "int16",
    },
    "test": {
        "id": "int32",
        "store_nbr": "int16",
        "family": "category",
        "onpromotion": "int16",
    },
    "stores": {
        "store_nbr": "int16",
        "city": "category",
        "state": "category",
        "type": "category",
        "cluster": "int16",
    },
    "transactions": {"store_nbr": "int16", "transactions": "int32"},
    "oil": {"dcoilwtico": "float32"},
    "sample_submission": {"id": "int32", "sales": "float32"},
}

# Columnas a parsear como fecha por archivo.
PARSE_DATES: dict[str, list[str]] = {
    "train": ["date"],
    "test": ["date"],
    "transactions": ["date"],
    "oil": ["date"],
    "holidays_events": ["date"],
}

# Columnas categoricas de holidays_events (se castean tras la carga).
HOLIDAY_CATEGORICAL_COLS: list[str] = ["type", "locale", "locale_name", "description"]
