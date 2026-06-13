"""Funciones de calculo de metricas para regresion, clasificacion y clustering."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    calinski_harabasz_score,
    davies_bouldin_score,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    precision_score,
    r2_score,
    recall_score,
    roc_auc_score,
    silhouette_score,
)


def mape(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Mean Absolute Percentage Error. Excluye filas con y_true == 0."""
    mask = y_true != 0
    if mask.sum() == 0:
        return np.nan
    return float(np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])) * 100)


def wape(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Weighted Absolute Percentage Error (WAPE = sum|error| / sum|actual| * 100)."""
    total = np.sum(np.abs(y_true))
    if total == 0:
        return np.nan
    return float(np.sum(np.abs(y_true - y_pred)) / total * 100)


def rmse(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Root Mean Squared Error."""
    return float(np.sqrt(mean_squared_error(y_true, y_pred)))


def rmsle(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Root Mean Squared Logarithmic Error (ambos deben ser >= 0)."""
    y_true_c = np.clip(y_true, 0, None)
    y_pred_c = np.clip(y_pred, 0, None)
    return float(np.sqrt(np.mean((np.log1p(y_true_c) - np.log1p(y_pred_c)) ** 2)))


def regression_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    """Calcula todas las metricas de regresion relevantes."""
    return {
        "MAE": float(mean_absolute_error(y_true, y_pred)),
        "RMSE": rmse(y_true, y_pred),
        "RMSLE": rmsle(y_true, y_pred),
        "MAPE": mape(y_true, y_pred),
        "WAPE": wape(y_true, y_pred),
        "R2": float(r2_score(y_true, y_pred)),
    }


def evaluar_en_unidades(
    y_true_log: np.ndarray, y_pred_log: np.ndarray
) -> dict[str, float]:
    """Invierte la transformacion ``log1p`` y evalua en la escala de unidades.

    Requisito de la Fase 2a: el modelo entrena en ``log1p(sales)`` pero **todas
    las metricas finales se reportan en unidades**. Aqui se aplica ``expm1`` a
    objetivo y prediccion (recortando negativas a 0, porque las ventas no pueden
    ser negativas) antes de calcular MAE/RMSE y companhia.
    """
    y_true = np.expm1(np.asarray(y_true_log, dtype="float64"))
    y_pred = np.clip(np.expm1(np.asarray(y_pred_log, dtype="float64")), 0.0, None)
    return regression_metrics(y_true, y_pred)


def classification_metrics(
    y_true: np.ndarray, y_pred: np.ndarray, y_prob: np.ndarray | None = None
) -> dict[str, float]:
    """Calcula metricas de clasificacion binaria."""
    metrics = {
        "Accuracy": float(accuracy_score(y_true, y_pred)),
        "Precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "Recall": float(recall_score(y_true, y_pred, zero_division=0)),
        "F1": float(f1_score(y_true, y_pred, zero_division=0)),
    }
    if y_prob is not None:
        try:
            metrics["AUC-ROC"] = float(roc_auc_score(y_true, y_prob))
        except ValueError:
            metrics["AUC-ROC"] = np.nan
    return metrics


def clustering_metrics(X: np.ndarray, labels: np.ndarray) -> dict[str, float]:
    """Calcula metricas de calidad de clustering."""
    n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
    if n_clusters < 2:
        return {"Silhouette": np.nan, "Calinski-Harabasz": np.nan, "Davies-Bouldin": np.nan}
    return {
        "Silhouette": float(silhouette_score(X, labels)),
        "Calinski-Harabasz": float(calinski_harabasz_score(X, labels)),
        "Davies-Bouldin": float(davies_bouldin_score(X, labels)),
    }


def format_metrics_table(results: list[dict]) -> pd.DataFrame:
    """Formatea una lista de resultados de modelos como DataFrame para display."""
    return pd.DataFrame(results).set_index("Modelo")
