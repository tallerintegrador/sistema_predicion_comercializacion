"""Feature engineering temporal para la regresion de VENTAS (Fase 2a).

Construye, de forma reutilizable y **sin fuga de futuro**, las variables que
alimentan a los modelos: rezagos y ventanas moviles del objetivo, rezagos de
transacciones y promocion, y calendario adicional. La regla de oro contra la
fuga es: todo rezago/estadistico movil se calcula **agrupando por serie**
``(store_nbr, family)`` y **desplazando (`shift`) antes** de cualquier ventana,
de modo que la fila del dia ``t`` solo ve informacion de dias < t.

Las variables de calendario y feriados ya vienen del dataset analitico
(`spc.data.integration`); aqui solo se agregan las temporales derivadas.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

# Granularidad de la serie segun el contrato de datos.
COLS_SERIE = ["store_nbr", "family"]
COL_FECHA = "date"
OBJETIVO = "sales"

# Variables ya presentes en el dataset analitico que se usan tal cual (son
# conocidas para fechas futuras: calendario, feriados planificados, promocion
# planificada y la macro del petroleo).
FEATURES_CALENDARIO = [
    "year",
    "month",
    "day",
    "dayofweek",
    "is_weekend",
    "is_month_end",
    "is_payday",
    "holiday_national",
    "holiday_regional",
    "holiday_local",
    "holiday_event_count",
    "holiday_any",
    "dcoilwtico",
]
# Identificadores/segmentadores tratados como categoricos.
FEATURES_CATEGORICAS = ["store_nbr", "family", "type", "city", "state", "cluster"]


@dataclass(frozen=True)
class ConfigFeatures:
    """Parametros de la ingenieria temporal (fijos para reproducibilidad)."""

    lags_objetivo: tuple[int, ...] = (1, 7, 14)
    ventanas_media_objetivo: tuple[int, ...] = (7, 28)
    ventanas_mediana_objetivo: tuple[int, ...] = (7,)
    lags_transacciones: tuple[int, ...] = (1, 7)
    ventanas_media_transacciones: tuple[int, ...] = (7,)
    lags_promocion: tuple[int, ...] = (1, 7)

    def as_dict(self) -> dict:
        return {
            "lags_objetivo": list(self.lags_objetivo),
            "ventanas_media_objetivo": list(self.ventanas_media_objetivo),
            "ventanas_mediana_objetivo": list(self.ventanas_mediana_objetivo),
            "lags_transacciones": list(self.lags_transacciones),
            "ventanas_media_transacciones": list(self.ventanas_media_transacciones),
            "lags_promocion": list(self.lags_promocion),
        }


def _rolling_pasado(
    df: pd.DataFrame, col_base: str, ventana: int, func: str
) -> pd.Series:
    """Estadistico movil calculado **solo con el pasado**.

    Se asume que ``col_base`` ya esta desplazada un dia (`shift(1)`), de modo que
    la ventana del dia ``t`` cubre ``[t-ventana, t-1]`` y nunca incluye ``t``.
    """
    grupos = df.groupby(COLS_SERIE, observed=True)[col_base]
    rodante = grupos.transform(
        lambda s: getattr(s.rolling(ventana, min_periods=1), func)()
    )
    return rodante


def construir_features(
    df: pd.DataFrame, config: ConfigFeatures | None = None
) -> tuple[pd.DataFrame, list[str], list[str], ConfigFeatures]:
    """Genera las features temporales y devuelve ``(df, features, categoricas, config)``.

    No elimina filas: las primeras observaciones de cada serie quedan con NaN en
    los rezagos (periodo de calentamiento). El consumidor decide como tratarlos.
    """
    cfg = config or ConfigFeatures()
    df = df.sort_values(COLS_SERIE + [COL_FECHA]).reset_index(drop=True).copy()
    grupo = df.groupby(COLS_SERIE, observed=True)
    features: list[str] = []

    # --- Calendario adicional (semana ISO del anio) ---
    df["weekofyear"] = df[COL_FECHA].dt.isocalendar().week.astype("int16")

    # --- Rezagos del objetivo ---
    for lag in cfg.lags_objetivo:
        col = f"sales_lag_{lag}"
        df[col] = grupo[OBJETIVO].shift(lag)
        features.append(col)

    # --- Ventanas moviles del objetivo (shift(1) -> solo pasado) ---
    df["_sales_prev"] = grupo[OBJETIVO].shift(1)
    for w in cfg.ventanas_media_objetivo:
        col = f"sales_rmean_{w}"
        df[col] = _rolling_pasado(df, "_sales_prev", w, "mean")
        features.append(col)
    for w in cfg.ventanas_mediana_objetivo:
        col = f"sales_rmed_{w}"
        df[col] = _rolling_pasado(df, "_sales_prev", w, "median")
        features.append(col)
    df = df.drop(columns="_sales_prev")

    # --- Transacciones: SOLO rezagos/medias del pasado (evita la fuga; en
    #     pronostico real no se conocen las transacciones del periodo a predecir).
    for lag in cfg.lags_transacciones:
        col = f"trans_lag_{lag}"
        df[col] = grupo["transactions_filled"].shift(lag)
        features.append(col)
    df["_trans_prev"] = grupo["transactions_filled"].shift(1)
    for w in cfg.ventanas_media_transacciones:
        col = f"trans_rmean_{w}"
        df[col] = _rolling_pasado(df, "_trans_prev", w, "mean")
        features.append(col)
    df = df.drop(columns="_trans_prev")

    # --- Promocion: la del dia es conocida (planificada); ademas rezagos ---
    features.append("onpromotion")
    for lag in cfg.lags_promocion:
        col = f"promo_lag_{lag}"
        df[col] = grupo["onpromotion"].shift(lag)
        features.append(col)

    # --- Calendario/feriados ya integrados + categoricas ---
    features.extend(FEATURES_CALENDARIO)
    features.extend(FEATURES_CATEGORICAS)

    return df, features, list(FEATURES_CATEGORICAS), cfg


def columnas_rezago(features: list[str]) -> list[str]:
    """Subconjunto de features que dependen del pasado (lags/ventanas).

    Util para detectar el periodo de calentamiento (filas con NaN) y para los
    tests de no-fuga.
    """
    prefijos = ("sales_lag_", "sales_rmean_", "sales_rmed_", "trans_lag_", "trans_rmean_", "promo_lag_")
    return [c for c in features if c.startswith(prefijos)]
