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
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import precision_recall_curve, auc, silhouette_score, f1_score
from sklearn.preprocessing import StandardScaler

from spc.catalogo.config import ConfigConsulta
from spc.utils.logging import get_logger

log = get_logger("catalogo.motor_catalogo")

# Máximo de filas de predicción devueltas por consulta (evita payloads enormes).
MAX_PREDICCIONES = 500

# Unidad de la magnitud predicha, por columna objetivo (para formatear en la UI).
_UNIDAD_POR_OBJETIVO = {
    "unidades_vendidas": "unidades",
    "ingreso": "S/",
    "cantidad_pedida": "unidades",
    "lead_time_dias": "días",
    "costo_total": "S/",
    "cumplimiento": "%",
    "demanda_dia": "unidades",
    "dias_de_cobertura": "días",
    "rotacion": "índice",
    "stock_maximo": "unidades",
}


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
    fecha_entrenamiento: datetime = field(default_factory=datetime.utcnow)
    advertencia: str | None = None
    unidad: str = ""
    nota_tecnica: str | None = None
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
        return _UNIDAD_POR_OBJETIVO.get(config.objetivo, "")
    return ""


def _nota_tecnica(config: ConfigConsulta) -> str | None:
    """Nota honesta para el detalle técnico (por qué la métrica puede salir muy alta)."""
    der = config.derivacion_etiqueta
    if config.tipo == "clasificacion" and der is not None:
        if der.tipo == "regla":
            return (
                "La etiqueta se calcula con una regla determinística "
                f"({der.formula}). Por eso la métrica sale muy alta: el modelo aprende una "
                "fórmula conocida, no un patrón incierto."
            )
        if der.tipo == "umbral":
            return (
                f"La etiqueta usa un umbral fijo de negocio "
                f"({der.columna_objetivo} ≥ {der.umbral_valor})."
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
    if len(np.unique(y_real)) < 2:
        return 0.0
    precision, recall, _ = precision_recall_curve(y_real, y_prob)
    return float(auc(recall, precision))


def _f1_macro(y_real: np.ndarray, y_pred: np.ndarray) -> float:
    return float(f1_score(y_real, y_pred, average="macro", zero_division=0))


def _construir_modelo_regresion(nombre: str, seed: int = 42) -> Any:
    if nombre == "ridge":
        return Ridge(alpha=1.0, random_state=seed)
    if nombre == "random_forest":
        return RandomForestRegressor(n_estimators=100, max_depth=10, random_state=seed)
    if nombre == "hist_gradient_boosting":
        return HistGradientBoostingRegressor(max_depth=5, random_state=seed)
    raise ValueError(f"Regresor desconocido: {nombre}")


def _construir_modelo_clasificacion(nombre: str, seed: int = 42) -> Any:
    if nombre == "logistic_regression":
        return LogisticRegression(class_weight="balanced", max_iter=1000, random_state=seed)
    if nombre == "random_forest":
        return RandomForestClassifier(
            n_estimators=100, max_depth=10, class_weight="balanced", random_state=seed
        )
    raise ValueError(f"Clasificador desconocido: {nombre}")


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

    tabla: list[FilaComparacion] = []
    mejor_nombre, mejor_wape, mejor_modelo = None, float("inf"), None
    for nombre in config.modelos_candidatos:
        try:
            modelo = _construir_modelo_regresion(nombre)
            modelo.fit(X_tr_s, y_tr)
            wape_va = _wape(y_va, modelo.predict(X_va_s))
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
    y_pred = mejor_modelo.predict(X_te_s)
    y_real = y_te if len(X_te) else y_va
    wape_test = _wape(y_real, y_pred)

    dims = _dims_categoricas(df_s, config)
    predicciones: list[dict[str, Any]] = []
    for pos in range(min(len(df_pred), MAX_PREDICCIONES)):
        fila_df = df_pred.iloc[pos]
        item: dict[str, Any] = {c: _safe(fila_df[c]) for c in dims if c in df_pred.columns}
        item["valor"] = _num2(y_pred[pos])
        item["real"] = _num2(y_real[pos])
        predicciones.append(item)

    return _Entrenamiento(tabla, predicciones, mejor_nombre, wape_test, None)


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
        item["clase"] = int(clase)
        item["probabilidad"] = 0.0
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
        return _Entrenamiento([], [], "—", 0.0, adv, {"clases": clases})

    idx = {c: i for i, c in enumerate(clases)}
    y = np.array([idx[v] for v in y_raw])
    y_tr, y_va, y_te = y[:i70], y[i70:i85], y[i85:]
    X_tr, X_va, X_te = X[:i70], X[i70:i85], X[i85:]
    if len(X_tr) == 0 or len(X_va) == 0 or len(np.unique(y_tr)) < 2:
        return _Entrenamiento([], _pred_clasif_degradado(df_pred, config, 0), "—", 0.0,
                              "Datos insuficientes en el periodo de entrenamiento.", {"clases": clases})

    scaler = StandardScaler()
    X_tr_s = scaler.fit_transform(X_tr)
    X_va_s = scaler.transform(X_va)
    X_te_s = scaler.transform(X_te) if len(X_te) else X_va_s

    tabla: list[FilaComparacion] = []
    mejor_nombre, mejor_f1, mejor_modelo = None, float("-inf"), None
    for nombre in config.modelos_candidatos:
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
                              "No se pudo entrenar el modelo multiclase.", {"clases": clases})
    for fila in tabla:
        fila.ganador = fila.modelo == mejor_nombre

    X_pred_s = X_te_s
    y_real = y_te if len(X_te) else y_va
    y_hat = mejor_modelo.predict(X_pred_s)
    proba = mejor_modelo.predict_proba(X_pred_s)
    clases_modelo = list(mejor_modelo.classes_)
    f1_test = _f1_macro(y_real, y_hat)

    id_cols = _id_cols(df_pred, config)
    predicciones: list[dict[str, Any]] = []
    for pos in range(min(len(df_pred), MAX_PREDICCIONES)):
        fila_df = df_pred.iloc[pos]
        item: dict[str, Any] = {c: _safe(fila_df[c]) for c in id_cols}
        if config.col_fecha and config.col_fecha in df_pred.columns:
            item[config.col_fecha] = _safe(fila_df[config.col_fecha])
        cls_idx = int(y_hat[pos])
        item["clase_predicha"] = clases[cls_idx]
        col_prob = clases_modelo.index(cls_idx) if cls_idx in clases_modelo else 0
        item["probabilidad"] = round(float(proba[pos, col_prob]), 4)
        predicciones.append(item)

    return _Entrenamiento(tabla, predicciones, mejor_nombre, f1_test, None, {"clases": clases})


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
    for nombre in config.modelos_candidatos:
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
    y_real = y_te if len(X_te) else y_va
    prob_pred = _prob_positiva(mejor_modelo, X_pred_s)
    clase_pred = mejor_modelo.predict(X_pred_s)
    pr_auc_test = _pr_auc(y_real, prob_pred)

    id_cols = _id_cols(df_pred, config)
    predicciones: list[dict[str, Any]] = []
    for pos in range(min(len(df_pred), MAX_PREDICCIONES)):
        fila_df = df_pred.iloc[pos]
        item: dict[str, Any] = {c: _safe(fila_df[c]) for c in id_cols}
        if config.col_fecha and config.col_fecha in df_pred.columns:
            item[config.col_fecha] = _safe(fila_df[config.col_fecha])
        item["clase"] = int(clase_pred[pos])
        item["probabilidad"] = round(float(prob_pred[pos]), 4)
        predicciones.append(item)

    return _Entrenamiento(tabla, predicciones, mejor_nombre, pr_auc_test, None)


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


def _etiquetas_por_estilo(estilo: str, k: int) -> list[str]:
    if estilo == "abc":
        base = ["Clase A (más importante)", "Clase B (intermedia)", "Clase C (menos importante)"]
    elif estilo == "servicio":
        base = ["Servicio premium (entrega rápida)", "Servicio estándar", "Servicio básico (entrega lenta)"]
    else:
        base = ["Volumen alto", "Volumen medio", "Volumen bajo"]
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


def entrenar_clustering(df: pd.DataFrame, config: ConfigConsulta) -> _Entrenamiento:
    """Agrupa entidades con KMeans; emite entidad→grupo + coordenadas 2D reales."""
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

    mejor_sil, mejor_k, mejor_labels = float("-inf"), None, None
    for k in k_values:
        try:
            labels = KMeans(n_clusters=k, random_state=42, n_init=10).fit_predict(X_s)
            if len(np.unique(labels)) < 2:
                continue
            sil = silhouette_score(X_s, labels)
            if sil > mejor_sil:
                mejor_sil, mejor_k, mejor_labels = sil, k, labels
        except Exception as e:
            log.warning(f"{config.id}: clustering k={k} falló: {e}")

    if mejor_labels is None:
        return _Entrenamiento([], [], "—", 0.0, "No fue posible formar grupos con estos datos.")

    # Etiquetas legibles: ordenar clusters por columna de ranking (o primera feature).
    rank_col = config.columna_etiqueta if config.columna_etiqueta in feats else (feats[0] if feats else None)
    agg_r = agg.reset_index(drop=True)
    medias = {cl: (float(agg_r.loc[mejor_labels == cl, rank_col].mean()) if rank_col else float(cl))
              for cl in np.unique(mejor_labels)}
    orden_desc = config.estilo_etiqueta != "servicio"
    clusters_ordenados = sorted(medias.keys(), key=lambda c: medias[c], reverse=orden_desc)
    nombres = _etiquetas_por_estilo(config.estilo_etiqueta, mejor_k)
    etiqueta_de = {cl: nombres[min(i, len(nombres) - 1)] for i, cl in enumerate(clusters_ordenados)}

    coords, ejes = _coordenadas_2d(agg, X_s, feats)

    entidades = agg.index.tolist()
    predicciones: list[dict[str, Any]] = []
    for pos, cl in enumerate(mejor_labels):
        clave = entidades[pos]
        entidad_str = "·".join(str(x) for x in clave) if isinstance(clave, tuple) else str(clave)
        predicciones.append({
            "entidad": entidad_str,
            "etiqueta": etiqueta_de[cl],
            "grupo": int(cl),
            "x": _num2(coords[pos, 0]),
            "y": _num2(coords[pos, 1]),
        })

    tabla = [FilaComparacion("kmeans", "silhouette", mejor_sil, ganador=True)]
    adv = "Grupos poco definidos: la separación entre segmentos es débil (referencial)." if mejor_sil < 0.25 else None
    return _Entrenamiento(tabla, predicciones, "kmeans", mejor_sil, adv, {"ejes": ejes})


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
        ent = entrenar_clustering(df, config)
        metrica = "silhouette"
    else:
        raise ValueError(f"Tipo de consulta desconocido: {config.tipo}")

    advertencia = ent.advertencia
    if advertencia is None:
        if config.tipo == "regresion" and ent.valor_metrica > 0.30:
            advertencia = (
                f"Señal débil: el modelo explica poca variación con estos factores "
                f"(error promedio {ent.valor_metrica:.0%})."
            )
        elif config.tipo == "clasificacion" and ent.tabla and ent.valor_metrica < 0.50:
            advertencia = "Señal débil: los factores disponibles distinguen poco esta clase."

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
        nota_tecnica=_nota_tecnica(config),
        meta=ent.meta,
    )
    log.info(
        f"Consulta {consulta_id}: {ent.ganador} ({metrica}={ent.valor_metrica:.3f}), "
        f"{len(ent.predicciones)} predicciones"
        + (f" — AVISO: {advertencia}" if advertencia else "")
    )
    return resultado
