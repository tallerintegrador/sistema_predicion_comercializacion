"""Clasificacion de ALMACEN (Fase 2b): predice `demanda_alta` (riesgo de quiebre).

Objetivo derivado: ``demanda_alta = 1`` si ``sales > P75`` de su **familia**, 0 en
otro caso (desbalance ~22 % de positivos, ~1:3.5). El umbral P75 se fija **solo con
TRAIN** (no puede mirar el futuro) y se aplica a valid/test.

Hereda el harness temporal de la 2a: mismos cortes por fecha, mismo feature
engineering **leak-safe** (``spc.features.temporales``). La cantidad que define la
etiqueta (``sales`` del periodo actual) **no es feature**: solo se usan rezagos/
ventanas pasadas de ``sales`` y el resto de variables de calendario/promocion/
transacciones-rezagadas (las mismas que la regresion).

Experimento central de la fase: comparar **tres estrategias** sobre la misma
validacion temporal con el mismo booster base, para **decidir empiricamente si
SMOTE aporta**:
  1. **Sin remuestreo** (linea de partida).
  2. **Costo-sensible** (``scale_pos_weight = n_neg/n_pos``).
  3. **SMOTE solo en train**, dentro de cada fold, via ``imblearn.Pipeline``
     (SMOTENC: respeta las categoricas). Nunca toca valid/test.

Seleccion de estrategia y de umbral **SIEMPRE en VALID**; TEST se evalua una sola
vez sobre la configuracion ya elegida. Metrica principal: **PR-AUC** (minoritaria),
luego recall -> F1 -> precision; matriz de confusion al umbral elegido; ROC-AUC de
contexto; linea sin-skill = prevalencia.

Capa de motor de ML: no conoce HTTP ni el negocio del cliente. El artefacto se
entrena offline (GPU para el booster, **predice en CPU**) y en produccion solo se
carga y predice: devuelve **clase y probabilidad** de ``demanda_alta``.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import precision_recall_curve

from spc.config import Settings
from spc.features.temporales import (
    COL_FECHA,
    OBJETIVO,
    ConfigFeatures,
    columnas_rezago,
    construir_features,
)
from spc.models.regresion import (
    CortesTemporales,
    _fijar_categorias,
    _matriz_categorica,
    calcular_cortes,
)
from spc.utils.formatters import markdown_table
from spc.utils.logging import get_logger
from spc.utils.metrics import classification_metrics_min, matriz_confusion
from spc.utils.serializacion import cargar_artefacto, guardar_artefacto

log = get_logger("models.clasificacion")

VERSION_MODELO = "clasificacion_v1"
ETIQUETA = "demanda_alta"
COL_P75 = "family_sales_p75"

# Marco de negocio para el umbral: `demanda_alta` senala riesgo de quiebre de
# stock; fallar un positivo (no detectar demanda alta) suele costar mas que una
# falsa alarma. Por eso el umbral en VALID prioriza **recall con una precision
# aceptable** (piso), no el 0.5 por defecto.
PRECISION_FLOOR = 0.50

# Validacion cruzada temporal (expanding) dentro de TRAIN+VALID (espejo de la 2a).
CV_N_FOLDS = 3
CV_DIAS_VAL = 14

# Tolerancia absoluta de PR-AUC en VALID para considerar dos estrategias
# "empatadas". Entre las empatadas se elige la **mas simple** (sin remuestreo <
# costo-sensible < SMOTE): SMOTE solo gana si SUPERA por mas de esta tolerancia.
TOL_PRAUC = 0.005

# Orden de simplicidad de las estrategias (menor = mas simple).
ORDEN_SIMPLICIDAD = {"sin_remuestreo": 0, "costo_sensible": 1, "smote": 2}
ESTRATEGIAS = tuple(ORDEN_SIMPLICIDAD)


# ---------------------------------------------------------------------------
# Etiqueta honesta (P75 por familia fijado SOLO en TRAIN)
# ---------------------------------------------------------------------------
@dataclass
class InfoEtiqueta:
    """Resumen de la construccion de la etiqueta y de las familias degeneradas."""

    p75_por_familia: dict[str, float]
    familias_degeneradas: list[str]
    n_familias: int
    prevalencia_train: float
    prevalencia_global: float


def construir_etiqueta(
    df_model: pd.DataFrame, cortes: CortesTemporales
) -> tuple[pd.DataFrame, InfoEtiqueta]:
    """Deriva ``demanda_alta`` con el **P75 por familia fijado solo en TRAIN**.

    El umbral que define la clase positiva no puede mirar el futuro: se calcula
    sobre las filas ``date <= train_fin`` y se aplica identico a valid/test. Las
    **familias degeneradas** (P75 <= 0: en ellas ``demanda_alta`` se reduce a
    "vendio algo" en vez de "demanda alta", una etiqueta ruidosa) se **excluyen**
    del entrenamiento y la evaluacion, y se reportan.
    """
    df = df_model.copy()
    mask_train = df[COL_FECHA] <= cortes.train_fin
    p75 = (
        df.loc[mask_train].groupby("family", observed=True)[OBJETIVO].quantile(0.75)
    )
    df[COL_P75] = df["family"].map(p75).astype("float64")
    df[ETIQUETA] = (df[OBJETIVO].to_numpy() > df[COL_P75].to_numpy()).astype("int8")

    degeneradas = sorted(str(f) for f in p75.index[p75 <= 0.0])
    prevalencia_global = float(df[ETIQUETA].mean())
    prevalencia_train = float(df.loc[mask_train, ETIQUETA].mean())

    if degeneradas:
        df = df[~df["family"].astype(str).isin(degeneradas)].copy()
        log.info(
            "Familias degeneradas excluidas (P75<=0, etiqueta ruidosa): %s",
            degeneradas,
        )

    info = InfoEtiqueta(
        p75_por_familia={str(k): float(v) for k, v in p75.items()},
        familias_degeneradas=degeneradas,
        n_familias=int(p75.size),
        prevalencia_train=prevalencia_train,
        prevalencia_global=prevalencia_global,
    )
    return df, info


# ---------------------------------------------------------------------------
# Estrategias de desbalance (mismo booster base)
# ---------------------------------------------------------------------------
def _lgbm(seed: int, *, usar_gpu: bool, scale_pos_weight: float | None = None) -> Any:
    """Booster base de produccion (LightGBM, coherente con la 2a).

    Entrena en GPU si ``usar_gpu`` (``device="gpu"`` via OpenCL); la prediccion de
    LightGBM corre en **CPU** de forma nativa, asi que el artefacto es portable.
    """
    from lightgbm import LGBMClassifier

    return LGBMClassifier(
        n_estimators=400,
        learning_rate=0.05,
        num_leaves=63,
        subsample=0.8,
        colsample_bytree=0.8,
        subsample_freq=1,
        scale_pos_weight=scale_pos_weight,
        objective="binary",
        device="gpu" if usar_gpu else "cpu",
        random_state=seed,
        n_jobs=-1,
        verbose=-1,
    )


def construir_estrategia(
    nombre: str, seed: int, *, usar_gpu: bool, scale_pos_weight: float
) -> Any:
    """Devuelve el estimador de una estrategia (sklearn-like con ``predict_proba``).

    - ``sin_remuestreo``: booster tal cual.
    - ``costo_sensible``: booster con ``scale_pos_weight = n_neg/n_pos``.
    - ``smote``: ``imblearn.Pipeline([SMOTENC, booster])``. El sampler **solo actua
      en ``fit``** (sobre el train del fold/split); en ``predict`` se omite, de modo
      que valid/test nunca se remuestrean. SMOTENC interpola las numericas y
      muestrea categorias validas (respeta ``store_nbr``/``family``/...). Regla de
      fuga innegociable: SMOTE va **despues** del corte temporal, solo sobre train.
    """
    if nombre == "sin_remuestreo":
        return _lgbm(seed, usar_gpu=usar_gpu)
    if nombre == "costo_sensible":
        return _lgbm(seed, usar_gpu=usar_gpu, scale_pos_weight=scale_pos_weight)
    if nombre == "smote":
        from imblearn.over_sampling import SMOTENC
        from imblearn.pipeline import Pipeline as ImbPipeline

        return ImbPipeline(
            [
                ("smote", SMOTENC(categorical_features="auto", random_state=seed)),
                ("clf", _lgbm(seed, usar_gpu=usar_gpu)),
            ]
        )
    raise ValueError(f"Estrategia desconocida: {nombre}")


def _proba(modelo: Any, X: Any) -> np.ndarray:
    """Probabilidad de la clase positiva (``demanda_alta=1``)."""
    return np.asarray(modelo.predict_proba(X), dtype="float64")[:, 1]


# ---------------------------------------------------------------------------
# Seleccion de umbral en VALID (marco de negocio: prioriza recall)
# ---------------------------------------------------------------------------
def seleccionar_umbral(
    y_true: np.ndarray, y_prob: np.ndarray, precision_floor: float = PRECISION_FLOOR
) -> tuple[float, dict[str, Any]]:
    """Elige el umbral en VALID priorizando **recall con precision aceptable**.

    Criterio (marco de negocio: no detectar demanda alta cuesta mas que una falsa
    alarma): entre los umbrales con ``precision >= precision_floor`` se toma el de
    **mayor recall**; si ninguno alcanza el piso, se cae a **max F2** (beta=2,
    favorece recall). Se decide SOLO sobre VALID.
    """
    prec, rec, thr = precision_recall_curve(y_true, y_prob)
    if len(thr) == 0:
        return 0.5, {
            "criterio": "sin variabilidad de probabilidad; umbral por defecto 0.5",
            "precision_floor": precision_floor,
        }
    cand = [(float(thr[i]), float(prec[i]), float(rec[i])) for i in range(len(thr))]
    viables = [c for c in cand if c[1] >= precision_floor]
    if viables:
        umbral, p, r = max(viables, key=lambda c: (c[2], c[0]))
        criterio = (
            f"max recall sujeto a precision >= {precision_floor:.2f} "
            "(marco de negocio: fallar un positivo -no detectar demanda alta- "
            "cuesta mas que una falsa alarma)"
        )
    else:
        def _f2(c: tuple[float, float, float]) -> float:
            p_, r_ = c[1], c[2]
            den = 4 * p_ + r_
            return (5 * p_ * r_ / den) if den > 0 else 0.0

        umbral, p, r = max(cand, key=_f2)
        criterio = (
            f"ninguna precision alcanza {precision_floor:.2f}; "
            "fallback a max F2 (favorece recall)"
        )
    return float(umbral), {
        "criterio": criterio,
        "precision_floor": precision_floor,
        "precision_en_umbral": round(float(p), 4),
        "recall_en_umbral": round(float(r), 4),
    }


# ---------------------------------------------------------------------------
# Predictor serializable (artefacto de produccion)
# ---------------------------------------------------------------------------
class PredictorClasificacion:
    """Envuelve la ingenieria de features + el clasificador entrenado + el umbral.

    Se serializa entero (joblib): en produccion se carga y se llama ``predecir``
    sin reentrenar. Reconstruye las features (leak-safe) desde un historico ya
    integrado y devuelve **clase y probabilidad** de ``demanda_alta``. El umbral
    elegido en VALID viaja con el artefacto (la clase por defecto lo usa).

    Es serializable con joblib: clase top-level bajo ``spc.models.clasificacion``
    (no ``__main__``), atributos picklables. El booster entrena en GPU pero
    **predice en CPU** (LightGBM lo hace de forma nativa): artefacto portable.
    """

    def __init__(
        self,
        modelo: Any,
        features: list[str],
        cats: list[str],
        categorias: dict[str, Any],
        cfg_features: ConfigFeatures,
        umbral: float,
        estrategia: str,
        familias_excluidas: list[str],
        version: str = VERSION_MODELO,
    ) -> None:
        self.modelo = modelo
        self.features = features
        self.cats = cats
        self.categorias = categorias
        self.cfg_features = cfg_features
        self.umbral = float(umbral)
        self.estrategia = estrategia
        self.familias_excluidas = list(familias_excluidas)
        self.version = version

    def _matriz(self, df_feat: pd.DataFrame) -> pd.DataFrame:
        df_cat, _ = _fijar_categorias(df_feat, self.cats, self.categorias)
        return _matriz_categorica(df_cat, self.features, self.cats)

    def predecir_proba(self, historico_integrado: pd.DataFrame) -> pd.Series:
        """Probabilidad de ``demanda_alta`` por fila del historico dado (en [0, 1])."""
        df_feat, _, _, _ = construir_features(historico_integrado, self.cfg_features)
        X = self._matriz(df_feat)
        prob = _proba(self.modelo, X)
        return pd.Series(prob, index=df_feat.index, name="probabilidad_demanda_alta")

    def predecir(
        self, historico_integrado: pd.DataFrame, umbral: float | None = None
    ) -> pd.DataFrame:
        """Devuelve ``clase_demanda_alta`` (0/1) y ``probabilidad_demanda_alta``.

        Usa el ``umbral`` elegido en VALID (override opcional). La clase 1 = "demanda
        alta" = riesgo de quiebre segun el contrato de ALMACEN.
        """
        u = self.umbral if umbral is None else float(umbral)
        prob = self.predecir_proba(historico_integrado)
        clase = (prob.to_numpy() >= u).astype("int8")
        return pd.DataFrame(
            {
                "clase_demanda_alta": clase,
                "probabilidad_demanda_alta": prob.to_numpy(),
            },
            index=prob.index,
        )


# ---------------------------------------------------------------------------
# Validacion cruzada temporal (SMOTE solo dentro del fold de train)
# ---------------------------------------------------------------------------
def _muestrear(idx: np.ndarray, max_filas: int | None, seed: int) -> np.ndarray:
    """Submuestrea filas (las features/lags ya estan calculadas por serie, asi que
    muestrear filas no introduce fuga)."""
    if max_filas is None or len(idx) <= max_filas:
        return idx
    rng = np.random.default_rng(seed)
    return rng.choice(idx, size=max_filas, replace=False)


def _agregar_cv(
    df_model: pd.DataFrame,
    X_cat: pd.DataFrame,
    y: np.ndarray,
    cortes: CortesTemporales,
    seed: int,
    max_train_rows: int | None,
    *,
    usar_gpu: bool,
    filas_metricas: list[dict],
) -> None:
    """CV temporal expanding dentro de TRAIN+VALID (nunca toca TEST).

    Para cada fold y estrategia, ajusta sobre el train del fold y evalua PR-AUC
    sobre el val del fold. En la estrategia ``smote`` el remuestreo lo aplica el
    ``imblearn.Pipeline`` **solo al train del fold** (en ``fit``), nunca al val.
    """
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
        Xtr, ytr = X_cat.iloc[idx_tr], y[idx_tr]
        Xva, yva = X_cat.iloc[idx_va], y[idx_va]
        n_pos = int(ytr.sum())
        n_neg = int(len(ytr) - n_pos)
        spw = (n_neg / n_pos) if n_pos else 1.0
        for nombre in ESTRATEGIAS:
            if nombre == "smote" and n_pos < 6:
                continue  # SMOTENC necesita >= 6 minoritarios (k_neighbors=5)
            modelo = construir_estrategia(
                nombre, seed, usar_gpu=usar_gpu, scale_pos_weight=spw
            )
            modelo.fit(Xtr, ytr)
            m = classification_metrics_min(yva, _proba(modelo, Xva))
            filas_metricas.append(
                {"estrategia": nombre, "split": f"cv_fold_{k + 1}", **m}
            )


# ---------------------------------------------------------------------------
# Seleccion de estrategia en VALID
# ---------------------------------------------------------------------------
def _elegir_estrategia(
    metricas_valid: dict[str, dict[str, float]]
) -> tuple[str, dict[str, Any]]:
    """Elige la estrategia **mas simple** que maximice la PR-AUC en VALID.

    Regla de decision (held-out, VALID): se toma la mejor PR-AUC; las estrategias
    dentro de ``TOL_PRAUC`` de esa mejor se consideran empatadas y entre ellas gana
    la **mas simple** (sin remuestreo < costo-sensible < SMOTE). Asi **SMOTE solo
    "gana" si supera** a la costo-sensible (y a la base) por mas de la tolerancia en
    la metrica principal de la minoritaria. Mostrar que SMOTE no aporta es un
    resultado valido.
    """
    pr = {e: metricas_valid[e]["PR_AUC"] for e in metricas_valid}
    mejor_prauc = max(pr.values())
    empatadas = [e for e, v in pr.items() if v >= mejor_prauc - TOL_PRAUC]
    elegida = min(empatadas, key=lambda e: ORDEN_SIMPLICIDAD[e])
    criterio = {
        "decision_en": "valid",
        "metrica_principal": "PR_AUC",
        "tol_prauc": TOL_PRAUC,
        "pr_auc_valid": {e: round(float(v), 4) for e, v in pr.items()},
        "recall_valid": {
            e: round(float(metricas_valid[e].get("Recall", float("nan"))), 4)
            for e in metricas_valid
        },
        "empatadas_dentro_tol": sorted(empatadas, key=lambda e: ORDEN_SIMPLICIDAD[e]),
        "regla": (
            "estrategia mas simple (sin_remuestreo < costo_sensible < smote) cuya "
            f"PR-AUC en VALID esta dentro de {TOL_PRAUC} de la mejor; SMOTE solo se "
            "adopta si SUPERA a la costo-sensible por mas de esa tolerancia"
        ),
    }
    return elegida, criterio


# ---------------------------------------------------------------------------
# Entrenamiento + comparacion de estrategias
# ---------------------------------------------------------------------------
@dataclass
class ResultadoClasificacion:
    metricas: pd.DataFrame
    cortes: CortesTemporales
    estrategia_elegida: str
    umbral: float
    criterio_umbral: dict[str, Any]
    criterio_seleccion: dict[str, Any]
    predictor: PredictorClasificacion
    features: list[str]
    cats: list[str]
    cfg_features: ConfigFeatures
    info_etiqueta: InfoEtiqueta
    metricas_valid: dict[str, dict[str, float]]
    metricas_test: dict[str, float]
    matriz_confusion_valid: dict[str, int]
    matriz_confusion_test: dict[str, int]
    metricas_referencia: dict[str, dict[str, float]]
    n_train: int
    n_artefacto: int


def entrenar_y_comparar(
    analytic: pd.DataFrame,
    settings: Settings,
    *,
    cfg_features: ConfigFeatures | None = None,
    max_train_rows: int | None = 300_000,
    con_cv: bool = True,
    usar_gpu: bool = False,
) -> ResultadoClasificacion:
    """Construye features, fija la etiqueta honesta y compara las 3 estrategias.

    Seleccion de estrategia y umbral en **VALID**; TEST se evalua una sola vez sobre
    la configuracion elegida. ``usar_gpu`` por defecto ``False`` para que la suite
    de tests sea portable; el entrenamiento de produccion (``entrenar``/``cli``) lo
    activa (el artefacto predice en CPU igualmente).
    """
    seed = settings.random_seed
    cfg_features = cfg_features or ConfigFeatures()

    log.info("Construyendo features temporales (leak-safe)...")
    df_feat, features, cats, cfg_features = construir_features(analytic, cfg_features)

    # Descarta el calentamiento (filas con NaN en los rezagos del objetivo) y
    # rellena el resto de NaN de rezago con 0 (igual que la 2a).
    cols_lag = columnas_rezago(features)
    df_model = df_feat.dropna(
        subset=[c for c in cols_lag if c.startswith("sales_lag_")]
    ).copy()
    df_model[cols_lag] = df_model[cols_lag].fillna(0.0)

    # Categorias fijas (consistencia de codigos entre splits y en prediccion).
    df_model, categorias = _fijar_categorias(df_model, cats, None)

    # Cortes temporales (mismos que la 2a) y etiqueta honesta (P75 train-only).
    cortes = calcular_cortes(df_model[COL_FECHA])
    log.info("Cortes -> %s", cortes.as_dict())
    df_model, info_etiqueta = construir_etiqueta(df_model, cortes)
    log.info(
        "Etiqueta: prevalencia train=%.4f | familias=%d | degeneradas=%s",
        info_etiqueta.prevalencia_train,
        info_etiqueta.n_familias,
        info_etiqueta.familias_degeneradas,
    )

    fechas = df_model[COL_FECHA]
    mask_train = (fechas <= cortes.train_fin).to_numpy()
    mask_valid = ((fechas >= cortes.valid_ini) & (fechas <= cortes.valid_fin)).to_numpy()
    mask_test = ((fechas >= cortes.test_ini) & (fechas <= cortes.test_fin)).to_numpy()

    X_cat = _matriz_categorica(df_model, features, cats)
    y = df_model[ETIQUETA].to_numpy(dtype="int8")

    idx = np.arange(len(df_model))
    idx_train = idx[mask_train]
    idx_valid = idx[mask_valid]
    idx_test = idx[mask_test]
    idx_train_fit = _muestrear(idx_train, max_train_rows, seed)

    n_pos = int(y[idx_train_fit].sum())
    n_neg = int(len(idx_train_fit) - n_pos)
    scale_pos_weight = (n_neg / n_pos) if n_pos else 1.0
    log.info(
        "TRAIN(fit) n=%d | pos=%d (%.3f) | scale_pos_weight=%.3f",
        len(idx_train_fit), n_pos, n_pos / max(1, len(idx_train_fit)), scale_pos_weight,
    )

    Xtr = X_cat.iloc[idx_train_fit]
    ytr = y[idx_train_fit]
    Xva, yva = X_cat.iloc[idx_valid], y[idx_valid]
    Xte, yte = X_cat.iloc[idx_test], y[idx_test]

    filas_metricas: list[dict] = []
    proba_valid: dict[str, np.ndarray] = {}
    proba_test: dict[str, np.ndarray] = {}

    # --- Estrategias: ajuste en TRAIN, prediccion en VALID y TEST ---
    for nombre in ESTRATEGIAS:
        log.info("Entrenando estrategia `%s`...", nombre)
        modelo = construir_estrategia(
            nombre, seed, usar_gpu=usar_gpu, scale_pos_weight=scale_pos_weight
        )
        modelo.fit(Xtr, ytr)
        proba_valid[nombre] = _proba(modelo, Xva)
        proba_test[nombre] = _proba(modelo, Xte)
        # Metricas al umbral 0.5 (referencia); el umbral de negocio se aplica luego.
        for split, yv, pv in (("valid", yva, proba_valid[nombre]), ("test", yte, proba_test[nombre])):
            m = classification_metrics_min(yv, pv)
            filas_metricas.append({"estrategia": nombre, "split": split, **m})

    # --- Umbral por estrategia (elegido en VALID, marco de negocio) ---
    umbrales: dict[str, tuple[float, dict[str, Any]]] = {
        nombre: seleccionar_umbral(yva, proba_valid[nombre]) for nombre in ESTRATEGIAS
    }
    # Metricas de VALID al umbral propio (las que guian la seleccion + el negocio).
    metricas_valid = {
        nombre: classification_metrics_min(yva, proba_valid[nombre], umbrales[nombre][0])
        for nombre in ESTRATEGIAS
    }

    # --- Baselines triviales + referencia interpretable (logistica) ---
    metricas_referencia = _evaluar_referencias(
        Xtr, ytr, Xva, yva, Xte, yte, features, cats, seed, filas_metricas
    )

    # --- CV temporal expanding (SMOTE solo dentro del fold de train) ---
    if con_cv:
        _agregar_cv(
            df_model, X_cat, y, cortes, seed, max_train_rows,
            usar_gpu=usar_gpu, filas_metricas=filas_metricas,
        )

    # --- Seleccion de estrategia en VALID (mas simple que maximiza PR-AUC) ---
    estrategia, criterio_sel = _elegir_estrategia(metricas_valid)
    umbral, criterio_umbral = umbrales[estrategia]
    log.info(
        "Estrategia elegida = `%s` (umbral=%.3f) | %s",
        estrategia, umbral, criterio_sel["regla"],
    )

    # --- TEST: evaluado UNA sola vez sobre la estrategia ya elegida ---
    met_test = classification_metrics_min(yte, proba_test[estrategia], umbral)
    cm_test = matriz_confusion(yte, proba_test[estrategia], umbral)
    cm_valid = matriz_confusion(yva, proba_valid[estrategia], umbral)

    # --- Artefacto: reajusta la estrategia elegida sobre TODO el historico
    #     etiquetado (no degenerado). El umbral viaja desde VALID. ---
    log.info("Reajustando `%s` sobre todo el historico para el artefacto...", estrategia)
    modelo_final = construir_estrategia(
        estrategia, seed, usar_gpu=usar_gpu, scale_pos_weight=scale_pos_weight
    )
    modelo_final.fit(X_cat, y)
    predictor = PredictorClasificacion(
        modelo=modelo_final,
        features=features,
        cats=cats,
        categorias=categorias,
        cfg_features=cfg_features,
        umbral=umbral,
        estrategia=estrategia,
        familias_excluidas=info_etiqueta.familias_degeneradas,
    )

    metricas_df = pd.DataFrame(filas_metricas)
    return ResultadoClasificacion(
        metricas=metricas_df,
        cortes=cortes,
        estrategia_elegida=estrategia,
        umbral=umbral,
        criterio_umbral=criterio_umbral,
        criterio_seleccion=criterio_sel,
        predictor=predictor,
        features=features,
        cats=cats,
        cfg_features=cfg_features,
        info_etiqueta=info_etiqueta,
        metricas_valid=metricas_valid,
        metricas_test=met_test,
        matriz_confusion_valid=cm_valid,
        matriz_confusion_test=cm_test,
        metricas_referencia=metricas_referencia,
        n_train=len(idx_train_fit),
        n_artefacto=len(y),
    )


def _evaluar_referencias(
    Xtr: pd.DataFrame,
    ytr: np.ndarray,
    Xva: pd.DataFrame,
    yva: np.ndarray,
    Xte: pd.DataFrame,
    yte: np.ndarray,
    features: list[str],
    cats: list[str],
    seed: int,
    filas_metricas: list[dict],
) -> dict[str, dict[str, float]]:
    """Referencia interpretable (logistica) + baselines triviales (Dummy).

    - **Regresion logistica** montada **correctamente** en su propio pipeline
      (estandarizacion de numericas + one-hot de categoricas + ``class_weight=
      'balanced'``): un lineal mal montado no es evidencia de nada (leccion del
      Ridge en la 2a).
    - **Baseline trivial**: ``DummyClassifier`` mayoritario y estratificado, para
      contextualizar (su PR-AUC ~ prevalencia = linea sin-skill).
    """
    from sklearn.compose import ColumnTransformer
    from sklearn.dummy import DummyClassifier
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder, StandardScaler

    num_features = [f for f in features if f not in cats]
    logistica = Pipeline(
        [
            (
                "pre",
                ColumnTransformer(
                    [
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
                ),
            ),
            (
                "clf",
                LogisticRegression(
                    max_iter=1000, class_weight="balanced", random_state=seed
                ),
            ),
        ]
    )
    referencias = {
        "LogisticReg(balanced)": logistica,
        "Dummy(mayoritario)": DummyClassifier(strategy="most_frequent"),
        "Dummy(estratificado)": DummyClassifier(strategy="stratified", random_state=seed),
    }
    resultados: dict[str, dict[str, float]] = {}
    for nombre, modelo in referencias.items():
        modelo.fit(Xtr, ytr)
        for split, yv, Xv in (("valid", yva, Xva), ("test", yte, Xte)):
            m = classification_metrics_min(yv, _proba(modelo, Xv))
            filas_metricas.append({"estrategia": nombre, "split": split, **m})
            if split == "test":
                resultados[nombre] = m
    return resultados


# ---------------------------------------------------------------------------
# Persistencia: registro de metricas, artefacto y reporte
# ---------------------------------------------------------------------------
def persistir_metricas(res: ResultadoClasificacion, settings: Settings) -> Path:
    """Guarda el registro de metricas en CSV y JSON (trazabilidad del efecto SMOTE).

    Una fila por **estrategia x split** (valid/test/cv) con PR-AUC, recall, F1,
    precision, ROC-AUC y prevalencia, para que el efecto de SMOTE quede en disco, no
    solo en prosa.
    """
    settings.processed_dir.mkdir(parents=True, exist_ok=True)
    ruta_csv = settings.processed_dir / "metricas_clasificacion_2b.csv"
    res.metricas.to_csv(ruta_csv, index=False)
    (settings.processed_dir / "metricas_clasificacion_2b.json").write_text(
        res.metricas.to_json(orient="records", force_ascii=False, indent=2),
        encoding="utf-8",
    )
    return ruta_csv


def _metadatos(res: ResultadoClasificacion, settings: Settings) -> dict[str, Any]:
    """Metadatos completos del artefacto (criterio de hecho de la 2b)."""
    return {
        "version": VERSION_MODELO,
        "fecha_entrenamiento": date.today().isoformat(),
        "campo": "almacen",
        "objetivo": "demanda_alta = sales > P75 de su familia (P75 fijado solo en TRAIN)",
        "modelo_base": "LightGBM (binary)",
        "estrategia_desbalance": res.estrategia_elegida,
        "usa_smote": res.estrategia_elegida == "smote",
        "umbral": res.umbral,
        "criterio_umbral": res.criterio_umbral,
        "criterio_seleccion": res.criterio_seleccion,
        "semilla": settings.random_seed,
        "features": res.features,
        "features_categoricas": res.cats,
        "config_features": res.cfg_features.as_dict(),
        "cortes_temporales": res.cortes.as_dict(),
        "prevalencia_train": round(res.info_etiqueta.prevalencia_train, 4),
        "prevalencia_valid": round(res.metricas_valid[res.estrategia_elegida]["prevalencia"], 4),
        "prevalencia_test": round(res.metricas_test["prevalencia"], 4),
        # No-skill del headline (PR-AUC de TEST) = prevalencia del split TEST (el
        # umbral P75 se fija en TRAIN y la prevalencia sube con el crecimiento de
        # ventas; los Dummy confirman este nivel).
        "linea_sin_skill_pr_auc": round(res.metricas_test["prevalencia"], 4),
        "nota_prevalencia": (
            "El umbral P75 se fija en TRAIN; como las ventas crecen en el tiempo, la "
            "prevalencia de positivos sube de ~0.224 (train) a ~0.347 (valid/test). La "
            "linea sin-skill de la PR-AUC es la prevalencia del split evaluado."
        ),
        "familias_degeneradas_excluidas": res.info_etiqueta.familias_degeneradas,
        "n_familias_total": res.info_etiqueta.n_familias,
        "metricas_valid": res.metricas_valid[res.estrategia_elegida],
        "metricas_test": res.metricas_test,
        "matriz_confusion_valid": res.matriz_confusion_valid,
        "matriz_confusion_test": res.matriz_confusion_test,
        "metricas_valid_por_estrategia": res.metricas_valid,
        "metricas_referencia_test": res.metricas_referencia,
        "nota_evaluacion": (
            "estrategia y umbral elegidos en VALID; TEST evaluado una sola vez sobre "
            "la configuracion elegida. PR-AUC es la metrica principal (minoritaria); "
            "se contextualiza contra la linea sin-skill = prevalencia."
        ),
        "nota_portabilidad": (
            "el booster entrena en GPU y predice en CPU (LightGBM nativo); el "
            "artefacto carga y predice sin GPU."
        ),
        "n_filas_comparacion": res.n_train,
        "n_filas_artefacto_final": res.n_artefacto,
    }


def serializar_artefacto(
    res: ResultadoClasificacion, settings: Settings
) -> tuple[Path, Path]:
    """Serializa el predictor elegido + metadatos en ``models/``."""
    ruta = settings.base_dir / "models" / f"{VERSION_MODELO}.joblib"
    return guardar_artefacto(res.predictor, ruta, _metadatos(res, settings))


def _tabla_estrategias(res: ResultadoClasificacion) -> pd.DataFrame:
    """Tabla con/sin SMOTE: una fila por estrategia con metricas de VALID al umbral
    elegido (la base de la decision)."""
    filas = []
    for nombre in ESTRATEGIAS:
        m = res.metricas_valid[nombre]
        filas.append(
            {
                "estrategia": nombre,
                "PR_AUC": round(m["PR_AUC"], 4),
                "Recall": round(m["Recall"], 4),
                "F1": round(m["F1"], 4),
                "Precision": round(m["Precision"], 4),
                "ROC_AUC": round(m["ROC_AUC"], 4),
                "umbral": round(m["umbral"], 4),
            }
        )
    return pd.DataFrame(filas)


def escribir_reporte(res: ResultadoClasificacion, settings: Settings) -> Path:
    """Genera ``docs/reporte_clasificacion_2b.md`` (efecto de SMOTE + cierre)."""
    info = res.info_etiqueta
    elegida = res.estrategia_elegida
    mt = res.metricas_test
    mv = res.metricas_valid[elegida]
    cm = res.matriz_confusion_test
    # Linea sin-skill de la PR-AUC = prevalencia **del split evaluado** (no la de
    # train): el umbral P75 se fija en TRAIN y, como las ventas crecen en el tiempo,
    # la prevalencia sube de train a valid/test. El no-skill del headline TEST es la
    # prevalencia de TEST (los Dummy lo confirman).
    prev_train = round(info.prevalencia_train, 4)
    prev_valid = round(mv["prevalencia"], 4)
    prev_test = round(mt["prevalencia"], 4)

    # Tabla de referencias (TEST) ordenada.
    ref_filas = [
        {
            "modelo": k,
            "PR_AUC": round(v["PR_AUC"], 4),
            "Recall": round(v["Recall"], 4),
            "F1": round(v["F1"], 4),
            "Precision": round(v["Precision"], 4),
            "ROC_AUC": round(v["ROC_AUC"], 4),
        }
        for k, v in res.metricas_referencia.items()
    ]

    lineas = [
        "# Reporte de Clasificacion (Fase 2b) - ALMACEN (`demanda_alta`)",
        "",
        "> Generado por `spc.models.clasificacion`. Objetivo: `demanda_alta = sales > "
        "P75 de su familia` (umbral P75 fijado **solo en TRAIN**). Validacion temporal "
        "sin fuga; seleccion de estrategia y umbral en **VALID**; TEST evaluado **una "
        "sola vez**. La cantidad que define la etiqueta (`sales` actual) **no es "
        "feature**: solo rezagos/ventanas pasadas, igual que la 2a.",
        "",
        "## Etiqueta y desbalance",
        "",
        f"- **Prevalencia de positivos (TRAIN):** {prev_train:.4f} "
        f"(~1:{(1 - prev_train) / max(prev_train, 1e-9):.1f}) — el desbalance moderado "
        "que anticipaba el EDA (~22 %).",
        f"- **La prevalencia sube en valid/test** (VALID {prev_valid:.4f}, TEST "
        f"{prev_test:.4f}): el umbral P75 se fija en TRAIN y, como las ventas crecen "
        "en el tiempo, mas dias superan ese umbral historico. Por eso la **linea "
        "sin-skill de la PR-AUC es la prevalencia del split evaluado** (no la de "
        "train); los `Dummy` lo confirman abajo.",
        f"- **Familias totales:** {info.n_familias}. "
        f"**Degeneradas excluidas (P75<=0)**: {info.familias_degeneradas or 'ninguna'} "
        f"({len(info.familias_degeneradas)} de {info.n_familias}). En ellas "
        "`demanda_alta` se reduce a 'vendio algo' en vez de 'demanda alta' (etiqueta "
        "ruidosa); se documentan y se excluyen del train/eval.",
        "",
        "## Cortes temporales (heredados de la 2a)",
        "",
        f"- **Train:** {res.cortes.as_dict()['train']}",
        f"- **Valid:** {res.cortes.as_dict()['valid']}  (seleccion de estrategia y umbral)",
        f"- **Test:** {res.cortes.as_dict()['test']}  (evaluado una sola vez)",
        "",
        "## Efecto de SMOTE - comparacion de estrategias (VALID, al umbral elegido)",
        "",
        "Mismo booster base (LightGBM). SMOTE aplicado **solo en train, dentro de cada "
        "fold** (SMOTENC, via `imblearn.Pipeline`). PR-AUC es independiente del umbral "
        "(metrica principal de la minoritaria); recall/F1/precision al umbral de "
        "negocio elegido en VALID.",
        "",
        markdown_table(_tabla_estrategias(res)),
        "",
        f"**Decision:** estrategia = **`{elegida}`**"
        f"{' (SMOTE NO se adopta)' if elegida != 'smote' else ' (SMOTE adoptado)'}. "
        f"{res.criterio_seleccion['regla']}.",
        "",
        f"- PR-AUC VALID por estrategia: {res.criterio_seleccion['pr_auc_valid']}.",
        f"- Recall VALID por estrategia: {res.criterio_seleccion['recall_valid']}.",
        f"- SMOTE solo se adoptaria si superara a la costo-sensible por > {TOL_PRAUC} "
        "de PR-AUC en VALID. Mostrar que no aporta es un resultado valido.",
        "",
        "## Umbral elegido (marco de negocio)",
        "",
        f"- **Umbral = {res.umbral:.4f}** (no el 0.5 por defecto). Criterio: "
        f"{res.criterio_umbral['criterio']}.",
        f"- En VALID al umbral: precision={res.criterio_umbral.get('precision_en_umbral')}, "
        f"recall={res.criterio_umbral.get('recall_en_umbral')}.",
        "",
        "## Resultado final en TEST (configuracion elegida, una sola vez)",
        "",
        f"- **PR-AUC = {mt['PR_AUC']:.4f}** vs linea sin-skill (prevalencia TEST) "
        f"{prev_test:.4f} -> **x{mt['PR_AUC'] / max(prev_test, 1e-9):.2f}** sobre el "
        "azar.",
        f"- **Recall (minoritaria) = {mt['Recall']:.4f}** | "
        f"**F1 = {mt['F1']:.4f}** | **Precision = {mt['Precision']:.4f}**.",
        f"- ROC-AUC (contexto) = {mt['ROC_AUC']:.4f}.",
        f"- (VALID de referencia: PR-AUC {mv['PR_AUC']:.4f}, recall {mv['Recall']:.4f}.)",
        f"- Nota: la precision en TEST ({mt['Precision']:.4f}) queda apenas por debajo "
        f"del piso de {PRECISION_FLOOR:.2f} usado en VALID; es el efecto esperado de "
        "fijar el umbral en VALID y evaluar TEST una sola vez (sin reajustar a TEST).",
        "",
        "### Matriz de confusion en TEST (al umbral elegido)",
        "",
        "|  | pred 0 | pred 1 |",
        "|---|---|---|",
        f"| **real 0** | {cm['TN']} (TN) | {cm['FP']} (FP) |",
        f"| **real 1** | {cm['FN']} (FN) | {cm['TP']} (TP) |",
        "",
        "## Referencia interpretable y baselines triviales (TEST)",
        "",
        "Regresion logistica en pipeline propio (estandarizacion + one-hot + "
        "`class_weight='balanced'`) y `DummyClassifier` (mayoritario/estratificado, "
        "PR-AUC ~ prevalencia = sin-skill).",
        "",
        markdown_table(pd.DataFrame(ref_filas)),
        "",
        "## Jerarquia de metricas",
        "",
        "**PR-AUC** (principal, minoritaria, independiente del umbral) -> **recall** "
        "(marco de negocio: no detectar demanda alta cuesta mas) -> **F1** -> "
        "**precision**. **Accuracy no** se usa como principal (enganha con clases "
        "desbalanceadas). ROC-AUC es contexto.",
        "",
        "## Notas de diseno",
        "",
        "- Features reutilizadas de la 2a (`spc.features.temporales`), leak-safe: "
        "`sales` actual, `family_sales_p75` y `demanda_alta` **no** son features.",
        "- Umbral P75 fijado **solo en TRAIN** (no mira el futuro).",
        "- SMOTE **solo en train, dentro de cada fold** (nunca valid/test ni el "
        "dataset completo). SMOTE interpola en el espacio de features ignorando el "
        "tiempo (discutible en datos panel): por eso es un candidato a evaluar, no un "
        "default.",
        "- Booster entrena en GPU, **predice en CPU** (artefacto portable).",
        "",
        "## Mejoras diferidas (documentadas, no implementadas)",
        "",
        "- **Calibracion de probabilidades** (Platt/isotonica) si la probabilidad se "
        "usa para decisiones de stock.",
        "- **Metodos especificos de demanda intermitente** para las familias de bajo "
        "volumen (las degeneradas excluidas y las de P75 entero bajo).",
        "",
    ]
    ruta = settings.base_dir / "docs" / "reporte_clasificacion_2b.md"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text("\n".join(lineas), encoding="utf-8")
    return ruta


# ---------------------------------------------------------------------------
# Flujo offline + CLI
# ---------------------------------------------------------------------------
def entrenar(
    settings: Settings,
    *,
    max_train_rows: int | None,
    con_cv: bool,
    usar_gpu: bool = True,
) -> ResultadoClasificacion:
    """Flujo offline: carga datos, compara estrategias, persiste metricas, artefacto
    y reporte. ``usar_gpu`` por defecto **True** (booster en GPU; artefacto en CPU)."""
    from spc.data.integration import build_analytic_dataset
    from spc.data.loaders import load_data

    np.random.seed(settings.random_seed)
    data = load_data(settings)
    analytic, _, _ = build_analytic_dataset(data, settings)

    res = entrenar_y_comparar(
        analytic, settings, max_train_rows=max_train_rows, con_cv=con_cv,
        usar_gpu=usar_gpu,
    )
    ruta_csv = persistir_metricas(res, settings)
    ruta_art, ruta_meta = serializar_artefacto(res, settings)
    ruta_rep = escribir_reporte(res, settings)
    log.info("Metricas: %s", ruta_csv)
    log.info("Artefacto: %s (+ %s)", ruta_art, ruta_meta.name)
    log.info("Reporte: %s", ruta_rep)
    return res


def cli(argv: list[str] | None = None) -> None:
    """Entrenamiento offline reproducible de la clasificacion de ALMACEN (Fase 2b)."""
    parser = argparse.ArgumentParser(
        description="Entrena y compara la clasificacion de ALMACEN (Fase 2b)."
    )
    parser.add_argument("--base-dir", type=Path, default=None, help="Raiz del proyecto.")
    parser.add_argument(
        "--max-train-rows", type=int, default=300_000,
        help="Tope de filas para ajustar (submuestreo de train; default 300000).",
    )
    parser.add_argument("--full", action="store_true", help="Ajustar sin tope (lento).")
    parser.add_argument("--sin-cv", action="store_true", help="Omitir la CV temporal.")
    parser.add_argument(
        "--cpu", action="store_true",
        help="Forzar CPU (por defecto el booster entrena en GPU: LightGBM gpu/OpenCL).",
    )
    args = parser.parse_args(argv)

    from spc.utils.logging import configure_logging

    configure_logging(verbose=True)
    settings = Settings(base_dir=args.base_dir) if args.base_dir else Settings()
    max_rows = None if args.full else args.max_train_rows

    res = entrenar(
        settings, max_train_rows=max_rows, con_cv=not args.sin_cv, usar_gpu=not args.cpu,
    )

    print("\n" + "=" * 72)
    print("  EFECTO DE SMOTE - estrategias en VALID (al umbral elegido)")
    print("=" * 72)
    print(_tabla_estrategias(res).to_string(index=False))
    print(
        f"\nEstrategia elegida: {res.estrategia_elegida} (umbral {res.umbral:.3f})"
        f" | usa_smote={res.estrategia_elegida == 'smote'}"
    )
    mt = res.metricas_test
    print(
        f"TEST (una vez) -> PR-AUC {mt['PR_AUC']:.4f} | recall {mt['Recall']:.4f} | "
        f"F1 {mt['F1']:.4f} | precision {mt['Precision']:.4f} "
        f"(sin-skill = prevalencia TEST {mt['prevalencia']:.4f}; "
        f"prevalencia train {res.info_etiqueta.prevalencia_train:.4f})"
    )
    print(f"Artefacto {VERSION_MODELO} en models/")


def cargar_predictor(ruta: Path) -> tuple[PredictorClasificacion, dict[str, Any]]:
    """Carga el predictor serializado y sus metadatos (para la capa servicio/API)."""
    return cargar_artefacto(ruta)


def train_classification_models(
    analytic: pd.DataFrame,
    settings: Settings,
    *,
    sample_frac: float = 0.3,
    test_days: int | None = None,  # noqa: ARG001 - compat: cortes 2a fijos
    **_: Any,
) -> dict[str, Any]:
    """Compat para el CLI exploratorio ``spc-models`` (``runner.cli``).

    Delega en el motor 2b (``entrenar_y_comparar``, CPU) y devuelve un dict con la
    tabla de metricas por estrategia x split, para que ``spc-models`` siga
    funcionando sin reescribir su salida. El flujo de produccion de la 2b es
    ``entrenar``/``cli`` (GPU, artefacto + reporte), no esta funcion.
    """
    max_rows = None if sample_frac >= 1.0 else 300_000
    res = entrenar_y_comparar(
        analytic, settings, max_train_rows=max_rows, con_cv=False, usar_gpu=False
    )
    return {
        "metrics": res.metricas,
        "estrategia_elegida": res.estrategia_elegida,
        "umbral": res.umbral,
        "predictor": res.predictor,
    }


# Portabilidad del artefacto: este modulo NO se ejecuta como ``__main__`` (sin
# bloque ``if __name__ == "__main__"``). El entrenamiento offline se lanza por
# **import** (`scripts/train_clasificacion.py` o el console-script
# ``spc-train-clasificacion``), de modo que ``PredictorClasificacion`` se picklea
# bajo ``spc.models.clasificacion`` y el ``.joblib`` carga desde un proceso limpio.
