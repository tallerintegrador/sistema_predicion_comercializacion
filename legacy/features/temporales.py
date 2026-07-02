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

import numpy as np
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

    lags_objetivo: tuple[int, ...] = (1, 7, 14, 21, 28)
    ventanas_media_objetivo: tuple[int, ...] = (7, 14, 28, 56)
    ventanas_mediana_objetivo: tuple[int, ...] = (7, 28)
    ventanas_std_objetivo: tuple[int, ...] = (7, 28)
    ventanas_minmax_objetivo: tuple[int, ...] = (28,)
    ewm_halflives: tuple[int, ...] = (7, 28)
    lags_transacciones: tuple[int, ...] = (1, 7)
    ventanas_media_transacciones: tuple[int, ...] = (7, 28)
    lags_promocion: tuple[int, ...] = (1, 7)
    ventanas_suma_promocion: tuple[int, ...] = (7, 28)
    # Activadores de bloques de features (todos leak-safe).
    intermitencia: bool = True
    calendario_ciclico: bool = True
    proximidad_calendario: bool = True
    macro_oil: bool = True

    def as_dict(self) -> dict:
        return {
            "lags_objetivo": list(self.lags_objetivo),
            "ventanas_media_objetivo": list(self.ventanas_media_objetivo),
            "ventanas_mediana_objetivo": list(self.ventanas_mediana_objetivo),
            "ventanas_std_objetivo": list(self.ventanas_std_objetivo),
            "ventanas_minmax_objetivo": list(self.ventanas_minmax_objetivo),
            "ewm_halflives": list(self.ewm_halflives),
            "lags_transacciones": list(self.lags_transacciones),
            "ventanas_media_transacciones": list(self.ventanas_media_transacciones),
            "lags_promocion": list(self.lags_promocion),
            "ventanas_suma_promocion": list(self.ventanas_suma_promocion),
            "intermitencia": self.intermitencia,
            "calendario_ciclico": self.calendario_ciclico,
            "proximidad_calendario": self.proximidad_calendario,
            "macro_oil": self.macro_oil,
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


def _ewm_pasado(df: pd.DataFrame, col_base: str, halflife: int) -> pd.Series:
    """Media exponencial movil sobre **solo el pasado**.

    ``col_base`` ya viene desplazada (`shift(1)`); el EWMA pondera mas los dias
    recientes (vida media ``halflife``) sin incluir el dia ``t``.
    """
    grupos = df.groupby(COLS_SERIE, observed=True)[col_base]
    return grupos.transform(lambda s: s.ewm(halflife=halflife, min_periods=1).mean())


def _dias_desde_ultima_venta(df: pd.DataFrame) -> pd.Series:
    """Dias transcurridos desde la ultima venta (>0), mirando SOLO el pasado.

    Para la fila del dia ``t`` devuelve ``t - s``, donde ``s`` es el dia mas
    reciente **estrictamente anterior** con ``sales > 0`` dentro de la misma serie
    ``(store_nbr, family)``. NaN si no hubo ninguna venta previa. Vectorizado por
    grupo (sin bucles por fila): se marca la posicion de los dias con venta, se
    desplaza un dia (para no mirar ``t``) y se arrastra hacia delante (`ffill`).
    """
    pos = df.groupby(COLS_SERIE, observed=True).cumcount().astype("float64")
    vendio = (df[OBJETIVO].to_numpy() > 0).astype("float64")
    pos_venta = pd.Series(np.where(vendio > 0, pos.to_numpy(), np.nan), index=df.index)
    g = pd.concat([df[COLS_SERIE], pos_venta.rename("_pv")], axis=1).groupby(
        COLS_SERIE, observed=True
    )["_pv"]
    ultima = g.transform(lambda s: s.shift(1).ffill())
    return pos - ultima


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
    for w in cfg.ventanas_std_objetivo:
        col = f"sales_rstd_{w}"
        df[col] = _rolling_pasado(df, "_sales_prev", w, "std")
        features.append(col)
    for w in cfg.ventanas_minmax_objetivo:
        col_min = f"sales_rmin_{w}"
        col_max = f"sales_rmax_{w}"
        df[col_min] = _rolling_pasado(df, "_sales_prev", w, "min")
        df[col_max] = _rolling_pasado(df, "_sales_prev", w, "max")
        features.extend([col_min, col_max])
    for hl in cfg.ewm_halflives:
        col = f"sales_ewm_{hl}"
        df[col] = _ewm_pasado(df, "_sales_prev", hl)
        features.append(col)

    # --- Intermitencia / zero-inflation (31% de ceros): senales de la demanda
    #     nula reciente, claves para series esporadicas. Solo miran al pasado.
    if cfg.intermitencia:
        df["_vendio_prev"] = (df["_sales_prev"] > 0).astype("float64")
        # Si _sales_prev es NaN (calentamiento), la mascara de venta tambien NaN.
        df.loc[df["_sales_prev"].isna(), "_vendio_prev"] = np.nan
        # Dias desde la ultima venta (recencia de la demanda positiva).
        df["dias_desde_venta"] = _dias_desde_ultima_venta(df)
        # Proporcion de dias con venta > 0 en las ultimas 28 (frecuencia de venta).
        df["frac_venta_28"] = _rolling_pasado(df, "_vendio_prev", 28, "mean")
        # Racha de ceros: cuantos de los ultimos 7 dias fueron cero.
        df["_cero_prev"] = (df["_sales_prev"] == 0).astype("float64")
        df.loc[df["_sales_prev"].isna(), "_cero_prev"] = np.nan
        df["ceros_rsum_7"] = _rolling_pasado(df, "_cero_prev", 7, "sum")
        features.extend(["dias_desde_venta", "frac_venta_28", "ceros_rsum_7"])
        df = df.drop(columns=["_vendio_prev", "_cero_prev"])

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
    # Intensidad promocional reciente (suma de dias en promo, solo pasado).
    df["_promo_prev"] = grupo["onpromotion"].shift(1)
    for w in cfg.ventanas_suma_promocion:
        col = f"promo_rsum_{w}"
        df[col] = _rolling_pasado(df, "_promo_prev", w, "sum")
        features.append(col)
    df = df.drop(columns="_promo_prev")

    # --- Calendario ciclico: codifica la periodicidad (lun-dom, ene-dic, semana
    #     del anio) sin imponer orden lineal artificial. Conocido a futuro.
    if cfg.calendario_ciclico:
        ciclos = {
            "dow": (df["dayofweek"].astype("float64"), 7.0),
            "month": (df["month"].astype("float64") - 1.0, 12.0),
            "woy": (df["weekofyear"].astype("float64") - 1.0, 52.0),
        }
        for nombre, (valor, periodo) in ciclos.items():
            df[f"{nombre}_sin"] = np.sin(2 * np.pi * valor / periodo)
            df[f"{nombre}_cos"] = np.cos(2 * np.pi * valor / periodo)
            features.extend([f"{nombre}_sin", f"{nombre}_cos"])

    # --- Proximidad a eventos de calendario (conocida a futuro) ---
    if cfg.proximidad_calendario:
        # Dias hasta fin de mes y desde inicio de mes (efecto quincena/cierre).
        df["dias_a_fin_mes"] = (
            df[COL_FECHA].dt.days_in_month - df["day"].astype("int16")
        ).astype("int16")
        df["dias_desde_inicio_mes"] = (df["day"].astype("int16") - 1).astype("int16")
        # Proximidad a quincena (dia 15) y a payday.
        df["dist_quincena"] = (df["day"].astype("int16") - 15).abs().astype("int16")
        features.extend(["dias_a_fin_mes", "dias_desde_inicio_mes", "dist_quincena"])

    # --- Macro petroleo: nivel ya viene; aqui rezago y tendencia (cambio) ---
    if cfg.macro_oil and "dcoilwtico" in df.columns:
        oil_diario = (
            df[[COL_FECHA, "dcoilwtico"]]
            .drop_duplicates(COL_FECHA)
            .sort_values(COL_FECHA)
            .set_index(COL_FECHA)["dcoilwtico"]
        )
        oil_lag7 = oil_diario.shift(7)
        oil_tend = oil_diario.shift(1) - oil_diario.shift(8)  # cambio semanal pasado
        df["oil_lag_7"] = df[COL_FECHA].map(oil_lag7).astype("float64")
        df["oil_tend_7"] = df[COL_FECHA].map(oil_tend).astype("float64")
        features.extend(["oil_lag_7", "oil_tend_7"])

    # --- Calendario/feriados ya integrados + categoricas ---
    features.extend(FEATURES_CALENDARIO)
    features.extend(FEATURES_CATEGORICAS)

    return df, features, list(FEATURES_CATEGORICAS), cfg


def columnas_rezago(features: list[str]) -> list[str]:
    """Subconjunto de features que dependen del pasado (lags/ventanas).

    Util para detectar el periodo de calentamiento (filas con NaN) y para los
    tests de no-fuga.
    """
    prefijos = (
        "sales_lag_",
        "sales_rmean_",
        "sales_rmed_",
        "sales_rstd_",
        "sales_rmin_",
        "sales_rmax_",
        "sales_ewm_",
        "trans_lag_",
        "trans_rmean_",
        "promo_lag_",
        "promo_rsum_",
        "dias_desde_venta",
        "frac_venta_28",
        "ceros_rsum_",
        "oil_lag_",
        "oil_tend_",
    )
    return [c for c in features if c.startswith(prefijos)]
