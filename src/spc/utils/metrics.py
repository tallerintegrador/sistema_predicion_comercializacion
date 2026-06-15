"""Funciones de calculo de metricas para regresion, clasificacion y clustering."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    calinski_harabasz_score,
    confusion_matrix,
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


def classification_metrics_min(
    y_true: np.ndarray, y_prob: np.ndarray, umbral: float = 0.5
) -> dict[str, float]:
    """Metricas de clasificacion binaria centradas en la **clase minoritaria** (Fase 2b).

    Jerarquia para desbalance: **PR-AUC** (principal, independiente del umbral,
    adecuada para la minoritaria) -> **recall** de la positiva -> **F1** ->
    **precision**. Se incluye **ROC-AUC** como contexto y la **prevalencia** de
    positivos (= linea *sin-skill* de la PR-AUC: una PR-AUC solo es buena si supera
    a la prevalencia). Recall/F1/precision se calculan al ``umbral`` dado (por
    defecto 0.5; en 2b se reemplaza por el umbral elegido en VALID).

    ``y_prob`` es la probabilidad de la clase positiva (``demanda_alta=1``). No se
    reporta *accuracy* como metrica principal: enganha con clases desbalanceadas.
    """
    y_true = np.asarray(y_true).astype(int)
    y_prob = np.asarray(y_prob, dtype="float64")
    y_pred = (y_prob >= umbral).astype(int)
    prevalencia = float(y_true.mean())
    # PR-AUC y ROC-AUC necesitan ambas clases presentes en y_true.
    if 0 < y_true.sum() < len(y_true):
        pr_auc = float(average_precision_score(y_true, y_prob))
        roc_auc = float(roc_auc_score(y_true, y_prob))
    else:
        pr_auc = roc_auc = np.nan
    return {
        "PR_AUC": pr_auc,
        "Recall": float(recall_score(y_true, y_pred, zero_division=0)),
        "F1": float(f1_score(y_true, y_pred, zero_division=0)),
        "Precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "ROC_AUC": roc_auc,
        "Accuracy": float(accuracy_score(y_true, y_pred)),
        "prevalencia": prevalencia,
        "umbral": float(umbral),
    }


def matriz_confusion(
    y_true: np.ndarray, y_prob: np.ndarray, umbral: float = 0.5
) -> dict[str, int]:
    """Matriz de confusion (TN/FP/FN/TP) al ``umbral`` dado, como dict serializable."""
    y_true = np.asarray(y_true).astype(int)
    y_pred = (np.asarray(y_prob, dtype="float64") >= umbral).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()
    return {"TN": int(tn), "FP": int(fp), "FN": int(fn), "TP": int(tp)}


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
