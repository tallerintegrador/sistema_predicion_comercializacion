"""Aptitud para clustering: features agregadas y segmentacion KMeans (tarea J)."""

from __future__ import annotations

from typing import Any

import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

from spc.config import Settings
from spc.data.loaders import write_csv


def clustering_features(
    analytic: pd.DataFrame, settings: Settings
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Perfiles agregados por tienda y por familia (insumo de segmentacion)."""
    store_features = (
        analytic.groupby("store_nbr", observed=True)
        .agg(
            ventas_total=("sales", "sum"),
            venta_media=("sales", "mean"),
            venta_mediana=("sales", "median"),
            promociones_media=("onpromotion", "mean"),
            transacciones_media=("transactions_filled", "mean"),
            pct_demanda_alta=("demanda_alta", "mean"),
            familias_activas=("family", "nunique"),
            cluster=("cluster", "first"),
        )
        .reset_index()
    )
    family_features = (
        analytic.groupby("family", observed=True)
        .agg(
            ventas_total=("sales", "sum"),
            venta_media=("sales", "mean"),
            venta_mediana=("sales", "median"),
            promociones_media=("onpromotion", "mean"),
            pct_demanda_alta=("demanda_alta", "mean"),
            tiendas_con_ventas=("store_nbr", "nunique"),
        )
        .reset_index()
    )
    write_csv(store_features, settings.processed_dir / "features_clustering_tiendas.csv")
    write_csv(family_features, settings.processed_dir / "features_clustering_familias.csv")
    return store_features, family_features


def run_kmeans_segmentation(
    features: pd.DataFrame,
    cols: list[str],
    k_range: range,
    out_prefix: str,
    settings: Settings,
) -> dict[str, Any]:
    """Estandariza, evalua silueta en ``k_range`` y ajusta KMeans con el mejor k.

    Demuestra de forma cuantitativa que la data SEPARA en segmentos (insumo de
    aptitud para clustering). Usa semilla fija para reproducibilidad.
    """
    X = StandardScaler().fit_transform(features[cols].to_numpy(dtype="float64"))
    sil_rows = []
    best_k, best_sil = 0, -1.0
    for k in k_range:
        km = KMeans(n_clusters=k, random_state=settings.random_seed, n_init=10)
        labels = km.fit_predict(X)
        sil = float(silhouette_score(X, labels))
        sil_rows.append({"k": int(k), "silueta": sil, "inercia": float(km.inertia_)})
        if sil > best_sil:
            best_k, best_sil = int(k), sil
    sil_df = pd.DataFrame(sil_rows)
    write_csv(sil_df, settings.processed_dir / f"silhouette_{out_prefix}.csv")

    km = KMeans(n_clusters=best_k, random_state=settings.random_seed, n_init=10)
    seg = features.copy()
    seg["segmento"] = km.fit_predict(X)
    write_csv(seg, settings.processed_dir / f"segmentacion_{out_prefix}.csv")

    profile = (
        seg.groupby("segmento")[cols]
        .mean()
        .reset_index()
        .assign(n=seg.groupby("segmento").size().to_numpy())
    )
    write_csv(profile, settings.processed_dir / f"perfil_segmentos_{out_prefix}.csv")
    return {
        "silhouette": sil_df,
        "best_k": best_k,
        "best_sil": best_sil,
        "seg": seg,
        "profile": profile,
    }
