"""Analisis bivariado y relacional (tarea G del enunciado)."""

from __future__ import annotations

import pandas as pd

from spc.config import Settings
from spc.data.loaders import write_csv


def relational_analysis(analytic: pd.DataFrame, settings: Settings) -> dict[str, pd.DataFrame]:
    """Relacion de `sales` con promociones, tipo, cluster, familia, transacciones y petroleo."""
    promo = (
        analytic.groupby("onpromotion", observed=True)["sales"]
        .agg(filas="size", media_sales="mean", mediana_sales="median")
        .reset_index()
        .sort_values("onpromotion")
    )
    # Comparacion directa con/sin promocion (a nivel fila).
    promo_flag = (
        analytic.assign(en_promo=analytic["onpromotion"] > 0)
        .groupby("en_promo", observed=True)["sales"]
        .agg(filas="size", media_sales="mean", mediana_sales="median")
        .reset_index()
    )
    promo_flag["en_promo"] = promo_flag["en_promo"].map({False: "Sin promo", True: "Con promo"})
    write_csv(promo_flag, settings.processed_dir / "relacional_promo_flag.csv")

    type_sales = (
        analytic.groupby("type", observed=True)["sales"]
        .agg(filas="size", ventas_total="sum", media_sales="mean", mediana_sales="median")
        .reset_index()
        .sort_values("ventas_total", ascending=False)
    )
    cluster_sales = (
        analytic.groupby("cluster", observed=True)["sales"]
        .agg(filas="size", ventas_total="sum", media_sales="mean")
        .reset_index()
        .sort_values("ventas_total", ascending=False)
    )
    family_sales = (
        analytic.groupby("family", observed=True)["sales"]
        .agg(filas="size", ventas_total="sum", media_sales="mean")
        .reset_index()
        .sort_values("ventas_total", ascending=False)
    )
    store_day = (
        analytic.groupby(["date", "store_nbr"], observed=True)
        .agg(sales_total=("sales", "sum"), transactions=("transactions", "max"))
        .reset_index()
    )
    oil_daily = (
        analytic.groupby("date", observed=True)
        .agg(sales_total=("sales", "sum"), dcoilwtico=("dcoilwtico", "max"))
        .reset_index()
    )
    oil_daily["year"] = oil_daily["date"].dt.year

    outputs = {
        "promo": promo,
        "promo_flag": promo_flag,
        "type_sales": type_sales,
        "cluster_sales": cluster_sales,
        "family_sales": family_sales,
        "store_day": store_day,
        "oil_daily": oil_daily,
    }
    for name, df in outputs.items():
        write_csv(df, settings.processed_dir / f"relacional_{name}.csv")
    return outputs
