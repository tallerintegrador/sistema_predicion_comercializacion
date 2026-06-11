"""Construccion de las 19 figuras del EDA.

Cada figura es una funcion pura que recibe el contexto ya calculado y dibuja sobre
la figura activa; el orquestador la guarda y registra su ruta. Las correcciones de
metodo respecto al script original estan comentadas en cada caso.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

from spc.config import Settings
from spc.logging_setup import get_logger
from spc.viz.style import apply_theme, save_figure, value_labels

log = get_logger("viz.figures")

_DOW_LABELS = {0: "Lun", 1: "Mar", 2: "Mie", 3: "Jue", 4: "Vie", 5: "Sab", 6: "Dom"}


@dataclass
class FigureContext:
    """Insumos ya calculados que necesitan las figuras."""

    train: pd.DataFrame
    sales: dict[str, Any]
    temporal: dict[str, pd.DataFrame]
    relational: dict[str, pd.DataFrame]
    corr: pd.DataFrame
    classes: pd.DataFrame
    analytic: pd.DataFrame
    store_seg: dict[str, Any]
    seed: int


# --- Figuras individuales -------------------------------------------------


def _fig_sales_distribution(ctx: FigureContext, s) -> None:
    plt.figure(figsize=s.figsize_default)
    sns.histplot(ctx.train["sales"], bins=80, color=s.color_primary)
    plt.title("Distribución de sales")
    plt.xlabel("Ventas (sales)")
    plt.ylabel("Frecuencia")


def _fig_sales_log_distribution(ctx: FigureContext, s) -> None:
    plt.figure(figsize=s.figsize_default)
    sns.histplot(np.log1p(ctx.train["sales"]), bins=80, color=s.color_secondary)
    plt.title("Distribución de log1p(sales)")
    plt.xlabel("log1p(ventas)")
    plt.ylabel("Frecuencia")


def _fig_daily_trend(ctx: FigureContext, s) -> None:
    daily = ctx.temporal["daily"]
    plt.figure(figsize=s.figsize_wide)
    plt.plot(daily["date"], daily["sales_total"], linewidth=1.0, color=s.color_primary)
    plt.title("Tendencia diaria de ventas agregadas")
    plt.xlabel("Fecha")
    plt.ylabel("Ventas totales diarias")


def _fig_monthly_seasonality(ctx: FigureContext, s) -> None:
    # CORRECCION: indice estacional (mes/media anual) en vez del promedio crudo por mes,
    # que mezclaba tendencia con estacionalidad. 1.0 = nivel tipico del anio.
    idx = ctx.temporal["month_index"]
    ax = sns.barplot(data=idx, x="month", y="indice_estacional", color=s.color_accent)
    plt.gcf().set_size_inches(*s.figsize_default)
    plt.axhline(1.0, color="gray", linestyle="--", linewidth=1)
    plt.title("Índice estacional mensual (relativo a la media anual)")
    plt.xlabel("Mes")
    plt.ylabel("Índice estacional (1.0 = media del año)")
    value_labels(ax, fmt="{:.2f}")


def _fig_dow_seasonality(ctx: FigureContext, s) -> None:
    dow = ctx.temporal["dow"].copy()
    dow["dia"] = dow["dayofweek"].map(_DOW_LABELS)
    plt.figure(figsize=s.figsize_default)
    sns.barplot(data=dow, x="dia", y="venta_media_diaria", color=s.color_accent)
    plt.title("Estacionalidad por día de semana")
    plt.xlabel("Día de semana")
    plt.ylabel("Venta diaria promedio")


def _fig_top_families(ctx: FigureContext, s) -> None:
    top_family = ctx.sales["family_scale"].head(15).copy()
    plt.figure(figsize=(10, 6))
    ax = sns.barplot(data=top_family, y="family", x="ventas_total", color=s.color_primary)
    plt.title("Top 15 familias por ventas totales")
    plt.xlabel("Ventas totales")
    plt.ylabel("Familia")
    value_labels(ax, horizontal=True)


def _fig_promo_sales(ctx: FigureContext, s) -> None:
    # CORRECCION: promedio directo de sales por bin de onpromotion sobre el dataset
    # integrado (antes era un promedio-de-promedios ponderado, mas opaco).
    bins = [-1, 0, 5, 20, np.inf]
    labels = ["0", "1-5", "6-20", ">20"]
    promo_bin = (
        ctx.analytic.assign(
            onpromotion_bin=pd.cut(ctx.analytic["onpromotion"], bins=bins, labels=labels)
        )
        .groupby("onpromotion_bin", observed=True)["sales"]
        .mean()
        .reset_index(name="media_sales")
    )
    plt.figure(figsize=s.figsize_default)
    ax = sns.barplot(data=promo_bin, x="onpromotion_bin", y="media_sales", color=s.color_highlight)
    plt.title("Ventas promedio según nivel de promoción")
    plt.xlabel("Unidades en promoción")
    plt.ylabel("Sales promedio")
    value_labels(ax)


def _fig_transactions_sales(ctx: FigureContext, s) -> None:
    # CORRECCION: linea de tendencia (regresion) para que se lea la relacion, no solo la nube.
    store_day = ctx.relational["store_day"].dropna(subset=["transactions"]).copy()
    sample = store_day.sample(min(len(store_day), 25000), random_state=ctx.seed)
    plt.figure(figsize=s.figsize_square)
    sns.regplot(
        data=sample,
        x="transactions",
        y="sales_total",
        scatter_kws={"alpha": 0.25, "s": 10, "color": s.color_accent, "edgecolor": None},
        line_kws={"color": s.color_secondary, "linewidth": 2},
        ci=None,
    )
    plt.title("Relación entre transacciones y ventas por tienda-día")
    plt.xlabel("Transacciones")
    plt.ylabel("Ventas totales tienda-día")


def _fig_oil_sales(ctx: FigureContext, s) -> None:
    # CORRECCION: colorear por anio. La correlacion negativa global es espuria por el
    # trend (ventas suben, petroleo baja en el tiempo); el color lo hace evidente.
    oil_daily = ctx.relational["oil_daily"]
    plt.figure(figsize=s.figsize_square)
    sns.scatterplot(
        data=oil_daily,
        x="dcoilwtico",
        y="sales_total",
        hue="year",
        palette="viridis",
        alpha=0.7,
        s=22,
        edgecolor=None,
    )
    plt.title("Precio del petróleo vs ventas diarias (color = año)")
    plt.xlabel("Precio WTI del petróleo")
    plt.ylabel("Ventas totales diarias")
    plt.legend(title="Año", fontsize=8)


def _fig_correlation(ctx: FigureContext, s) -> None:
    # CORRECCION: enmascarar triangulo superior (matriz simetrica, mitad redundante).
    corr = ctx.corr
    mask = np.triu(np.ones_like(corr, dtype=bool), k=1)
    plt.figure(figsize=(11, 9))
    sns.heatmap(
        corr,
        mask=mask,
        annot=True,
        fmt=".2f",
        cmap=s.cmap_diverging,
        center=0,
        square=True,
        annot_kws={"size": 7},
        cbar_kws={"shrink": 0.8},
    )
    plt.title("Matriz de correlación de variables numéricas")


def _fig_class_balance(ctx: FigureContext, s) -> None:
    plt.figure(figsize=(6, 5))
    ax = sns.barplot(data=ctx.classes, x="demanda_alta", y="filas", color=s.color_primary)
    plt.title("Distribución de clases: demanda alta")
    plt.xlabel("Demanda alta")
    plt.ylabel("Filas")
    value_labels(ax)


def _fig_cluster_sales(ctx: FigureContext, s) -> None:
    cluster_sales = ctx.relational["cluster_sales"]
    plt.figure(figsize=s.figsize_default)
    sns.barplot(data=cluster_sales, x="cluster", y="media_sales", color=s.color_accent)
    plt.title("Sales promedio por cluster de tienda")
    plt.xlabel("Cluster")
    plt.ylabel("Sales promedio")


def _fig_annual_seasonality(ctx: FigureContext, s) -> None:
    ym = ctx.temporal["year_month"]
    plt.figure(figsize=(10, 5.5))
    for year, grp in ym.groupby("year"):
        plt.plot(grp["month"], grp["venta_media_diaria"], marker="o", label=str(year))
    plt.title("Estacionalidad anual: perfil mensual por año")
    plt.xlabel("Mes")
    plt.ylabel("Venta diaria promedio")
    plt.xticks(range(1, 13))
    plt.legend(title="Año")


def _fig_year_month_heatmap(ctx: FigureContext, s) -> None:
    ym = ctx.temporal["year_month"]
    pivot = ym.pivot(index="year", columns="month", values="venta_media_diaria")
    plt.figure(figsize=(11, 5))
    sns.heatmap(pivot, cmap=s.cmap_sequential, annot=True, fmt=".0f", annot_kws={"size": 7})
    plt.title("Venta diaria promedio por año y mes")
    plt.xlabel("Mes")
    plt.ylabel("Año")


def _fig_holiday_type(ctx: FigureContext, s) -> None:
    te = ctx.temporal["type_effect"]
    plt.figure(figsize=s.figsize_default)
    sns.barplot(data=te, x="type", y="venta_media_diaria", color=s.color_accent)
    plt.title("Venta diaria promedio por tipo de feriado/evento nacional")
    plt.xlabel("Tipo")
    plt.ylabel("Venta diaria promedio")
    plt.xticks(rotation=20, ha="right")


def _fig_promo_penetration(ctx: FigureContext, s) -> None:
    pm = ctx.temporal["promo_month"].copy()
    pm["periodo_dt"] = pd.to_datetime(pm["periodo"] + "-01")
    plt.figure(figsize=(12, 5))
    plt.plot(pm["periodo_dt"], pm["pct_en_promo"], color=s.color_highlight, linewidth=1.6)
    plt.title("Penetración de promociones en el tiempo (% filas con onpromotion>0)")
    plt.xlabel("Mes")
    plt.ylabel("% de filas en promoción")


def _fig_dist_by_type(ctx: FigureContext, s) -> None:
    sample = ctx.analytic.sample(min(len(ctx.analytic), 200000), random_state=ctx.seed).copy()
    sample["log_sales"] = np.log1p(sample["sales"])
    plt.figure(figsize=s.figsize_default)
    sns.boxplot(
        data=sample,
        x="type",
        y="log_sales",
        color=s.color_primary,
        order=sorted(sample["type"].astype(str).unique()),
    )
    plt.title("Distribución de log1p(sales) por tipo de tienda (muestra 200k)")
    plt.xlabel("Tipo de tienda")
    plt.ylabel("log1p(ventas)")


def _fig_store_segments(ctx: FigureContext, s) -> None:
    seg = ctx.store_seg["seg"]
    plt.figure(figsize=(8.5, 6))
    sns.scatterplot(
        data=seg,
        x="transacciones_media",
        y="venta_media",
        hue="segmento",
        palette=s.palette_qualitative,
        s=90,
        edgecolor="black",
    )
    plt.title(f"Segmentación de tiendas (KMeans k={ctx.store_seg['best_k']})")
    plt.xlabel("Transacciones promedio diarias")
    plt.ylabel("Venta media por fila")
    plt.legend(title="Segmento")


def _fig_silhouette(ctx: FigureContext, s) -> None:
    sil = ctx.store_seg["silhouette"]
    plt.figure(figsize=s.figsize_default)
    sns.lineplot(data=sil, x="k", y="silueta", marker="o", color=s.color_secondary)
    plt.axvline(ctx.store_seg["best_k"], color="gray", linestyle="--", linewidth=1)
    plt.title("Coeficiente de silueta por número de clusters (tiendas)")
    plt.xlabel("k (número de clusters)")
    plt.ylabel("Silueta promedio")


# --- Registro: clave -> (archivo, builder). El orden fija la numeracion. -----
FIGURE_REGISTRY: list[tuple[str, str, Callable[[FigureContext, Any], None]]] = [
    ("sales_distribution", "01_distribucion_sales.png", _fig_sales_distribution),
    ("sales_log_distribution", "02_distribucion_log_sales.png", _fig_sales_log_distribution),
    ("daily_trend", "03_tendencia_ventas_diarias.png", _fig_daily_trend),
    ("monthly_seasonality", "04_estacionalidad_mensual.png", _fig_monthly_seasonality),
    ("dow_seasonality", "05_estacionalidad_dia_semana.png", _fig_dow_seasonality),
    ("top_families", "06_top_familias_ventas.png", _fig_top_families),
    ("promo_sales", "07_promocion_vs_sales.png", _fig_promo_sales),
    ("transactions_sales", "08_transacciones_vs_sales.png", _fig_transactions_sales),
    ("oil_sales", "09_petroleo_vs_sales.png", _fig_oil_sales),
    ("correlation", "10_correlaciones_numericas.png", _fig_correlation),
    ("class_balance", "11_balance_clases_demanda.png", _fig_class_balance),
    ("cluster_sales", "12_sales_promedio_cluster.png", _fig_cluster_sales),
    ("annual_seasonality", "13_estacionalidad_anual.png", _fig_annual_seasonality),
    ("year_month_heatmap", "14_heatmap_anio_mes.png", _fig_year_month_heatmap),
    ("holiday_type", "15_efecto_tipo_feriado.png", _fig_holiday_type),
    ("promo_penetration", "16_penetracion_promo_mensual.png", _fig_promo_penetration),
    ("dist_by_type", "17_dist_log_sales_por_tipo.png", _fig_dist_by_type),
    ("store_segments", "18_segmentacion_tiendas_kmeans.png", _fig_store_segments),
    ("silhouette", "19_silueta_k_tiendas.png", _fig_silhouette),
]


def build_all_figures(ctx: FigureContext, settings: Settings) -> dict[str, str]:
    """Dibuja y guarda todas las figuras registradas; devuelve clave -> ruta."""
    apply_theme(settings.style)
    paths: dict[str, str] = {}
    for key, filename, builder in FIGURE_REGISTRY:
        builder(ctx, settings.style)
        paths[key] = save_figure(settings.figures_dir / filename, settings.style.dpi)
        log.debug("Figura generada: %s", filename)
    log.info("Figuras generadas: %d", len(paths))
    return paths
