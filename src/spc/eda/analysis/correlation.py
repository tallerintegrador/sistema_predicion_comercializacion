"""Correlaciones numericas y ranking de senal lineal contra `sales` (tarea I)."""

from __future__ import annotations

import pandas as pd

from spc.config import Settings
from spc.data.loaders import write_csv

NUMERIC_CORR_COLS: list[str] = [
    "sales",
    "onpromotion",
    "transactions_filled",
    "dcoilwtico",
    "holiday_event_count",
    "holiday_national",
    "holiday_regional",
    "holiday_local",
    "is_payday",
    "is_weekend",
    "is_month_end",
    "year",
    "month",
    "day",
    "dayofweek",
    "cluster",
]


def correlation_analysis(
    analytic: pd.DataFrame, settings: Settings
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Matriz de correlacion de Pearson y ranking de |correlacion| contra `sales`."""
    frame = analytic[NUMERIC_CORR_COLS].copy()
    for col in ["is_payday", "is_weekend", "is_month_end"]:
        frame[col] = frame[col].astype("int8")
    corr = frame.corr(numeric_only=True)
    write_csv(corr, settings.processed_dir / "correlaciones_numericas.csv", index=True)

    signal = corr["sales"].drop(labels=["sales"]).rename("correlacion_sales").to_frame()
    signal["abs_corr"] = signal["correlacion_sales"].abs()
    signal = (
        signal.sort_values("abs_corr", ascending=False)
        .reset_index()
        .rename(columns={"index": "variable"})
    )
    write_csv(signal, settings.processed_dir / "senal_regresion.csv")
    return corr, signal
