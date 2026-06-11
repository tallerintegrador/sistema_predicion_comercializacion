"""Evaluacion extendida de clustering con multiples metricas."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

from spc.config import Settings
from spc.modeling.metrics import clustering_metrics, format_metrics_table


_STORE_COLS = [
    "ventas_total",
    "venta_media",
    "venta_mediana",
    "promociones_media",
    "transacciones_media",
    "pct_demanda_alta",
    "familias_activas",
]

_FAMILY_COLS = ["ventas_total", "venta_media", "promociones_media", "pct_demanda_alta"]


def evaluate_clustering(
    store_features: pd.DataFrame,
    family_features: pd.DataFrame,
    settings: Settings,
) -> dict[str, Any]:
    """Evalua clustering con KMeans sobre tiendas y familias con metricas extendidas.

    Ademas de silhouette, agrega Calinski-Harabasz (mayor = mejor separacion)
    y Davies-Bouldin (menor = clusters mas compactos).
    """
    results = []

    # --- Clustering de Tiendas ---
    store_cols = [c for c in _STORE_COLS if c in store_features.columns]
    X_stores = StandardScaler().fit_transform(
        store_features[store_cols].to_numpy(dtype="float64")
    )
    best_k_stores = _find_best_k(X_stores, range(2, 9), settings.random_seed)
    km_stores = KMeans(n_clusters=best_k_stores, random_state=settings.random_seed, n_init=10)
    labels_stores = km_stores.fit_predict(X_stores)
    metrics_stores = clustering_metrics(X_stores, labels_stores)
    metrics_stores["Modelo"] = f"KMeans Tiendas (k={best_k_stores})"
    metrics_stores["Inercia"] = float(km_stores.inertia_)
    results.append(metrics_stores)

    # --- Clustering de Familias ---
    family_cols = [c for c in _FAMILY_COLS if c in family_features.columns]
    X_families = StandardScaler().fit_transform(
        family_features[family_cols].to_numpy(dtype="float64")
    )
    best_k_families = _find_best_k(X_families, range(2, 7), settings.random_seed)
    km_families = KMeans(n_clusters=best_k_families, random_state=settings.random_seed, n_init=10)
    labels_families = km_families.fit_predict(X_families)
    metrics_families = clustering_metrics(X_families, labels_families)
    metrics_families["Modelo"] = f"KMeans Familias (k={best_k_families})"
    metrics_families["Inercia"] = float(km_families.inertia_)
    results.append(metrics_families)

    metrics_df = format_metrics_table(results)

    return {
        "metrics": metrics_df,
        "results": results,
        "store_labels": labels_stores,
        "family_labels": labels_families,
        "best_k_stores": best_k_stores,
        "best_k_families": best_k_families,
    }


def _find_best_k(X: np.ndarray, k_range: range, seed: int) -> int:
    """Selecciona el k con mayor silhouette."""
    from sklearn.metrics import silhouette_score

    best_k, best_sil = 2, -1.0
    for k in k_range:
        km = KMeans(n_clusters=k, random_state=seed, n_init=10)
        labels = km.fit_predict(X)
        sil = silhouette_score(X, labels)
        if sil > best_sil:
            best_k, best_sil = k, sil
    return best_k
