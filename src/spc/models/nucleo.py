"""Núcleo reutilizable del motor de regresión (agnóstico al dominio).

Primitivas compartidas por el AutoML agnóstico (`spc.models.automl`) y el zoo liviano
(`spc.models.zoo_liviano`): cortes temporales, construcción de matrices, el zoo de
regresores, el entrenamiento GPU-train/CPU-predict, la conversión a unidades y el
ensemble ponderado. **No** conoce el esquema retail (`temporales`), ni `Settings`, ni la
serialización de artefactos: solo numpy/pandas/scikit-learn (+ LightGBM/XGBoost, importados
de forma perezosa). El entrenamiento retail Favorita que antes convivía aquí se archivó en
``legacy/models/regresion.py``.

Capa de motor de ML: no conoce HTTP ni el negocio del cliente.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Cortes temporales
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class CortesTemporales:
    """Fechas de corte train/valid/test (documentadas y reproducibles)."""

    train_fin: pd.Timestamp
    valid_ini: pd.Timestamp
    valid_fin: pd.Timestamp
    test_ini: pd.Timestamp
    test_fin: pd.Timestamp

    def as_dict(self) -> dict[str, str]:
        return {
            "train": f"<= {self.train_fin.date()}",
            "valid": f"{self.valid_ini.date()} .. {self.valid_fin.date()}",
            "test": f"{self.test_ini.date()} .. {self.test_fin.date()}",
        }


# ---------------------------------------------------------------------------
# Preparacion de matrices (categoricas vs numericas)
# ---------------------------------------------------------------------------
def _fijar_categorias(
    df: pd.DataFrame, cats: list[str], dtypes: dict[str, Any] | None
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Convierte ``cats`` a dtype ``category`` con un ``CategoricalDtype`` fijo.

    Se guarda y reaplica el ``CategoricalDtype`` completo (no solo la lista de
    niveles) para que el **tipo del indice de categorias** coincida exactamente
    entre entrenamiento y prediccion. XGBoost con categoricas nativas es estricto
    en esto: reconstruir desde una lista cambiaria el dtype (p. ej. int16->int64)
    y romperia la prediccion sobre subconjuntos.
    """
    df = df.copy()
    fijados: dict[str, Any] = {}
    for c in cats:
        if dtypes is not None and c in dtypes:
            df[c] = df[c].astype(dtypes[c])
        else:
            df[c] = df[c].astype("category")
        fijados[c] = df[c].dtype  # CategoricalDtype (preserva niveles y su dtype)
    return df, fijados


def _matriz_categorica(df: pd.DataFrame, features: list[str], cats: list[str]) -> pd.DataFrame:
    """Matriz para modelos con soporte nativo de categoricas (LightGBM, XGBoost,
    HistGradientBoosting): mantiene dtype category y castea booleanos a int8."""
    X = df[features].copy()
    for c in X.columns:
        if c in cats:
            continue
        if X[c].dtype == "bool":
            X[c] = X[c].astype("int8")
        elif str(X[c].dtype) != "category":
            X[c] = pd.to_numeric(X[c], errors="coerce").astype("float64")
    return X


def _matriz_numerica(df: pd.DataFrame, features: list[str], cats: list[str]) -> np.ndarray:
    """Matriz puramente numerica para Ridge y Random Forest: categoricas via
    codigos enteros, booleanos a int, NaN de calentamiento a 0."""
    X = df[features].copy()
    for c in X.columns:
        if c in cats:
            X[c] = X[c].cat.codes.astype("int32")
        elif X[c].dtype == "bool":
            X[c] = X[c].astype("int8")
        else:
            X[c] = pd.to_numeric(X[c], errors="coerce")
    return X.to_numpy(dtype="float64", na_value=0.0)


# ---------------------------------------------------------------------------
# Zoo de modelos
# ---------------------------------------------------------------------------
@dataclass
class EspecModelo:
    """Un modelo del zoo: como se construye y que tipo de matriz consume."""

    nombre: str
    tipo: str  # "numerico" | "categorico" | "lineal"
    construir: Any  # callable() -> estimador sklearn-like
    espacio: str = "log"  # "log" -> y=log1p(sales) (expm1); "unidades" -> y=sales


def _construir_pipeline_lineal(features: list[str], cats: list[str]) -> Any:
    """Pipeline para el modelo lineal (Ridge), aislado de los modelos de arbol.

    Ridge es **sensible a la escala** y NO debe recibir categoricos de alta
    cardinalidad como enteros crudos (eso disparaba R2 = -143). Por eso el
    pipeline, exclusivo del lineal:
      - **one-hot** de los categoricos (`store_nbr`, `family`, ...), con
        ``handle_unknown="ignore"`` para tolerar niveles no vistos en prediccion;
      - **imputacion + estandarizacion** de las numericas.
    Los modelos de arbol no usan nada de esto (toleran escala y codigos ordinales).
    """
    from sklearn.compose import ColumnTransformer
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import Ridge
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder, StandardScaler

    num_features = [f for f in features if f not in cats]
    preprocesador = ColumnTransformer(
        transformers=[
            ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=True), cats),
            (
                "num",
                Pipeline(
                    [
                        ("imputar", SimpleImputer(strategy="median")),
                        ("escalar", StandardScaler()),
                    ]
                ),
                num_features,
            ),
        ],
        remainder="drop",
    )
    return Pipeline([("pre", preprocesador), ("ridge", Ridge(alpha=1.0))])


def construir_zoo(
    seed: int,
    features: list[str],
    cats: list[str],
    params: dict[str, dict[str, Any]] | None = None,
    *,
    usar_gpu: bool = False,
) -> dict[str, EspecModelo]:
    """Define los regresores a comparar (semilla fija para reproducibilidad).

    Incluye dos familias de **objetivo**:
      - escala ``log1p`` (espacio ``"log"``): Ridge, RandomForest, y los boosters
        con perdida cuadratica estandar;
      - escala de **unidades** (espacio ``"unidades"``): boosters con objetivos
        **Tweedie** y **Poisson**, disenados para conteos con exceso de ceros
        (31% en ``sales``) y cola larga; predicen ventas directas (sin ``expm1``).

    ``params`` permite inyectar hiperparametros optimizados por Optuna; si una
    clave no aparece, se usa el valor por defecto razonable indicado abajo.

    Con ``usar_gpu=True`` los **boosters** entrenan en GPU (XGBoost ``device="cuda"``,
    LightGBM ``device="gpu"`` via OpenCL). HistGradientBoosting, RandomForest y
    Ridge son de scikit-learn y **no tienen backend GPU**: siguen en CPU. Tras el
    ajuste se conmuta la prediccion de XGBoost a CPU (:func:`_post_fit_cpu`) para
    que el artefacto sea portable y se sirva sin GPU en produccion.
    """
    from lightgbm import LGBMRegressor
    from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
    from xgboost import XGBRegressor

    params = params or {}
    dev_xgb = "cuda" if usar_gpu else "cpu"
    dev_lgbm = "gpu" if usar_gpu else "cpu"

    def p(nombre: str, base: dict[str, Any]) -> dict[str, Any]:
        """Combina los hiperparametros por defecto con los tuneados (si existen)."""
        return {**base, **params.get(nombre, {})}

    return {
        "Ridge": EspecModelo(
            "Ridge", "lineal",
            lambda: _construir_pipeline_lineal(features, cats),
            espacio="log",
        ),
        "RandomForest": EspecModelo(
            "RandomForest", "numerico",
            lambda: RandomForestRegressor(
                **p("RandomForest", {
                    "n_estimators": 120, "max_depth": 14, "min_samples_leaf": 20,
                }),
                random_state=seed, n_jobs=-1,
            ),
            espacio="log",
        ),
        "HistGradientBoosting": EspecModelo(
            "HistGradientBoosting", "categorico",
            lambda: HistGradientBoostingRegressor(
                **p("HistGradientBoosting", {
                    "max_iter": 300, "learning_rate": 0.06, "max_leaf_nodes": 63,
                    "l2_regularization": 1.0,
                }),
                categorical_features="from_dtype", random_state=seed,
            ),
            espacio="log",
        ),
        "LightGBM": EspecModelo(
            "LightGBM", "categorico",
            lambda: LGBMRegressor(
                **p("LightGBM", {
                    "n_estimators": 600, "learning_rate": 0.05, "num_leaves": 63,
                    "subsample": 0.8, "colsample_bytree": 0.8,
                }),
                subsample_freq=1, importance_type="gain", device=dev_lgbm,
                random_state=seed, n_jobs=-1, verbose=-1,
            ),
            espacio="log",
        ),
        "XGBoost": EspecModelo(
            "XGBoost", "categorico",
            lambda: XGBRegressor(
                **p("XGBoost", {
                    "n_estimators": 600, "learning_rate": 0.05, "max_depth": 8,
                    "subsample": 0.8, "colsample_bytree": 0.8,
                }),
                tree_method="hist", enable_categorical=True, device=dev_xgb,
                random_state=seed, n_jobs=-1,
            ),
            espacio="log",
        ),
        # --- Objetivos para conteos con exceso de ceros (predicen unidades) ---
        "LightGBM_Tweedie": EspecModelo(
            "LightGBM_Tweedie", "categorico",
            lambda: LGBMRegressor(
                **p("LightGBM_Tweedie", {
                    "n_estimators": 700, "learning_rate": 0.05, "num_leaves": 63,
                    "subsample": 0.8, "colsample_bytree": 0.8, "tweedie_variance_power": 1.2,
                }),
                objective="tweedie", subsample_freq=1, importance_type="gain",
                device=dev_lgbm, random_state=seed, n_jobs=-1, verbose=-1,
            ),
            espacio="unidades",
        ),
        "LightGBM_Poisson": EspecModelo(
            "LightGBM_Poisson", "categorico",
            lambda: LGBMRegressor(
                **p("LightGBM_Poisson", {
                    "n_estimators": 700, "learning_rate": 0.05, "num_leaves": 63,
                    "subsample": 0.8, "colsample_bytree": 0.8,
                }),
                objective="poisson", subsample_freq=1, importance_type="gain",
                device=dev_lgbm, random_state=seed, n_jobs=-1, verbose=-1,
            ),
            espacio="unidades",
        ),
        "XGBoost_Tweedie": EspecModelo(
            "XGBoost_Tweedie", "categorico",
            lambda: XGBRegressor(
                **p("XGBoost_Tweedie", {
                    "n_estimators": 700, "learning_rate": 0.05, "max_depth": 8,
                    "subsample": 0.8, "colsample_bytree": 0.8,
                    "tweedie_variance_power": 1.2,
                }),
                objective="reg:tweedie", tree_method="hist", enable_categorical=True,
                device=dev_xgb, random_state=seed, n_jobs=-1,
            ),
            espacio="unidades",
        ),
    }


# ---------------------------------------------------------------------------
# Entrenamiento de un estimador (entrena en GPU, predice en CPU)
# ---------------------------------------------------------------------------
def _post_fit_cpu(modelo: Any) -> Any:
    """Conmuta la **prediccion** de un XGBoost entrenado en GPU a CPU.

    El motor entrena en GPU (rapido) pero el artefacto se sirve **sin GPU** en
    produccion: la prediccion debe correr en CPU para ser portable. En XGBoost
    el ``device`` se fija en el booster, asi que tras ``fit`` se cambia a ``cpu``
    (la prediccion en CPU coincide con la de GPU salvo error de redondeo ~1e-7).
    LightGBM ya predice en CPU; el resto (sklearn) no usa GPU. No-op si el modelo
    no es XGBoost.
    """
    with contextlib.suppress(Exception):
        modelo.get_booster().set_param({"device": "cpu"})  # solo XGBoost
    return modelo


def _entrenar_modelo(spec: EspecModelo, X: Any, y: np.ndarray) -> Any:
    """Construye, ajusta y deja el estimador listo para predecir en CPU."""
    modelo = spec.construir()
    modelo.fit(X, y)
    return _post_fit_cpu(modelo)


# ---------------------------------------------------------------------------
# Predictor serializable (artefacto de produccion)
# ---------------------------------------------------------------------------
def _a_unidades(
    pred_crudo: np.ndarray,
    espacio: str,
    techo_log: float | None,
    techo_unidades: float | None,
) -> np.ndarray:
    """Convierte la salida cruda del modelo a **unidades de venta** (>= 0).

    Dos espacios de objetivo conviven en el zoo:
      - ``"log"``: el modelo predice ``log1p(sales)``; se recorta al techo en
        log-space y se invierte con ``expm1``.
      - ``"unidades"``: el modelo predice ``sales`` directo (objetivos Tweedie/
        Poisson, idoneos para conteos con muchos ceros); solo se recorta a [0, techo].
    """
    if espacio == "log":
        p = np.asarray(pred_crudo, dtype="float64")
        if techo_log is not None:
            p = np.clip(p, 0.0, techo_log)
        return np.clip(np.expm1(p), 0.0, None)
    # espacio "unidades"
    p = np.clip(np.asarray(pred_crudo, dtype="float64"), 0.0, None)
    if techo_unidades is not None:
        p = np.clip(p, 0.0, techo_unidades)
    return p


class ModeloEnsemble:
    """Combinacion lineal de varios boosters (todos del tipo ``"categorico"``).

    Cada submodelo puede vivir en un espacio distinto (``"log"`` o ``"unidades"``);
    el ensemble los lleva **a unidades** con :func:`_a_unidades` y los promedia con
    pesos convexos (``>= 0`` y suma 1). Asi un objetivo Tweedie (bueno en la cola)
    y uno log (bueno en el grueso) se complementan. Expone ``predict`` para encajar
    en un predictor como un estimador mas (espacio ``"unidades"``).

    Es serializable con joblib (clase top-level + atributos picklables).
    """

    def __init__(
        self,
        modelos: list[Any],
        espacios: list[str],
        pesos: np.ndarray,
        techo_log: float | None,
        techo_unidades: float | None,
        nombres: list[str] | None = None,
    ) -> None:
        self.modelos = modelos
        self.espacios = list(espacios)
        self.pesos = np.asarray(pesos, dtype="float64")
        self.techo_log = techo_log
        self.techo_unidades = techo_unidades
        self.nombres = nombres or [f"m{i}" for i in range(len(modelos))]

    def _columnas_unidades(self, X: Any) -> np.ndarray:
        cols = [
            _a_unidades(m.predict(X), esp, self.techo_log, self.techo_unidades)
            for m, esp in zip(self.modelos, self.espacios, strict=False)
        ]
        return np.column_stack(cols)

    def predict(self, X: Any) -> np.ndarray:
        """Predice unidades como combinacion ponderada de los submodelos."""
        return self._columnas_unidades(X) @ self.pesos


def _mejores_pesos(M: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Elige pesos convexos (>=0, suma 1) que minimizan el MAE sobre VALID.

    Compara tres estrategias y se queda con la de menor MAE en VALID (sin tocar
    TEST): (1) promedio simple, (2) pesos inversos al MAE de cada miembro y
    (3) mezcla por minimos cuadrados no negativos (``scipy.optimize.nnls``)
    renormalizada. La combinacion convexa evita el sobreajuste tipico del
    stacking sin restricciones.
    """
    from sklearn.metrics import mean_absolute_error

    k = M.shape[1]
    candidatos: list[np.ndarray] = [np.full(k, 1.0 / k)]

    maes = np.array([mean_absolute_error(y, M[:, j]) for j in range(k)])
    inv = 1.0 / np.clip(maes, 1e-9, None)
    candidatos.append(inv / inv.sum())

    try:
        from scipy.optimize import nnls

        w, _ = nnls(M, y)
        if w.sum() > 0:
            candidatos.append(w / w.sum())
    except Exception:  # pragma: no cover - scipy siempre disponible con sklearn
        pass

    return min(candidatos, key=lambda w: mean_absolute_error(y, M @ w))
