"""Analisis univariado de categoricas y numericas (tarea E del enunciado)."""

from __future__ import annotations

import pandas as pd
from scipy import stats

from spc.config import Settings
from spc.io.loaders import write_csv


def analyze_univariate(
    data: dict[str, pd.DataFrame], settings: Settings
) -> dict[str, pd.DataFrame]:
    """Resumen de cardinalidad/frecuencia (categoricas) y momentos (numericas)."""
    train = data["train"]
    stores = data["stores"]
    transactions = data["transactions"]
    oil = data["oil"]

    categoricals = {
        "family": train["family"],
        "store_nbr": train["store_nbr"],
        "city": stores["city"],
        "state": stores["state"],
        "type": stores["type"],
        "cluster": stores["cluster"],
    }
    categorical_summary = pd.DataFrame(
        [
            {
                "variable": name,
                "cardinalidad": int(series.nunique(dropna=True)),
                "valor_mas_frecuente": str(series.value_counts(dropna=False).index[0]),
                "frecuencia_maxima": int(series.value_counts(dropna=False).iloc[0]),
            }
            for name, series in categoricals.items()
        ]
    )
    write_csv(categorical_summary, settings.processed_dir / "univariado_categoricas.csv")

    numeric_sources = {
        "onpromotion_train": train["onpromotion"],
        "transactions": transactions["transactions"],
        "dcoilwtico": oil["dcoilwtico"],
    }
    numeric_summary = pd.DataFrame(
        [
            {
                "variable": name,
                "conteo": int(series.count()),
                "nulos": int(series.isna().sum()),
                "media": float(series.mean()),
                "mediana": float(series.median()),
                "desv_std": float(series.std()),
                "asimetria": float(stats.skew(series.dropna())),
                "min": float(series.min()),
                "p25": float(series.quantile(0.25)),
                "p75": float(series.quantile(0.75)),
                "max": float(series.max()),
            }
            for name, series in numeric_sources.items()
        ]
    )
    write_csv(numeric_summary, settings.processed_dir / "univariado_numericas.csv")
    return {"categoricas": categorical_summary, "numericas": numeric_summary}
