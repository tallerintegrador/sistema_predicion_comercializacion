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
    ConfigFeatures,
    columnas_rezago,
    construir_features,
)
from spc.utils.formatters import markdown_table
from spc.utils.logging import get_logger
from spc.utils.metrics import evaluar_en_unidades, regression_metrics
from spc.utils.serializacion import cargar_artefacto, guardar_artefacto

log = get_logger("models.regresion")

VERSION_MODELO = "regresion_v2"
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


def construir_zoo(seed: int, features: list[str], cats: list[str]) -> dict[str, EspecModelo]:
    """Define los 5 regresores a comparar (semilla fija para reproducibilidad)."""
    from lightgbm import LGBMRegressor
    from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
    from xgboost import XGBRegressor

    return {
        "Ridge": EspecModelo(
            "Ridge", "lineal",
            lambda: _construir_pipeline_lineal(features, cats),
        ),
        "RandomForest": EspecModelo(
            "RandomForest", "numerico",
            lambda: RandomForestRegressor(
                n_estimators=120, max_depth=14, min_samples_leaf=20,
                random_state=seed, n_jobs=-1,
            ),
        ),
        "HistGradientBoosting": EspecModelo(
            "HistGradientBoosting", "categorico",
            lambda: HistGradientBoostingRegressor(
                max_iter=300, learning_rate=0.06, max_leaf_nodes=63,
                l2_regularization=1.0, categorical_features="from_dtype",
                random_state=seed,
            ),
        ),
        "LightGBM": EspecModelo(
            "LightGBM", "categorico",
            lambda: LGBMRegressor(
                n_estimators=600, learning_rate=0.05, num_leaves=63,
                subsample=0.8, subsample_freq=1, colsample_bytree=0.8,
                importance_type="gain",
                random_state=seed, n_jobs=-1, verbose=-1,
            ),
        ),
        "XGBoost": EspecModelo(
            "XGBoost", "categorico",
            lambda: XGBRegressor(
                n_estimators=600, learning_rate=0.05, max_depth=8,
                subsample=0.8, colsample_bytree=0.8, tree_method="hist",
                enable_categorical=True, random_state=seed, n_jobs=-1,
            ),
        ),
    }


# ---------------------------------------------------------------------------
# Predictor serializable (artefacto de produccion)
# ---------------------------------------------------------------------------
class PredictorRegresion:
    """Envuelve la ingenieria de features + el modelo entrenado.

    Se serializa entero (joblib): en produccion se carga y se llama ``predecir``
    sin reentrenar. Reconstruye las features desde un historico ya integrado y
    devuelve la demanda en **unidades** (invierte ``log1p``).
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
        self.version = version
        self.transformacion = "log1p"

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
        pred_log = self.modelo.predict(X)
        if self.techo_log is not None:
            pred_log = np.clip(pred_log, 0.0, self.techo_log)
        unidades = np.clip(np.expm1(pred_log), 0.0, None)
        return pd.Series(unidades, index=df_feat.index, name="demanda_pronosticada")


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


def _muestrear(idx: np.ndarray, max_filas: int | None, seed: int) -> np.ndarray:
    """Submuestrea filas de entrenamiento (las features/lags ya estan calculadas
    sobre la serie completa, asi que muestrear filas no introduce fuga)."""
    if max_filas is None or len(idx) <= max_filas:
        return idx
    rng = np.random.default_rng(seed)
    return rng.choice(idx, size=max_filas, replace=False)


def entrenar_y_comparar(
    analytic: pd.DataFrame,
    settings: Settings,
    *,
    cfg_features: ConfigFeatures | None = None,
    max_train_rows: int | None = 250_000,
    con_cv: bool = True,
) -> ResultadoEntrenamiento:
    """Construye features, valida temporalmente y compara baselines vs 5 modelos."""
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

    # Objetivo en escala log1p.
    y_log = np.log1p(df_model[OBJETIVO].to_numpy("float64"))
    # Techo de prediccion: ningun pronostico debe superar el maximo historico
    # (evita que un lineal en log-space dispare expm1 a valores absurdos).
    techo_log = float(np.nanmax(y_log))

    cortes = calcular_cortes(df_model[COL_FECHA])
    fechas = df_model[COL_FECHA]
    mask_train = fechas <= cortes.train_fin
    mask_valid = (fechas >= cortes.valid_ini) & (fechas <= cortes.valid_fin)
    mask_test = (fechas >= cortes.test_ini) & (fechas <= cortes.test_fin)
    log.info("Cortes -> %s", cortes.as_dict())

    # Matrices por tipo.
    X_cat = _matriz_categorica(df_model, features, cats)
    X_num = _matriz_numerica(df_model, features, cats)

    idx = np.arange(len(df_model))
    idx_train = idx[mask_train.to_numpy()]
    idx_valid = idx[mask_valid.to_numpy()]
    idx_test = idx[mask_test.to_numpy()]
    idx_train_fit = _muestrear(idx_train, max_train_rows, seed)

    zoo = construir_zoo(seed, features, cats)
    filas_metricas: list[dict] = []

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
        modelo.fit(Xtr, y_log[idx_train_fit])

        for split, X_split, idx_split in (("valid", Xva, idx_valid), ("test", Xte, idx_test)):
            pred_log = np.clip(modelo.predict(X_split), 0.0, techo_log)
            m = evaluar_en_unidades(y_log[idx_split], pred_log)
            filas_metricas.append({"modelo": nombre, "split": split, **m})
            if split == "test":
                metricas_test_por_modelo[nombre] = m

    # --- Validacion cruzada temporal (expanding) sobre TRAIN+VALID ---
    if con_cv:
        _agregar_cv(
            df_model, X_cat, X_num, y_log, zoo, cortes, seed,
            max_train_rows, techo_log, filas_metricas,
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
    modelo_final.fit(X_full, y_log)
    predictor_final = PredictorRegresion(
        modelo=modelo_final, features=features, cats=cats, categorias=categorias,
        cfg_features=cfg_features, tipo=spec.tipo,
        nombre_modelo=mejor, techo_log=techo_log,
    )
    importancias = calcular_importancias(
        spec, X_cat, X_num, y_log, idx_train_fit, idx_test, features, seed=seed
    )

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
    )


def _agregar_cv(
    df_model: pd.DataFrame,
    X_cat: pd.DataFrame,
    X_num: np.ndarray,
    y_log: np.ndarray,
    zoo: dict[str, EspecModelo],
    cortes: CortesTemporales,
    seed: int,
    max_train_rows: int | None,
    techo_log: float,
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
            modelo = spec.construir()
            modelo.fit(Xtr, y_log[idx_tr])
            pred_log = np.clip(modelo.predict(Xva), 0.0, techo_log)
            m = evaluar_en_unidades(y_log[idx_va], pred_log)
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
    return ruta_csv


def serializar_artefacto(res: ResultadoEntrenamiento, settings: Settings) -> tuple[Path, Path]:
    """Serializa el predictor ganador + metadatos en ``models/``."""
    ruta = settings.base_dir / "models" / f"{VERSION_MODELO}.joblib"
    metadatos = {
        "version": VERSION_MODELO,
        "fecha_entrenamiento": date.today().isoformat(),
        "modelo": res.mejor_modelo,
        "criterio_seleccion": res.criterio_seleccion,
        "transformacion_objetivo": "log1p",
        "escala_metricas": "unidades",
        "techo_log_prediccion": res.predictor.techo_log,
        "semilla": settings.random_seed,
        "features": res.features,
        "features_categoricas": res.cats,
        "config_features": res.cfg_features.as_dict(),
        "cortes_temporales": res.cortes.as_dict(),
        "metricas_test": res.metricas_test_por_modelo.get(
            res.mejor_modelo, res.metricas_test_mejor
        ),
        "metricas_test_baseline": res.metricas_baseline,
        "n_filas_comparacion": res.n_train,
        "n_filas_artefacto_final": res.n_artefacto,
    }
    return guardar_artefacto(res.predictor, ruta, metadatos)


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
    settings: Settings, *, max_train_rows: int | None, con_cv: bool
) -> ResultadoEntrenamiento:
    """Flujo offline: carga datos, entrena, persiste metricas, artefacto y reporte."""
    from spc.data.integration import build_analytic_dataset
    from spc.data.loaders import load_data

    np.random.seed(settings.random_seed)
    data = load_data(settings)
    analytic, _, _ = build_analytic_dataset(data, settings)

    res = entrenar_y_comparar(analytic, settings, max_train_rows=max_train_rows, con_cv=con_cv)
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
    args = parser.parse_args(argv)

    from spc.utils.logging import configure_logging

    configure_logging(verbose=True)
    settings = Settings(base_dir=args.base_dir) if args.base_dir else Settings()
    max_rows = None if args.full else args.max_train_rows

    res = entrenar(settings, max_train_rows=max_rows, con_cv=not args.sin_cv)

    print("\n" + "=" * 72)
    print("  COMPARACION DE MODELOS - TEST (MAE en unidades, menor es mejor)")
    print("=" * 72)
    test = res.metricas[res.metricas["split"] == "test"].sort_values("MAE")
    print(test[["modelo", "MAE", "RMSE", "R2"]].to_string(index=False))
    print(f"\nGanador: {res.mejor_modelo} -> artefacto {VERSION_MODELO} en models/")


def cargar_predictor(ruta: Path) -> tuple[PredictorRegresion, dict[str, Any]]:
    """Carga el predictor serializado y sus metadatos (para la capa servicio/API)."""
    return cargar_artefacto(ruta)


if __name__ == "__main__":
    cli()
