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

VERSION_MODELO = "regresion_v1"
OBJETIVO = "sales"
COL_FECHA = "date"

# Horizonte de los holdouts: 16 dias = espejo del test real de Corporacion
# Favorita (2017-08-16 .. 2017-08-31).
DIAS_TEST = 16
DIAS_VALID = 16
# Validacion cruzada temporal (expanding window) sobre TRAIN+VALID.
CV_N_FOLDS = 3
CV_DIAS_VAL = 14


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
    tipo: str  # "numerico" | "categorico"
    escala: bool  # estandarizar (solo Ridge)
    construir: Any  # callable() -> estimador sklearn-like


def construir_zoo(seed: int) -> dict[str, EspecModelo]:
    """Define los 5 regresores a comparar (semilla fija para reproducibilidad)."""
    from lightgbm import LGBMRegressor
    from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
    from sklearn.linear_model import Ridge
    from xgboost import XGBRegressor

    return {
        "Ridge": EspecModelo("Ridge", "numerico", True, lambda: Ridge(alpha=1.0)),
        "RandomForest": EspecModelo(
            "RandomForest", "numerico", False,
            lambda: RandomForestRegressor(
                n_estimators=120, max_depth=14, min_samples_leaf=20,
                random_state=seed, n_jobs=-1,
            ),
        ),
        "HistGradientBoosting": EspecModelo(
            "HistGradientBoosting", "categorico", False,
            lambda: HistGradientBoostingRegressor(
                max_iter=300, learning_rate=0.06, max_leaf_nodes=63,
                l2_regularization=1.0, categorical_features="from_dtype",
                random_state=seed,
            ),
        ),
        "LightGBM": EspecModelo(
            "LightGBM", "categorico", False,
            lambda: LGBMRegressor(
                n_estimators=600, learning_rate=0.05, num_leaves=63,
                subsample=0.8, subsample_freq=1, colsample_bytree=0.8,
                random_state=seed, n_jobs=-1, verbose=-1,
            ),
        ),
        "XGBoost": EspecModelo(
            "XGBoost", "categorico", False,
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
        escalador: Any | None,
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
        self.escalador = escalador
        self.nombre_modelo = nombre_modelo
        self.techo_log = techo_log
        self.version = version
        self.transformacion = "log1p"

    def _matriz(self, df_feat: pd.DataFrame) -> Any:
        df_cat, _ = _fijar_categorias(df_feat, self.cats, self.categorias)
        if self.tipo == "categorico":
            return _matriz_categorica(df_cat, self.features, self.cats)
        X = _matriz_numerica(df_cat, self.features, self.cats)
        if self.escalador is not None:
            X = self.escalador.transform(X)
        return X

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
    metricas_baseline: dict[str, dict[str, float]]
    n_train: int


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

    from sklearn.preprocessing import StandardScaler

    zoo = construir_zoo(seed)
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
    mae_test: dict[str, float] = {}
    rmse_test: dict[str, float] = {}

    for nombre, spec in zoo.items():
        log.info("Entrenando %s...", nombre)
        escalador = None
        if spec.tipo == "categorico":
            Xtr = X_cat.iloc[idx_train_fit]
            Xva, Xte = X_cat.iloc[idx_valid], X_cat.iloc[idx_test]
        else:
            if spec.escala:
                escalador = StandardScaler()
                Xtr = escalador.fit_transform(X_num[idx_train_fit])
                Xva = escalador.transform(X_num[idx_valid])
                Xte = escalador.transform(X_num[idx_test])
            else:
                Xtr, Xva, Xte = X_num[idx_train_fit], X_num[idx_valid], X_num[idx_test]

        modelo = spec.construir()
        modelo.fit(Xtr, y_log[idx_train_fit])

        for split, X_split, idx_split in (("valid", Xva, idx_valid), ("test", Xte, idx_test)):
            pred_log = np.clip(modelo.predict(X_split), 0.0, techo_log)
            m = evaluar_en_unidades(y_log[idx_split], pred_log)
            filas_metricas.append({"modelo": nombre, "split": split, **m})
            if split == "test":
                mae_test[nombre] = m["MAE"]
                rmse_test[nombre] = m["RMSE"]

    # --- Validacion cruzada temporal (expanding) sobre TRAIN+VALID ---
    if con_cv:
        _agregar_cv(
            df_model, X_cat, X_num, y_log, zoo, cortes, seed,
            max_train_rows, techo_log, filas_metricas,
        )

    metricas_df = pd.DataFrame(filas_metricas)

    # --- Eleccion del ganador: menor MAE en TEST entre los modelos ---
    mejor = min(mae_test, key=mae_test.get)
    log.info("Mejor modelo por MAE(test) = %s (%.3f)", mejor, mae_test[mejor])

    # --- Reajuste del ganador sobre TODO lo etiquetado (mas datos = mejor artefacto) ---
    log.info("Reajustando %s sobre todo el historico para el artefacto...", mejor)
    spec = zoo[mejor]
    escalador_final = None
    if spec.tipo == "categorico":
        X_full: Any = X_cat
    elif spec.escala:
        escalador_final = StandardScaler()
        X_full = escalador_final.fit_transform(X_num)
    else:
        X_full = X_num
    modelo_final = spec.construir()
    modelo_final.fit(X_full, y_log)
    predictor_final = PredictorRegresion(
        modelo=modelo_final, features=features, cats=cats, categorias=categorias,
        cfg_features=cfg_features, tipo=spec.tipo, escalador=escalador_final,
        nombre_modelo=mejor, techo_log=techo_log,
    )

    return ResultadoEntrenamiento(
        metricas=metricas_df,
        cortes=cortes,
        mejor_modelo=mejor,
        predictor=predictor_final,
        features=features,
        cats=cats,
        cfg_features=cfg_features,
        metricas_test_mejor={"MAE": mae_test[mejor], "RMSE": rmse_test[mejor]},
        metricas_baseline=metricas_baseline,
        n_train=len(idx_train_fit),
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
    from sklearn.preprocessing import StandardScaler

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
            if spec.tipo == "categorico":
                Xtr, Xva = X_cat.iloc[idx_tr], X_cat.iloc[idx_va]
            elif spec.escala:
                sc = StandardScaler()
                Xtr = sc.fit_transform(X_num[idx_tr])
                Xva = sc.transform(X_num[idx_va])
            else:
                Xtr, Xva = X_num[idx_tr], X_num[idx_va]
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
    return ruta_csv


def serializar_artefacto(res: ResultadoEntrenamiento, settings: Settings) -> tuple[Path, Path]:
    """Serializa el predictor ganador + metadatos en ``models/``."""
    ruta = settings.base_dir / "models" / f"{VERSION_MODELO}.joblib"
    metadatos = {
        "version": VERSION_MODELO,
        "fecha_entrenamiento": date.today().isoformat(),
        "modelo": res.mejor_modelo,
        "transformacion_objetivo": "log1p",
        "escala_metricas": "unidades",
        "techo_log_prediccion": res.predictor.techo_log,
        "semilla": settings.random_seed,
        "features": res.features,
        "features_categoricas": res.cats,
        "config_features": res.cfg_features.as_dict(),
        "cortes_temporales": res.cortes.as_dict(),
        "metricas_test": res.metricas_test_mejor,
        "metricas_test_baseline": res.metricas_baseline,
        "n_filas_entrenamiento_fit": res.n_train,
    }
    return guardar_artefacto(res.predictor, ruta, metadatos)


def escribir_reporte(res: ResultadoEntrenamiento, settings: Settings) -> Path:
    """Genera ``docs/reporte_regresion_2a.md`` con la comparacion de modelos."""
    md = res.metricas.copy()
    test = md[md["split"] == "test"].copy().sort_values("MAE")
    valid = md[md["split"] == "valid"].copy().sort_values("MAE")
    cv = md[md["split"].str.startswith("cv_")].copy()
    cv_resumen = (
        cv.groupby("modelo")[["MAE", "RMSE"]].agg(["mean", "std"]).round(3)
        if not cv.empty
        else pd.DataFrame()
    )

    metricas_cols = ["MAE", "RMSE", "RMSLE", "MAPE", "WAPE", "R2"]

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
        "## Cortes temporales",
        "",
        f"- **Train:** {res.cortes.as_dict()['train']}",
        f"- **Valid:** {res.cortes.as_dict()['valid']}",
        f"- **Test:** {res.cortes.as_dict()['test']}",
        f"- Filas usadas para ajustar (submuestreo de train): "
        f"{res.n_train:,}".replace(",", " "),
        "",
        "## Resultados en TEST (ordenado por MAE, menor es mejor)",
        "",
        markdown_table(_fmt(test)),
        "",
        f"**Modelo ganador: `{mejor}`** (artefacto `{VERSION_MODELO}`).",
        "",
        f"- MAE ganador = {gan_mae:.3f} vs mejor baseline = {base_mae:.3f} "
        f"-> mejora {mejora_mae:.1f}%.",
        f"- RMSE ganador = {gan_rmse:.3f} vs mejor baseline = {base_rmse:.3f} "
        f"-> mejora {mejora_rmse:.1f}%.",
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
    lineas += [
        "## Notas de diseno",
        "",
        "- Transacciones usadas **solo como rezagos** (t-1, t-7) y medias del "
        "pasado: en pronostico real no se conocen las del periodo a predecir.",
        "- Rezagos/ventanas del objetivo calculados por serie "
        "`(store_nbr, family)` con `shift` antes de la ventana (sin fuga).",
        "- Zero-inflation (31.3% de ceros) presente; el recorte a 0 tras `expm1` "
        "respeta que las ventas no son negativas.",
        "- **Intervalos de prediccion:** pendientes (mejora futura via cuantiles "
        "de boosting o residuos empiricos).",
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
