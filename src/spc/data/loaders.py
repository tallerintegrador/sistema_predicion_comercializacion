"""Carga de los CSV crudos y helpers de escritura de artefactos."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from spc.config import Settings
from spc.data.schemas import DTYPES, HOLIDAY_CATEGORICAL_COLS, PARSE_DATES
from spc.utils.logging import get_logger

log = get_logger("io.loaders")


def check_files(settings: Settings) -> pd.DataFrame:
    """Verifica que los 7 CSV esperados existan en `data/raw`.

    Devuelve un DataFrame con el inventario (archivo, encontrado, tamano_mb) y
    lanza ``FileNotFoundError`` si falta alguno.
    """
    rows = []
    for filename in settings.expected_files.values():
        path = settings.raw_dir / filename
        rows.append(
            {
                "archivo": filename,
                "encontrado": path.exists(),
                "tamano_mb": path.stat().st_size / 1024 / 1024 if path.exists() else np.nan,
            }
        )
    files = pd.DataFrame(rows)
    missing = files.loc[~files["encontrado"], "archivo"].tolist()
    if missing:
        raise FileNotFoundError(f"Faltan archivos requeridos en {settings.raw_dir}: {missing}")
    log.info("Archivos verificados: %d/%d presentes", len(files), len(files))
    return files


def load_data(settings: Settings) -> dict[str, pd.DataFrame]:
    """Carga los 7 CSV con tipos eficientes y fechas parseadas."""
    raw = settings.raw_dir

    def read(name: str) -> pd.DataFrame:
        # Any para los esquemas: el tipado de `dtype`/`parse_dates` en pandas es
        # demasiado estricto (Mapping invariante) y rechaza un dict[str, str] valido.
        dtype: Any = DTYPES.get(name)
        parse: Any = PARSE_DATES.get(name)
        return pd.read_csv(raw / settings.expected_files[name], parse_dates=parse, dtype=dtype)

    train = read("train")
    test = read("test")
    stores = read("stores")
    transactions = read("transactions")
    oil = read("oil")

    holidays = read("holidays_events")
    for col in HOLIDAY_CATEGORICAL_COLS:
        holidays[col] = holidays[col].astype("category")
    if holidays["transferred"].dtype != bool:
        holidays["transferred"] = holidays["transferred"].astype(str).str.lower().eq("true")

    sample_submission = read("sample_submission")

    log.info("Carga completa: train=%d filas, integrando %d fuentes", len(train), 7)
    return {
        "train": train,
        "test": test,
        "stores": stores,
        "transactions": transactions,
        "oil": oil,
        "holidays_events": holidays,
        "sample_submission": sample_submission,
    }


def write_csv(df: pd.DataFrame, path: Path, index: bool = False) -> Path:
    """Escribe un DataFrame a CSV, creando la carpeta si hace falta."""
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=index)
    return path


def write_json(data: dict[str, Any], path: Path) -> Path:
    """Serializa un dict a JSON (UTF-8, indentado), tolerando tipos de numpy/pandas."""
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.Series(data, dtype="object").to_json(path, force_ascii=False, indent=2)
    return path


# Pequeno helper para artefactos que no son dict (p.ej. resumen final del pipeline).
def dump_json(data: dict[str, Any], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return path
