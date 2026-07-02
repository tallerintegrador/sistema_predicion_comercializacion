"""Bloques de analisis: objetivo, univariado, temporal, relacional, correlaciones,
clasificacion y clustering."""

from __future__ import annotations

from spc.eda.analysis.classification import classification_analysis
from spc.eda.analysis.clustering import clustering_features, run_kmeans_segmentation
from spc.eda.analysis.correlation import NUMERIC_CORR_COLS, correlation_analysis
from spc.eda.analysis.relational import relational_analysis
from spc.eda.analysis.target import analyze_sales
from spc.eda.analysis.temporal import temporal_analysis
from spc.eda.analysis.univariate import analyze_univariate

__all__ = [
    "analyze_sales",
    "analyze_univariate",
    "temporal_analysis",
    "relational_analysis",
    "correlation_analysis",
    "NUMERIC_CORR_COLS",
    "classification_analysis",
    "clustering_features",
    "run_kmeans_segmentation",
]
