"""AutoML **agnóstico al rubro**: entrena el algoritmo ganador sobre un esquema declarado.

Reutiliza el **mismo zoo de modelos** y la **misma selección honesta** del motor retail
(`spc.models.regresion` / `spc.models.clasificacion`) pero alimentado por el feature
engineering genérico (`spc.features.generico`), de modo que el cliente puede traer
**columnas arbitrarias** (otro rubro) y el sistema:

1. construye features leak-safe del esquema declarado;
2. parte la historia en train/valid/test **temporal sin fuga**;
3. entrena el zoo, **elige el ganador en VALID** (y opcionalmente combina los mejores
   boosters en un ensemble), reporta la métrica honesta en TEST (WAPE recursivo);
4. reajusta el ganador sobre toda la historia y devuelve un **predictor serializable**
   que pronostica de forma recursiva multi-horizonte (regresión) o clase+probabilidad
   (clasificación).

No conoce HTTP ni el negocio: la capa de servicio (`spc.service.agnostico`) lo orquesta.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from spc.features.generico import (
    EspecEsquema,
    columnas_lag_objetivo,
    construir_features,
)
from spc.models.regresion import (
    CortesTemporales,
    ModeloEnsemble,
    _a_unidades,
    _entrenar_modelo,
    _fijar_categorias,
    _matriz_categorica,
    _matriz_numerica,
    _mejores_pesos,
    construir_zoo,
)
from spc.utils.logging import get_logger
from spc.utils.metrics import regression_metrics

log = get_logger("models.automl")

# Cuántos boosters (mejores en VALID) entran como máximo en el ensemble.
ENSEMBLE_TOP_K = 3


# ===========================================================================
# Cortes temporales adaptativos a la historia disponible
# ===========================================================================
def cortes_adaptativos(
    fechas: pd.Series, *, valid_frac: float = 0.15, min_w: int = 7, max_w: int = 16
) -> CortesTemporales:
    """Cortes train/valid/test con ventana proporcional a la historia útil.

    Cada holdout (valid y test) dura ``round(dias * valid_frac)`` recortado a
    ``[min_w, max_w]``. Con poca historia las ventanas son cortas pero honestas; con
    mucha llegan al máximo (= la ventana del motor congelado, 16d).
    """
    fechas = pd.to_datetime(fechas)
    fmax = pd.Timestamp(fechas.max())
    fmin = pd.Timestamp(fechas.min())
    dias = max(1, (fmax - fmin).days + 1)
    w = int(max(min_w, min(max_w, round(dias * valid_frac))))
    test_ini = fmax - pd.Timedelta(days=w - 1)
    valid_fin = test_ini - pd.Timedelta(days=1)
    valid_ini = valid_fin - pd.Timedelta(days=w - 1)
    train_fin = valid_ini - pd.Timedelta(days=1)
    return CortesTemporales(train_fin, valid_ini, valid_fin, test_ini, fmax)


# ===========================================================================
# Predictor serializable de REGRESIÓN agnóstica
# ===========================================================================
class PredictorGenericoRegresion:
    """Features genéricas + modelo entrenado, serializable (joblib, clase top-level).

    Pronostica en **unidades del objetivo** (``>= 0``). El pronóstico recursivo
    multi-horizonte reinyecta cada día pronosticado para alimentar los rezagos del
    siguiente (forecast honesto), igual que el motor retail pero sobre el esquema
    **declarado** por el cliente.
    """

    def __init__(
        self,
        modelo: Any,
        spec: EspecEsquema,
        features: list[str],
        cats: list[str],
        categorias: dict[str, Any],
        tipo: str,
        nombre_modelo: str,
        espacio: str,
        techo_log: float | None,
        techo_unidades: float | None,
    ) -> None:
        self.modelo = modelo
        self.spec = spec
        self.features = features
        self.cats = cats
        self.categorias = categorias
        self.tipo = tipo
        self.nombre_modelo = nombre_modelo
        self.espacio = espacio
        self.techo_log = techo_log
        self.techo_unidades = techo_unidades
        self.transformacion = "log1p" if espacio == "log" else "identidad"

    def _matriz(self, df_feat: pd.DataFrame) -> Any:
        df_cat, _ = _fijar_categorias(df_feat, self.cats, self.categorias)
        if self.tipo == "numerico":
            return _matriz_numerica(df_cat, self.features, self.cats)
        return _matriz_categorica(df_cat, self.features, self.cats)

    def _a_unidades(self, crudo: np.ndarray) -> np.ndarray:
        return _a_unidades(crudo, self.espacio, self.techo_log, self.techo_unidades)

    def predecir(self, df: pd.DataFrame) -> pd.Series:
        """Predicción por fila (teacher-forcing: asume rezagos reales conocidos)."""
        df_feat, _, _ = construir_features(df, self.spec)
        X = self._matriz(df_feat)
        unidades = self._a_unidades(self.modelo.predict(X))
        return pd.Series(unidades, index=df_feat.index, name="prediccion")

    def pronosticar_horizonte(
        self, df_completo: pd.DataFrame, inicio: Any, fin: Any
    ) -> pd.DataFrame:
        """Pronóstico **recursivo** día a día sobre ``[inicio, fin]`` (forecast honesto).

        ``df_completo`` trae la historia + las filas del horizonte ya presentes (con el
        calendario y las features conocidas-a-futuro fijadas); el objetivo de esas filas
        se ignora y se sobreescribe. Devuelve ``(cols_serie, col_fecha, prediccion)``.
        """
        spec = self.spec
        obj, fecha = spec.objetivo, spec.col_fecha
        serie = list(spec.cols_serie)
        orden = serie + [fecha]
        inicio, fin = pd.Timestamp(inicio), pd.Timestamp(fin)

        df = df_completo.sort_values(orden).reset_index(drop=True).copy()
        df[obj] = df[obj].astype("float64")
        mask_h = (pd.to_datetime(df[fecha]) >= inicio) & (pd.to_datetime(df[fecha]) <= fin)
        df.loc[mask_h, obj] = np.nan

        resultados: list[pd.DataFrame] = []
        for dia in pd.date_range(inicio, fin, freq="D"):
            df_feat, _, _ = construir_features(df, spec)
            fila = df_feat[pd.to_datetime(df_feat[fecha]) == dia]
            if fila.empty:
                continue
            unidades = self._a_unidades(self.modelo.predict(self._matriz(fila)))
            out = fila[serie].copy() if serie else pd.DataFrame(index=fila.index)
            out[fecha] = dia
            out["prediccion"] = unidades
            resultados.append(out)

            m = (pd.to_datetime(df[fecha]) == dia).to_numpy()
            if serie:
                pred_map = {
                    tuple(k): v
                    for k, v in zip(out[serie].itertuples(index=False, name=None), unidades, strict=False)
                }
                claves = df.loc[m, serie].itertuples(index=False, name=None)
                df.loc[m, obj] = np.array(
                    [pred_map.get(tuple(k), 0.0) for k in claves], dtype="float64"
                )
            else:
                df.loc[m, obj] = float(unidades[0]) if len(unidades) else 0.0

        cols = (serie + [fecha, "prediccion"])
        if not resultados:
            return pd.DataFrame(columns=cols)
        return pd.concat(resultados, ignore_index=True)[cols]


# ===========================================================================
# Entrenamiento + selección honesta (REGRESIÓN)
# ===========================================================================
@dataclass
class ResultadoAutoMLRegresion:
    predictor: PredictorGenericoRegresion
    ganador: str
    metricas_test: dict[str, float]
    metricas_baseline: dict[str, float]
    cortes: CortesTemporales
    n_filas: int
    candidatos: dict[str, float] = field(default_factory=dict)


def _matriz_por_tipo(
    df: pd.DataFrame, features: list[str], cats: list[str], tipo: str
) -> Any:
    if tipo == "numerico":
        return _matriz_numerica(df, features, cats)
    return _matriz_categorica(df, features, cats)


def entrenar_regresion(
    df: pd.DataFrame,
    spec: EspecEsquema,
    *,
    seed: int = 42,
    usar_gpu: bool = False,
    ensemble: bool = True,
) -> ResultadoAutoMLRegresion:
    """Entrena el zoo sobre el esquema declarado, elige el ganador en VALID y reajusta.

    Selección honesta: cada modelo se ajusta en TRAIN y se evalúa en VALID (MAE en
    unidades); gana el de menor MAE. Si ``ensemble`` y hay ≥2 boosters, se combinan los
    mejores con pesos convexos. La métrica de cierre (TEST) se calcula con **pronóstico
    recursivo** (honesto). El predictor final se reajusta sobre TODA la historia.
    """
    obj = spec.objetivo
    df_feat, features, cats = construir_features(df, spec)

    # Descarta el calentamiento (NaN en los rezagos del objetivo) si es temporal.
    cols_lag = columnas_lag_objetivo(features)
    df_model = df_feat.dropna(subset=cols_lag).copy() if cols_lag else df_feat.copy()
    if df_model.empty:
        raise ValueError(
            "Tras descartar el calentamiento no quedan filas para entrenar. "
            "Aporta más historia por serie."
        )

    # Rellena el resto de NaN de rezago con 0 (sin señal), igual que el motor retail.
    cols_warm = [c for c in features if c.startswith(("tgt_", "feat_", "featkf_"))]
    df_model[cols_warm] = df_model[cols_warm].fillna(0.0)

    df_model, categorias = _fijar_categorias(df_model, cats, None)
    cortes = cortes_adaptativos(df_model[spec.col_fecha]) if spec.es_temporal else None

    fechas = pd.to_datetime(df_model[spec.col_fecha]) if spec.es_temporal else None
    if cortes is not None:
        m_train = (fechas <= cortes.train_fin).to_numpy()
        m_valid = ((fechas >= cortes.valid_ini) & (fechas <= cortes.valid_fin)).to_numpy()
        m_test = ((fechas >= cortes.test_ini) & (fechas <= cortes.test_fin)).to_numpy()
    else:
        # Tabular: holdout aleatorio reproducible (80/10/10).
        rng = np.random.default_rng(seed)
        idx = rng.permutation(len(df_model))
        n = len(idx)
        m = np.zeros(n, dtype=bool)
        m_train, m_valid, m_test = m.copy(), m.copy(), m.copy()
        m_train[idx[: int(0.8 * n)]] = True
        m_valid[idx[int(0.8 * n) : int(0.9 * n)]] = True
        m_test[idx[int(0.9 * n) :]] = True

    if m_train.sum() == 0:
        m_train = np.ones(len(df_model), dtype=bool)
    if m_valid.sum() == 0:
        m_valid = m_train

    y_units = df_model[obj].to_numpy("float64")
    y_log = np.log1p(np.clip(y_units, 0.0, None))
    techo_unidades = float(np.quantile(y_units[m_train], 0.999)) * 2.0 if m_train.any() else None
    techo_log = float(np.log1p(techo_unidades)) if techo_unidades else None

    zoo = construir_zoo(seed, features, cats, usar_gpu=usar_gpu)
    X_cat = _matriz_categorica(df_model, features, cats)
    X_num = _matriz_numerica(df_model, features, cats)

    def _X(tipo: str, mask: np.ndarray) -> Any:
        return X_num[mask] if tipo == "numerico" else X_cat.iloc[mask]

    # --- Ajuste en TRAIN, evaluación en VALID (MAE en unidades) ---
    pred_valid: dict[str, np.ndarray] = {}
    mae_valid: dict[str, float] = {}
    modelos_train: dict[str, Any] = {}
    for nombre, spec_m in zoo.items():
        y_fit = y_log if spec_m.espacio == "log" else y_units
        modelo = _entrenar_modelo(spec_m, _X(spec_m.tipo, m_train), y_fit[m_train])
        u = _a_unidades(modelo.predict(_X(spec_m.tipo, m_valid)), spec_m.espacio, techo_log, techo_unidades)
        pred_valid[nombre] = u
        mae_valid[nombre] = float(np.mean(np.abs(y_units[m_valid] - u)))
        modelos_train[nombre] = modelo

    ganador = min(mae_valid, key=lambda k: mae_valid[k])
    log.info("AutoML regresión: ganador=%s (MAE_valid=%.3f)", ganador, mae_valid[ganador])

    # --- Ensemble de los mejores boosters (si procede) ---
    usar_ens = False
    elegidos: list[str] = []
    pesos = np.array([1.0])
    if ensemble:
        boosters = [n for n, s in zoo.items() if s.tipo == "categorico"]
        boosters = sorted(boosters, key=lambda n: mae_valid[n])[:ENSEMBLE_TOP_K]
        if len(boosters) >= 2:
            M = np.column_stack([pred_valid[n] for n in boosters])
            pesos = _mejores_pesos(M, y_units[m_valid])
            mae_ens = float(np.mean(np.abs(y_units[m_valid] - M @ pesos)))
            if mae_ens <= mae_valid[ganador]:
                usar_ens, elegidos = True, boosters
                log.info("AutoML regresión: ensemble %s (MAE_valid=%.3f)", elegidos, mae_ens)

    # --- Constructor del predictor (ganador o ensemble) ajustado sobre un subconjunto ---
    def _construir_predictor(mask: np.ndarray) -> PredictorGenericoRegresion:
        if usar_ens:
            modelos, espacios = [], []
            for nombre in elegidos:
                s = zoo[nombre]
                y_fit = y_log if s.espacio == "log" else y_units
                modelos.append(_entrenar_modelo(s, _X(s.tipo, mask), y_fit[mask]))
                espacios.append(s.espacio)
            modelo_f: Any = ModeloEnsemble(
                modelos, espacios, pesos, techo_log, techo_unidades, nombres=list(elegidos)
            )
            tipo_f, espacio_f, nombre_f = "categorico", "unidades", "Ensemble(" + "+".join(elegidos) + ")"
        else:
            s = zoo[ganador]
            y_fit = y_log if s.espacio == "log" else y_units
            modelo_f = _entrenar_modelo(s, _X(s.tipo, mask), y_fit[mask])
            tipo_f, espacio_f, nombre_f = s.tipo, s.espacio, ganador
        return PredictorGenericoRegresion(
            modelo=modelo_f, spec=spec, features=features, cats=cats,
            categorias=categorias, tipo=tipo_f, nombre_modelo=nombre_f,
            espacio=espacio_f, techo_log=techo_log, techo_unidades=techo_unidades,
        )

    # --- Predictor final (artefacto): reajuste sobre TODA la historia etiquetada ---
    predictor = _construir_predictor(np.ones(len(df_model), dtype=bool))
    nombre_final = predictor.nombre_modelo

    # --- Métrica honesta en TEST (pronóstico recursivo) ---
    # CLAVE anti-fuga: la métrica se calcula con un modelo entrenado SOLO con datos
    # previos a la ventana TEST. Usar el artefacto reajustado sobre TODO (que ya vio
    # TEST) deja que los modelos de alta capacidad memoricen esas filas y reporten una
    # métrica falsamente perfecta (la ruta de clasificación ya entrena solo en train).
    predictor_eval = predictor
    if cortes is not None and fechas is not None:
        m_pre_test = (fechas < pd.Timestamp(cortes.test_ini)).to_numpy()
        if m_pre_test.any():
            predictor_eval = _construir_predictor(m_pre_test)
    metricas_test, metricas_base = _evaluar_test_recursivo(
        predictor_eval, df_model, spec, cortes
    )

    return ResultadoAutoMLRegresion(
        predictor=predictor,
        ganador=nombre_final,
        metricas_test=metricas_test,
        metricas_baseline=metricas_base,
        cortes=cortes if cortes is not None else cortes_adaptativos(pd.Series([pd.Timestamp.today()])),
        n_filas=int(len(df_model)),
        candidatos={k: round(v, 3) for k, v in sorted(mae_valid.items(), key=lambda kv: kv[1])},
    )


def _evaluar_test_recursivo(
    predictor: PredictorGenericoRegresion,
    df_model: pd.DataFrame,
    spec: EspecEsquema,
    cortes: CortesTemporales | None,
) -> tuple[dict[str, float], dict[str, float]]:
    """WAPE/MAE honestos sobre la ventana TEST con pronóstico recursivo, y baseline."""
    if cortes is None or not spec.es_temporal:
        return {}, {}
    obj, fecha = spec.objetivo, spec.col_fecha
    serie = list(spec.cols_serie)
    inicio, fin = pd.Timestamp(cortes.test_ini), pd.Timestamp(cortes.test_fin)
    fechas = pd.to_datetime(df_model[fecha])
    if (fechas >= inicio).sum() == 0:
        return {}, {}

    reales = df_model[(fechas >= inicio) & (fechas <= fin)][serie + [fecha, obj]].copy()
    try:
        pred = predictor.pronosticar_horizonte(df_model.copy(), inicio, fin)
    except Exception as exc:  # noqa: BLE001 - no romper el entrenamiento por la métrica
        log.warning("No se pudo evaluar TEST recursivo: %s", exc)
        return {}, {}
    if pred.empty:
        return {}, {}
    reales[fecha] = pd.to_datetime(reales[fecha])
    pred[fecha] = pd.to_datetime(pred[fecha])
    merged = reales.merge(pred, on=serie + [fecha], how="inner") if serie else reales.merge(pred, on=[fecha])
    if merged.empty:
        return {}, {}
    y_true = merged[obj].to_numpy("float64")
    y_pred = merged["prediccion"].to_numpy("float64")
    return regression_metrics(y_true, y_pred), {}


# ===========================================================================
# Predictor serializable de CLASIFICACIÓN agnóstica
# ===========================================================================
class PredictorGenericoClasificacion:
    """Features genéricas + clasificador binario + umbral, serializable.

    El objetivo es una etiqueta 0/1 (``demanda_alta`` u otra que el cliente declare /
    se derive). Devuelve clase y probabilidad por fila.
    """

    def __init__(
        self,
        modelo: Any,
        spec: EspecEsquema,
        features: list[str],
        cats: list[str],
        categorias: dict[str, Any],
        umbral: float,
    ) -> None:
        self.modelo = modelo
        self.spec = spec
        self.features = features
        self.cats = cats
        self.categorias = categorias
        self.umbral = float(umbral)

    def _matriz(self, df_feat: pd.DataFrame) -> pd.DataFrame:
        df_cat, _ = _fijar_categorias(df_feat, self.cats, self.categorias)
        return _matriz_categorica(df_cat, self.features, self.cats)

    def predecir_proba(self, df: pd.DataFrame) -> pd.Series:
        df_feat, _, _ = construir_features(df, self.spec)
        X = self._matriz(df_feat)
        prob = np.asarray(self.modelo.predict_proba(X), dtype="float64")[:, 1]
        return pd.Series(prob, index=df_feat.index, name="probabilidad")

    def predecir(self, df: pd.DataFrame, umbral: float | None = None) -> pd.DataFrame:
        u = self.umbral if umbral is None else float(umbral)
        prob = self.predecir_proba(df)
        clase = (prob.to_numpy() >= u).astype("int8")
        return pd.DataFrame(
            {"clase": clase, "probabilidad": prob.to_numpy()}, index=prob.index
        )


@dataclass
class ResultadoAutoMLClasificacion:
    predictor: PredictorGenericoClasificacion
    ganador: str
    umbral: float
    metricas_test: dict[str, float]
    prevalencia: float
    n_filas: int


def entrenar_clasificacion(
    df: pd.DataFrame,
    spec: EspecEsquema,
    *,
    seed: int = 42,
    usar_gpu: bool = False,
) -> ResultadoAutoMLClasificacion:
    """Entrena el clasificador ganador (LightGBM, estrategia de desbalance elegida en VALID).

    ``spec.objetivo`` debe ser una etiqueta binaria (0/1) ya presente en ``df``. Reutiliza
    las estrategias de desbalance y la selección de umbral del motor retail
    (`spc.models.clasificacion`), pero sobre features genéricas.
    """
    from spc.models.clasificacion import (
        ESTRATEGIAS,
        _elegir_estrategia,
        _proba,
        construir_estrategia,
        seleccionar_umbral,
    )
    from spc.utils.metrics import classification_metrics_min

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
        m_valid[idx[int(0.8 * n) : int(0.9 * n)]] = True
        m_test[idx[int(0.9 * n) :]] = True

    if m_train.sum() == 0 or y[m_train].sum() == 0:
        m_train = np.ones(len(df_model), dtype=bool)
    if m_valid.sum() == 0:
        m_valid = m_train

    X_cat = _matriz_categorica(df_model, features, cats)
    Xtr, ytr = X_cat.iloc[m_train], y[m_train]
    Xva, yva = X_cat.iloc[m_valid], y[m_valid]
    n_pos = int(ytr.sum())
    spw = ((len(ytr) - n_pos) / n_pos) if n_pos else 1.0

    metricas_valid: dict[str, dict[str, float]] = {}
    proba_valid: dict[str, np.ndarray] = {}
    umbrales: dict[str, float] = {}
    for nombre in ESTRATEGIAS:
        if nombre == "smote" and n_pos < 6:
            continue
        modelo = construir_estrategia(nombre, seed, usar_gpu=usar_gpu, scale_pos_weight=spw)
        modelo.fit(Xtr, ytr)
        pv = _proba(modelo, Xva)
        proba_valid[nombre] = pv
        u, _ = seleccionar_umbral(yva, pv)
        umbrales[nombre] = u
        metricas_valid[nombre] = classification_metrics_min(yva, pv, u)

    estrategia, _ = _elegir_estrategia(metricas_valid)
    umbral = umbrales[estrategia]

    # Métrica honesta en TEST (estrategia y umbral ya elegidos en VALID).
    met_test: dict[str, float] = {}
    if m_test.sum() > 0:
        modelo_sel = construir_estrategia(estrategia, seed, usar_gpu=usar_gpu, scale_pos_weight=spw)
        modelo_sel.fit(Xtr, ytr)
        met_test = classification_metrics_min(y[m_test], _proba(modelo_sel, X_cat.iloc[m_test]), umbral)

    # Artefacto: reajuste de la estrategia elegida sobre TODA la historia.
    modelo_final = construir_estrategia(estrategia, seed, usar_gpu=usar_gpu, scale_pos_weight=spw)
    modelo_final.fit(X_cat, y)
    predictor = PredictorGenericoClasificacion(
        modelo=modelo_final, spec=spec, features=features, cats=cats,
        categorias=categorias, umbral=umbral,
    )
    log.info("AutoML clasificación: estrategia=%s umbral=%.3f prevalencia=%.3f", estrategia, umbral, prevalencia)
    return ResultadoAutoMLClasificacion(
        predictor=predictor, ganador=f"LightGBM[{estrategia}]", umbral=umbral,
        metricas_test=met_test, prevalencia=prevalencia, n_filas=int(len(df_model)),
    )
