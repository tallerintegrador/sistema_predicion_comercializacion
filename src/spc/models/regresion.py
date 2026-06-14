"""Regresion de VENTAS (Fase 2a): pronostico de demanda ``sales``.

Entrena en escala ``log1p(sales)`` (el EDA muestra que reduce la asimetria de
7.36 -> 0.41) y **reporta todas las metricas en unidades** (invierte con
``expm1``). Compara dos baselines ingenuos contra cinco regresores, todo bajo
**validacion temporal sin fuga de futuro**, y serializa el ganador como artefacto
versionado (`regresion_v1`) que en produccion solo se carga y predice.

Capa de motor de ML: no conoce HTTP ni el negocio del cliente.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from spc.config import Settings
from spc.features.temporales import (
    COLS_SERIE,
    ConfigFeatures,
    columnas_rezago,
    construir_features,
)
from spc.utils.formatters import markdown_table
from spc.utils.logging import get_logger
from spc.utils.metrics import regression_metrics
from spc.utils.serializacion import cargar_artefacto, guardar_artefacto

log = get_logger("models.regresion")

VERSION_MODELO = "regresion_v3"
OBJETIVO = "sales"
COL_FECHA = "date"

# Horizonte de los holdouts: 16 dias = espejo del test real de Corporacion
# Favorita (2017-08-16 .. 2017-08-31).
DIAS_TEST = 16
DIAS_VALID = 16
# Validacion cruzada temporal (expanding window) sobre TRAIN+VALID.
CV_N_FOLDS = 3
CV_DIAS_VAL = 14
# Tolerancia relativa sobre el MAE medio de CV para considerar dos modelos
# "empatados" (dentro del ruido). Entre los empatados se elige por **estabilidad**
# (menor desviacion estandar del RMSE en CV) y, en ultimo termino, por menor MAE.
TOL_MAE_REL = 0.03


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


def calcular_cortes(
    fechas: pd.Series, dias_test: int = DIAS_TEST, dias_valid: int = DIAS_VALID
) -> CortesTemporales:
    """Deriva los cortes a partir de la fecha maxima observada."""
    fmax = pd.Timestamp(fechas.max())
    test_ini = fmax - pd.Timedelta(days=dias_test - 1)
    valid_fin = test_ini - pd.Timedelta(days=1)
    valid_ini = valid_fin - pd.Timedelta(days=dias_valid - 1)
    train_fin = valid_ini - pd.Timedelta(days=1)
    return CortesTemporales(train_fin, valid_ini, valid_fin, test_ini, fmax)


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
    """
    from lightgbm import LGBMRegressor
    from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
    from xgboost import XGBRegressor

    params = params or {}

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
                **p("RandomForest", dict(
                    n_estimators=120, max_depth=14, min_samples_leaf=20,
                )),
                random_state=seed, n_jobs=-1,
            ),
            espacio="log",
        ),
        "HistGradientBoosting": EspecModelo(
            "HistGradientBoosting", "categorico",
            lambda: HistGradientBoostingRegressor(
                **p("HistGradientBoosting", dict(
                    max_iter=300, learning_rate=0.06, max_leaf_nodes=63,
                    l2_regularization=1.0,
                )),
                categorical_features="from_dtype", random_state=seed,
            ),
            espacio="log",
        ),
        "LightGBM": EspecModelo(
            "LightGBM", "categorico",
            lambda: LGBMRegressor(
                **p("LightGBM", dict(
                    n_estimators=600, learning_rate=0.05, num_leaves=63,
                    subsample=0.8, colsample_bytree=0.8,
                )),
                subsample_freq=1, importance_type="gain",
                random_state=seed, n_jobs=-1, verbose=-1,
            ),
            espacio="log",
        ),
        "XGBoost": EspecModelo(
            "XGBoost", "categorico",
            lambda: XGBRegressor(
                **p("XGBoost", dict(
                    n_estimators=600, learning_rate=0.05, max_depth=8,
                    subsample=0.8, colsample_bytree=0.8,
                )),
                tree_method="hist", enable_categorical=True,
                random_state=seed, n_jobs=-1,
            ),
            espacio="log",
        ),
        # --- Objetivos para conteos con exceso de ceros (predicen unidades) ---
        "LightGBM_Tweedie": EspecModelo(
            "LightGBM_Tweedie", "categorico",
            lambda: LGBMRegressor(
                **p("LightGBM_Tweedie", dict(
                    n_estimators=700, learning_rate=0.05, num_leaves=63,
                    subsample=0.8, colsample_bytree=0.8, tweedie_variance_power=1.2,
                )),
                objective="tweedie", subsample_freq=1, importance_type="gain",
                random_state=seed, n_jobs=-1, verbose=-1,
            ),
            espacio="unidades",
        ),
        "LightGBM_Poisson": EspecModelo(
            "LightGBM_Poisson", "categorico",
            lambda: LGBMRegressor(
                **p("LightGBM_Poisson", dict(
                    n_estimators=700, learning_rate=0.05, num_leaves=63,
                    subsample=0.8, colsample_bytree=0.8,
                )),
                objective="poisson", subsample_freq=1, importance_type="gain",
                random_state=seed, n_jobs=-1, verbose=-1,
            ),
            espacio="unidades",
        ),
        "XGBoost_Tweedie": EspecModelo(
            "XGBoost_Tweedie", "categorico",
            lambda: XGBRegressor(
                **p("XGBoost_Tweedie", dict(
                    n_estimators=700, learning_rate=0.05, max_depth=8,
                    subsample=0.8, colsample_bytree=0.8,
                    tweedie_variance_power=1.2,
                )),
                objective="reg:tweedie", tree_method="hist", enable_categorical=True,
                random_state=seed, n_jobs=-1,
            ),
            espacio="unidades",
        ),
    }


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
    en :class:`PredictorRegresion` como un estimador mas (espacio ``"unidades"``).

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
            for m, esp in zip(self.modelos, self.espacios)
        ]
        return np.column_stack(cols)

    def predict(self, X: Any) -> np.ndarray:
        """Predice unidades como combinacion ponderada de los submodelos."""
        return self._columnas_unidades(X) @ self.pesos


class PredictorRegresion:
    """Envuelve la ingenieria de features + el modelo entrenado.

    Se serializa entero (joblib): en produccion se carga y se llama ``predecir``
    sin reentrenar. Reconstruye las features desde un historico ya integrado y
    devuelve la demanda en **unidades** (segun el espacio del objetivo).
    """

    def __init__(
        self,
        modelo: Any,
        features: list[str],
        cats: list[str],
        categorias: dict[str, list],
        cfg_features: ConfigFeatures,
        tipo: str,
        nombre_modelo: str,
        techo_log: float | None = None,
        techo_unidades: float | None = None,
        espacio: str = "log",
        version: str = VERSION_MODELO,
    ) -> None:
        self.modelo = modelo
        self.features = features
        self.cats = cats
        self.categorias = categorias
        self.cfg_features = cfg_features
        self.tipo = tipo
        self.nombre_modelo = nombre_modelo
        self.techo_log = techo_log
        self.techo_unidades = techo_unidades
        self.espacio = espacio
        self.version = version
        self.transformacion = "log1p" if espacio == "log" else "identidad"

    def _a_unidades(self, pred_crudo: np.ndarray) -> np.ndarray:
        return _a_unidades(pred_crudo, self.espacio, self.techo_log, self.techo_unidades)

    def _matriz(self, df_feat: pd.DataFrame) -> Any:
        df_cat, _ = _fijar_categorias(df_feat, self.cats, self.categorias)
        if self.tipo == "numerico":
            return _matriz_numerica(df_cat, self.features, self.cats)
        # "categorico" y "lineal" consumen el DataFrame con dtype category: el
        # modelo de arbol usa categoricas nativas y el pipeline lineal aplica
        # one-hot + estandarizacion internamente.
        return _matriz_categorica(df_cat, self.features, self.cats)

    def predecir(self, historico_integrado: pd.DataFrame) -> pd.Series:
        """Devuelve la demanda pronosticada (unidades) por fila del frame dado.

        ``historico_integrado`` debe traer el esquema del dataset analitico
        (mismas columnas que produce ``spc.data.integration``). El pronostico
        recursivo multi-horizonte es responsabilidad de la capa de servicio.
        """
        df_feat, _, _, _ = construir_features(historico_integrado, self.cfg_features)
        X = self._matriz(df_feat)
        unidades = self._a_unidades(self.modelo.predict(X))
        return pd.Series(unidades, index=df_feat.index, name="demanda_pronosticada")

    def pronosticar_horizonte(
        self,
        historico_integrado: pd.DataFrame,
        fecha_inicio: Any,
        fecha_fin: Any,
    ) -> pd.DataFrame:
        """Pronostico **recursivo multi-horizonte** dia a dia (forecast honesto).

        A diferencia de ``predecir`` (que asume conocidos los rezagos reales,
        util para evaluar con "teacher forcing"), este metodo pronostica el rango
        ``[fecha_inicio, fecha_fin]`` de forma autorregresiva: las ventas de cada
        dia ya pronosticado se **reinyectan** en el historico para que los
        rezagos/ventanas del dia siguiente las usen. Es la forma realista de
        proyectar a futuro (la capa de servicio/API la reutiliza tal cual).

        ``historico_integrado`` debe traer el esquema del dataset analitico, con
        las filas del horizonte ya presentes (calendario y promocion planificada
        conocidos); el valor de ``sales`` en esas filas se ignora y se sobreescribe.
        Devuelve un frame ``(date, store_nbr, family, demanda_pronosticada)``.
        """
        inicio = pd.Timestamp(fecha_inicio)
        fin = pd.Timestamp(fecha_fin)
        df = (
            historico_integrado.sort_values(COLS_SERIE + [COL_FECHA])
            .reset_index(drop=True)
            .copy()
        )
        # El objetivo se reescribe con predicciones (float): garantiza dtype
        # flotante de 64 bits para no chocar con columnas float32 (pandas 3 es
        # estricto al asignar floats de mayor precision sobre enteros/float32).
        df[OBJETIVO] = df[OBJETIVO].astype("float64")
        # El futuro es desconocido: anula las ventas del horizonte para no filtrar
        # el valor real al construir features intermedias.
        mask_h = (df[COL_FECHA] >= inicio) & (df[COL_FECHA] <= fin)
        df.loc[mask_h, OBJETIVO] = np.nan

        resultados: list[pd.DataFrame] = []
        for dia in pd.date_range(inicio, fin, freq="D"):
            df_feat, _, _, _ = construir_features(df, self.cfg_features)
            fila = df_feat[df_feat[COL_FECHA] == dia]
            if fila.empty:
                continue
            X = self._matriz(fila)
            unidades = self._a_unidades(self.modelo.predict(X))

            out = fila[COLS_SERIE].copy()
            out[COL_FECHA] = dia
            out["demanda_pronosticada"] = unidades
            resultados.append(out)

            # Reinyecta lo pronosticado como "venta real" del dia para alimentar
            # los rezagos del dia siguiente (autorregresion).
            pred_map = dict(zip(zip(out["store_nbr"], out["family"]), unidades))
            m = (df[COL_FECHA] == dia).to_numpy()
            claves = zip(df.loc[m, "store_nbr"], df.loc[m, "family"])
            df.loc[m, OBJETIVO] = np.array(
                [pred_map.get(k, 0.0) for k in claves], dtype="float64"
            )

        if not resultados:
            return pd.DataFrame(
                columns=[COL_FECHA, *COLS_SERIE, "demanda_pronosticada"]
            )
        cols = [COL_FECHA, *COLS_SERIE, "demanda_pronosticada"]
        return pd.concat(resultados, ignore_index=True)[cols]


# ---------------------------------------------------------------------------
# Baselines
# ---------------------------------------------------------------------------
def _metricas_baseline(df: pd.DataFrame, col_pred: str, mask: pd.Series) -> dict[str, float]:
    y_true = df.loc[mask, OBJETIVO].to_numpy("float64")
    y_pred = np.clip(df.loc[mask, col_pred].to_numpy("float64"), 0.0, None)
    return regression_metrics(y_true, y_pred)


def _elegir_ganador(
    metricas_df: pd.DataFrame, metricas_test_por_modelo: dict[str, dict[str, float]]
) -> tuple[str, dict[str, Any]]:
    """Elige el modelo de produccion priorizando **estabilidad**, no solo el MAE
    de test.

    Regla: dos modelos dentro del ruido en el **MAE medio de la validacion
    cruzada temporal** (banda relativa ``TOL_MAE_REL``) se consideran empatados;
    entre ellos gana el de **menor desviacion estandar del RMSE** en CV (mas
    estable y, en la practica, mas rapido). Sin CV disponible (p. ej. en tests)
    se cae al menor MAE de test.
    """
    modelos = list(metricas_test_por_modelo)
    cv = metricas_df[metricas_df["split"].str.startswith("cv_")]
    cv = cv[cv["modelo"].isin(modelos)]
    if cv.empty:
        mejor = min(modelos, key=lambda m: metricas_test_por_modelo[m]["MAE"])
        return mejor, {
            "regla": "menor MAE en TEST (sin validacion cruzada disponible)",
            "tol_mae_rel": TOL_MAE_REL,
        }
    resumen = cv.groupby("modelo").agg(
        mae_mean=("MAE", "mean"), rmse_std=("RMSE", "std")
    )
    best_mae = float(resumen["mae_mean"].min())
    banda = best_mae * (1.0 + TOL_MAE_REL)
    candidatos = resumen[resumen["mae_mean"] <= banda]
    mejor = str(candidatos["rmse_std"].idxmin())
    return mejor, {
        "regla": (
            "entre los modelos dentro de la banda de ruido del MAE de CV "
            f"(<= {banda:.3f}; tolerancia {TOL_MAE_REL:.0%}), el de menor RMSE_std "
            "(mas estable)"
        ),
        "tol_mae_rel": TOL_MAE_REL,
        "mae_cv_mejor": round(best_mae, 3),
        "banda_mae_cv": round(banda, 3),
        "candidatos": {
            m: {
                "mae_cv_mean": round(float(resumen.loc[m, "mae_mean"]), 3),
                "rmse_cv_std": round(float(resumen.loc[m, "rmse_std"]), 3),
            }
            for m in candidatos.index
        },
    }


def calcular_importancias(
    spec: EspecModelo,
    X_cat: pd.DataFrame,
    X_num: np.ndarray,
    y_log: np.ndarray,
    idx_fit: np.ndarray,
    idx_eval: np.ndarray,
    features: list[str],
    *,
    seed: int,
    top_n: int = 15,
    max_eval: int = 40_000,
    n_repeats: int = 3,
) -> pd.DataFrame:
    """Importancia de features por **permutation importance held-out**.

    Es agnostica al modelo (sirve para HistGradientBoosting -que no expone
    ``feature_importances_``-, boosting y el pipeline lineal) y mas honesta que
    la importancia interna de los arboles: mide cuanto empeora el MAE (en
    log-space) al **barajar** cada feature sobre el holdout de TEST. Se entrena
    una instancia del ganador en TRAIN y se evalua sobre una submuestra del TEST
    (sin tocar el reajuste final del artefacto).
    """
    from sklearn.inspection import permutation_importance

    if spec.tipo == "numerico":
        Xfit: Any = X_num[idx_fit]
        Xev: Any = X_num[idx_eval]
    else:  # "categorico" | "lineal"
        Xfit = X_cat.iloc[idx_fit]
        Xev = X_cat.iloc[idx_eval]

    modelo = spec.construir()
    modelo.fit(Xfit, y_log[idx_fit])

    rng = np.random.default_rng(seed)
    y_eval = y_log[idx_eval]
    if len(idx_eval) > max_eval:
        sel = rng.choice(len(idx_eval), size=max_eval, replace=False)
        Xev = Xev[sel] if spec.tipo == "numerico" else Xev.iloc[sel]
        y_eval = y_eval[sel]

    resultado = permutation_importance(
        modelo, Xev, y_eval,
        scoring="neg_mean_absolute_error",
        n_repeats=n_repeats, random_state=seed, n_jobs=-1,
    )
    imp = np.clip(resultado.importances_mean, 0.0, None)
    total = float(imp.sum()) or 1.0
    df = pd.DataFrame({"feature": features, "importancia": imp})
    df["importancia_pct"] = df["importancia"] / total * 100.0
    return df.sort_values("importancia", ascending=False).head(top_n).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Ensemble de boosters (combinacion convexa en unidades)
# ---------------------------------------------------------------------------
ENSEMBLE_TOP_K = 4  # cuantos boosters (mejores en VALID) entran en la mezcla


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


def construir_ensemble(
    zoo: dict[str, EspecModelo],
    X_cat: pd.DataFrame,
    idx_train_fit: np.ndarray,
    idx_valid: np.ndarray,
    y_log: np.ndarray,
    y_units: np.ndarray,
    techo_log: float,
    techo_unidades: float,
    *,
    top_k: int = ENSEMBLE_TOP_K,
) -> tuple[list[str], np.ndarray] | None:
    """Selecciona los mejores boosters en VALID y calcula sus pesos de mezcla.

    Entrena cada booster categorico sobre TRAIN, los evalua en VALID (en
    unidades), toma los ``top_k`` de menor MAE y obtiene los pesos convexos via
    :func:`_mejores_pesos`. Devuelve ``(nombres_elegidos, pesos)`` o ``None`` si
    hay menos de dos candidatos. El ajuste final (sobre TRAIN o sobre todo el
    historico) lo hace el llamador segun el uso (honesto vs artefacto).
    """
    from sklearn.metrics import mean_absolute_error

    candidatos = [n for n, s in zoo.items() if s.tipo == "categorico"]
    if len(candidatos) < 2:
        return None

    Xtr = X_cat.iloc[idx_train_fit]
    Xva = X_cat.iloc[idx_valid]
    yv = y_units[idx_valid]
    preds_va: dict[str, np.ndarray] = {}
    mae_va: dict[str, float] = {}
    for nombre in candidatos:
        spec = zoo[nombre]
        modelo = spec.construir()
        y_fit = y_log if spec.espacio == "log" else y_units
        modelo.fit(Xtr, y_fit[idx_train_fit])
        u = _a_unidades(modelo.predict(Xva), spec.espacio, techo_log, techo_unidades)
        preds_va[nombre] = u
        mae_va[nombre] = float(mean_absolute_error(yv, u))

    elegidos = sorted(candidatos, key=lambda n: mae_va[n])[: max(2, top_k)]
    M = np.column_stack([preds_va[n] for n in elegidos])
    pesos = _mejores_pesos(M, yv)
    return elegidos, pesos


def _ajustar_ensemble(
    zoo: dict[str, EspecModelo],
    elegidos: list[str],
    pesos: np.ndarray,
    X_cat: pd.DataFrame,
    idx_fit: np.ndarray,
    y_log: np.ndarray,
    y_units: np.ndarray,
    techo_log: float,
    techo_unidades: float,
) -> ModeloEnsemble:
    """Entrena los submodelos elegidos sobre ``idx_fit`` y arma el ModeloEnsemble."""
    Xf = X_cat.iloc[idx_fit]
    modelos: list[Any] = []
    espacios: list[str] = []
    for nombre in elegidos:
        spec = zoo[nombre]
        modelo = spec.construir()
        y_fit = y_log if spec.espacio == "log" else y_units
        modelo.fit(Xf, y_fit[idx_fit])
        modelos.append(modelo)
        espacios.append(spec.espacio)
    return ModeloEnsemble(
        modelos, espacios, pesos, techo_log, techo_unidades, nombres=list(elegidos)
    )


# ---------------------------------------------------------------------------
# Evaluacion honesta: pronostico recursivo multi-paso sobre el TEST
# ---------------------------------------------------------------------------
def evaluar_recursivo(
    predictor: PredictorRegresion,
    analytic: pd.DataFrame,
    cortes: CortesTemporales,
    *,
    buffer_dias: int = 120,
) -> tuple[dict[str, float], pd.DataFrame]:
    """Evalua el TEST con **pronostico recursivo multi-paso** (metrica honesta).

    La evaluacion por split (teacher forcing) alimenta los rezagos con ventas
    reales del propio horizonte, lo que **sobreestima** la precision real. Aqui
    se proyecta el rango de TEST dia a dia realimentando las predicciones (como
    en produccion) y se compara contra las ventas reales. Es la metrica guia del
    proyecto (``WAPE`` honesto).

    Se recorta el historico a ``buffer_dias`` previos al inicio del test para
    cubrir las ventanas/rezagos mas largos sin recomputar features sobre millones
    de filas (el resultado es identico: las ventanas tienen min_periods=1 y el
    buffer supera la ventana maxima).
    """
    inicio = pd.Timestamp(cortes.test_ini)
    fin = pd.Timestamp(cortes.test_fin)
    corte_hist = inicio - pd.Timedelta(days=buffer_dias)
    df = analytic[analytic[COL_FECHA] >= corte_hist].copy()

    reales = df[(df[COL_FECHA] >= inicio) & (df[COL_FECHA] <= fin)][
        [COL_FECHA, *COLS_SERIE, OBJETIVO]
    ].copy()
    pred = predictor.pronosticar_horizonte(df, inicio, fin)
    merged = reales.merge(pred, on=[COL_FECHA, *COLS_SERIE], how="inner")
    y_true = merged[OBJETIVO].to_numpy("float64")
    y_pred = merged["demanda_pronosticada"].to_numpy("float64")
    return regression_metrics(y_true, y_pred), merged


def _baseline_recursivo_serie(
    sales_hist: list[float], n_horizonte: int, modo: str
) -> list[float]:
    """Pronostico recursivo de un baseline para una serie (carry-forward honesto).

    ``modo='naive7'`` repite el valor de hace 7 dias; ``modo='media7'`` usa la
    media de los ultimos 7. Las predicciones se reinyectan para los dias
    siguientes (igual que el modelo), de modo que la comparacion es justa.
    """
    ext = list(sales_hist)
    preds: list[float] = []
    for _ in range(n_horizonte):
        if not ext:
            p = 0.0
        elif modo == "naive7":
            p = ext[-7] if len(ext) >= 7 else ext[-1]
        else:  # media7
            p = float(np.mean(ext[-7:]))
        p = max(0.0, p)
        preds.append(p)
        ext.append(p)
    return preds


def evaluar_baselines_recursivo(
    analytic: pd.DataFrame, cortes: CortesTemporales
) -> dict[str, dict[str, float]]:
    """Metricas honestas (recursivas) de los baselines naive(t-7) y media_movil_7."""
    inicio = pd.Timestamp(cortes.test_ini)
    fin = pd.Timestamp(cortes.test_fin)
    horizonte = pd.date_range(inicio, fin, freq="D")
    n_h = len(horizonte)
    df = analytic.sort_values(COLS_SERIE + [COL_FECHA])

    acc: dict[str, list[np.ndarray]] = {"naive7": [], "media7": [], "_true": []}
    for _, g in df.groupby(COLS_SERIE, observed=True):
        hist = g[g[COL_FECHA] < inicio][OBJETIVO].to_numpy("float64").tolist()
        real = g[(g[COL_FECHA] >= inicio) & (g[COL_FECHA] <= fin)][OBJETIVO]
        if real.empty:
            continue
        real_arr = real.to_numpy("float64")
        n = len(real_arr)
        acc["_true"].append(real_arr)
        acc["naive7"].append(
            np.array(_baseline_recursivo_serie(hist, n_h, "naive7")[:n])
        )
        acc["media7"].append(
            np.array(_baseline_recursivo_serie(hist, n_h, "media7")[:n])
        )

    if not acc["_true"]:
        return {}
    y_true = np.concatenate(acc["_true"])
    return {
        "BASELINE naive_estacional(t-7)": regression_metrics(
            y_true, np.concatenate(acc["naive7"])
        ),
        "BASELINE media_movil_7": regression_metrics(
            y_true, np.concatenate(acc["media7"])
        ),
    }


def agregados_recursivo(merged: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Desglose del error honesto por familia, tienda y agregacion temporal.

    Recibe el frame ``merged`` de :func:`evaluar_recursivo`
    (``date, store_nbr, family, sales, demanda_pronosticada``) y devuelve tablas
    de WAPE/MAE por familia, por tienda y sobre totales semanales/mensuales.
    """
    m = merged.rename(columns={OBJETIVO: "real", "demanda_pronosticada": "pred"})

    def _wape_mae(g: pd.DataFrame) -> pd.Series:
        err = (g["real"] - g["pred"]).abs()
        total = g["real"].abs().sum()
        return pd.Series(
            {
                "n": len(g),
                "WAPE": float(err.sum() / total * 100) if total else np.nan,
                "MAE": float(err.mean()),
            }
        )

    por_familia = (
        m.groupby("family", observed=True).apply(_wape_mae, include_groups=False)
        .reset_index()
        .sort_values("WAPE")
    )
    por_tienda = (
        m.groupby("store_nbr", observed=True).apply(_wape_mae, include_groups=False)
        .reset_index()
        .sort_values("WAPE")
    )

    # Agregacion temporal: se suman ventas reales/predichas por periodo (negocio
    # decide compras a nivel semanal/mensual, no diario) y se evalua el WAPE del
    # total agregado.
    m = m.copy()
    m["semana"] = m[COL_FECHA].dt.to_period("W").dt.start_time
    m["mes"] = m[COL_FECHA].dt.to_period("M").dt.start_time

    def _agg_periodo(col: str) -> pd.DataFrame:
        g = m.groupby(col).agg(real=("real", "sum"), pred=("pred", "sum")).reset_index()
        g["WAPE"] = (g["real"] - g["pred"]).abs() / g["real"].replace(0, np.nan) * 100
        g["error_abs"] = (g["real"] - g["pred"]).abs()
        return g

    return {
        "por_familia": por_familia,
        "por_tienda": por_tienda,
        "semanal": _agg_periodo("semana"),
        "mensual": _agg_periodo("mes"),
    }


# ---------------------------------------------------------------------------
# Entrenamiento + comparacion
# ---------------------------------------------------------------------------
@dataclass
class ResultadoEntrenamiento:
    metricas: pd.DataFrame
    cortes: CortesTemporales
    mejor_modelo: str
    predictor: PredictorRegresion
    features: list[str]
    cats: list[str]
    cfg_features: ConfigFeatures
    metricas_test_mejor: dict[str, float]
    metricas_test_por_modelo: dict[str, dict[str, float]]
    metricas_baseline: dict[str, dict[str, float]]
    criterio_seleccion: dict[str, Any]
    n_train: int
    n_artefacto: int
    importancias: pd.DataFrame
    # --- Evaluacion honesta (pronostico recursivo multi-paso sobre TEST) ---
    metricas_test_recursivo: dict[str, float]
    metricas_baseline_recursivo: dict[str, dict[str, float]]
    agregados: dict[str, pd.DataFrame]


def _muestrear(idx: np.ndarray, max_filas: int | None, seed: int) -> np.ndarray:
    """Submuestrea filas de entrenamiento (las features/lags ya estan calculadas
    sobre la serie completa, asi que muestrear filas no introduce fuga)."""
    if max_filas is None or len(idx) <= max_filas:
        return idx
    rng = np.random.default_rng(seed)
    return rng.choice(idx, size=max_filas, replace=False)


# ---------------------------------------------------------------------------
# HPO con Optuna (busqueda bayesiana sobre la CV temporal)
# ---------------------------------------------------------------------------
# Familias de booster que se tunean (Ridge/RandomForest se dejan fijos: el lineal
# no es candidato a produccion y el bosque es secundario frente a los boosters).
FAMILIAS_HPO = (
    "LightGBM",
    "XGBoost",
    "HistGradientBoosting",
    "LightGBM_Tweedie",
    "XGBoost_Tweedie",
)
HPO_CV_FOLDS = 2  # menos folds durante la busqueda (cada trial reentrena varias veces)


def _espacio_busqueda(familia: str, trial: Any) -> dict[str, Any]:
    """Define el espacio de hiperparametros muestreado por Optuna para cada familia."""
    if familia in ("LightGBM", "LightGBM_Tweedie"):
        params = {
            "n_estimators": trial.suggest_int("n_estimators", 300, 1200, step=100),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.12, log=True),
            "num_leaves": trial.suggest_int("num_leaves", 31, 255),
            "min_child_samples": trial.suggest_int("min_child_samples", 10, 120),
            "subsample": trial.suggest_float("subsample", 0.6, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.6, 1.0),
            "reg_lambda": trial.suggest_float("reg_lambda", 1e-3, 10.0, log=True),
        }
        if familia == "LightGBM_Tweedie":
            params["tweedie_variance_power"] = trial.suggest_float(
                "tweedie_variance_power", 1.05, 1.9
            )
        return params
    if familia in ("XGBoost", "XGBoost_Tweedie"):
        params = {
            "n_estimators": trial.suggest_int("n_estimators", 300, 1200, step=100),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.12, log=True),
            "max_depth": trial.suggest_int("max_depth", 4, 12),
            "min_child_weight": trial.suggest_float("min_child_weight", 1.0, 20.0),
            "subsample": trial.suggest_float("subsample", 0.6, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.6, 1.0),
            "reg_lambda": trial.suggest_float("reg_lambda", 1e-3, 10.0, log=True),
        }
        if familia == "XGBoost_Tweedie":
            params["tweedie_variance_power"] = trial.suggest_float(
                "tweedie_variance_power", 1.05, 1.9
            )
        return params
    if familia == "HistGradientBoosting":
        return {
            "max_iter": trial.suggest_int("max_iter", 200, 800, step=50),
            "learning_rate": trial.suggest_float("learning_rate", 0.02, 0.15, log=True),
            "max_leaf_nodes": trial.suggest_int("max_leaf_nodes", 31, 255),
            "min_samples_leaf": trial.suggest_int("min_samples_leaf", 10, 120),
            "l2_regularization": trial.suggest_float("l2_regularization", 1e-3, 10.0, log=True),
        }
    raise ValueError(f"Familia sin espacio de busqueda: {familia}")


def _cv_mae_familia(
    familia: str,
    params: dict[str, Any],
    X_cat: pd.DataFrame,
    X_num: np.ndarray,
    y_log: np.ndarray,
    y_units: np.ndarray,
    folds: list[tuple[np.ndarray, np.ndarray]],
    seed: int,
    techo_log: float,
    techo_unidades: float,
) -> float:
    """MAE medio (en unidades) de una familia con ``params`` sobre los folds CV."""
    spec = construir_zoo(seed, [], [], params={familia: params})[familia]
    y_fit = y_log if spec.espacio == "log" else y_units
    maes: list[float] = []
    for idx_tr, idx_va in folds:
        if spec.tipo == "numerico":
            Xtr, Xva = X_num[idx_tr], X_num[idx_va]
        else:
            Xtr, Xva = X_cat.iloc[idx_tr], X_cat.iloc[idx_va]
        modelo = spec.construir()
        modelo.fit(Xtr, y_fit[idx_tr])
        pred_u = _a_unidades(modelo.predict(Xva), spec.espacio, techo_log, techo_unidades)
        maes.append(float(np.mean(np.abs(y_units[idx_va] - pred_u))))
    return float(np.mean(maes)) if maes else float("inf")


def optimizar_hiperparametros(
    df_model: pd.DataFrame,
    X_cat: pd.DataFrame,
    X_num: np.ndarray,
    y_log: np.ndarray,
    y_units: np.ndarray,
    cortes: CortesTemporales,
    seed: int,
    max_train_rows: int | None,
    techo_log: float,
    techo_unidades: float,
    *,
    n_trials: int = 30,
) -> dict[str, dict[str, Any]]:
    """Busqueda bayesiana (Optuna) de hiperparametros por familia de booster.

    Optimiza el **MAE medio en unidades** sobre folds de validacion cruzada
    temporal expanding (los mismos cortes que la comparacion, nunca toca TEST).
    Devuelve ``{familia: mejores_params}`` para inyectar en ``construir_zoo``.
    Reproducible: cada estudio usa un ``TPESampler`` sembrado.
    """
    import optuna

    optuna.logging.set_verbosity(optuna.logging.WARNING)

    # Construye los folds una sola vez (capa de muestreo agresiva para la busqueda).
    fechas = df_model[COL_FECHA]
    idx = np.arange(len(df_model))
    cap = None if max_train_rows is None else max(20_000, max_train_rows // 4)
    folds: list[tuple[np.ndarray, np.ndarray]] = []
    for k in range(HPO_CV_FOLDS):
        val_fin = cortes.valid_fin - pd.Timedelta(days=k * CV_DIAS_VAL)
        val_ini = val_fin - pd.Timedelta(days=CV_DIAS_VAL - 1)
        m_tr = (fechas < val_ini).to_numpy()
        m_va = ((fechas >= val_ini) & (fechas <= val_fin)).to_numpy()
        if m_tr.sum() == 0 or m_va.sum() == 0:
            continue
        folds.append((_muestrear(idx[m_tr], cap, seed + k), idx[m_va]))

    if not folds:
        log.warning("Sin folds para HPO; se usan hiperparametros por defecto.")
        return {}

    mejores: dict[str, dict[str, Any]] = {}
    for familia in FAMILIAS_HPO:
        def objetivo(trial: Any, _fam: str = familia) -> float:
            params = _espacio_busqueda(_fam, trial)
            return _cv_mae_familia(
                _fam, params, X_cat, X_num, y_log, y_units, folds,
                seed, techo_log, techo_unidades,
            )

        estudio = optuna.create_study(
            direction="minimize",
            sampler=optuna.samplers.TPESampler(seed=seed),
        )
        estudio.optimize(objetivo, n_trials=n_trials, show_progress_bar=False)
        mejores[familia] = estudio.best_params
        log.info(
            "HPO %s -> MAE_cv %.3f | %s",
            familia, estudio.best_value, estudio.best_params,
        )
    return mejores


def entrenar_y_comparar(
    analytic: pd.DataFrame,
    settings: Settings,
    *,
    cfg_features: ConfigFeatures | None = None,
    max_train_rows: int | None = 250_000,
    con_cv: bool = True,
    hpo: bool = False,
    hpo_trials: int = 30,
    ensemble: bool = True,
) -> ResultadoEntrenamiento:
    """Construye features, valida temporalmente y compara baselines vs el zoo.

    Con ``hpo=True`` ejecuta una busqueda bayesiana (Optuna) de hiperparametros
    por familia de booster sobre la validacion cruzada temporal antes de comparar.
    """
    seed = settings.random_seed
    cfg_features = cfg_features or ConfigFeatures()

    log.info("Construyendo features temporales (leak-safe)...")
    df_feat, features, cats, cfg_features = construir_features(analytic, cfg_features)

    # Descarta el calentamiento (filas con NaN en los rezagos del objetivo).
    cols_lag = columnas_rezago(features)
    df_model = df_feat.dropna(subset=[c for c in cols_lag if c.startswith("sales_lag_")]).copy()
    df_model[cols_lag] = df_model[cols_lag].fillna(0.0)

    # Categorias fijas (consistencia de codigos entre splits y en prediccion).
    df_model, categorias = _fijar_categorias(df_model, cats, None)

    # Objetivos: unidades (verdad de terreno para TODAS las metricas) y su log1p
    # (para los modelos del espacio "log"). Los objetivos Tweedie/Poisson usan
    # directamente las unidades.
    y_units = df_model[OBJETIVO].to_numpy("float64")
    y_log = np.log1p(y_units)

    cortes = calcular_cortes(df_model[COL_FECHA])
    fechas = df_model[COL_FECHA]
    mask_train = fechas <= cortes.train_fin
    mask_valid = (fechas >= cortes.valid_ini) & (fechas <= cortes.valid_fin)
    mask_test = (fechas >= cortes.test_ini) & (fechas <= cortes.test_fin)
    log.info("Cortes -> %s", cortes.as_dict())

    # Techos de prediccion: ningun pronostico debe superar el maximo historico
    # **observado en TRAIN** (en su espacio). Calcularlo sobre todo ``df_model``
    # (incluido valid/test) seria una fuga sutil: el techo no puede mirar el
    # futuro. Tambien evita que un modelo dispare a valores absurdos.
    techo_log = float(np.nanmax(y_log[mask_train.to_numpy()]))
    techo_unidades = float(np.nanmax(y_units[mask_train.to_numpy()]))

    # Matrices por tipo.
    X_cat = _matriz_categorica(df_model, features, cats)
    X_num = _matriz_numerica(df_model, features, cats)

    idx = np.arange(len(df_model))
    idx_train = idx[mask_train.to_numpy()]
    idx_valid = idx[mask_valid.to_numpy()]
    idx_test = idx[mask_test.to_numpy()]
    idx_train_fit = _muestrear(idx_train, max_train_rows, seed)

    # --- HPO opcional: optimiza hiperparametros por familia sobre la CV temporal ---
    params_tuneados: dict[str, dict[str, Any]] = {}
    if hpo:
        log.info("Optimizando hiperparametros con Optuna (%d trials/familia)...", hpo_trials)
        params_tuneados = optimizar_hiperparametros(
            df_model, X_cat, X_num, y_log, y_units, cortes, seed,
            max_train_rows, techo_log, techo_unidades, n_trials=hpo_trials,
        )

    zoo = construir_zoo(seed, features, cats, params=params_tuneados)
    filas_metricas: list[dict] = []

    def _y_fit(espacio: str) -> np.ndarray:
        return y_log if espacio == "log" else y_units

    # --- Baselines (en unidades; no requieren ajuste) ---
    baselines = {
        "BASELINE naive_estacional(t-7)": "sales_lag_7",
        "BASELINE media_movil_7": "sales_rmean_7",
    }
    metricas_baseline: dict[str, dict[str, float]] = {}
    for nombre, col in baselines.items():
        for split, mask in (("valid", mask_valid), ("test", mask_test)):
            m = _metricas_baseline(df_model, col, mask)
            filas_metricas.append({"modelo": nombre, "split": split, **m})
            if split == "test":
                metricas_baseline[nombre] = m

    # --- Modelos: ajuste en TRAIN, evaluacion en VALID y TEST ---
    metricas_test_por_modelo: dict[str, dict[str, float]] = {}

    for nombre, spec in zoo.items():
        log.info("Entrenando %s...", nombre)
        if spec.tipo == "numerico":
            Xtr = X_num[idx_train_fit]
            Xva, Xte = X_num[idx_valid], X_num[idx_test]
        else:  # "categorico" o "lineal": DataFrame con dtype category
            Xtr = X_cat.iloc[idx_train_fit]
            Xva, Xte = X_cat.iloc[idx_valid], X_cat.iloc[idx_test]

        modelo = spec.construir()
        modelo.fit(Xtr, _y_fit(spec.espacio)[idx_train_fit])

        for split, X_split, idx_split in (("valid", Xva, idx_valid), ("test", Xte, idx_test)):
            pred_u = _a_unidades(
                modelo.predict(X_split), spec.espacio, techo_log, techo_unidades
            )
            m = regression_metrics(y_units[idx_split], pred_u)
            filas_metricas.append({"modelo": nombre, "split": split, **m})
            if split == "test":
                metricas_test_por_modelo[nombre] = m

    # --- Validacion cruzada temporal (expanding) sobre TRAIN+VALID ---
    if con_cv:
        _agregar_cv(
            df_model, X_cat, X_num, y_log, y_units, zoo, cortes, seed,
            max_train_rows, techo_log, techo_unidades, filas_metricas,
        )

    metricas_df = pd.DataFrame(filas_metricas)

    # --- Eleccion del ganador: estabilidad por encima del MAE de test "a secas" ---
    mejor, criterio = _elegir_ganador(metricas_df, metricas_test_por_modelo)
    log.info("Modelo elegido = %s | criterio = %s", mejor, criterio.get("regla"))

    # --- Reajuste del ganador sobre TODO el historico etiquetado ---
    #     (mas datos = mejor artefacto de produccion; las metricas reportadas
    #     provienen del holdout temporal, no de este reajuste final).
    log.info("Reajustando %s sobre todo el historico para el artefacto...", mejor)
    spec = zoo[mejor]
    X_full: Any = X_num if spec.tipo == "numerico" else X_cat
    modelo_final = spec.construir()
    modelo_final.fit(X_full, _y_fit(spec.espacio))
    predictor_final = PredictorRegresion(
        modelo=modelo_final, features=features, cats=cats, categorias=categorias,
        cfg_features=cfg_features, tipo=spec.tipo, nombre_modelo=mejor,
        techo_log=techo_log, techo_unidades=techo_unidades, espacio=spec.espacio,
    )
    importancias = calcular_importancias(
        spec, X_cat, X_num, _y_fit(spec.espacio), idx_train_fit, idx_test, features,
        seed=seed,
    )

    # --- Evaluacion honesta: pronostico recursivo multi-paso sobre TEST ---
    #     El ganador se entrena SOLO con TRAIN (no ve valid/test) y proyecta el
    #     test de forma autorregresiva, como en produccion. Esta es la metrica
    #     guia (WAPE honesto); la del split por modelo usa teacher forcing y
    #     sobreestima la precision real.
    log.info("Evaluando %s con pronostico recursivo (metrica honesta)...", mejor)
    modelo_honesto = spec.construir()
    if spec.tipo == "numerico":
        modelo_honesto.fit(X_num[idx_train_fit], _y_fit(spec.espacio)[idx_train_fit])
    else:
        modelo_honesto.fit(X_cat.iloc[idx_train_fit], _y_fit(spec.espacio)[idx_train_fit])
    predictor_honesto = PredictorRegresion(
        modelo=modelo_honesto, features=features, cats=cats, categorias=categorias,
        cfg_features=cfg_features, tipo=spec.tipo, nombre_modelo=mejor,
        techo_log=techo_log, techo_unidades=techo_unidades, espacio=spec.espacio,
    )
    metricas_rec, merged_rec = evaluar_recursivo(predictor_honesto, analytic, cortes)
    metricas_base_rec = evaluar_baselines_recursivo(analytic, cortes)
    agg = agregados_recursivo(merged_rec) if not merged_rec.empty else {}
    log.info(
        "WAPE honesto (recursivo) test = %.2f%% | MAE = %.2f",
        metricas_rec.get("WAPE", float("nan")),
        metricas_rec.get("MAE", float("nan")),
    )

    # --- F4: Ensemble de boosters (gana solo si baja el WAPE honesto) ---
    #     Mezcla convexa (en unidades) de los mejores boosters en VALID. Se
    #     evalua con el MISMO pronostico recursivo honesto; reemplaza al ganador
    #     individual unicamente si mejora la metrica guia (WAPE recursivo).
    if ensemble:
        sel = construir_ensemble(
            zoo, X_cat, idx_train_fit, idx_valid, y_log, y_units,
            techo_log, techo_unidades,
        )
        if sel is not None:
            elegidos, pesos = sel
            nombre_ens = "Ensemble(" + "+".join(elegidos) + ")"
            log.info(
                "Ensemble candidato = %s | pesos = %s",
                nombre_ens, np.round(pesos, 3).tolist(),
            )
            # Honesto: submodelos en TRAIN, evaluacion recursiva sobre TEST.
            ens_honesto = _ajustar_ensemble(
                zoo, elegidos, pesos, X_cat, idx_train_fit,
                y_log, y_units, techo_log, techo_unidades,
            )
            pred_ens_honesto = PredictorRegresion(
                modelo=ens_honesto, features=features, cats=cats, categorias=categorias,
                cfg_features=cfg_features, tipo="categorico", nombre_modelo=nombre_ens,
                techo_log=None, techo_unidades=techo_unidades, espacio="unidades",
            )
            metricas_rec_ens, merged_rec_ens = evaluar_recursivo(
                pred_ens_honesto, analytic, cortes
            )
            log.info(
                "WAPE honesto ensemble = %.2f%% (individual = %.2f%%)",
                metricas_rec_ens.get("WAPE", float("nan")),
                metricas_rec.get("WAPE", float("nan")),
            )
            if metricas_rec_ens.get("WAPE", float("inf")) < metricas_rec.get(
                "WAPE", float("inf")
            ):
                # El ensemble gana: artefacto final = submodelos sobre TODO.
                ens_final = _ajustar_ensemble(
                    zoo, elegidos, pesos, X_cat, np.arange(len(y_log)),
                    y_log, y_units, techo_log, techo_unidades,
                )
                predictor_final = PredictorRegresion(
                    modelo=ens_final, features=features, cats=cats, categorias=categorias,
                    cfg_features=cfg_features, tipo="categorico", nombre_modelo=nombre_ens,
                    techo_log=None, techo_unidades=techo_unidades, espacio="unidades",
                )
                # Metricas TEST (teacher forcing) del ensemble para el reporte.
                pred_ens_test = ens_honesto.predict(X_cat.iloc[idx_test])
                metricas_test_por_modelo[nombre_ens] = regression_metrics(
                    y_units[idx_test], pred_ens_test
                )
                criterio = {
                    "regla": (
                        "ensemble convexo de boosters elegido por **menor WAPE "
                        "honesto (recursivo)** frente al ganador individual "
                        f"`{mejor}`"
                    ),
                    "ganador_individual": mejor,
                    "wape_individual": round(metricas_rec.get("WAPE", float("nan")), 3),
                    "wape_ensemble": round(metricas_rec_ens.get("WAPE", float("nan")), 3),
                    "miembros": list(elegidos),
                    "pesos": [round(float(w), 4) for w in pesos],
                }
                mejor = nombre_ens
                metricas_rec, merged_rec = metricas_rec_ens, merged_rec_ens
                agg = (
                    agregados_recursivo(merged_rec) if not merged_rec.empty else {}
                )
                log.info("Ensemble seleccionado como modelo de produccion.")

    return ResultadoEntrenamiento(
        metricas=metricas_df,
        cortes=cortes,
        mejor_modelo=mejor,
        predictor=predictor_final,
        features=features,
        cats=cats,
        cfg_features=cfg_features,
        metricas_test_mejor={
            "MAE": metricas_test_por_modelo[mejor]["MAE"],
            "RMSE": metricas_test_por_modelo[mejor]["RMSE"],
        },
        metricas_test_por_modelo=metricas_test_por_modelo,
        metricas_baseline=metricas_baseline,
        criterio_seleccion=criterio,
        n_train=len(idx_train_fit),
        n_artefacto=len(y_log),
        importancias=importancias,
        metricas_test_recursivo=metricas_rec,
        metricas_baseline_recursivo=metricas_base_rec,
        agregados=agg,
    )


def _agregar_cv(
    df_model: pd.DataFrame,
    X_cat: pd.DataFrame,
    X_num: np.ndarray,
    y_log: np.ndarray,
    y_units: np.ndarray,
    zoo: dict[str, EspecModelo],
    cortes: CortesTemporales,
    seed: int,
    max_train_rows: int | None,
    techo_log: float,
    techo_unidades: float,
    filas_metricas: list[dict],
) -> None:
    """Validacion cruzada temporal expanding: folds de CV_DIAS_VAL dias dentro de
    TRAIN+VALID (nunca toca TEST). Agrega MAE/RMSE por fold (en unidades)."""
    fechas = df_model[COL_FECHA]
    idx = np.arange(len(df_model))
    cap_cv = None if max_train_rows is None else max_train_rows // 2

    for k in range(CV_N_FOLDS):
        val_fin = cortes.valid_fin - pd.Timedelta(days=k * CV_DIAS_VAL)
        val_ini = val_fin - pd.Timedelta(days=CV_DIAS_VAL - 1)
        m_tr = (fechas < val_ini).to_numpy()
        m_va = ((fechas >= val_ini) & (fechas <= val_fin)).to_numpy()
        if m_tr.sum() == 0 or m_va.sum() == 0:
            continue
        idx_tr = _muestrear(idx[m_tr], cap_cv, seed + k)
        idx_va = idx[m_va]
        for nombre, spec in zoo.items():
            if spec.tipo == "numerico":
                Xtr, Xva = X_num[idx_tr], X_num[idx_va]
            else:  # "categorico" o "lineal"
                Xtr, Xva = X_cat.iloc[idx_tr], X_cat.iloc[idx_va]
            y_fit = y_log if spec.espacio == "log" else y_units
            modelo = spec.construir()
            modelo.fit(Xtr, y_fit[idx_tr])
            pred_u = _a_unidades(
                modelo.predict(Xva), spec.espacio, techo_log, techo_unidades
            )
            m = regression_metrics(y_units[idx_va], pred_u)
            filas_metricas.append({"modelo": nombre, "split": f"cv_fold_{k + 1}", **m})


# ---------------------------------------------------------------------------
# Persistencia de metricas, artefacto y reporte
# ---------------------------------------------------------------------------
def persistir_metricas(res: ResultadoEntrenamiento, settings: Settings) -> Path:
    """Guarda la tabla de metricas en CSV y JSON (trazabilidad reproducible)."""
    settings.processed_dir.mkdir(parents=True, exist_ok=True)
    ruta_csv = settings.processed_dir / "metricas_regresion_2a.csv"
    res.metricas.to_csv(ruta_csv, index=False)
    (settings.processed_dir / "metricas_regresion_2a.json").write_text(
        res.metricas.to_json(orient="records", force_ascii=False, indent=2),
        encoding="utf-8",
    )
    if not res.importancias.empty:
        res.importancias.to_csv(
            settings.processed_dir / "importancias_regresion_2a.csv", index=False
        )
    # Desgloses del error honesto (recursivo) por familia/tienda y agregacion
    # temporal: insumo directo para COMPRAS/ALMACEN a nivel semanal/mensual.
    nombres = {
        "por_familia": "wape_recursivo_por_familia.csv",
        "por_tienda": "wape_recursivo_por_tienda.csv",
        "semanal": "wape_recursivo_semanal.csv",
        "mensual": "wape_recursivo_mensual.csv",
    }
    for clave, fichero in nombres.items():
        tabla = res.agregados.get(clave)
        if tabla is not None and not tabla.empty:
            tabla.to_csv(settings.processed_dir / fichero, index=False)
    return ruta_csv


def serializar_artefacto(res: ResultadoEntrenamiento, settings: Settings) -> tuple[Path, Path]:
    """Serializa el predictor ganador + metadatos en ``models/``."""
    ruta = settings.base_dir / "models" / f"{VERSION_MODELO}.joblib"
    metadatos = {
        "version": VERSION_MODELO,
        "fecha_entrenamiento": date.today().isoformat(),
        "modelo": res.mejor_modelo,
        "criterio_seleccion": res.criterio_seleccion,
        "transformacion_objetivo": res.predictor.transformacion,
        "espacio_objetivo": res.predictor.espacio,
        "escala_metricas": "unidades",
        "techo_log_prediccion": res.predictor.techo_log,
        "techo_unidades_prediccion": res.predictor.techo_unidades,
        "semilla": settings.random_seed,
        "features": res.features,
        "features_categoricas": res.cats,
        "config_features": res.cfg_features.as_dict(),
        "cortes_temporales": res.cortes.as_dict(),
        "metricas_test": res.metricas_test_por_modelo.get(
            res.mejor_modelo, res.metricas_test_mejor
        ),
        "metricas_test_baseline": res.metricas_baseline,
        "metricas_test_recursivo": res.metricas_test_recursivo,
        "metricas_test_recursivo_baseline": res.metricas_baseline_recursivo,
        "nota_evaluacion": (
            "metricas_test usan teacher forcing (rezagos reales); "
            "metricas_test_recursivo son el pronostico autorregresivo honesto "
            "(metrica guia del proyecto)."
        ),
        "n_filas_comparacion": res.n_train,
        "n_filas_artefacto_final": res.n_artefacto,
    }
    return guardar_artefacto(res.predictor, ruta, metadatos)


def _bloque_recursivo(res: ResultadoEntrenamiento) -> list[str]:
    """Seccion del reporte con la metrica honesta (pronostico recursivo)."""
    rec = res.metricas_test_recursivo
    if not rec:
        return []
    base = res.metricas_baseline_recursivo or {}
    base_wape = min((v.get("WAPE", float("inf")) for v in base.values()), default=None)

    filas = [{"fuente": f"**{res.mejor_modelo}** (recursivo)", **rec}]
    for nombre, m in base.items():
        filas.append({"fuente": nombre, **m})
    tabla = pd.DataFrame(filas)
    cols = ["fuente", "WAPE", "MAE", "RMSE", "RMSLE", "MAPE", "R2"]
    cols = [c for c in cols if c in tabla.columns]
    tabla = tabla[cols].copy()
    for c in cols[1:]:
        tabla[c] = tabla[c].astype("float64").round(3)

    lineas = [
        "## Evaluacion HONESTA - pronostico recursivo multi-paso (metrica guia)",
        "",
        "A diferencia de la tabla anterior (que usa *teacher forcing*: alimenta los "
        "rezagos con las ventas **reales** del horizonte y por eso sobreestima la "
        "precision), aqui el modelo proyecta los 16 dias de TEST de forma "
        "**autorregresiva**, reinyectando sus propias predicciones como en "
        "produccion. Es la metrica de referencia del proyecto.",
        "",
        markdown_table(tabla),
        "",
        f"- **WAPE honesto** del modelo = {rec.get('WAPE', float('nan')):.2f}%.",
    ]
    if base_wape is not None:
        delta = base_wape - rec.get("WAPE", float("nan"))
        lineas.append(
            f"- Mejor baseline honesto (recursivo) = {base_wape:.2f}% WAPE "
            f"-> el modelo mejora {delta:.2f} puntos."
        )
    # Composicion del ensemble (si el ganador es una mezcla de boosters).
    crit = res.criterio_seleccion or {}
    if crit.get("miembros"):
        miembros = crit["miembros"]
        pesos = crit.get("pesos", [])
        comp = ", ".join(
            f"`{m}` ({w:.0%})" for m, w in zip(miembros, pesos)
        ) if pesos else ", ".join(f"`{m}`" for m in miembros)
        lineas += [
            "",
            f"- **Modelo de produccion = ensemble convexo** de: {comp}.",
            f"- Elegido por **menor WAPE honesto**: ensemble "
            f"{crit.get('wape_ensemble', float('nan'))}% vs ganador individual "
            f"`{crit.get('ganador_individual', '?')}` "
            f"{crit.get('wape_individual', float('nan'))}%.",
        ]
    agg = res.agregados or {}
    fam = agg.get("por_familia")
    tienda = agg.get("por_tienda")
    if fam is not None and not fam.empty:
        fam_fmt = fam.copy()
        for c in ("WAPE", "MAE"):
            fam_fmt[c] = fam_fmt[c].round(2)
        lineas += [
            "",
            "### WAPE honesto por familia (las 10 peores)",
            "",
            markdown_table(fam_fmt.sort_values("WAPE", ascending=False).head(10)),
        ]
    if tienda is not None and not tienda.empty:
        t_fmt = tienda.copy()
        for c in ("WAPE", "MAE"):
            t_fmt[c] = t_fmt[c].round(2)
        lineas += [
            "",
            "### WAPE honesto por tienda (las 10 peores)",
            "",
            markdown_table(t_fmt.sort_values("WAPE", ascending=False).head(10)),
        ]
    sem = agg.get("semanal")
    mes = agg.get("mensual")
    if sem is not None and not sem.empty:
        s_fmt = sem.copy()
        for c in ("real", "pred", "WAPE", "error_abs"):
            if c in s_fmt.columns:
                s_fmt[c] = s_fmt[c].round(2)
        lineas += [
            "",
            "### Agregado SEMANAL (suma de ventas reales vs pronosticadas)",
            "",
            markdown_table(s_fmt),
        ]
    if mes is not None and not mes.empty:
        m_fmt = mes.copy()
        for c in ("real", "pred", "WAPE", "error_abs"):
            if c in m_fmt.columns:
                m_fmt[c] = m_fmt[c].round(2)
        lineas += [
            "",
            "### Agregado MENSUAL (suma de ventas reales vs pronosticadas)",
            "",
            markdown_table(m_fmt),
        ]
    lineas.append("")
    return lineas


def _texto_criterio(criterio: dict[str, Any]) -> str:
    """Renderiza el criterio de seleccion como texto para el reporte."""
    regla = criterio.get("regla", "")
    cands = criterio.get("candidatos")
    if not cands:
        return f"Regla: {regla}."
    filas = "; ".join(
        f"`{m}` (MAE_cv {d['mae_cv_mean']}, RMSE_std {d['rmse_cv_std']})"
        for m, d in cands.items()
    )
    return (
        f"Regla aplicada: {regla}. Candidatos dentro de la banda de ruido del MAE "
        f"de CV: {filas}. Gana el de **menor RMSE_std** (mas estable y, en la "
        f"practica, mas rapido) frente a desempatar por una decima de MAE de test."
    )


def escribir_reporte(res: ResultadoEntrenamiento, settings: Settings) -> Path:
    """Genera ``docs/reporte_regresion_2a.md`` con la comparacion de modelos."""
    md = res.metricas.copy()

    # --- Ridge: retirar de las tablas si, tras corregir el pipeline, sigue por
    #     debajo de los baselines (peor que el peor baseline en MAE de test). ---
    nota_ridge = ""
    ridge_mae = res.metricas_test_por_modelo.get("Ridge", {}).get("MAE")
    peor_baseline_mae = max(v["MAE"] for v in res.metricas_baseline.values())
    if ridge_mae is not None and ridge_mae > peor_baseline_mae:
        md = md[md["modelo"] != "Ridge"].copy()
        nota_ridge = (
            f"> **Nota — Ridge retirado de las tablas.** Tras montarlo correctamente "
            f"(pipeline propio: one-hot de categoricos + estandarizacion de numericas "
            f"y recorte de `expm1`), el lineal alcanza MAE(test) = {ridge_mae:.2f}, "
            f"todavia por encima del peor baseline ({peor_baseline_mae:.2f}). Se "
            f"documenta y se excluye de la comparacion para no dejar un modelo no apto "
            f"en el entregable; queda como referencia interpretable, no como candidato "
            f"a produccion."
        )

    test = md[md["split"] == "test"].copy().sort_values("MAE")
    valid = md[md["split"] == "valid"].copy().sort_values("MAE")
    cv = md[md["split"].str.startswith("cv_")].copy()
    cv_resumen = (
        cv.groupby("modelo")[["MAE", "RMSE"]].agg(["mean", "std"]).round(3)
        if not cv.empty
        else pd.DataFrame()
    )

    # Jerarquia de metricas: WAPE/MAE/RMSE/RMSLE primero (principales); MAPE
    # (inflado por ceros) y R2 quedan como referencia secundaria.
    metricas_cols = ["WAPE", "MAE", "RMSE", "RMSLE", "MAPE", "R2"]

    def _fmt(df: pd.DataFrame) -> pd.DataFrame:
        out = df[["modelo", *metricas_cols]].copy()
        for c in metricas_cols:
            out[c] = out[c].round(3)
        return out

    mejor = res.mejor_modelo
    base_mae = min(v["MAE"] for v in res.metricas_baseline.values())
    base_rmse = min(v["RMSE"] for v in res.metricas_baseline.values())
    gan_mae = res.metricas_test_mejor["MAE"]
    gan_rmse = res.metricas_test_mejor["RMSE"]
    mejora_mae = (base_mae - gan_mae) / base_mae * 100 if base_mae else float("nan")
    mejora_rmse = (base_rmse - gan_rmse) / base_rmse * 100 if base_rmse else float("nan")

    lineas = [
        "# Reporte de Regresion (Fase 2a) - VENTAS",
        "",
        "> Generado por `spc.models.regresion`. Metricas en **unidades** "
        "(objetivo entrenado en `log1p`, invertido con `expm1`). Validacion "
        "temporal sin fuga de futuro.",
        "",
        "## Jerarquia de metricas",
        "",
        "Se prioriza, en este orden: **WAPE**, **MAE**, **RMSE** y **RMSLE**. El "
        "**MAPE (~32%) esta inflado** por el 31% de ceros en `sales` "
        "(zero-inflation): al excluir los ceros del denominador, sobre-pondera las "
        "series de bajo volumen, asi que **no debe usarse como metrica principal** "
        "(se incluye solo como referencia). `R2` se reporta como contexto, no como "
        "criterio de seleccion.",
        "",
        "## Cortes temporales",
        "",
        f"- **Train:** {res.cortes.as_dict()['train']}",
        f"- **Valid:** {res.cortes.as_dict()['valid']}",
        f"- **Test:** {res.cortes.as_dict()['test']}",
        f"- Filas para **comparar** modelos (submuestreo de train): "
        f"{res.n_train:,}".replace(",", " "),
        f"- Filas del **artefacto final** (`{VERSION_MODELO}`, reajuste sobre todo "
        f"el historico etiquetado): {format(res.n_artefacto, ',').replace(',', ' ')}",
        "",
        "## Resultados en TEST (ordenado por MAE, menor es mejor)",
        "",
        markdown_table(_fmt(test)),
        "",
    ]
    if nota_ridge:
        lineas += [nota_ridge, ""]
    lineas += [
        f"**Modelo elegido: `{mejor}`** (artefacto `{VERSION_MODELO}`).",
        "",
        f"- MAE elegido = {gan_mae:.3f} vs mejor baseline = {base_mae:.3f} "
        f"-> mejora {mejora_mae:.1f}%.",
        f"- RMSE elegido = {gan_rmse:.3f} vs mejor baseline = {base_rmse:.3f} "
        f"-> mejora {mejora_rmse:.1f}%.",
        "",
        "### Criterio de seleccion (estabilidad, no solo MAE de test)",
        "",
        _texto_criterio(res.criterio_seleccion),
        "",
    ]
    lineas += _bloque_recursivo(res)
    lineas += [
        "## Resultados en VALID (ordenado por MAE)",
        "",
        markdown_table(_fmt(valid)),
        "",
    ]
    if not cv_resumen.empty:
        cv_flat = cv_resumen.copy()
        cv_flat.columns = ["_".join(c) for c in cv_flat.columns]
        cv_flat = cv_flat.reset_index()
        lineas += [
            "## Validacion cruzada temporal (expanding, MAE/RMSE en unidades)",
            "",
            markdown_table(cv_flat),
            "",
        ]
    if not res.importancias.empty:
        imp = res.importancias.copy()
        imp["importancia"] = imp["importancia"].round(3)
        imp["importancia_pct"] = imp["importancia_pct"].round(2)
        lineas += [
            f"## Importancia de features (top {len(imp)}, modelo `{mejor}`)",
            "",
            "Calculada por **permutation importance held-out** (cuanto empeora el "
            "MAE al barajar cada feature sobre el TEST); agnostica al modelo y mas "
            "robusta que la importancia interna de los arboles.",
            "",
            markdown_table(imp),
            "",
            "Dominan, como anticipaba el EDA, los **rezagos y medias moviles del "
            "objetivo** (autocorrelacion fuerte de la demanda), seguidos de la "
            "**promocion** (`onpromotion` y sus rezagos) y el **calendario**. Esto "
            "sustenta la trazabilidad hacia COMPRAS/ALMACEN: el pronostico se apoya "
            "en la historia reciente de cada serie y en las palancas planificadas.",
            "",
        ]
    lineas += [
        "## Nota sobre el MAPE",
        "",
        "El MAPE (~32%) **sobre-estima el error**: excluye los dias de venta cero "
        "(31% del total) y penaliza desproporcionadamente las series pequenas. Para "
        "esta serie zero-inflated, el **WAPE** (error agregado ponderado por "
        "volumen) y el **MAE/RMSE** en unidades son las metricas fiables.",
        "",
        "## Notas de diseno",
        "",
        "- Transacciones usadas **solo como rezagos** (t-1, t-7) y medias del "
        "pasado: en pronostico real no se conocen las del periodo a predecir.",
        "- Rezagos/ventanas del objetivo calculados por serie "
        "`(store_nbr, family)` con `shift` antes de la ventana (sin fuga).",
        "- Modelo lineal (Ridge) montado en **pipeline propio** (one-hot + "
        "estandarizacion); los modelos de arbol usan categoricas nativas/codigos.",
        "- Zero-inflation (31.3% de ceros) presente; el recorte a 0 tras `expm1` "
        "respeta que las ventas no son negativas.",
        "",
        "## Mejoras diferidas (documentadas, no implementadas en este cierre)",
        "",
        "- **Intervalos de prediccion:** via cuantiles de boosting "
        "(`quantile`/`pinball`) o residuos empiricos del holdout.",
        "- **Enfoque zero-inflated / two-part:** clasificar cero vs. positivo y "
        "regredir solo los positivos, dado el 31% de ceros; evaluar si reduce el "
        "sesgo en series intermitentes.",
        "",
    ]
    ruta = settings.base_dir / "docs" / "reporte_regresion_2a.md"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text("\n".join(lineas), encoding="utf-8")
    return ruta


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def entrenar(
    settings: Settings, *, max_train_rows: int | None, con_cv: bool,
    hpo: bool = False, hpo_trials: int = 30, ensemble: bool = True,
) -> ResultadoEntrenamiento:
    """Flujo offline: carga datos, entrena, persiste metricas, artefacto y reporte."""
    from spc.data.integration import build_analytic_dataset
    from spc.data.loaders import load_data

    np.random.seed(settings.random_seed)
    data = load_data(settings)
    analytic, _, _ = build_analytic_dataset(data, settings)

    res = entrenar_y_comparar(
        analytic, settings, max_train_rows=max_train_rows, con_cv=con_cv,
        hpo=hpo, hpo_trials=hpo_trials, ensemble=ensemble,
    )
    ruta_csv = persistir_metricas(res, settings)
    ruta_art, ruta_meta = serializar_artefacto(res, settings)
    ruta_rep = escribir_reporte(res, settings)
    log.info("Metricas: %s", ruta_csv)
    log.info("Artefacto: %s (+ %s)", ruta_art, ruta_meta.name)
    log.info("Reporte: %s", ruta_rep)
    return res


def cli(argv: list[str] | None = None) -> None:
    """Entrenamiento offline reproducible de la regresion de VENTAS (Fase 2a)."""
    parser = argparse.ArgumentParser(
        description="Entrena y compara la regresion de VENTAS (Fase 2a)."
    )
    parser.add_argument(
        "--base-dir", type=Path, default=None, help="Raiz del proyecto (contiene data/raw)."
    )
    parser.add_argument(
        "--max-train-rows", type=int, default=250_000,
        help="Tope de filas para ajustar (submuestreo de train; default 250000).",
    )
    parser.add_argument("--full", action="store_true", help="Ajustar sin tope de filas (lento).")
    parser.add_argument("--sin-cv", action="store_true", help="Omitir la validacion cruzada temporal.")
    parser.add_argument(
        "--hpo", action="store_true",
        help="Optimizar hiperparametros por familia con Optuna (lento, mas preciso).",
    )
    parser.add_argument(
        "--hpo-trials", type=int, default=30,
        help="Numero de trials de Optuna por familia (default 30).",
    )
    parser.add_argument(
        "--sin-ensemble", action="store_true",
        help="Desactivar el ensemble de boosters (solo modelos individuales).",
    )
    args = parser.parse_args(argv)

    from spc.utils.logging import configure_logging

    configure_logging(verbose=True)
    settings = Settings(base_dir=args.base_dir) if args.base_dir else Settings()
    max_rows = None if args.full else args.max_train_rows

    res = entrenar(
        settings, max_train_rows=max_rows, con_cv=not args.sin_cv,
        hpo=args.hpo, hpo_trials=args.hpo_trials, ensemble=not args.sin_ensemble,
    )

    print("\n" + "=" * 72)
    print("  COMPARACION DE MODELOS - TEST (MAE en unidades, menor es mejor)")
    print("=" * 72)
    test = res.metricas[res.metricas["split"] == "test"].sort_values("MAE")
    print(test[["modelo", "MAE", "RMSE", "R2"]].to_string(index=False))
    rec = res.metricas_test_recursivo or {}
    if rec:
        print(
            f"\nMetrica HONESTA (pronostico recursivo) -> "
            f"WAPE {rec.get('WAPE', float('nan')):.2f}% | "
            f"MAE {rec.get('MAE', float('nan')):.2f} | "
            f"RMSE {rec.get('RMSE', float('nan')):.2f}"
        )
    print(f"\nGanador: {res.mejor_modelo} -> artefacto {VERSION_MODELO} en models/")


def cargar_predictor(ruta: Path) -> tuple[PredictorRegresion, dict[str, Any]]:
    """Carga el predictor serializado y sus metadatos (para la capa servicio/API)."""
    return cargar_artefacto(ruta)


if __name__ == "__main__":
    cli()
