"""Analisis de la variable objetivo `sales` (tarea D del enunciado)."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from spc.config import Settings
from spc.io.loaders import write_csv
from spc.reporting.formatters import pct


def analyze_sales(train: pd.DataFrame, settings: Settings) -> dict[str, Any]:
    """Descriptivos, forma de la distribucion, outliers IQR y escala por familia/tienda."""
    sales = train["sales"].astype("float64")
    q1 = float(sales.quantile(0.25))
    q3 = float(sales.quantile(0.75))
    iqr = q3 - q1
    upper = q3 + 1.5 * iqr
    lower = q1 - 1.5 * iqr
    outliers = (sales < lower) | (sales > upper)

    desc = sales.describe(percentiles=[0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99]).to_frame("sales")
    write_csv(desc, settings.processed_dir / "sales_descriptivos.csv", index=True)

    # Forma de la distribucion: asimetria y curtosis sobre crudo y log1p.
    sales_pos = sales[sales > 0]
    log_sales = np.log1p(sales)
    shape_stats = {
        "asimetria_cruda": float(stats.skew(sales)),
        "curtosis_cruda": float(stats.kurtosis(sales)),
        "asimetria_log1p": float(stats.skew(log_sales)),
        "curtosis_log1p": float(stats.kurtosis(log_sales)),
        "coef_variacion": float(sales.std() / sales.mean()) if sales.mean() else np.nan,
        "media_sin_ceros": float(sales_pos.mean()) if len(sales_pos) else np.nan,
        "mediana_sin_ceros": float(sales_pos.median()) if len(sales_pos) else np.nan,
    }

    family_scale = (
        train.groupby("family", observed=True)["sales"]
        .agg(
            filas="size",
            ventas_total="sum",
            media="mean",
            mediana="median",
            maximo="max",
            desv="std",
        )
        .reset_index()
    )
    family_scale["coef_variacion"] = family_scale["desv"] / family_scale["media"]
    zeros_by_family = (
        train.assign(es_cero=train["sales"].eq(0))
        .groupby("family", observed=True)["es_cero"]
        .mean()
        .mul(100)
        .rename("pct_ceros")
        .reset_index()
    )
    family_scale = family_scale.merge(zeros_by_family, on="family").sort_values(
        "ventas_total", ascending=False
    )
    write_csv(family_scale, settings.processed_dir / "sales_por_familia.csv")

    store_scale = (
        train.groupby("store_nbr", observed=True)["sales"]
        .agg(filas="size", ventas_total="sum", media="mean", mediana="median", maximo="max")
        .reset_index()
        .sort_values("ventas_total", ascending=False)
    )
    write_csv(store_scale, settings.processed_dir / "sales_por_tienda.csv")

    return {
        "descriptivos": desc,
        "shape_stats": shape_stats,
        "q1": q1,
        "q3": q3,
        "iqr": iqr,
        "outlier_lower": lower,
        "outlier_upper": upper,
        "outlier_count": int(outliers.sum()),
        "outlier_pct": pct(outliers.sum(), len(train)),
        "zero_count": int((sales == 0).sum()),
        "zero_pct": pct((sales == 0).sum(), len(train)),
        "family_scale": family_scale,
        "store_scale": store_scale,
    }
