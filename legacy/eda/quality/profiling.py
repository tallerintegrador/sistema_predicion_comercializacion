"""Perfilado general de cada archivo (tarea B del enunciado)."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from spc.config import Settings
from spc.data.loaders import write_csv
from spc.utils.formatters import pct


def profile_dataframe(name: str, df: pd.DataFrame) -> dict[str, Any]:
    """Resumen de una tabla: forma, memoria, rango de fechas, duplicados y nulos."""
    date_range = ""
    if "date" in df.columns and not df["date"].dropna().empty:
        date_range = f"{df['date'].min().date()} a {df['date'].max().date()}"
    unique_stores = int(df["store_nbr"].nunique()) if "store_nbr" in df.columns else np.nan
    unique_families = int(df["family"].nunique()) if "family" in df.columns else np.nan
    return {
        "archivo": name,
        "filas": int(df.shape[0]),
        "columnas": int(df.shape[1]),
        "memoria_mb": float(df.memory_usage(deep=True).sum() / 1024 / 1024),
        "rango_fechas": date_range,
        "tiendas_unicas": unique_stores,
        "familias_unicas": unique_families,
        "duplicados": int(df.duplicated().sum()),
        "pct_nulos_total": float(df.isna().sum().sum() / df.size * 100.0),
        "columnas_y_tipos": ", ".join(f"{col}: {dtype}" for col, dtype in df.dtypes.items()),
    }


def build_profiles(
    data: dict[str, pd.DataFrame], settings: Settings
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Construye el perfil por archivo y el detalle de nulos por columna.

    Persiste ``resumen_perfil_archivos.csv`` y ``resumen_nulos_columnas.csv``.
    """
    profiles = pd.DataFrame([profile_dataframe(name, df) for name, df in data.items()])

    missing_rows = []
    for name, df in data.items():
        total = len(df)
        for col in df.columns:
            nulls = int(df[col].isna().sum())
            missing_rows.append(
                {"archivo": name, "columna": col, "nulos": nulls, "pct_nulos": pct(nulls, total)}
            )
    missing = pd.DataFrame(missing_rows)

    write_csv(profiles, settings.processed_dir / "resumen_perfil_archivos.csv")
    write_csv(missing, settings.processed_dir / "resumen_nulos_columnas.csv")
    return profiles, missing
