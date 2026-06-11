"""Modulo de clasificacion: entrena modelos para predecir `demanda_alta` y calcula metricas."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from spc.config import Settings
from spc.modeling.metrics import classification_metrics, format_metrics_table


_DEFAULT_FEATURES = [
    "store_nbr",
    "onpromotion",
    "transactions_filled",
    "dcoilwtico",
    "holiday_national",
    "holiday_regional",
    "holiday_local",
    "holiday_event_count",
    "year",
    "month",
    "day",
    "dayofweek",
    "is_weekend",
    "is_month_end",
    "is_payday",
    "cluster",
]


def _prepare_data(
    analytic: pd.DataFrame, features: list[str], target: str = "demanda_alta", test_days: int = 30
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Split temporal para clasificacion."""
    df = analytic.dropna(subset=features + [target]).copy()
    for col in features:
        if df[col].dtype == "bool":
            df[col] = df[col].astype(int)

    df[target] = df[target].astype(int)

    max_date = df["date"].max()
    cutoff = max_date - pd.Timedelta(days=test_days)

    train_mask = df["date"] <= cutoff
    test_mask = df["date"] > cutoff

    X_train = df.loc[train_mask, features].to_numpy(dtype="float64")
    y_train = df.loc[train_mask, target].to_numpy(dtype="int32")
    X_test = df.loc[test_mask, features].to_numpy(dtype="float64")
    y_test = df.loc[test_mask, target].to_numpy(dtype="int32")

    return X_train, y_train, X_test, y_test


def train_classification_models(
    analytic: pd.DataFrame,
    settings: Settings,
    features: list[str] | None = None,
    test_days: int = 30,
    sample_frac: float = 0.3,
) -> dict[str, Any]:
    """Entrena 3 modelos de clasificacion y devuelve metricas comparativas.

    Split temporal para evitar fuga de datos. Muestreo para velocidad.
    """
    features = features or _DEFAULT_FEATURES
    features = [f for f in features if f in analytic.columns]

    if sample_frac < 1.0:
        sample = analytic.sample(frac=sample_frac, random_state=settings.random_seed)
    else:
        sample = analytic

    X_train, y_train, X_test, y_test = _prepare_data(sample, features)

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    models = {
        "Logistic Regression": LogisticRegression(
            max_iter=500, random_state=settings.random_seed
        ),
        "Random Forest": RandomForestClassifier(
            n_estimators=100, max_depth=10, random_state=settings.random_seed, n_jobs=-1
        ),
        "Gradient Boosting": HistGradientBoostingClassifier(
            max_iter=200,
            max_depth=6,
            learning_rate=0.1,
            random_state=settings.random_seed,
        ),
    }

    results = []
    predictions = {}

    for name, model in models.items():
        if "Logistic" in name:
            model.fit(X_train_scaled, y_train)
            y_pred = model.predict(X_test_scaled)
            y_prob = model.predict_proba(X_test_scaled)[:, 1]
        else:
            model.fit(X_train, y_train)
            y_pred = model.predict(X_test)
            y_prob = model.predict_proba(X_test)[:, 1]

        metrics = classification_metrics(y_test, y_pred, y_prob)
        metrics["Modelo"] = name
        results.append(metrics)
        predictions[name] = {"y_pred": y_pred, "y_prob": y_prob}

    metrics_df = format_metrics_table(results)

    return {
        "metrics": metrics_df,
        "results": results,
        "predictions": predictions,
        "y_test": y_test,
        "features_used": features,
        "n_train": len(X_train),
        "n_test": len(X_test),
    }
