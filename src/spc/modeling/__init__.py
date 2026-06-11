"""Modulo de modelado predictivo: regresion, clasificacion y clustering."""

from __future__ import annotations

from spc.modeling.metrics import (
    regression_metrics,
    classification_metrics,
    clustering_metrics,
)
from spc.modeling.regression import train_regression_models
from spc.modeling.classification_model import train_classification_models
from spc.modeling.clustering_eval import evaluate_clustering

__all__ = [
    "regression_metrics",
    "classification_metrics",
    "clustering_metrics",
    "train_regression_models",
    "train_classification_models",
    "evaluate_clustering",
]
