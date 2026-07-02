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

# Marco de negocio para el umbral por defecto. `demanda_alta` senala riesgo de
# quiebre; fallar un positivo (no detectar demanda alta) cuesta mas que una falsa
# alarma, asi que el default prioriza **recall**. Pero el operativo debe ser
# **accionable**: un piso de precision demasiado debil (0.50, lift de solo ~1.44x
# sobre la prevalencia ~0.346) degenera en "marcar casi todo" -inutil para
# priorizar un almacen-. Por eso el default usa un **piso REAL de precision (0.80)**
# y toma el maximo recall que lo respeta.
PRECISION_FLOOR = 0.80

# Margen anadido al piso al elegir en VALID (robustez VALID->TEST). En la corrida
# vieja la precision se deslizo de 0.50 (valid) a 0.484 (test); con un piso mas
# alto ese deslizamiento importa mas, asi que en VALID se apunta a
# precision >= PRECISION_FLOOR + MARGEN_VALID para que el piso aguante en TEST.
MARGEN_VALID = 0.02

# Piso del punto de operacion **recall-prioritario**, que se reporta SOLO como
# alternativa informativa (es el default viejo, operativo degenerado): no es el
# default del artefacto.
PISO_RECALL_PRIORITARIO = 0.50

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
# Seleccion de umbral en VALID (marco de negocio: max recall con piso REAL de precision)
# ---------------------------------------------------------------------------
def _candidatos_pr(
    y_true: np.ndarray, y_prob: np.ndarray
) -> list[tuple[float, float, float]]:
    """Lista de ``(umbral, precision, recall)`` de la curva PR (sin el punto final
    sin umbral que devuelve ``precision_recall_curve``)."""
    prec, rec, thr = precision_recall_curve(y_true, y_prob)
    return [(float(thr[i]), float(prec[i]), float(rec[i])) for i in range(len(thr))]


def _max_recall_con_piso(
    cand: list[tuple[float, float, float]], piso: float
) -> tuple[float, float, float] | None:
    """Entre los umbrales con ``precision >= piso``, el de **mayor recall** (desempate:
    mayor umbral). ``None`` si ninguno alcanza el piso."""
    viables = [c for c in cand if c[1] >= piso]
    if not viables:
        return None
    return max(viables, key=lambda c: (c[2], c[0]))


def _max_f1(cand: list[tuple[float, float, float]]) -> tuple[float, float, float]:
    """Umbral de **maximo F1** sobre los candidatos."""
    def f1(c: tuple[float, float, float]) -> float:
        p_, r_ = c[1], c[2]
        return (2 * p_ * r_ / (p_ + r_)) if (p_ + r_) > 0 else 0.0

    return max(cand, key=f1)


def seleccionar_umbral(
    y_true: np.ndarray,
    y_prob: np.ndarray,
    precision_floor: float = PRECISION_FLOOR,
    margen: float = MARGEN_VALID,
) -> tuple[float, dict[str, Any]]:
    """Elige el umbral por defecto en VALID: **max recall sujeto a un piso REAL de
    precision** (default 0.80), con margen de robustez VALID->TEST.

    Marco de negocio: no detectar demanda alta cuesta mas que una falsa alarma, asi
    que se prioriza recall; pero el operativo debe ser accionable, asi que se exige
    un piso real de precision (0.80, no 0.50). El piso efectivo en VALID es
    ``precision_floor + margen`` (se apunta un poco mas alto en valid para que el
    piso aguante en test). Si ningun umbral alcanza el piso efectivo se intenta sin
    margen; si tampoco, se cae a **max F1** (operativo equilibrado, no degenerado).
    Se decide SOLO sobre VALID.
    """
    cand = _candidatos_pr(y_true, y_prob)
    if not cand:
        return 0.5, {
            "criterio": "sin variabilidad de probabilidad; umbral por defecto 0.5",
            "precision_floor": precision_floor,
            "margen_valid": margen,
        }
    piso_efectivo = precision_floor + margen
    punto = _max_recall_con_piso(cand, piso_efectivo)
    if punto is not None:
        umbral, p, r = punto
        criterio = (
            f"max recall sujeto a precision >= {precision_floor:.2f} "
            f"(piso de negocio REAL, no 0.50; margen +{margen:.2f} en VALID -> piso "
            f"efectivo {piso_efectivo:.2f}- para que el piso aguante en TEST)"
        )
    elif (punto := _max_recall_con_piso(cand, precision_floor)) is not None:
        umbral, p, r = punto
        criterio = (
            f"max recall sujeto a precision >= {precision_floor:.2f} "
            f"(sin margen: ningun umbral alcanza el piso efectivo {piso_efectivo:.2f})"
        )
    else:
        umbral, p, r = _max_f1(cand)
        criterio = (
            f"ningun umbral alcanza precision {precision_floor:.2f}; "
            "fallback a max F1 (operativo equilibrado, no degenerado)"
        )
    return float(umbral), {
        "criterio": criterio,
        "precision_floor": precision_floor,
        "margen_valid": margen,
        "piso_efectivo_valid": round(piso_efectivo, 4),
        "precision_en_umbral": round(float(p), 4),
        "recall_en_umbral": round(float(r), 4),
    }


# ---------------------------------------------------------------------------
# Puntos de operacion + curva PR (reporte para que la Fase 3 elija su tolerancia)
# ---------------------------------------------------------------------------
def curva_pr(y_true: np.ndarray, y_prob: np.ndarray) -> pd.DataFrame:
    """Curva precision-recall completa ``(umbral, precision, recall)`` para persistir.

    Se descarta el punto final que ``precision_recall_curve`` anade sin umbral
    (recall=0, precision=1). La Fase 3 puede elegir cualquier punto segun su
    tolerancia sin quedar amarrada al umbral por defecto.
    """
    prec, rec, thr = precision_recall_curve(y_true, y_prob)
    return pd.DataFrame(
        {"umbral": thr, "precision": prec[:-1], "recall": rec[:-1]}
    )


def puntos_de_operacion(
    y_valid: np.ndarray,
    prob_valid: np.ndarray,
    y_test: np.ndarray,
    prob_test: np.ndarray,
    *,
    precision_floor: float = PRECISION_FLOOR,
    margen: float = MARGEN_VALID,
    piso_recall: float = PISO_RECALL_PRIORITARIO,
) -> tuple[dict[str, float], dict[str, dict[str, Any]]]:
    """Define varios puntos de operacion (umbral elegido **siempre en VALID**) y los
    evalua en VALID y TEST.

    Tres puntos: el **default** (max recall con precision >= ``precision_floor``), el
    de **maximo F1**, y el **recall-prioritario** (piso 0.50, el default viejo) como
    referencia. Devuelve ``(umbrales, detalle)`` donde ``umbrales`` mapea
    punto->umbral y ``detalle`` lleva, por punto, las metricas completas en valid y
    test, la matriz de confusion de test y cuantas filas marca (operatividad).
    """
    cand_va = _candidatos_pr(y_valid, prob_valid)
    umbral_default, _ = seleccionar_umbral(y_valid, prob_valid, precision_floor, margen)
    umbral_f1 = _max_f1(cand_va)[0] if cand_va else 0.5
    punto_rp = _max_recall_con_piso(cand_va, piso_recall)
    umbral_rp = punto_rp[0] if punto_rp is not None else umbral_default

    clave_default = f"precision>={precision_floor:.2f}"
    clave_rp = f"recall_prioritario(p>={piso_recall:.2f})"
    umbrales: dict[str, float] = {
        clave_default: float(umbral_default),
        "max_f1": float(umbral_f1),
        clave_rp: float(umbral_rp),
    }
    etiquetas = {
        clave_default: f"max recall s.t. precision >= {precision_floor:.2f} (DEFAULT)",
        "max_f1": "max F1",
        clave_rp: f"max recall s.t. precision >= {piso_recall:.2f} (referencia)",
    }
    n_test = len(y_test)
    detalle: dict[str, dict[str, Any]] = {}
    for clave, u in umbrales.items():
        mv = classification_metrics_min(y_valid, prob_valid, u)
        mt = classification_metrics_min(y_test, prob_test, u)
        cm_test = matriz_confusion(y_test, prob_test, u)
        n_pos = cm_test["TP"] + cm_test["FP"]
        detalle[clave] = {
            "punto": clave,
            "etiqueta": etiquetas[clave],
            "umbral": float(u),
            "es_default": clave == clave_default,
            "valid": mv,
            "test": mt,
            "matriz_confusion_test": cm_test,
            "n_pos_pred_test": int(n_pos),
            "pct_marcado_test": round(100.0 * n_pos / max(1, n_test), 1),
        }
    return umbrales, detalle


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
# Preparacion de datos compartida (features + etiqueta + cortes + splits)
# ---------------------------------------------------------------------------
@dataclass
class DatosPreparados:
    """Frame modelable, matriz de features, etiqueta y splits temporales.

    Lo comparten el entrenamiento/comparacion (``entrenar_y_comparar``) y la
    recalibracion post-hoc del umbral (``recalibrar_umbral``), de modo que ambos
    usan **identicos** features, etiqueta honesta y cortes (sin riesgo de deriva).
    """

    df_model: pd.DataFrame
    features: list[str]
    cats: list[str]
    categorias: dict[str, Any]
    cfg_features: ConfigFeatures
    cortes: CortesTemporales
    info_etiqueta: InfoEtiqueta
    X_cat: pd.DataFrame
    y: np.ndarray
    idx_train: np.ndarray
    idx_valid: np.ndarray
    idx_test: np.ndarray


def preparar_datos(
    analytic: pd.DataFrame, cfg_features: ConfigFeatures
) -> DatosPreparados:
    """Construye features leak-safe, fija la etiqueta honesta (P75 train-only) y los
    cortes temporales de la 2a, y devuelve la matriz + los indices de cada split."""
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
    return DatosPreparados(
        df_model=df_model,
        features=features,
        cats=cats,
        categorias=categorias,
        cfg_features=cfg_features,
        cortes=cortes,
        info_etiqueta=info_etiqueta,
        X_cat=X_cat,
        y=y,
        idx_train=idx[mask_train],
        idx_valid=idx[mask_valid],
        idx_test=idx[mask_test],
    )


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

    datos = preparar_datos(analytic, cfg_features)
    df_model = datos.df_model
    features, cats, categorias = datos.features, datos.cats, datos.categorias
    cfg_features = datos.cfg_features
    cortes, info_etiqueta = datos.cortes, datos.info_etiqueta
    X_cat, y = datos.X_cat, datos.y
    idx_train, idx_valid, idx_test = datos.idx_train, datos.idx_valid, datos.idx_test
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
        f"- Nota: umbral elegido en VALID con piso real de precision {PRECISION_FLOOR:.2f} "
        f"(margen +{MARGEN_VALID:.2f}); TEST se evalua una sola vez sin reajustar. Para la "
        "tabla de puntos de operacion y la curva PR, ver la recalibracion post-hoc "
        "(`scripts/recalibrar_umbral_clasificacion.py`).",
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


# ---------------------------------------------------------------------------
# Recalibracion POST-HOC del umbral (sin reentrenar el booster de produccion)
# ---------------------------------------------------------------------------
@dataclass
class ResultadoRecalibracion:
    """Salida de la recalibracion post-hoc del punto de operacion (umbral)."""

    estrategia: str
    umbral: float
    criterio_umbral: dict[str, Any]
    umbrales_punto: dict[str, float]
    detalle_puntos: dict[str, dict[str, Any]]
    curva_pr_valid: pd.DataFrame
    metricas_valid: dict[str, float]
    metricas_test: dict[str, float]
    matriz_confusion_valid: dict[str, int]
    matriz_confusion_test: dict[str, int]
    cortes: CortesTemporales
    info_etiqueta: InfoEtiqueta
    n_train_fit: int


def recalibrar_umbral(
    analytic: pd.DataFrame,
    settings: Settings,
    *,
    estrategia: str = "sin_remuestreo",
    cfg_features: ConfigFeatures | None = None,
    max_train_rows: int | None = 300_000,
    usar_gpu: bool = False,
) -> ResultadoRecalibracion:
    """Re-elige el umbral por defecto **post-hoc** sobre la estrategia ya elegida.

    Reproduce SOLO la estrategia de produccion (``sin_remuestreo``) ajustada en
    TRAIN (determinista, semilla 42) para obtener las probabilidades held-out de
    VALID/TEST. **No** re-corre SMOTE/costo-sensible/CV ni re-decide nada. Sobre esas
    probabilidades elige el nuevo umbral por defecto en **VALID** (max recall con piso
    REAL de precision), calcula los puntos de operacion y la curva PR, y evalua TEST
    **una sola vez** al nuevo default. El booster de produccion no se reentrena: lo
    reusa ``aplicar_recalibracion`` desde el ``.joblib`` (solo cambia su umbral).
    """
    seed = settings.random_seed
    cfg_features = cfg_features or ConfigFeatures()
    datos = preparar_datos(analytic, cfg_features)
    idx_train_fit = _muestrear(datos.idx_train, max_train_rows, seed)
    n_pos = int(datos.y[idx_train_fit].sum())
    n_neg = int(len(idx_train_fit) - n_pos)
    spw = (n_neg / n_pos) if n_pos else 1.0

    log.info(
        "Reproduciendo `%s` en TRAIN (CPU determinista) para recalibrar el umbral...",
        estrategia,
    )
    modelo = construir_estrategia(
        estrategia, seed, usar_gpu=usar_gpu, scale_pos_weight=spw
    )
    modelo.fit(datos.X_cat.iloc[idx_train_fit], datos.y[idx_train_fit])
    yva = datos.y[datos.idx_valid]
    yte = datos.y[datos.idx_test]
    prob_va = _proba(modelo, datos.X_cat.iloc[datos.idx_valid])
    prob_te = _proba(modelo, datos.X_cat.iloc[datos.idx_test])

    umbral, criterio_umbral = seleccionar_umbral(yva, prob_va)
    umbrales_punto, detalle = puntos_de_operacion(yva, prob_va, yte, prob_te)
    log.info("Nuevo default umbral=%.4f | %s", umbral, criterio_umbral["criterio"])
    return ResultadoRecalibracion(
        estrategia=estrategia,
        umbral=umbral,
        criterio_umbral=criterio_umbral,
        umbrales_punto=umbrales_punto,
        detalle_puntos=detalle,
        curva_pr_valid=curva_pr(yva, prob_va),
        metricas_valid=classification_metrics_min(yva, prob_va, umbral),
        metricas_test=classification_metrics_min(yte, prob_te, umbral),
        matriz_confusion_valid=matriz_confusion(yva, prob_va, umbral),
        matriz_confusion_test=matriz_confusion(yte, prob_te, umbral),
        cortes=datos.cortes,
        info_etiqueta=datos.info_etiqueta,
        n_train_fit=len(idx_train_fit),
    )


def _tabla_puntos_operacion(res: ResultadoRecalibracion) -> pd.DataFrame:
    """Tabla compacta de puntos de operacion (valid + test) para meta/reporte."""
    filas = []
    for d in res.detalle_puntos.values():
        filas.append(
            {
                "punto": d["etiqueta"],
                "umbral": round(d["umbral"], 4),
                "P_valid": round(d["valid"]["Precision"], 4),
                "R_valid": round(d["valid"]["Recall"], 4),
                "F1_valid": round(d["valid"]["F1"], 4),
                "P_test": round(d["test"]["Precision"], 4),
                "R_test": round(d["test"]["Recall"], 4),
                "F1_test": round(d["test"]["F1"], 4),
                "%marcado_test": d["pct_marcado_test"],
            }
        )
    return pd.DataFrame(filas)


def _puntos_operacion_meta(res: ResultadoRecalibracion) -> dict[str, dict[str, Any]]:
    """Version serializable de los puntos de operacion para el meta del artefacto."""
    return {
        d["etiqueta"]: {
            "umbral": round(d["umbral"], 6),
            "es_default": d["es_default"],
            "precision_valid": round(d["valid"]["Precision"], 4),
            "recall_valid": round(d["valid"]["Recall"], 4),
            "F1_valid": round(d["valid"]["F1"], 4),
            "precision_test": round(d["test"]["Precision"], 4),
            "recall_test": round(d["test"]["Recall"], 4),
            "F1_test": round(d["test"]["F1"], 4),
            "n_pos_pred_test": d["n_pos_pred_test"],
            "pct_marcado_test": d["pct_marcado_test"],
        }
        for d in res.detalle_puntos.values()
    }


def aplicar_recalibracion(
    res: ResultadoRecalibracion, settings: Settings
) -> tuple[Path, Path]:
    """Actualiza el artefacto (mismo booster, nuevo umbral) y sus metadatos.

    Carga el ``.joblib`` existente, le fija el nuevo umbral por defecto -el booster de
    produccion **no se reentrena**- y reescribe el meta con el nuevo umbral, su
    criterio, la tabla de puntos de operacion, la referencia a la curva PR y las
    metricas/matrices al nuevo umbral. La comparacion de estrategias (registro de la
    decision de SMOTE, PR-AUC threshold-independent) se conserva.
    """
    ruta = settings.base_dir / "models" / f"{VERSION_MODELO}.joblib"
    predictor, meta = cargar_artefacto(ruta)
    umbral_anterior = getattr(predictor, "umbral", None)
    predictor.umbral = float(res.umbral)  # mismo modelo, nuevo punto de operacion

    meta = dict(meta)
    meta.pop("guardado_utc", None)  # se refresca al re-serializar
    meta["umbral"] = res.umbral
    meta["umbral_anterior"] = umbral_anterior
    meta["criterio_umbral"] = res.criterio_umbral
    meta["puntos_operacion"] = _puntos_operacion_meta(res)
    meta["curva_pr_ref"] = "data/processed/curva_pr_clasificacion_2b.csv"
    meta["metricas_valid"] = res.metricas_valid
    meta["metricas_test"] = res.metricas_test
    meta["matriz_confusion_valid"] = res.matriz_confusion_valid
    meta["matriz_confusion_test"] = res.matriz_confusion_test
    meta["fecha_recalibracion"] = date.today().isoformat()
    meta["nota_recalibracion"] = (
        "Umbral por defecto re-elegido POST-HOC en VALID (max recall con piso real de "
        "precision 0.80, margen +0.02 VALID->TEST). El booster de produccion NO se "
        "reentreno: se reuso el del .joblib y solo cambio su umbral/metadatos. Las "
        "probabilidades held-out se reprodujeron con la estrategia elegida ajustada en "
        "TRAIN (CPU determinista, semilla 42). La comparacion de estrategias (decision "
        "de SMOTE) se conserva del entrenamiento original."
    )
    return guardar_artefacto(predictor, ruta, meta)


def persistir_curva_pr(res: ResultadoRecalibracion, settings: Settings) -> Path:
    """Persiste la curva precision-recall de VALID (umbral, precision, recall)."""
    settings.processed_dir.mkdir(parents=True, exist_ok=True)
    ruta = settings.processed_dir / "curva_pr_clasificacion_2b.csv"
    res.curva_pr_valid.to_csv(ruta, index=False)
    (settings.processed_dir / "curva_pr_clasificacion_2b.json").write_text(
        res.curva_pr_valid.to_json(orient="records", indent=2),
        encoding="utf-8",
    )
    return ruta


def agregar_puntos_a_registro(
    res: ResultadoRecalibracion, settings: Settings
) -> Path:
    """Anade al registro una fila por **punto de operacion x split** (columna ``punto``).

    Conserva las filas existentes de la comparacion de estrategias (su ``punto`` queda
    vacio) e idempotente: re-ejecutar la recalibracion reemplaza solo las filas de
    puntos de operacion previas.
    """
    settings.processed_dir.mkdir(parents=True, exist_ok=True)
    ruta_csv = settings.processed_dir / "metricas_clasificacion_2b.csv"
    base = pd.read_csv(ruta_csv) if ruta_csv.exists() else pd.DataFrame()
    if not base.empty and "punto" in base.columns:
        base = base[base["punto"].isna()].copy()

    filas = []
    for d in res.detalle_puntos.values():
        for split in ("valid", "test"):
            m = dict(d[split])
            m.update(
                {
                    "estrategia": res.estrategia,
                    "split": f"op_{split}",
                    "punto": d["etiqueta"],
                }
            )
            filas.append(m)
    combinado = pd.concat([base, pd.DataFrame(filas)], ignore_index=True)
    combinado.to_csv(ruta_csv, index=False)
    (settings.processed_dir / "metricas_clasificacion_2b.json").write_text(
        combinado.to_json(orient="records", force_ascii=False, indent=2),
        encoding="utf-8",
    )
    return ruta_csv


def escribir_reporte_recalibrado(
    res: ResultadoRecalibracion, meta: dict[str, Any], settings: Settings
) -> Path:
    """Regenera ``docs/reporte_clasificacion_2b.md`` con el nuevo punto de operacion.

    Headline = nuevo default (precision>=0.80); el recall-prioritario queda como
    alternativa. La comparacion de SMOTE y las referencias se toman del meta (decision
    intacta, PR-AUC threshold-independent).
    """
    info = res.info_etiqueta
    mv, mt = res.metricas_valid, res.metricas_test
    cm = res.matriz_confusion_test
    cu = res.criterio_umbral
    prev_train = round(info.prevalencia_train, 4)
    prev_valid = round(mv["prevalencia"], 4)
    prev_test = round(mt["prevalencia"], 4)
    default = next(d for d in res.detalle_puntos.values() if d["es_default"])

    por_estr = meta.get("metricas_valid_por_estrategia", {})
    filas_estr = [
        {
            "estrategia": e,
            "PR_AUC_valid": round(v.get("PR_AUC", float("nan")), 4),
            "ROC_AUC_valid": round(v.get("ROC_AUC", float("nan")), 4),
        }
        for e, v in por_estr.items()
    ]
    regla_sel = meta.get("criterio_seleccion", {}).get("regla", "")
    estrategia_elegida = meta.get("estrategia_desbalance", res.estrategia)

    ref = meta.get("metricas_referencia_test", {})
    ref_filas = [
        {
            "modelo": k,
            "PR_AUC": round(v["PR_AUC"], 4),
            "Recall": round(v["Recall"], 4),
            "F1": round(v["F1"], 4),
            "Precision": round(v["Precision"], 4),
            "ROC_AUC": round(v["ROC_AUC"], 4),
        }
        for k, v in ref.items()
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
        "> **Punto de operacion recalibrado (post-hoc).** El default ya **no** es el "
        "recall-prioritario (precision>=0.50), que degeneraba en marcar ~71 % de las "
        "filas con precision ~0.48 (lift de solo ~1.4x sobre la prevalencia). El nuevo "
        "default usa un **piso REAL de precision (0.80)** y toma el maximo recall que "
        "lo respeta. El **booster de produccion no cambio**: es solo recalibracion del "
        "umbral (las probabilidades del modelo son las mismas).",
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
        "## Efecto de SMOTE - comparacion de estrategias (VALID)",
        "",
        "Mismo booster base (LightGBM). La decision de SMOTE descansa en la **PR-AUC** "
        "(metrica principal de la minoritaria, **independiente del umbral**); por eso "
        "la recalibracion del umbral **no la altera**. ROC-AUC de contexto (tambien "
        "independiente del umbral).",
        "",
        markdown_table(pd.DataFrame(filas_estr)),
        "",
        f"**Decision (intacta):** estrategia = **`{estrategia_elegida}`** "
        f"{'(SMOTE NO se adopta)' if estrategia_elegida != 'smote' else '(SMOTE adoptado)'}"
        f". {regla_sel}.",
        "",
        "## Umbral por defecto (marco de negocio: piso REAL de precision)",
        "",
        f"- **Umbral = {res.umbral:.4f}** (no el 0.5 por defecto, **ni** el viejo "
        f"recall-prioritario). Criterio: {cu['criterio']}.",
        f"- En VALID al umbral: precision={mv['Precision']:.4f}, recall={mv['Recall']:.4f}, "
        f"F1={mv['F1']:.4f}.",
        f"- En TEST al umbral: precision={mt['Precision']:.4f}, recall={mt['Recall']:.4f}, "
        f"F1={mt['F1']:.4f} (el piso de precision aguanta gracias al margen "
        f"+{cu.get('margen_valid', 0):.2f} en VALID).",
        "",
        "### Puntos de operacion (umbral elegido en VALID; TEST informativo)",
        "",
        "Para que la **Fase 3** elija segun su tolerancia (no quede amarrada a un solo "
        "umbral). La **curva PR completa** (umbral, precision, recall) de VALID se "
        f"persiste en `{meta.get('curva_pr_ref', 'data/processed/curva_pr_clasificacion_2b.csv')}`.",
        "",
        markdown_table(_tabla_puntos_operacion(res)),
        "",
        "## Resultado final en TEST (default elegido en VALID, una sola vez)",
        "",
        f"- **PR-AUC = {mt['PR_AUC']:.4f}** vs linea sin-skill (prevalencia TEST) "
        f"{prev_test:.4f} -> **x{mt['PR_AUC'] / max(prev_test, 1e-9):.2f}** sobre el "
        "azar (independiente del umbral; no cambia con la recalibracion).",
        f"- Al **default**: precision={mt['Precision']:.4f}, recall={mt['Recall']:.4f}, "
        f"F1={mt['F1']:.4f}. ROC-AUC (contexto) = {mt['ROC_AUC']:.4f}.",
        f"- El operativo es **accionable**: marca {default['n_pos_pred_test']} filas "
        f"({default['pct_marcado_test']} %) como riesgo (antes ~71 %), con precision "
        f"~{mt['Precision']:.2f} (antes ~0.48).",
        f"- (VALID de referencia: precision {mv['Precision']:.4f}, recall {mv['Recall']:.4f}.)",
        "",
        "### Matriz de confusion en TEST (al default)",
        "",
        "|  | pred 0 | pred 1 |",
        "|---|---|---|",
        f"| **real 0** | {cm['TN']} (TN) | {cm['FP']} (FP) |",
        f"| **real 1** | {cm['FN']} (FN) | {cm['TP']} (TP) |",
        "",
        "## Referencia interpretable y baselines triviales (TEST, umbral 0.5)",
        "",
        "Regresion logistica en pipeline propio (estandarizacion + one-hot + "
        "`class_weight='balanced'`) y `DummyClassifier` (mayoritario/estratificado, "
        "PR-AUC ~ prevalencia = sin-skill). Recall/F1/precision al **0.5 por defecto** "
        "(no al umbral de negocio); la PR-AUC es la comparacion limpia.",
        "",
        markdown_table(pd.DataFrame(ref_filas)),
        "",
        "## Jerarquia de metricas",
        "",
        "**PR-AUC** (principal, minoritaria, independiente del umbral) -> **recall** "
        "(marco de negocio: no detectar demanda alta cuesta mas) -> **F1** -> "
        "**precision**. El **umbral por defecto** ya no maximiza recall a ciegas: exige "
        "un **piso real de precision (0.80)** para que el operativo sea accionable. "
        "**Accuracy no** se usa como principal (enganha con clases desbalanceadas). "
        "ROC-AUC es contexto.",
        "",
        "## Notas de diseno",
        "",
        "- Features reutilizadas de la 2a (`spc.features.temporales`), leak-safe: "
        "`sales` actual, `family_sales_p75` y `demanda_alta` **no** son features.",
        "- Umbral P75 fijado **solo en TRAIN** (no mira el futuro).",
        "- SMOTE **solo en train, dentro de cada fold** (nunca valid/test ni el "
        "dataset completo).",
        "- Booster entrena en GPU, **predice en CPU** (artefacto portable). La "
        "recalibracion reproduce las probabilidades en **CPU determinista** y solo "
        "cambia el umbral del artefacto (el modelo no se reentrena).",
        "",
        "## Mejoras diferidas (documentadas, no implementadas)",
        "",
        "- **Calibracion de probabilidades** (Platt/isotonica) si la probabilidad se "
        "usa para decisiones de stock por nivel de servicio.",
        "- **Etiqueta no estacionaria:** `demanda_alta` usa el **P75 historico fijo de "
        "TRAIN**; con ventas crecientes la prevalencia sube en valid/test. Un "
        "**percentil movil** (P75 por ventana reciente) definiria 'demanda alta' "
        "relativa al regimen actual. Es una decision de **diseno de etiqueta** "
        "diferida (cambia el objetivo, no solo el umbral); se documenta y no se aplica "
        "aqui.",
        "- **Metodos especificos de demanda intermitente** para las familias de bajo "
        "volumen (las degeneradas excluidas y las de P75 entero bajo).",
        "",
    ]
    ruta = settings.base_dir / "docs" / "reporte_clasificacion_2b.md"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text("\n".join(lineas), encoding="utf-8")
    return ruta


def recalibrar(
    settings: Settings, *, max_train_rows: int | None, usar_gpu: bool = False
) -> ResultadoRecalibracion:
    """Flujo offline de recalibracion: carga datos, re-elige el umbral post-hoc y
    actualiza artefacto+meta, curva PR, registro y reporte. CPU por defecto
    (determinista). **No** reentrena el booster de produccion."""
    from spc.data.integration import build_analytic_dataset
    from spc.data.loaders import load_data

    np.random.seed(settings.random_seed)
    data = load_data(settings)
    analytic, _, _ = build_analytic_dataset(data, settings)

    res = recalibrar_umbral(
        analytic, settings, max_train_rows=max_train_rows, usar_gpu=usar_gpu
    )
    ruta_art, _ = aplicar_recalibracion(res, settings)
    ruta_curva = persistir_curva_pr(res, settings)
    ruta_reg = agregar_puntos_a_registro(res, settings)
    _, meta = cargar_artefacto(ruta_art)
    ruta_rep = escribir_reporte_recalibrado(res, meta, settings)
    log.info("Artefacto actualizado: %s (umbral %.4f)", ruta_art, res.umbral)
    log.info("Curva PR: %s", ruta_curva)
    log.info("Registro: %s | Reporte: %s", ruta_reg, ruta_rep)
    return res


def cli_recalibrar(argv: list[str] | None = None) -> None:
    """Recalibracion offline reproducible del umbral de ALMACEN (Fase 2b)."""
    parser = argparse.ArgumentParser(
        description="Recalibra POST-HOC el umbral del clasificador de ALMACEN (Fase 2b)."
    )
    parser.add_argument("--base-dir", type=Path, default=None, help="Raiz del proyecto.")
    parser.add_argument(
        "--max-train-rows", type=int, default=300_000,
        help="Tope de filas para reproducir el modelo en train (default 300000).",
    )
    parser.add_argument("--full", action="store_true", help="Reproducir sin tope (lento).")
    parser.add_argument(
        "--gpu", action="store_true",
        help="Reproducir probabilidades en GPU (por defecto CPU determinista).",
    )
    args = parser.parse_args(argv)

    from spc.utils.logging import configure_logging

    configure_logging(verbose=True)
    settings = Settings(base_dir=args.base_dir) if args.base_dir else Settings()
    max_rows = None if args.full else args.max_train_rows

    res = recalibrar(settings, max_train_rows=max_rows, usar_gpu=args.gpu)

    print("\n" + "=" * 72)
    print("  PUNTOS DE OPERACION (umbral elegido en VALID; TEST informativo)")
    print("=" * 72)
    print(_tabla_puntos_operacion(res).to_string(index=False))
    mv, mt = res.metricas_valid, res.metricas_test
    cm = res.matriz_confusion_test
    n_pos = cm["TP"] + cm["FP"]
    n = cm["TN"] + cm["FP"] + cm["FN"] + cm["TP"]
    print(f"\nNuevo default: umbral {res.umbral:.4f} | {res.criterio_umbral['criterio']}")
    print(
        f"VALID -> precision {mv['Precision']:.4f} recall {mv['Recall']:.4f} "
        f"F1 {mv['F1']:.4f}"
    )
    print(
        f"TEST  -> precision {mt['Precision']:.4f} recall {mt['Recall']:.4f} "
        f"F1 {mt['F1']:.4f} (PR-AUC {mt['PR_AUC']:.4f})"
    )
    print(f"TEST marca {n_pos}/{n} filas ({100 * n_pos / max(1, n):.1f} %) como riesgo.")


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
