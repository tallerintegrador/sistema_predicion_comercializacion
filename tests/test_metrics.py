"""Tests de las métricas puras (`spc.utils.metrics`).

Verifican las fórmulas que sostienen todo el reporte honesto del proyecto: WAPE/MAPE/RMSE
de regresión, el bloque de clasificación centrado en la minoritaria (PR-AUC, prevalencia)
y las guardas de casos degenerados (denominador cero, una sola clase, <2 clusters). Son
propiedades exactas: entrada conocida → salida conocida.
"""

from __future__ import annotations

import numpy as np

from spc.utils import metrics


# ---------------------------------------------------------------------------
# Regresión
# ---------------------------------------------------------------------------
def test_wape_predicion_perfecta_es_cero() -> None:
    y = np.array([10.0, 20.0, 30.0])
    assert metrics.wape(y, y.copy()) == 0.0


def test_wape_valor_conocido() -> None:
    # sum|error| = |1|+|1| = 2 ; sum|actual| = 10+20 = 30 → 2/30*100 = 6.666…
    y_true = np.array([10.0, 20.0])
    y_pred = np.array([11.0, 19.0])
    assert abs(metrics.wape(y_true, y_pred) - (2 / 30 * 100)) < 1e-9


def test_wape_denominador_cero_es_nan() -> None:
    # Todos los actuales en cero → WAPE indefinido (no división por cero).
    assert np.isnan(metrics.wape(np.zeros(3), np.array([1.0, 2.0, 3.0])))


def test_mape_excluye_ceros_del_actual() -> None:
    # La fila con y_true=0 se ignora; el resto es predicción perfecta → MAPE 0.
    y_true = np.array([0.0, 100.0, 200.0])
    y_pred = np.array([50.0, 100.0, 200.0])
    assert metrics.mape(y_true, y_pred) == 0.0


def test_mape_todos_cero_es_nan() -> None:
    assert np.isnan(metrics.mape(np.zeros(3), np.ones(3)))


def test_rmse_valor_conocido() -> None:
    # errores [0, 2] → MSE = (0+4)/2 = 2 → RMSE = sqrt(2)
    y_true = np.array([1.0, 3.0])
    y_pred = np.array([1.0, 5.0])
    assert abs(metrics.rmse(y_true, y_pred) - np.sqrt(2.0)) < 1e-9


def test_rmsle_recorta_negativos_a_cero() -> None:
    # No debe lanzar con negativos: los recorta antes del log1p.
    val = metrics.rmsle(np.array([-5.0, 10.0]), np.array([0.0, 10.0]))
    assert np.isfinite(val) and val >= 0.0


def test_regression_metrics_tiene_todas_las_claves() -> None:
    y_true = np.array([1.0, 2.0, 3.0, 4.0])
    y_pred = np.array([1.1, 1.9, 3.2, 3.8])
    out = metrics.regression_metrics(y_true, y_pred)
    assert set(out) == {"MAE", "RMSE", "RMSLE", "MAPE", "WAPE", "R2"}
    assert out["MAE"] > 0


def test_evaluar_en_unidades_invierte_log1p() -> None:
    # Predicción perfecta en log-espacio ⇒ métricas ~perfectas en unidades.
    unidades = np.array([0.0, 5.0, 50.0])
    log = np.log1p(unidades)
    out = metrics.evaluar_en_unidades(log, log.copy())
    assert out["MAE"] < 1e-6
    assert out["WAPE"] < 1e-6


# ---------------------------------------------------------------------------
# Clasificación (centrada en la minoritaria)
# ---------------------------------------------------------------------------
def test_classification_metrics_min_claves_y_prevalencia() -> None:
    y_true = np.array([0, 0, 0, 1, 1])
    y_prob = np.array([0.1, 0.2, 0.3, 0.8, 0.9])
    out = metrics.classification_metrics_min(y_true, y_prob)
    assert {"PR_AUC", "Recall", "F1", "Precision", "ROC_AUC", "Accuracy", "prevalencia", "umbral"} <= set(out)
    assert abs(out["prevalencia"] - 2 / 5) < 1e-9
    # Separación perfecta al umbral 0.5 → recall y precisión 1.
    assert out["Recall"] == 1.0 and out["Precision"] == 1.0


def test_classification_metrics_min_una_sola_clase_pr_auc_nan() -> None:
    # Sin positivos, PR-AUC/ROC-AUC son indefinidas (no lanzan).
    y_true = np.zeros(4, dtype=int)
    y_prob = np.array([0.1, 0.2, 0.3, 0.4])
    out = metrics.classification_metrics_min(y_true, y_prob)
    assert np.isnan(out["PR_AUC"]) and np.isnan(out["ROC_AUC"])


def test_matriz_confusion_cuenta_correcta() -> None:
    y_true = np.array([1, 0, 1, 0])
    y_prob = np.array([0.9, 0.1, 0.2, 0.8])  # umbral 0.5 → pred [1,0,0,1]
    cm = metrics.matriz_confusion(y_true, y_prob)
    assert cm == {"TN": 1, "FP": 1, "FN": 1, "TP": 1}


# ---------------------------------------------------------------------------
# Clustering
# ---------------------------------------------------------------------------
def test_clustering_metrics_menos_de_dos_clusters_es_nan() -> None:
    X = np.random.default_rng(42).normal(size=(10, 2))
    labels = np.zeros(10, dtype=int)  # un solo grupo
    out = metrics.clustering_metrics(X, labels)
    assert np.isnan(out["Silhouette"])


def test_clustering_metrics_dos_grupos_separados() -> None:
    rng = np.random.default_rng(42)
    X = np.vstack([rng.normal(0, 0.1, (10, 2)), rng.normal(10, 0.1, (10, 2))])
    labels = np.array([0] * 10 + [1] * 10)
    out = metrics.clustering_metrics(X, labels)
    assert out["Silhouette"] > 0.9  # grupos bien separados
