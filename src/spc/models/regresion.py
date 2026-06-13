"""Modulo de regresion: entrena modelos para predecir `sales` y calcula metricas."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

from spc.config import Settings
from spc.utils.metrics import format_metrics_table, regression_metrics

# Columnas predictoras numericas por defecto (las que vienen del dataset analitico).
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
    analytic: pd.DataFrame, features: list[str], target: str = "sales", test_days: int = 30
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Split temporal: ultimos `test_days` dias como test, el resto como train."""
    df = analytic.dropna(subset=features + [target]).copy()
    # Asegurar tipos numericos
    for col in features:
        if df[col].dtype == "bool":
            df[col] = df[col].astype(int)

    max_date = df["date"].max()
    cutoff = max_date - pd.Timedelta(days=test_days)

    train_mask = df["date"] <= cutoff
    test_mask = df["date"] > cutoff

    X_train = df.loc[train_mask, features].to_numpy(dtype="float64")
    y_train = df.loc[train_mask, target].to_numpy(dtype="float64")
    X_test = df.loc[test_mask, features].to_numpy(dtype="float64")
    y_test = df.loc[test_mask, target].to_numpy(dtype="float64")

    return X_train, y_train, X_test, y_test


def train_regression_models(
    analytic: pd.DataFrame,
    settings: Settings,
    features: list[str] | None = None,
    test_days: int = 30,
    sample_frac: float = 0.3,
) -> dict[str, Any]:
    """Entrena 3 modelos de regresion y devuelve metricas comparativas.

    Para eficiencia se usa un muestreo estratificado por tienda. El split es
    temporal (ultimos `test_days` dias como test) para respetar la naturaleza
    temporal y evitar fuga de datos.
    """
    features = features or _DEFAULT_FEATURES
    # Filtrar features que realmente existan en el dataframe
    features = [f for f in features if f in analytic.columns]

    # Muestreo para velocidad (3M filas es mucho para GBM sin GPU)
    if sample_frac < 1.0:
        sample = analytic.sample(frac=sample_frac, random_state=settings.random_seed)
    else:
        sample = analytic

    X_train, y_train, X_test, y_test = _prepare_data(sample, features)

    # Escalar para Ridge
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    models = {
        "Ridge Regression": Ridge(alpha=1.0, random_state=settings.random_seed),
        "Random Forest": RandomForestRegressor(
            n_estimators=100, max_depth=10, random_state=settings.random_seed, n_jobs=-1
        ),
        "Gradient Boosting": HistGradientBoostingRegressor(
            max_iter=200,
            max_depth=6,
            learning_rate=0.1,
            random_state=settings.random_seed,
        ),
    }

    results = []
    predictions = {}

    for name, model in models.items():
        if "Ridge" in name:
            model.fit(X_train_scaled, y_train)
            y_pred = model.predict(X_test_scaled)
        else:
            model.fit(X_train, y_train)
            y_pred = model.predict(X_test)

        # Clamp negativas a 0 (ventas no pueden ser negativas)
        y_pred = np.clip(y_pred, 0, None)
        metrics = regression_metrics(y_test, y_pred)
        metrics["Modelo"] = name
        results.append(metrics)
        predictions[name] = y_pred

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
