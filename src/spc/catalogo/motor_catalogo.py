"""Motor genérico de ejecución de consultas del catálogo.

Toma una ConfigConsulta y un DataFrame, entrena candidatos, elige ganador por métrica
y devuelve predicciones REALES + tabla de comparación (sin fuga de datos, anti-leak-safe).

Tipos soportados:
- regresión (WAPE): predice un número; emite valor predicho + valor real por fila.
- clasificación binaria (PR-AUC): alerta sí/no con probabilidad por fila.
- clasificación multiclase (F1 macro): predice una categoría (p. ej. canal) por fila.
- clustering (silueta): agrupa entidades; emite coordenadas 2D reales (PCA) por entidad.

Anti-fuga: excluye columnas derivadas, calcula umbrales solo en TRAIN, selecciona el
ganador en VALID y reporta al usuario la métrica de TEST (evaluada una sola vez).
Robustez: si una etiqueta queda de una sola clase, degrada con aviso en vez de reventar.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import (
    ExtraTreesRegressor,
    HistGradientBoostingClassifier,
    HistGradientBoostingRegressor,
    RandomForestClassifier,
    RandomForestRegressor,
)
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.dummy import DummyClassifier, DummyRegressor
from sklearn.cluster import AgglomerativeClustering, KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import average_precision_score, silhouette_score, f1_score
from sklearn.preprocessing import StandardScaler

from spc.catalogo.config import (
    ConfigConsulta,
    UmbralesCalidad,
    obtener_horizonte_tendencia,
    obtener_magnitudes,
    obtener_umbrales,
    obtener_unidades,
)
from spc.utils.logging import get_logger

log = get_logger("catalogo.motor_catalogo")

# Máximo de filas de predicción devueltas por consulta (evita payloads enormes).
MAX_PREDICCIONES = 500


# ==============================================================================
# Estructuras de Resultado
# ==============================================================================

@dataclass
class FilaComparacion:
    modelo: str
    metrica: str
    valor: float
    ganador: bool = False


@dataclass
class _Entrenamiento:
    """Salida interna de cada entrenador (regresión/clasificación/clustering)."""

    tabla: list[FilaComparacion]
    predicciones: list[dict[str, Any]]
    ganador: str
    valor_metrica: float
    advertencia: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)
    resumen: dict[str, Any] | None = None  # A2: recuadro resumen sobre TODO el test (no truncado a 500)


@dataclass
class Tendencia:
    """Serie temporal agregada (histórico + pronóstico referencial). Datos planos JSON-safe."""

    unidad: str
    metodo: str
    horizonte: int = 14
    historico: list[dict[str, Any]] = field(default_factory=list)
    pronostico: list[dict[str, Any]] = field(default_factory=list)
    resumen: dict[str, Any] | None = None  # {projection, change_pct, direction}
    desgloses: list[dict[str, Any]] = field(default_factory=list)  # [{label, historico, pronostico}]


@dataclass
class ResultadoConsulta:
    """Resultado de ejecutar una consulta del catálogo."""

    consulta_id: str
    pregunta: str
    tipo: str
    modelo_ganador: str
    metrica_ganador: str
    valor_metrica: float
    predicciones: list[dict[str, Any]]
    tabla_comparacion: list[FilaComparacion] = field(default_factory=list)
    fecha_entrenamiento: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    advertencia: str | None = None
    unidad: str = ""
    nota_tecnica: str | None = None
    calidad: str = "limitada"  # "buena" | "limitada" (según umbrales del catálogo)
    resumen: dict[str, Any] | None = None  # A2: recuadro resumen (suma/promedio según magnitud)
    meta: dict[str, Any] = field(default_factory=dict)


# ==============================================================================
# Utilidades
# ==============================================================================

def _safe(v: Any) -> Any:
    """Convierte escalares de numpy/pandas a tipos JSON-safe (sin NaN/Inf)."""
    if v is None:
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.bool_, bool)):
        return bool(v)
    if isinstance(v, (np.floating, float)):
        f = float(v)
        return None if (math.isnan(f) or math.isinf(f)) else round(f, 4)
    if isinstance(v, (pd.Timestamp,)):
        return str(v.date())
    return v


def _num2(v: Any) -> float:
    try:
        f = float(v)
        return 0.0 if (math.isnan(f) or math.isinf(f)) else round(f, 2)
    except Exception:
        return 0.0


def _nombre_etiqueta(config: ConfigConsulta) -> str:
    der = config.derivacion_etiqueta
    if der is not None and der.descripcion and "=" in der.descripcion:
        return der.descripcion.split("=")[0].strip()
    return f"{config.objetivo or 'objetivo'}_clase"


def _unidad(config: ConfigConsulta) -> str:
    if config.tipo == "regresion":
        return obtener_unidades().get(config.objetivo, "")
    return ""


def _nota_tecnica(config: ConfigConsulta) -> str | None:
    """Nota honesta para el detalle técnico (por qué la métrica puede salir muy alta)."""
    der = config.derivacion_etiqueta
    if config.tipo == "clasificacion" and der is not None:
        if der.tipo == "regla":
            return (
                "La etiqueta se define con una regla determinística "
                f"({der.formula}). Las columnas que intervienen en esa regla están excluidas "
                "de las entradas; el modelo estima la alerta desde otros factores, no la recalcula."
            )
        if der.tipo == "umbral":
            return (
                f"La etiqueta usa un umbral fijo de negocio "
                f"({der.columna_objetivo} ≥ {der.umbral_valor}); la columna del umbral está "
                "excluida de las entradas."
            )
        if der.tipo == "percentil":
            grupo = f" por {der.agrupar_por}" if der.agrupar_por else " global"
            return (
                f"La etiqueta se deriva de un umbral de datos (P{der.percentil} de "
                f"{der.columna_objetivo}{grupo}, fijado solo en TRAIN). Las columnas que la "
                "definen están excluidas de las features."
            )
    return None


def _nota_metrica_casi_perfecta(
    config: ConfigConsulta, valor_metrica: float, umbral: float
) -> str | None:
    """Aviso honesto cuando una clasificación derivada sale casi perfecta (no es fuga)."""
    if (
        config.tipo == "clasificacion"
        and config.derivacion_etiqueta is not None
        and valor_metrica >= umbral
    ):
        return (
            f"La métrica es muy alta ({valor_metrica:.0%}): con estos datos los factores "
            "disponibles ya casi determinan la etiqueta. Conviene leerla con cautela (una cifra "
            "cercana al 100% suele indicar un problema fácil, no necesariamente un mejor modelo)."
        )
    return None


def _calidad(tipo: str, metrica: str, valor: float, u: UmbralesCalidad) -> str:
    """Etiqueta de calidad honesta ('buena' | 'limitada') según los umbrales del catálogo."""
    if tipo == "regresion":
        return "buena" if valor <= u.wape_buena else "limitada"
    if tipo == "clasificacion":
        if metrica == "f1_macro":
            return "buena" if valor >= u.f1_buena else "limitada"
        return "buena" if valor >= u.pr_auc_buena else "limitada"
    if tipo == "clustering":
        return "buena" if valor >= u.silhouette_buena else "limitada"
    return "limitada"


def _resumen_regresion(config: ConfigConsulta, valores: Any) -> dict[str, Any] | None:
    """Recuadro resumen A2: SUMA para magnitudes extensivas, PROMEDIO para intensivas.

    `valores` es el conjunto de valores predichos de TODO el tramo de TEST (no la lista
    truncada a MAX_PREDICCIONES que se muestra en la tabla): así el "Total estimado" refleja
    el periodo completo y no depende del tope de visualización.

    El tipo de magnitud se lee del catálogo (no se hard-codea). Extensiva = flujo acumulable
    (unidades, S/); intensiva = tasa/nivel/ratio (%, días, rotación, cobertura…), que no tiene
    sentido sumar.
    """
    vals: list[float] = []
    for v in valores:
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        if not (math.isnan(f) or math.isinf(f)):
            vals.append(f)
    if not vals:
        return None
    magnitud = obtener_magnitudes().get(config.objetivo, "extensiva")
    if magnitud == "intensiva":
        agg, valor, label = "mean", float(np.mean(vals)), "Promedio estimado"
    else:
        agg, valor, label = "sum", float(np.sum(vals)), "Total estimado"
    return {
        "aggregation": agg,
        "value": _num2(valor),
        "label": label,
        "unit": _unidad(config),
        "magnitude": magnitud,
    }


def _nota_objetivo_facil(config: ConfigConsulta, df: pd.DataFrame, u: UmbralesCalidad) -> str | None:
    """A4: nota honesta cuando el objetivo de regresión es casi constante (métrica fácil)."""
    if config.tipo != "regresion" or not config.objetivo or config.objetivo not in df.columns:
        return None
    y = pd.to_numeric(df[config.objetivo], errors="coerce").dropna()
    if len(y) < 5:
        return None
    media = float(abs(y.mean()))
    cv = float(y.std() / media) if media > 1e-9 else 0.0
    if cv < u.cv_objetivo_facil:
        return (
            f"Métrica fácil: el objetivo es casi constante (varía muy poco, ~{cv:.0%} relativo), "
            "así que predecir siempre su valor típico ya da poco error. La métrica luce buena sin "
            "aportar mucho: conviene leerla con cautela."
        )
    return None


def _aviso_degenerado(predicciones: list[dict[str, Any]]) -> str | None:
    """A5: aviso cuando la clasificación predice una sola clase para TODOS los casos."""
    if not predicciones:
        return None
    clave = "clase_predicha" if "predicted_class" not in predicciones[0] and "clase_predicha" in predicciones[0] else (
        "predicted_class" if "predicted_class" in predicciones[0] else "class"
    )
    valores = {p.get(clave) for p in predicciones}
    if len(valores) <= 1:
        unico = next(iter(valores), None)
        if clave in ("class",):
            estado = "se enciende (todos en alerta)" if unico == 1 else "no se enciende (nadie en alerta)"
        else:
            estado = f"predice siempre la misma categoría ({unico})"
        return (
            f"Alerta poco informativa: {estado} para todos los casos de prueba; el modelo no "
            "discrimina con estos datos."
        )
    return None


def _dims_categoricas(df: pd.DataFrame, config: ConfigConsulta) -> list[str]:
    cats = [
        c
        for c in config.columnas_entrada
        if c in df.columns and (df[c].dtype == object or str(df[c].dtype).startswith("category"))
    ]
    if not cats and "categoria" in df.columns:
        cats = ["categoria"]
    return cats


def _id_cols(df: pd.DataFrame, config: ConfigConsulta) -> list[str]:
    cols = [c for c in (config.cols_serie or []) if c in df.columns]
    if "categoria" in df.columns and "categoria" not in cols:
        cols.append("categoria")
    return cols


# ==============================================================================
# Validación y Preparación
# ==============================================================================

def validar_dataframe(df: pd.DataFrame, config: ConfigConsulta) -> None:
    """Verifica que el DataFrame tenga las columnas necesarias."""
    cols_requeridas = set(config.columnas_entrada)
    if config.col_fecha:
        cols_requeridas.add(config.col_fecha)

    # Regresión necesita el objetivo; clasificación multiclase también (la etiqueta es real).
    if config.tipo == "regresion" and config.objetivo:
        cols_requeridas.add(config.objetivo)
    if config.tipo == "clasificacion" and config.derivacion_etiqueta is None and config.objetivo:
        cols_requeridas.add(config.objetivo)

    faltan = cols_requeridas - set(df.columns)
    if faltan:
        raise ValueError(
            f"Consulta {config.id}: faltan columnas {sorted(faltan)}. "
            f"Disponibles: {sorted(df.columns)}"
        )


def construir_features(
    df: pd.DataFrame, config: ConfigConsulta, modulo_config: Any
) -> pd.DataFrame:
    """Construye el DataFrame de features (one-hot para categóricas), excluyendo fugas."""
    columnas_excluir = set(modulo_config.columnas_excluir_features.keys())
    columnas_excluir.add(config.objetivo)

    cols_ok = [c for c in config.columnas_entrada if c not in columnas_excluir]
    if not cols_ok:
        raise ValueError(
            f"Consulta {config.id}: tras excluir anti-fuga, no quedan features."
        )

    features = df[cols_ok].copy()
    categorical_cols = features.select_dtypes(include=["object", "string", "category"]).columns
    if len(categorical_cols) > 0:
        features = pd.get_dummies(features, columns=categorical_cols, drop_first=False)
    features = features.astype("float64", errors="ignore")
    return features


def partir_temporal(
    df: pd.DataFrame, col_fecha: str
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Particiona por fecha: 70% train, 15% valid, 15% test (orden cronológico)."""
    if col_fecha not in df.columns:
        raise ValueError(f"Columna de fecha no encontrada: {col_fecha}")
    df_sorted = df.sort_values(col_fecha, kind="stable").reset_index(drop=True)
    n = len(df_sorted)
    return df_sorted.iloc[: int(0.7 * n)], df_sorted.iloc[int(0.7 * n): int(0.85 * n)], df_sorted.iloc[int(0.85 * n):]


def _preparar_temporal(
    df: pd.DataFrame, features_df: pd.DataFrame, col_fecha: str | None
) -> tuple[pd.DataFrame, np.ndarray, int, int]:
    """Ordena df y features por fecha; devuelve (df_ordenado, X_ordenado, i70, i85)."""
    if col_fecha and col_fecha in df.columns:
        order = df.sort_values(col_fecha, kind="stable").index
    else:
        order = df.index
    df_s = df.loc[order].reset_index(drop=True)
    X = features_df.loc[order].reset_index(drop=True).to_numpy(dtype="float64")
    n = len(df_s)
    return df_s, X, int(0.7 * n), int(0.85 * n)


# ==============================================================================
# Derivación de Etiquetas (Clasificación binaria)
# ==============================================================================

def derivar_etiqueta_clasificacion(
    df: pd.DataFrame, config: ConfigConsulta, col_fecha: str | None
) -> pd.DataFrame:
    """Genera la columna etiqueta (0/1). Umbral/percentil fijado en el TRAIN temporal."""
    if config.derivacion_etiqueta is None:
        raise ValueError(f"Consulta {config.id}: sin derivacion_etiqueta")

    der = config.derivacion_etiqueta
    out = df.copy()
    etq = _nombre_etiqueta(config)

    if col_fecha and col_fecha in out.columns:
        order = out.sort_values(col_fecha, kind="stable").index
    else:
        order = out.index
    i70 = max(1, int(0.7 * len(order)))
    train = out.loc[order[:i70]]

    if der.tipo == "percentil":
        col_obj = der.columna_objetivo
        serie = pd.to_numeric(out[col_obj], errors="coerce")
        if der.agrupar_por:
            p_por_grupo = pd.to_numeric(train[col_obj], errors="coerce").groupby(
                train[der.agrupar_por]
            ).quantile(der.percentil / 100.0)
            umbrales = out[der.agrupar_por].map(p_por_grupo)
            p_global = float(pd.to_numeric(train[col_obj], errors="coerce").quantile(der.percentil / 100.0))
            umbrales = umbrales.fillna(p_global)
        else:
            umbrales = float(pd.to_numeric(train[col_obj], errors="coerce").quantile(der.percentil / 100.0))
        out[etq] = (serie > umbrales).astype("int8")

    elif der.tipo == "umbral":
        out[etq] = (pd.to_numeric(out[der.columna_objetivo], errors="coerce") >= der.umbral_valor).astype("int8")

    elif der.tipo == "regla":
        try:
            out[etq] = pd.eval(der.formula, local_dict=out.to_dict("series")).astype("int8")
        except Exception as e:
            raise ValueError(f"Consulta {config.id}: error evaluando regla: {der.formula} — {e}")

    else:
        raise ValueError(f"Consulta {config.id}: tipo de derivación desconocido: {der.tipo}")

    return out


# ==============================================================================
# Métricas y factories
# ==============================================================================

def _wape(y_real: np.ndarray, y_pred: np.ndarray) -> float:
    denom = np.sum(np.abs(y_real))
    if denom == 0:
        return 0.0
    return float(np.sum(np.abs(y_real - y_pred)) / denom)


def _pr_auc(y_real: np.ndarray, y_prob: np.ndarray) -> float:
    """PR-AUC = Average Precision (métrica correcta; el no-skill = prevalencia de positivos).

    Antes se usaba auc(recall, precision) con interpolación lineal, que SOBREESTIMA (un
    predictor constante daba ~0.60 en vez de la prevalencia ~0.20), haciendo que 'baseline'
    ganara de forma artificial incluso cuando un modelo real tenía señal. average_precision_score
    corrige ese sesgo (sklearn lo recomienda explícitamente sobre auc(recall, precision)).
    """
    if len(np.unique(y_real)) < 2:
        return 0.0
    return float(average_precision_score(y_real, y_prob))


def _f1_macro(y_real: np.ndarray, y_pred: np.ndarray) -> float:
    return float(f1_score(y_real, y_pred, average="macro", zero_division=0))


def _construir_modelo_regresion(nombre: str, seed: int = 42) -> Any:
    if nombre == "ridge":
        return Ridge(alpha=1.0, random_state=seed)
    if nombre == "random_forest":
        return RandomForestRegressor(n_estimators=100, max_depth=10, random_state=seed)
    if nombre == "hist_gradient_boosting":
        return HistGradientBoostingRegressor(max_depth=5, random_state=seed)
    if nombre == "extra_trees":
        return ExtraTreesRegressor(n_estimators=100, max_depth=12, random_state=seed)
    if nombre == "baseline":  # B2: referencia (predice siempre la mediana)
        return DummyRegressor(strategy="median")
    raise ValueError(f"Regresor desconocido: {nombre}")


def _construir_modelo_clasificacion(nombre: str, seed: int = 42) -> Any:
    if nombre == "logistic_regression":
        return LogisticRegression(class_weight="balanced", max_iter=1000, random_state=seed)
    if nombre == "random_forest":
        return RandomForestClassifier(
            n_estimators=100, max_depth=10, class_weight="balanced", random_state=seed
        )
    if nombre == "hist_gradient_boosting":
        return HistGradientBoostingClassifier(max_depth=5, random_state=seed)
    if nombre == "baseline":  # B2: referencia (predice según la prevalencia de clases)
        return DummyClassifier(strategy="prior")
    raise ValueError(f"Clasificador desconocido: {nombre}")


def _candidatos_con_baseline(config: ConfigConsulta) -> list[str]:
    """Candidatos del catálogo + un baseline al final (para contextualizar la métrica, B2)."""
    cands = list(config.modelos_candidatos)
    if "baseline" not in cands:
        cands.append("baseline")
    return cands


def _prob_positiva(modelo: Any, X: np.ndarray) -> np.ndarray:
    proba = modelo.predict_proba(X)
    clases = list(modelo.classes_)
    if 1 in clases:
        return proba[:, clases.index(1)]
    return np.zeros(len(X)) if clases and clases[0] == 0 else np.ones(len(X))


# ==============================================================================
# Regresión
# ==============================================================================

def entrenar_regresion(
    df: pd.DataFrame, config: ConfigConsulta, features_df: pd.DataFrame
) -> _Entrenamiento:
    """Entrena regresores; selecciona en VALID, reporta WAPE de TEST; emite real+predicho."""
    df_s, X, i70, i85 = _preparar_temporal(df, features_df, config.col_fecha)
    y = pd.to_numeric(df_s[config.objetivo], errors="coerce").fillna(0.0).to_numpy(dtype="float64")

    X_tr, X_va, X_te = X[:i70], X[i70:i85], X[i85:]
    y_tr, y_va, y_te = y[:i70], y[i70:i85], y[i85:]
    if len(X_tr) == 0 or len(X_va) == 0:
        return _Entrenamiento([], [], "—", 0.0, "Datos insuficientes para entrenar (muy pocas filas).")

    scaler = StandardScaler()
    X_tr_s = scaler.fit_transform(X_tr)
    X_va_s = scaler.transform(X_va)
    X_te_s = scaler.transform(X_te) if len(X_te) else X_va_s

    # B2/B1: objetivo sesgado → entrenar en log1p e invertir con expm1 (métrica en escala real).
    usar_log = config.transform_objetivo == "log"
    y_fit_tr = np.log1p(np.maximum(0.0, y_tr)) if usar_log else y_tr

    def _pred_inv(m: Any, Xs: np.ndarray) -> np.ndarray:
        p = m.predict(Xs)
        return np.expm1(p) if usar_log else p

    tabla: list[FilaComparacion] = []
    mejor_nombre, mejor_wape, mejor_modelo = None, float("inf"), None
    for nombre in _candidatos_con_baseline(config):  # incluye baseline (B2)
        try:
            modelo = _construir_modelo_regresion(nombre)
            modelo.fit(X_tr_s, y_fit_tr)
            wape_va = _wape(y_va, _pred_inv(modelo, X_va_s))
            tabla.append(FilaComparacion(nombre, "wape", wape_va))
            if wape_va < mejor_wape:
                mejor_wape, mejor_nombre, mejor_modelo = wape_va, nombre, modelo
        except Exception as e:
            log.warning(f"{config.id}: falló {nombre}: {e}")
            tabla.append(FilaComparacion(nombre, "wape", float("nan")))

    if mejor_modelo is None:
        return _Entrenamiento(tabla, [], "—", 0.0, "No se pudo entrenar ningún modelo con estos datos.")
    for fila in tabla:
        fila.ganador = fila.modelo == mejor_nombre

    df_pred = df_s.iloc[i85:] if len(X_te) else df_s.iloc[i70:i85]
    y_pred = _pred_inv(mejor_modelo, X_te_s)
    y_real = y_te if len(X_te) else y_va
    wape_test = _wape(y_real, y_pred)

    dims = _dims_categoricas(df_s, config)
    predicciones: list[dict[str, Any]] = []
    for pos in range(min(len(df_pred), MAX_PREDICCIONES)):
        fila_df = df_pred.iloc[pos]
        item: dict[str, Any] = {c: _safe(fila_df[c]) for c in dims if c in df_pred.columns}
        item["value"] = _num2(y_pred[pos])
        item["actual"] = _num2(y_real[pos])
        predicciones.append(item)

    # A2 (fix tope 500): el resumen se calcula sobre TODO el tramo de test (y_pred completo),
    # aunque la tabla mostrada se limite a MAX_PREDICCIONES filas.
    resumen = _resumen_regresion(config, y_pred)
    return _Entrenamiento(tabla, predicciones, mejor_nombre, wape_test, None, resumen=resumen)


# ==============================================================================
# Clasificación (binaria o multiclase)
# ==============================================================================

def _pred_clasif_degradado(
    df_pred: pd.DataFrame, config: ConfigConsulta, clase: int
) -> list[dict[str, Any]]:
    id_cols = _id_cols(df_pred, config)
    filas: list[dict[str, Any]] = []
    for pos in range(min(len(df_pred), MAX_PREDICCIONES)):
        fila_df = df_pred.iloc[pos]
        item: dict[str, Any] = {c: _safe(fila_df[c]) for c in id_cols}
        if config.col_fecha and config.col_fecha in df_pred.columns:
            item[config.col_fecha] = _safe(fila_df[config.col_fecha])
        item["class"] = int(clase)
        item["probability"] = 0.0
        filas.append(item)
    return filas


def _entrenar_multiclase(
    df: pd.DataFrame, config: ConfigConsulta, features_df: pd.DataFrame
) -> _Entrenamiento:
    """Clasificación MULTICLASE sobre config.objetivo (p. ej. canal_venta). Métrica: F1 macro."""
    df_s, X, i70, i85 = _preparar_temporal(df, features_df, config.col_fecha)
    y_raw = df_s[config.objetivo].astype(str).to_numpy()
    clases = sorted(pd.unique(y_raw).tolist())
    df_pred = df_s.iloc[i85:] if i85 < len(df_s) else df_s.iloc[i70:i85]

    if len(clases) < 2:
        adv = "Sin casos suficientes: solo hay una categoría en el objetivo; no se puede predecir."
        return _Entrenamiento([], [], "—", 0.0, adv, {"classes": clases})

    idx = {c: i for i, c in enumerate(clases)}
    y = np.array([idx[v] for v in y_raw])
    y_tr, y_va, y_te = y[:i70], y[i70:i85], y[i85:]
    X_tr, X_va, X_te = X[:i70], X[i70:i85], X[i85:]
    if len(X_tr) == 0 or len(X_va) == 0 or len(np.unique(y_tr)) < 2:
        return _Entrenamiento([], _pred_clasif_degradado(df_pred, config, 0), "—", 0.0,
                              "Datos insuficientes en el periodo de entrenamiento.", {"classes": clases})

    scaler = StandardScaler()
    X_tr_s = scaler.fit_transform(X_tr)
    X_va_s = scaler.transform(X_va)
    X_te_s = scaler.transform(X_te) if len(X_te) else X_va_s

    tabla: list[FilaComparacion] = []
    mejor_nombre, mejor_f1, mejor_modelo = None, float("-inf"), None
    for nombre in _candidatos_con_baseline(config):  # incluye baseline (B2)
        try:
            modelo = _construir_modelo_clasificacion(nombre)
            modelo.fit(X_tr_s, y_tr)
            f1_va = _f1_macro(y_va, modelo.predict(X_va_s))
            tabla.append(FilaComparacion(nombre, "f1_macro", f1_va))
            if f1_va > mejor_f1:
                mejor_f1, mejor_nombre, mejor_modelo = f1_va, nombre, modelo
        except Exception as e:
            log.warning(f"{config.id}: falló {nombre}: {e}")
            tabla.append(FilaComparacion(nombre, "f1_macro", float("nan")))

    if mejor_modelo is None:
        return _Entrenamiento(tabla, _pred_clasif_degradado(df_pred, config, 0), "—", 0.0,
                              "No se pudo entrenar el modelo multiclase.", {"classes": clases})
    for fila in tabla:
        fila.ganador = fila.modelo == mejor_nombre

    X_pred_s = X_te_s
    X_pred = X_te if len(X_te) else X_va
    y_real = y_te if len(X_te) else y_va
    y_hat = mejor_modelo.predict(X_pred_s)
    proba = mejor_modelo.predict_proba(X_pred_s)
    clases_modelo = list(mejor_modelo.classes_)
    f1_test = _f1_macro(y_real, y_hat)

    # Coordenadas 2D REALES para el scatter (proyección PCA), como en clustering.
    feats = list(features_df.columns)
    coords, ejes = _coordenadas_2d(pd.DataFrame(X_pred, columns=feats), X_pred_s, feats)

    id_cols = _id_cols(df_pred, config)
    predicciones: list[dict[str, Any]] = []
    for pos in range(min(len(df_pred), MAX_PREDICCIONES)):
        fila_df = df_pred.iloc[pos]
        item: dict[str, Any] = {c: _safe(fila_df[c]) for c in id_cols}
        if config.col_fecha and config.col_fecha in df_pred.columns:
            item[config.col_fecha] = _safe(fila_df[config.col_fecha])
        cls_idx = int(y_hat[pos])
        item["predicted_class"] = clases[cls_idx]
        item["actual"] = clases[int(y_real[pos])]
        col_prob = clases_modelo.index(cls_idx) if cls_idx in clases_modelo else 0
        item["probability"] = round(float(proba[pos, col_prob]), 4)
        item["x"] = _num2(coords[pos, 0])
        item["y"] = _num2(coords[pos, 1])
        predicciones.append(item)

    return _Entrenamiento(tabla, predicciones, mejor_nombre, f1_test, None, {"axes": ejes, "classes": clases})


def entrenar_clasificacion(
    df: pd.DataFrame, config: ConfigConsulta, features_df: pd.DataFrame
) -> _Entrenamiento:
    """Clasificación: multiclase (sin derivacion) o binaria (con derivacion)."""
    if config.derivacion_etiqueta is None:
        return _entrenar_multiclase(df, config, features_df)

    df_etiq = derivar_etiqueta_clasificacion(df, config, config.col_fecha)
    etq = _nombre_etiqueta(config)
    df_s, X, i70, i85 = _preparar_temporal(df_etiq, features_df, config.col_fecha)
    y = pd.to_numeric(df_s[etq], errors="coerce").fillna(0).astype(int).to_numpy()
    df_pred = df_s.iloc[i85:] if i85 < len(df_s) else df_s.iloc[i70:i85]

    clases_all = np.unique(y)
    if len(clases_all) < 2:
        unica = int(clases_all[0]) if len(clases_all) else 0
        adv = (
            "Sin casos suficientes: todos los registros caen en la misma categoría "
            f"({'con alerta' if unica == 1 else 'sin alerta'}); no se puede entrenar esta alerta."
        )
        return _Entrenamiento([], _pred_clasif_degradado(df_pred, config, unica), "—", 0.0, adv)

    X_tr, X_va, X_te = X[:i70], X[i70:i85], X[i85:]
    y_tr, y_va, y_te = y[:i70], y[i70:i85], y[i85:]
    if len(X_tr) == 0 or len(X_va) == 0:
        return _Entrenamiento([], _pred_clasif_degradado(df_pred, config, int(clases_all[0])), "—", 0.0,
                              "Datos insuficientes para entrenar (muy pocas filas).")

    scaler = StandardScaler()
    X_tr_s = scaler.fit_transform(X_tr)
    X_va_s = scaler.transform(X_va)
    X_te_s = scaler.transform(X_te) if len(X_te) else X_va_s

    tabla: list[FilaComparacion] = []
    mejor_nombre, mejor_pr, mejor_modelo = None, float("-inf"), None
    for nombre in _candidatos_con_baseline(config):  # incluye baseline (B2)
        try:
            if len(np.unique(y_tr)) < 2:
                raise ValueError("el periodo de entrenamiento tiene una sola clase")
            modelo = _construir_modelo_clasificacion(nombre)
            modelo.fit(X_tr_s, y_tr)
            pr_va = _pr_auc(y_va, _prob_positiva(modelo, X_va_s))
            tabla.append(FilaComparacion(nombre, "pr_auc", pr_va))
            if pr_va > mejor_pr:
                mejor_pr, mejor_nombre, mejor_modelo = pr_va, nombre, modelo
        except Exception as e:
            log.warning(f"{config.id}: falló {nombre}: {e}")
            tabla.append(FilaComparacion(nombre, "pr_auc", float("nan")))

    if mejor_modelo is None:
        return _Entrenamiento(tabla, _pred_clasif_degradado(df_pred, config, int(clases_all[0])), "—", 0.0,
                              "Sin casos suficientes en el periodo de entrenamiento para aprender la alerta.")
    for fila in tabla:
        fila.ganador = fila.modelo == mejor_nombre

    X_pred_s = X_te_s
    X_pred = X_te if len(X_te) else X_va
    y_real = y_te if len(X_te) else y_va
    prob_pred = _prob_positiva(mejor_modelo, X_pred_s)
    clase_pred = mejor_modelo.predict(X_pred_s)
    pr_auc_test = _pr_auc(y_real, prob_pred)

    # Coordenadas 2D REALES para el scatter (proyección PCA), como en clustering.
    feats = list(features_df.columns)
    coords, ejes = _coordenadas_2d(pd.DataFrame(X_pred, columns=feats), X_pred_s, feats)

    id_cols = _id_cols(df_pred, config)
    predicciones: list[dict[str, Any]] = []
    for pos in range(min(len(df_pred), MAX_PREDICCIONES)):
        fila_df = df_pred.iloc[pos]
        item: dict[str, Any] = {c: _safe(fila_df[c]) for c in id_cols}
        if config.col_fecha and config.col_fecha in df_pred.columns:
            item[config.col_fecha] = _safe(fila_df[config.col_fecha])
        item["class"] = int(clase_pred[pos])
        item["actual"] = int(y_real[pos])
        item["probability"] = round(float(prob_pred[pos]), 4)
        item["x"] = _num2(coords[pos, 0])
        item["y"] = _num2(coords[pos, 1])
        predicciones.append(item)

    return _Entrenamiento(tabla, predicciones, mejor_nombre, pr_auc_test, None, {"axes": ejes})


# ==============================================================================
# Clustering (agrega por entidad, coordenadas 2D reales, etiquetas legibles)
# ==============================================================================

def _agregar_clustering(df: pd.DataFrame, config: ConfigConsulta) -> tuple[pd.DataFrame, list[str]]:
    feats = [c for c in config.columnas_entrada if c in df.columns]
    dfx = df.copy()
    for c in feats:
        dfx[c] = pd.to_numeric(dfx[c], errors="coerce")
    if config.agregacion == "by_date_proveedor":
        keys = [k for k in ["fecha_orden", "id_proveedor"] if k in dfx.columns]
    elif config.entidad_cluster and config.entidad_cluster in dfx.columns:
        keys = [config.entidad_cluster]
    else:
        keys = [c for c in [config.entidad_cluster] if c and c in dfx.columns]
    if not keys:
        return dfx[feats].dropna(), []
    return dfx.groupby(keys)[feats].mean().dropna(), keys


# Nombre legible de una variable del dominio (para nombrar segmentos por su criterio real).
_NOMBRE_VARIABLE = {
    "unidades_vendidas": "Ventas", "ingreso": "Ingreso", "precio_unitario": "Precio",
    "precio_unitario_compra": "Precio de compra", "cantidad_pedida": "Cantidad pedida",
    "descuento_pct": "Descuento", "descuento_volumen": "Descuento por volumen",
    "en_promocion": "Uso de promoción", "lead_time_dias": "Tiempo de entrega",
    "cumplimiento": "Cumplimiento", "costo_total": "Costo", "stock_actual": "Stock",
    "demanda_diaria_promedio": "Demanda media", "demanda_dia": "Demanda",
    "dias_de_cobertura": "Cobertura", "rotacion": "Rotación",
}


def _nombre_variable(col: str) -> str:
    return _NOMBRE_VARIABLE.get(col) or col.replace("_", " ").capitalize()


def _variable_dominante(agg_r: pd.DataFrame, labels: np.ndarray, feats: list[str]) -> str | None:
    """Variable que MÁS separa los grupos (mayor eta² = varianza entre-grupos / total)."""
    mejor, mejor_eta = (feats[0] if feats else None), -1.0
    for c in feats:
        x = pd.to_numeric(agg_r[c], errors="coerce").to_numpy(dtype="float64")
        tot = float(np.nanvar(x))
        if tot <= 1e-12:
            continue
        gm = float(np.nanmean(x))
        entre = sum(len(x[labels == cl]) * (float(np.nanmean(x[labels == cl])) - gm) ** 2
                    for cl in np.unique(labels))
        eta = (entre / len(x)) / tot
        if eta > mejor_eta:
            mejor_eta, mejor = eta, c
    return mejor


def _niveles(nombre: str, k: int) -> list[str]:
    """Nombres de segmento por nivel de la variable dominante (formato neutro de género, B4)."""
    if k <= 1:
        return [f"{nombre}: nivel único"]
    if k == 2:
        return [f"{nombre}: alto", f"{nombre}: bajo"]
    if k == 3:
        return [f"{nombre}: alto", f"{nombre}: medio", f"{nombre}: bajo"]
    return [f"{nombre}: nivel {i + 1} (de mayor a menor)" for i in range(k)]


def _etiquetas_por_estilo(estilo: str, k: int) -> list[str]:
    """Estilos con taxonomía de negocio fija (abc, servicio). El resto usa la variable dominante."""
    if estilo == "abc":
        base = ["Clase A (más importante)", "Clase B (intermedia)", "Clase C (menos importante)"]
    else:  # servicio
        base = ["Servicio premium (entrega rápida)", "Servicio estándar", "Servicio básico (entrega lenta)"]
    if k == 1:
        return [base[0]]
    if k == 2:
        return [base[0], base[-1]]
    if k == 3:
        return base
    return [f"Grupo {i + 1} (de mayor a menor)" for i in range(k)]


def _coordenadas_2d(agg: pd.DataFrame, X_s: np.ndarray, feats: list[str]) -> tuple[np.ndarray, dict[str, str]]:
    """Coordenadas 2D REALES para graficar (PCA si hay ≥3 features; si no, las features)."""
    n_feat = X_s.shape[1]
    if n_feat >= 3:
        comp = PCA(n_components=2, random_state=42).fit_transform(X_s)
        return comp, {"x": "Componente principal 1", "y": "Componente principal 2"}
    if n_feat == 2:
        return agg[feats].to_numpy(dtype="float64"), {"x": feats[0], "y": feats[1]}
    # una sola feature: eje X = feature, eje Y = 0
    col = agg[feats[0]].to_numpy(dtype="float64")
    return np.column_stack([col, np.zeros_like(col)]), {"x": feats[0], "y": ""}


def _fit_cluster(algo: str, k: int, X_s: np.ndarray) -> np.ndarray:
    if algo == "agglomerative":
        return AgglomerativeClustering(n_clusters=k).fit_predict(X_s)
    return KMeans(n_clusters=k, random_state=42, n_init=10).fit_predict(X_s)  # kmeans por defecto


def entrenar_clustering(df: pd.DataFrame, config: ConfigConsulta) -> _Entrenamiento:
    """Agrupa entidades (KMeans/Aglomerativo compiten por silueta); anti-singleton (B2)."""
    agg, keys = _agregar_clustering(df, config)
    n = len(agg)
    if n < 2 or not keys:
        return _Entrenamiento([], [], "—", 0.0, "Muy pocas entidades para formar grupos.")

    feats = list(agg.columns)
    X = agg.to_numpy(dtype="float64")
    scaler = StandardScaler()
    X_s = scaler.fit_transform(X)

    if config.k_fijo:
        k_values = [min(config.k_fijo, n - 1)]
    else:
        k_values = list(range(2, min(9, n)))
    k_values = [k for k in k_values if 2 <= k < n] or [2]

    u = obtener_umbrales()
    min_miembros = max(1, u.min_miembros_cluster)
    algos = [a for a in config.modelos_candidatos if a in ("kmeans", "agglomerative")] or ["kmeans"]

    # Compiten los algoritmos; para cada uno el mejor k por silueta, descartando particiones
    # con algún grupo de menos de `min_miembros` (evita clusters de 1 elemento, B2).
    mejor_sil, mejor_algo, mejor_labels = float("-inf"), None, None
    mejor_por_algo: dict[str, float] = {}
    for algo in algos:
        best_a, best_a_labels = float("-inf"), None
        for k in k_values:
            try:
                labels = _fit_cluster(algo, k, X_s)
                _, counts = np.unique(labels, return_counts=True)
                if len(counts) < 2 or counts.min() < min_miembros:
                    continue
                sil = silhouette_score(X_s, labels)
                if sil > best_a:
                    best_a, best_a_labels = sil, labels
            except Exception as e:
                log.warning(f"{config.id}: clustering {algo} k={k} falló: {e}")
        if best_a_labels is not None:
            mejor_por_algo[algo] = best_a
            if best_a > mejor_sil:
                mejor_sil, mejor_algo, mejor_labels = best_a, algo, best_a_labels

    # Fallback (toda partición dejaba grupos diminutos): elige la que MENOS singletons deje y,
    # entre esas, la de mejor silueta (reduce k para evitar grupos de 1; si es inevitable, se avisa).
    if mejor_labels is None:
        mejor_score = None  # (n_singletons, -silueta): menor es mejor
        for k in k_values:
            try:
                labels = KMeans(n_clusters=k, random_state=42, n_init=10).fit_predict(X_s)
                if len(np.unique(labels)) < 2:
                    continue
                _, counts = np.unique(labels, return_counts=True)
                n_sing = int((counts < min_miembros).sum())
                sil = silhouette_score(X_s, labels)
                score = (n_sing, -sil)
                if mejor_score is None or score < mejor_score:
                    mejor_score, mejor_sil, mejor_algo, mejor_labels = score, sil, "kmeans", labels
            except Exception as e:
                log.warning(f"{config.id}: clustering fallback k={k} falló: {e}")
        if mejor_labels is not None:
            mejor_por_algo = {"kmeans": mejor_sil}

    if mejor_labels is None:
        return _Entrenamiento([], [], "—", 0.0, "No fue posible formar grupos con estos datos.")
    mejor_k = int(len(np.unique(mejor_labels)))

    # Etiquetas legibles. Estilos con taxonomía fija (abc/servicio) usan columna_etiqueta;
    # el resto ("auto") deriva el nombre de la VARIABLE DOMINANTE (la que más separa).
    agg_r = agg.reset_index(drop=True)
    estilo = config.estilo_etiqueta
    if estilo in ("abc", "servicio"):
        rank_col = config.columna_etiqueta if config.columna_etiqueta in feats else (feats[0] if feats else None)
        nombres = _etiquetas_por_estilo(estilo, mejor_k)
        orden_desc = estilo != "servicio"
    else:  # auto
        rank_col = _variable_dominante(agg_r, mejor_labels, feats)
        nombres = _niveles(_nombre_variable(rank_col) if rank_col else "Grupo", mejor_k)
        orden_desc = True

    medias = {cl: (float(agg_r.loc[mejor_labels == cl, rank_col].mean()) if rank_col else float(cl))
              for cl in np.unique(mejor_labels)}
    clusters_ordenados = sorted(medias.keys(), key=lambda c: medias[c], reverse=orden_desc)
    etiqueta_de = {cl: nombres[min(i, len(nombres) - 1)] for i, cl in enumerate(clusters_ordenados)}

    coords, ejes = _coordenadas_2d(agg, X_s, feats)

    # Miembros con id legible: para órdenes (fecha·proveedor) mostrar "Proveedor (fecha)".
    por_fecha_prov = config.agregacion == "by_date_proveedor"
    entidades = agg.index.tolist()
    predicciones: list[dict[str, Any]] = []
    for pos, cl in enumerate(mejor_labels):
        clave = entidades[pos]
        if isinstance(clave, tuple):
            if por_fecha_prov and len(clave) == 2:
                entidad_str = f"{clave[1]} ({clave[0]})"  # (fecha, proveedor) → "Proveedor (fecha)"
            else:
                entidad_str = " · ".join(str(x) for x in clave)
        else:
            entidad_str = str(clave)
        predicciones.append({
            "entity": entidad_str,
            "label": etiqueta_de[cl],
            "group": int(cl),
            "x": _num2(coords[pos, 0]),
            "y": _num2(coords[pos, 1]),
        })

    tabla = [
        FilaComparacion(a, "silhouette", s, ganador=(a == mejor_algo))
        for a, s in mejor_por_algo.items()
    ] or [FilaComparacion(mejor_algo or "kmeans", "silhouette", mejor_sil, ganador=True)]
    avisos: list[str] = []
    _, counts_final = np.unique(mejor_labels, return_counts=True)
    n_singleton = int((counts_final < min_miembros).sum())
    if n_singleton:
        avisos.append(
            f"Segmentación con {n_singleton} grupo(s) de 1 solo elemento: referencial, no accionable."
        )
    if n < u.min_entidades_cluster:
        avisos.append(f"Segmentación sobre pocas entidades ({n}): referencial, no concluyente.")
    if mejor_sil < u.silhouette_aviso:
        avisos.append("Grupos poco definidos: la separación entre segmentos es débil (referencial).")
    adv = " ".join(avisos) or None
    return _Entrenamiento(tabla, predicciones, mejor_algo or "kmeans", mejor_sil, adv, {"axes": ejes})


# ==============================================================================
# Clasificación ABC (REGLA de Pareto por valor acumulado; NO clustering) — ALM-K1
# ==============================================================================

def entrenar_abc(df: pd.DataFrame, config: ConfigConsulta) -> _Entrenamiento:
    """Análisis ABC CLÁSICO por valor acumulado (Pareto ~80/15/5).

    Es una REGLA de negocio determinística, no clustering: ordena las entidades (SKU) por su
    VALOR de mayor a menor y las parte en A/B/C según el % ACUMULADO del valor total.

    Criterio de valor: ``demanda_diaria_promedio`` (volumen de movimiento por SKU); si no está,
    la primera columna de entrada. Cortes: A hasta 80% acumulado, B 80–95%, C 95–100%.
    """
    agg, keys = _agregar_clustering(df, config)
    if len(agg) < 2 or not keys:
        return _Entrenamiento([], [], "—", 0.0, "Muy pocas entidades para el análisis ABC.")

    feats = list(agg.columns)
    val_col = "demanda_diaria_promedio" if "demanda_diaria_promedio" in feats else feats[0]
    valor = pd.to_numeric(agg[val_col], errors="coerce").fillna(0.0).clip(lower=0.0)
    orden = valor.sort_values(ascending=False)
    total = float(orden.sum()) or 1.0
    cum = orden.cumsum() / total

    def _clase(frac: float) -> int:
        if frac <= 0.80:
            return 0  # A (más importante)
        if frac <= 0.95:
            return 1  # B (intermedia)
        return 2      # C (menos importante)

    grupo_de = {ent_id: _clase(float(frac)) for ent_id, frac in cum.items()}
    labels = np.array([grupo_de[i] for i in agg.index], dtype=int)
    nombres = _etiquetas_por_estilo("abc", 3)

    predicciones: list[dict[str, Any]] = []
    for ent_id in agg.index:
        g = int(grupo_de[ent_id])
        entidad = " · ".join(str(x) for x in ent_id) if isinstance(ent_id, tuple) else str(ent_id)
        predicciones.append({
            "entity": entidad,
            "label": nombres[min(g, len(nombres) - 1)],
            "group": g,
            "x": _num2(float(valor[ent_id])),
            "y": _num2(float(cum[ent_id]) * 100.0),
        })

    # Métrica propia del ABC (una regla NO tiene "cohesión"/silueta): fracción del valor total
    # que concentra la Clase A. Es la lectura honesta de un análisis de Pareto.
    share_a = float(valor[[i for i in agg.index if grupo_de[i] == 0]].sum()) / total

    adv = ("Todos los SKU cayeron en una sola clase ABC (valor muy concentrado): referencial."
           if len(np.unique(labels)) < 2 else None)
    tabla = [FilaComparacion("regla_abc_pareto", "value_share_a", share_a, ganador=True)]
    meta = {"axes": {"x": val_col, "y": "valor acumulado %"}, "abc_valor": val_col}
    return _Entrenamiento(tabla, predicciones, "regla_abc_pareto", share_a, adv, meta)


# ==============================================================================
# Análisis / Tendencia (la ÚNICA salida con línea temporal)
# ==============================================================================

# Magnitud principal y columna de fecha por módulo (para la línea de tendencia).
_TENDENCIA_POR_MODULO = {
    "ventas": ("fecha", "unidades_vendidas", "unidades"),
    "compras": ("fecha_orden", "cantidad_pedida", "unidades"),
    "almacen": ("fecha", "demanda_dia", "unidades"),
}


def _proyectar(serie: pd.Series, horizonte: int) -> tuple[list[dict], list[dict], dict | None]:
    """Histórico + pronóstico (tendencia lineal × estacionalidad semanal) + resumen honesto."""
    fechas = serie.index
    y = serie.to_numpy(dtype="float64")
    n = len(y)
    historico = [{"date": str(f.date()), "value": round(float(v), 2)} for f, v in zip(fechas, y)]
    if n < 8:  # muy corto para pronosticar con honestidad
        return historico, [], None

    x = np.arange(n)
    coef = np.polyfit(x, y, 1)
    dow = fechas.dayofweek.to_numpy()
    media = y.mean() or 1.0
    factor = {d: (y[dow == d].mean() / media if (dow == d).any() else 1.0) for d in range(7)}

    ult = fechas[-1]
    pron: list[dict] = []
    for i in range(1, horizonte + 1):
        f = ult + pd.Timedelta(days=i)
        base_val = float(np.polyval(coef, n - 1 + i))
        val = max(0.0, base_val * factor.get(int(f.dayofweek), 1.0))
        pron.append({"date": str(f.date()), "value": round(val, 2)})

    reciente = float(np.mean(y[-horizonte:])) if n >= horizonte else float(np.mean(y))
    fut_media = float(np.mean([p["value"] for p in pron])) if pron else reciente
    change_pct = round((fut_media - reciente) / reciente * 100, 1) if reciente > 1e-9 else 0.0
    pend = coef[0] / media
    direccion = "creciente" if pend > 0.005 else ("decreciente" if pend < -0.005 else "estable")
    resumen = {
        "projection": round(float(sum(p["value"] for p in pron)), 2),
        "change_pct": change_pct,
        "direction": direccion,
    }
    return historico, pron, resumen


def calcular_tendencia(modulo: str, df: pd.DataFrame) -> Tendencia:
    """Serie temporal del total diario de la magnitud principal + pronóstico simple y honesto.

    Método: tendencia lineal (mínimos cuadrados) sobre el total diario, con estacionalidad
    SEMANAL. Única salida con línea de tiempo (referencial). Añade horizonte, resumen
    interpretativo y desglose por categoría (para filtrar). Devuelve datos planos.
    """
    col_fecha, magnitud, unidad = _TENDENCIA_POR_MODULO.get(modulo, (None, None, ""))
    horizonte = obtener_horizonte_tendencia()
    base = Tendencia(
        unidad=unidad, horizonte=horizonte,
        metodo="Tendencia lineal + estacionalidad semanal (referencial)",
    )
    if not col_fecha or col_fecha not in df.columns or magnitud not in df.columns:
        return base

    try:
        cols = [col_fecha, magnitud] + (["categoria"] if "categoria" in df.columns else [])
        tmp = df[cols].copy()
        tmp[col_fecha] = pd.to_datetime(tmp[col_fecha], errors="coerce")
        tmp[magnitud] = pd.to_numeric(tmp[magnitud], errors="coerce")
        tmp = tmp.dropna(subset=[col_fecha, magnitud])
        if tmp.empty:
            return base

        serie = tmp.groupby(col_fecha)[magnitud].sum().sort_index()
        base.historico, base.pronostico, base.resumen = _proyectar(serie, horizonte)

        # Desglose por categoría (acotado a las más grandes) para el filtro del frontend.
        if "categoria" in tmp.columns:
            desgloses: list[dict[str, Any]] = []
            for cat, sub in tmp.groupby("categoria"):
                s = sub.groupby(col_fecha)[magnitud].sum().sort_index()
                h, p, _ = _proyectar(s, horizonte)
                if h:
                    desgloses.append({"label": str(cat), "historico": h, "pronostico": p})
            base.desgloses = sorted(
                desgloses, key=lambda d: -sum(x["value"] for x in d["historico"])
            )[:8]
        return base
    except Exception as e:
        log.warning(f"Tendencia {modulo}: {e}")
        return base


# ==============================================================================
# Interfaz Principal
# ==============================================================================

def ejecutar_consulta(consulta_id: str, df: pd.DataFrame) -> ResultadoConsulta:
    """Ejecuta una consulta del catálogo y devuelve predicciones reales + comparación."""
    from spc.catalogo.config import obtener_consulta, obtener_modulo

    config = obtener_consulta(consulta_id)
    modulo_config = obtener_modulo(config.modulo)
    log.info(f"Ejecutando consulta {consulta_id}: {config.pregunta}")

    validar_dataframe(df, config)

    if config.tipo == "regresion":
        ent = entrenar_regresion(df, config, construir_features(df, config, modulo_config))
        metrica = "wape"
    elif config.tipo == "clasificacion":
        ent = entrenar_clasificacion(df, config, construir_features(df, config, modulo_config))
        metrica = "f1_macro" if config.derivacion_etiqueta is None else "pr_auc"
    elif config.tipo == "clustering":
        if config.estilo_etiqueta == "abc":
            # ALM-K1 NO es clustering: es la regla de Pareto por valor acumulado.
            ent = entrenar_abc(df, config)
            metrica = "value_share_a"
        else:
            ent = entrenar_clustering(df, config)
            metrica = "silhouette"
    else:
        raise ValueError(f"Tipo de consulta desconocido: {config.tipo}")

    u = obtener_umbrales()
    advertencia = ent.advertencia
    # A5: clasificador degenerado (predice una sola clase para todos) — tiene prioridad.
    if advertencia is None and config.tipo == "clasificacion" and ent.tabla:
        degenerado = _aviso_degenerado(ent.predicciones)
        if degenerado:
            advertencia = degenerado
    if advertencia is None:
        if config.tipo == "regresion" and ent.valor_metrica > u.wape_aviso:
            advertencia = (
                f"Señal débil: el modelo explica poca variación con estos factores "
                f"(error promedio {ent.valor_metrica:.0%})."
            )
        elif config.tipo == "clasificacion" and ent.tabla and ent.valor_metrica < u.clasificacion_aviso:
            advertencia = "Señal débil: los factores disponibles distinguen poco esta clase."

    # Nota técnica honesta: derivación de etiqueta, métrica casi perfecta (clasif) y objetivo fácil (regr).
    nota = _nota_tecnica(config)
    if ent.tabla:
        caveat = _nota_metrica_casi_perfecta(config, ent.valor_metrica, u.metrica_casi_perfecta)
        if caveat:
            nota = f"{nota} {caveat}" if nota else caveat
        facil = _nota_objetivo_facil(config, df, u)  # A4
        if facil:
            nota = f"{nota} {facil}" if nota else facil

    # ABC (ALM-K1): dejar claro que es una REGLA de negocio, no clustering, y su criterio de valor.
    if config.tipo == "clustering" and config.estilo_etiqueta == "abc":
        crit = ent.meta.get("abc_valor", "demanda_diaria_promedio")
        nota_abc = (
            "Clasificación ABC por REGLA de Pareto (no es clustering): se ordenan los SKU por su "
            f"valor ({crit} = volumen de movimiento) y se asignan A/B/C por valor acumulado "
            "(A ≈ primeros 80%, B 80–95%, C 95–100%)."
        )
        nota = f"{nota_abc} {nota}" if nota else nota_abc

    # Calidad honesta (solo si hubo entrenamiento real; degradado = limitada).
    calidad = _calidad(config.tipo, metrica, ent.valor_metrica, u) if ent.tabla else "limitada"

    # A2: recuadro resumen (suma para extensivas, promedio para intensivas), calculado en el
    # entrenador sobre TODO el tramo de test (no sobre la lista truncada a MAX_PREDICCIONES).
    resumen = ent.resumen if config.tipo == "regresion" else None

    resultado = ResultadoConsulta(
        consulta_id=consulta_id,
        pregunta=config.pregunta,
        tipo=config.tipo,
        modelo_ganador=ent.ganador,
        metrica_ganador=metrica,
        valor_metrica=float(ent.valor_metrica),
        predicciones=ent.predicciones,
        tabla_comparacion=ent.tabla,
        advertencia=advertencia,
        unidad=_unidad(config),
        nota_tecnica=nota,
        calidad=calidad,
        resumen=resumen,
        meta=ent.meta,
    )
    log.info(
        f"Consulta {consulta_id}: {ent.ganador} ({metrica}={ent.valor_metrica:.3f}), "
        f"{len(ent.predicciones)} predicciones"
        + (f" — AVISO: {advertencia}" if advertencia else "")
    )
    return resultado
