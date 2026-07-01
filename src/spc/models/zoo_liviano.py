"""Zoo **liviano de scikit-learn** para el rediseño 3×3 (modelos en el momento).

El docente pidió **modelos ya hechos de scikit-learn que corran rápido** y se entrenen
en el backend al recibir la petición (no boosters pesados con HPO/GPU). Este módulo
provee, reutilizando la maquinaria leak-safe del motor agnóstico:

- ``construir_zoo_liviano`` — subconjunto **solo sklearn** del zoo (Ridge,
  RandomForest, HistGradientBoosting) para la **regresión**. Se enchufa en
  ``spc.models.automl.entrenar_regresion(..., usar_zoo_liviano=True)``.
- ``entrenar_clasificacion_liviana`` — clasificador binario con candidatos sklearn
  (LogisticRegression, RandomForestClassifier), selección por **PR-AUC en VALID** y
  umbral de negocio; métrica honesta en TEST.
- ``entrenar_clustering`` + ``ClusterizadorLiviano`` — **KMeans real** (escalado, k por
  silueta) sobre un perfil por entidad; reemplaza el proxy de terciles de volumen.

Todos los predictores son serializables (joblib): clases top-level, atributos
picklables, predicción en CPU.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

from spc.features.generico import EspecEsquema, columnas_lag_objetivo, construir_features
from spc.models.automl import cortes_adaptativos
from spc.models.regresion import (
    EspecModelo,
    _construir_pipeline_lineal,
    _fijar_categorias,
    _matriz_categorica,
)
from spc.utils.logging import get_logger
from spc.utils.metrics import classification_metrics_min

log = get_logger("models.zoo_liviano")


# ===========================================================================
# REGRESIÓN — zoo liviano (subconjunto solo-sklearn del zoo agnóstico)
# ===========================================================================
def construir_zoo_liviano(
    seed: int, features: list[str], cats: list[str], **_ignore: Any
) -> dict[str, EspecModelo]:
    """Candidatos de regresión **solo sklearn**, rápidos con pocos datos.

    Misma forma que ``spc.models.regresion.construir_zoo`` (para enchufar sin tocar el
    flujo de selección honesta), pero **sin** LightGBM/XGBoost/Tweedie ni GPU:

    - ``Ridge`` (lineal, escala log): baseline robusto e interpretable.
    - ``RandomForest`` (no lineal, escala log): captura interacciones sin tuneo.
    - ``HistGradientBoosting`` (sklearn nativo, escala log): boosting ligero y veloz.
    """
    from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor

    return {
        "Ridge": EspecModelo(
            "Ridge", "lineal",
            lambda: _construir_pipeline_lineal(features, cats),
            espacio="log",
        ),
        "RandomForest": EspecModelo(
            "RandomForest", "numerico",
            lambda: RandomForestRegressor(
                n_estimators=200, max_depth=14, min_samples_leaf=5,
                random_state=seed, n_jobs=-1,
            ),
            espacio="log",
        ),
        "HistGradientBoosting": EspecModelo(
            "HistGradientBoosting", "categorico",
            lambda: HistGradientBoostingRegressor(
                max_iter=300, learning_rate=0.06, max_leaf_nodes=31,
                l2_regularization=1.0, categorical_features="from_dtype",
                random_state=seed,
            ),
            espacio="log",
        ),
    }


# ===========================================================================
# CLASIFICACIÓN — candidatos sklearn (pipelines que aceptan la matriz categórica)
# ===========================================================================
def _pipeline_logistica(features: list[str], cats: list[str], seed: int) -> Any:
    """Regresión logística en pipeline propio (one-hot + escala + class_weight balanced)."""
    from sklearn.compose import ColumnTransformer
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder
    from sklearn.preprocessing import StandardScaler as _SS

    num = [f for f in features if f not in cats]
    pre = ColumnTransformer(
        [
            ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=True), cats),
            ("num", Pipeline([("imp", SimpleImputer(strategy="median")), ("sc", _SS())]), num),
        ],
        remainder="drop",
    )
    return Pipeline(
        [("pre", pre), ("clf", LogisticRegression(max_iter=1000, class_weight="balanced", random_state=seed))]
    )


def _pipeline_bosque(features: list[str], cats: list[str], seed: int) -> Any:
    """Random Forest en pipeline (one-hot de categóricas + imputación de numéricas)."""
    from sklearn.compose import ColumnTransformer
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.impute import SimpleImputer
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder

    num = [f for f in features if f not in cats]
    pre = ColumnTransformer(
        [
            ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), cats),
            ("num", SimpleImputer(strategy="median"), num),
        ],
        remainder="drop",
    )
    return Pipeline(
        [
            ("pre", pre),
            ("clf", RandomForestClassifier(
                n_estimators=200, min_samples_leaf=3, class_weight="balanced_subsample",
                random_state=seed, n_jobs=-1,
            )),
        ]
    )


def _proba1(modelo: Any, X: Any) -> np.ndarray:
    """Probabilidad de la clase positiva (índice 1)."""
    return np.asarray(modelo.predict_proba(X), dtype="float64")[:, 1]


# Recall mínimo pedido al umbral de operación (fallar en detectar el evento es caro).
RECALL_MIN_OPERATIVO = 0.75


def _umbral_operativo(y: np.ndarray, p: np.ndarray, *, recall_min: float = RECALL_MIN_OPERATIVO) -> float:
    """Umbral de operación del **camino 3×3** (ADR-0025 c).

    Reemplaza —SOLO aquí, sin tocar ``spc.models.clasificacion.seleccionar_umbral`` del motor
    viejo/compartido— la elección del punto de corte. Sobre la partición de **VALIDACIÓN**
    (sin mirar TEST → sin fuga), recorre una grilla de umbrales y, como **no detectar el
    evento** (p. ej. un retraso) es costoso, **prioriza el recall**: entre los umbrales con
    ``recall ≥ recall_min`` elige el de **mayor F1**; si ninguno alcanza ese recall, cae al de
    mayor F1 global. Corrige el punto de operación roto (recall≈0) que el selector automático
    elegía sobre datos realistas.
    """
    y = np.asarray(y).astype(int)
    if y.min() == y.max():  # una sola clase en validación → sin criterio
        return 0.5
    mejor_umbral, mejor_clave = 0.5, (-1, -1.0)
    for thr in np.linspace(0.05, 0.95, 19):
        pred = p >= thr
        tp = int(np.sum(pred & (y == 1)))
        fp = int(np.sum(pred & (y == 0)))
        fn = int(np.sum(~pred & (y == 1)))
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        rec = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
        clave = (1 if rec >= recall_min else 0, f1)  # 1º: cumplir recall; 2º: maximizar F1
        if clave > mejor_clave:
            mejor_clave, mejor_umbral = clave, float(thr)
    return mejor_umbral


def entrenar_clasificacion_liviana(
    df: pd.DataFrame, spec: EspecEsquema, *, seed: int = 42
):
    """Entrena el clasificador binario sklearn ganador (selección honesta en VALID).

    ``spec.objetivo`` debe ser una etiqueta 0/1 ya presente en ``df``. Construye features
    leak-safe, parte la historia en train/valid/test temporal, ajusta cada candidato en
    TRAIN, elige por **PR-AUC en VALID**, fija el umbral de negocio y reporta TEST una
    vez; reajusta el ganador sobre toda la historia. Devuelve un
    ``ResultadoAutoMLClasificacion`` (mismo contrato que el motor agnóstico).
    """
    from spc.models.automl import PredictorGenericoClasificacion, ResultadoAutoMLClasificacion

    obj = spec.objetivo
    df_feat, features, cats = construir_features(df, spec)
    cols_lag = columnas_lag_objetivo(features)
    df_model = df_feat.dropna(subset=cols_lag).copy() if cols_lag else df_feat.copy()
    cols_warm = [c for c in features if c.startswith(("tgt_", "feat_", "featkf_"))]
    if cols_warm:
        df_model[cols_warm] = df_model[cols_warm].fillna(0.0)
    if df_model.empty:
        raise ValueError("Sin filas tras el calentamiento; aporta más historia.")

    df_model, categorias = _fijar_categorias(df_model, cats, None)
    y = df_model[obj].to_numpy("int8")
    prevalencia = float(y.mean())

    cortes = cortes_adaptativos(df_model[spec.col_fecha]) if spec.es_temporal else None
    if cortes is not None:
        fechas = pd.to_datetime(df_model[spec.col_fecha])
        m_train = (fechas <= cortes.valid_ini - pd.Timedelta(days=1)).to_numpy()
        m_valid = ((fechas >= cortes.valid_ini) & (fechas <= cortes.valid_fin)).to_numpy()
        m_test = ((fechas >= cortes.test_ini) & (fechas <= cortes.test_fin)).to_numpy()
    else:
        rng = np.random.default_rng(seed)
        idx = rng.permutation(len(df_model))
        n = len(idx)
        z = np.zeros(n, dtype=bool)
        m_train, m_valid, m_test = z.copy(), z.copy(), z.copy()
        m_train[idx[: int(0.8 * n)]] = True
        m_valid[idx[int(0.8 * n): int(0.9 * n)]] = True
        m_test[idx[int(0.9 * n):]] = True

    if m_train.sum() == 0 or y[m_train].sum() == 0:
        m_train = np.ones(len(df_model), dtype=bool)
    if m_valid.sum() == 0:
        m_valid = m_train

    X = _matriz_categorica(df_model, features, cats)
    Xtr, ytr = X.iloc[m_train], y[m_train]
    Xva, yva = X.iloc[m_valid], y[m_valid]

    candidatos = {
        "LogisticReg": _pipeline_logistica(features, cats, seed),
        "RandomForest": _pipeline_bosque(features, cats, seed),
    }

    pr_auc_valid: dict[str, float] = {}
    umbral_valid: dict[str, float] = {}
    una_clase_valid = yva.sum() == 0 or yva.sum() == len(yva)
    for nombre, modelo in candidatos.items():
        modelo.fit(Xtr, ytr)
        pv = _proba1(modelo, Xva)
        if una_clase_valid:
            pr_auc_valid[nombre] = 0.0
            umbral_valid[nombre] = 0.5
        else:
            m = classification_metrics_min(yva, pv)
            pr_auc_valid[nombre] = float(m.get("PR_AUC", 0.0))
            umbral_valid[nombre] = _umbral_operativo(yva, pv)

    ganador = max(pr_auc_valid, key=lambda k: pr_auc_valid[k])
    umbral = umbral_valid[ganador]

    met_test: dict[str, float] = {}
    if m_test.sum() > 0:
        yte = y[m_test]
        if not (yte.sum() == 0 or yte.sum() == len(yte)):
            modelo_sel = candidatos[ganador]  # ya ajustado en TRAIN
            met_test = classification_metrics_min(yte, _proba1(modelo_sel, X.iloc[m_test]), umbral)

    # Artefacto: reajuste del ganador sobre TODA la historia etiquetada.
    if ganador == "LogisticReg":
        modelo_final = _pipeline_logistica(features, cats, seed)
    else:
        modelo_final = _pipeline_bosque(features, cats, seed)
    modelo_final.fit(X, y)

    predictor = PredictorGenericoClasificacion(
        modelo=modelo_final, spec=spec, features=features, cats=cats,
        categorias=categorias, umbral=umbral,
    )
    log.info(
        "Clasificación liviana: ganador=%s PR-AUC_valid=%.3f umbral=%.3f prevalencia=%.3f",
        ganador, pr_auc_valid[ganador], umbral, prevalencia,
    )
    return ResultadoAutoMLClasificacion(
        predictor=predictor, ganador=f"sklearn[{ganador}]", umbral=umbral,
        metricas_test=met_test, prevalencia=prevalencia, n_filas=int(len(df_model)),
        cortes=cortes, df_model=df_model,
    )


# ===========================================================================
# CLUSTERING — KMeans real sobre un perfil por entidad
# ===========================================================================
class ClusterizadorLiviano:
    """Escalado + KMeans entrenado sobre un perfil por entidad, serializable.

    Guarda el ``StandardScaler`` y el ``KMeans`` (dentro de un pipeline conceptual),
    las columnas del perfil, las etiquetas narrativas por segmento (nivel de volumen) y
    la silueta. ``asignar`` toma un perfil nuevo (mismas columnas) y devuelve el segmento
    + su etiqueta. CPU puro y determinista (semilla fija).
    """

    def __init__(
        self,
        clave: str,
        columnas: list[str],
        scaler: StandardScaler,
        kmeans: KMeans,
        k: int,
        silueta: float,
        etiquetas: dict[int, str],
        centroides: dict[int, dict[str, float]],
        n_por_segmento: dict[int, int],
    ) -> None:
        self.clave = clave
        self.columnas = list(columnas)
        self.scaler = scaler
        self.kmeans = kmeans
        self.k = int(k)
        self.silueta = float(silueta)
        self.etiquetas = {int(c): str(v) for c, v in etiquetas.items()}
        self.centroides = centroides
        self.n_por_segmento = {int(c): int(v) for c, v in n_por_segmento.items()}

    def asignar(self, perfil: pd.DataFrame) -> pd.DataFrame:
        """Asigna a cada fila del perfil su ``segmento`` + ``etiqueta`` narrativa.

        ``perfil`` debe traer la entidad en el índice (como lo produce
        ``ConfigDominio.perfil_entidades``) y las mismas columnas del entrenamiento.
        """
        X = self.scaler.transform(perfil[self.columnas].to_numpy(dtype="float64"))
        seg = self.kmeans.predict(X).astype("int64")
        return pd.DataFrame(
            {
                self.clave: perfil.index.to_numpy(),
                "segmento": seg,
                "etiqueta": [self.etiquetas.get(int(s), f"segmento {s}") for s in seg],
            }
        )


@dataclass
class ResultadoClustering:
    clusterizador: ClusterizadorLiviano
    k: int
    silueta: float
    n_entidades: int
    curva_silueta: dict[int, float]
    asignacion: pd.DataFrame


def _etiquetas_por_volumen(
    perfil: pd.DataFrame, columnas: list[str], labels: np.ndarray, columna_volumen: str
) -> tuple[dict[int, str], dict[int, dict[str, float]]]:
    """Etiqueta cada segmento por su nivel de ``columna_volumen`` (bajo/medio/alto)."""
    medias = perfil.assign(_seg=labels).groupby("_seg")[columnas].mean()
    orden = medias[columna_volumen].sort_values().index.tolist()  # bajo → alto
    k = len(orden)
    if k <= 2:
        nivel = {orden[0]: "bajo", orden[-1]: "alto"}
    elif k == 3:
        nivel = {orden[0]: "bajo", orden[1]: "medio", orden[2]: "alto"}
    else:
        nivel = {seg: f"nivel {i + 1}/{k}" for i, seg in enumerate(orden)}
    etiquetas = {int(s): f"volumen {nivel[s]}" for s in medias.index}
    centroides = {
        int(s): {c: round(float(medias.loc[s, c]), 4) for c in columnas} for s in medias.index
    }
    return etiquetas, centroides


def entrenar_clustering(
    perfil: pd.DataFrame,
    clave: str,
    columnas: list[str],
    columna_volumen: str,
    *,
    seed: int = 42,
    k_min: int = 2,
    k_max: int = 6,
    k_fijo: int | None = None,
) -> ResultadoClustering:
    """Entrena KMeans sobre el ``perfil`` (índice = entidad).

    Escala obligatoria (StandardScaler dentro del artefacto). Siempre calcula la **curva de
    silueta** en ``[k_min, min(k_max, n-1)]`` (para transparencia). La elección de k:

    - ``k_fijo=None`` (por defecto): elige el k de **mayor silueta** (automático). Es lo que
      usa COMPRAS, donde el nº de grupos debe **emerger** de datos realistas.
    - ``k_fijo=<int>``: usa ese k aunque no maximice la silueta. Lo usa ALMACÉN con k=3, por
      la interpretación de negocio **A/B/C**; la silueta se sigue reportando con honestidad.

    Requiere ≥ 3 entidades (si no, lanza: el motor cae a una segmentación por volumen).
    """
    n = len(perfil)
    if n < 3:
        raise ValueError(f"Clustering necesita ≥3 entidades; hay {n}.")
    X_raw = perfil[columnas].to_numpy(dtype="float64")
    scaler = StandardScaler().fit(X_raw)
    Xs = scaler.transform(X_raw)

    k_top = min(k_max, n - 1)
    curva: dict[int, float] = {}
    mejor_k, mejor_sil = 2, -1.0
    for k in range(k_min, k_top + 1):
        km = KMeans(n_clusters=k, init="k-means++", n_init=10, random_state=seed)
        labels = km.fit_predict(Xs)
        if len(set(labels)) < 2:
            continue
        sil = float(silhouette_score(Xs, labels))
        curva[k] = round(sil, 4)
        if sil > mejor_sil:
            mejor_k, mejor_sil = k, sil

    # k fijo por interpretación de negocio (p. ej. A/B/C): respeta la elección aunque la
    # silueta prefiera otro k. Solo se aplica si cabe (2 ≤ k ≤ entidades-1).
    if k_fijo is not None:
        k_obj = int(k_fijo)
        if 2 <= k_obj <= k_top:
            mejor_k = k_obj
            mejor_sil = curva.get(k_obj, mejor_sil)
        else:
            log.warning("k_fijo=%d fuera de rango [2,%d]; se mantiene k automático=%d.", k_obj, k_top, mejor_k)

    kmeans = KMeans(n_clusters=mejor_k, init="k-means++", n_init=10, random_state=seed).fit(Xs)
    labels = kmeans.labels_
    etiquetas, centroides = _etiquetas_por_volumen(perfil, columnas, labels, columna_volumen)
    valores, conteos = np.unique(labels, return_counts=True)
    n_por_seg: dict[int, int] = {int(v): int(c) for v, c in zip(valores, conteos, strict=True)}

    clusterizador = ClusterizadorLiviano(
        clave=clave, columnas=columnas, scaler=scaler, kmeans=kmeans,
        k=mejor_k, silueta=mejor_sil, etiquetas=etiquetas, centroides=centroides,
        n_por_segmento=n_por_seg,
    )
    asignacion = pd.DataFrame(
        {
            clave: perfil.index.to_numpy(),
            "segmento": labels.astype("int64"),
            "etiqueta": [etiquetas[int(s)] for s in labels],
        }
    )
    log.info("Clustering liviano [%s]: k=%d silueta=%.4f (%d entidades)", clave, mejor_k, mejor_sil, n)
    return ResultadoClustering(
        clusterizador=clusterizador, k=mejor_k, silueta=mejor_sil, n_entidades=n,
        curva_silueta=curva, asignacion=asignacion,
    )
