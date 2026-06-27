"""Feature engineering **agnóstico al rubro** (predicción auto-entrenada, ADR-0023).

A diferencia de `spc.features.temporales` —clavado al esquema retail
(``store_nbr``/``family``/``sales`` + calendario/feriados/petróleo)— este módulo
construye features **leak-safe** sobre un esquema que el cliente **declara**: cuál
columna es el objetivo, cuál la fecha, cuáles las claves de serie y qué features
extra trae (numéricas conocidas a futuro, numéricas solo-pasado, o categóricas).

Dos modos, según el esquema declarado:

- **Serie temporal** (hay ``col_fecha``): rezagos/ventanas móviles del objetivo por
  serie, calendario derivado de la fecha (conocido a futuro), rezagos de las
  numéricas "solo-pasado" y *passthrough* de las "conocidas-a-futuro". Habilita el
  pronóstico recursivo multi-horizonte (`spc.models.automl`).
- **Tabular** (no hay ``col_fecha``): sin rezagos; las features declaradas se usan
  tal cual. El modelo predice por fila (no hay horizonte temporal que proyectar).

La **regla de oro contra la fuga** es la misma que en el motor retail: todo
rezago/estadístico móvil se calcula **agrupando por serie** y **desplazando
(`shift`) antes** de cualquier ventana, de modo que la fila del día ``t`` solo ve
información de días ``< t``. El objetivo del período actual **nunca** es feature.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

# Prefijo único de los rezagos/ventanas del objetivo (para detectar el calentamiento
# y para los tests de no-fuga, con independencia del nombre real del objetivo).
PREFIJO_LAG_OBJETIVO = "tgt_lag_"
PREFIJOS_PASADO = (
    PREFIJO_LAG_OBJETIVO,
    "tgt_rmean_",
    "tgt_rmed_",
    "tgt_rstd_",
    "tgt_rmin_",
    "tgt_rmax_",
    "tgt_ewm_",
    "tgt_dias_desde_pos",
    "tgt_frac_pos_28",
    "tgt_ceros_rsum_7",
    "feat_lag_",
    "feat_rmean_",
    "featkf_lag_",
    "featkf_rmean_",
)


@dataclass(frozen=True)
class EspecEsquema:
    """Esquema **declarado por el cliente** para entrenar/predecir de forma agnóstica.

    - ``objetivo``: nombre de la columna a predecir (numérica para regresión; 0/1 o
      derivable para clasificación).
    - ``col_fecha``: nombre de la columna de fecha (``None`` → modo tabular sin rezagos).
    - ``cols_serie``: claves que identifican cada serie (generaliza ``store_nbr+family``).
      Lista vacía → una sola serie global. Las claves de serie también entran como
      features **categóricas** (igual que ``store_nbr``/``family`` en el motor retail).
    - ``num_conocidas_futuro``: numéricas cuyo valor del período a predecir **se conoce**
      (calendario, promoción planificada, precio fijado): se usan tal cual + rezagos.
    - ``num_solo_pasado``: numéricas que en el futuro **no se conocen** (transacciones,
      tráfico): solo se usan sus rezagos/medias del pasado (evita la fuga).
    - ``cats_extra``: categóricas declaradas que no son claves de serie.
    """

    objetivo: str
    col_fecha: str | None = None
    cols_serie: tuple[str, ...] = ()
    num_conocidas_futuro: tuple[str, ...] = ()
    num_solo_pasado: tuple[str, ...] = ()
    cats_extra: tuple[str, ...] = ()

    # --- Parámetros de la ingeniería temporal (fijos para reproducibilidad) ---
    lags_objetivo: tuple[int, ...] = (1, 7, 14, 21, 28)
    ventanas_media_objetivo: tuple[int, ...] = (7, 14, 28)
    ventanas_std_objetivo: tuple[int, ...] = (7, 28)
    ventanas_minmax_objetivo: tuple[int, ...] = (28,)
    ewm_halflives: tuple[int, ...] = (7, 28)
    lags_feature: tuple[int, ...] = (1, 7)
    ventanas_media_feature: tuple[int, ...] = (7, 28)
    intermitencia: bool = True
    calendario_ciclico: bool = True
    proximidad_calendario: bool = True

    @property
    def es_temporal(self) -> bool:
        """¿El esquema declara una fecha (→ rezagos + pronóstico recursivo)?"""
        return self.col_fecha is not None

    @property
    def cats(self) -> list[str]:
        """Categóricas del modelo: claves de serie + categóricas extra (sin duplicar)."""
        vistas: list[str] = []
        for c in (*self.cols_serie, *self.cats_extra):
            if c not in vistas:
                vistas.append(c)
        return vistas

    def as_dict(self) -> dict:
        return {
            "objetivo": self.objetivo,
            "col_fecha": self.col_fecha,
            "cols_serie": list(self.cols_serie),
            "num_conocidas_futuro": list(self.num_conocidas_futuro),
            "num_solo_pasado": list(self.num_solo_pasado),
            "cats_extra": list(self.cats_extra),
            "lags_objetivo": list(self.lags_objetivo),
            "ventanas_media_objetivo": list(self.ventanas_media_objetivo),
            "ventanas_std_objetivo": list(self.ventanas_std_objetivo),
            "ventanas_minmax_objetivo": list(self.ventanas_minmax_objetivo),
            "ewm_halflives": list(self.ewm_halflives),
            "lags_feature": list(self.lags_feature),
            "ventanas_media_feature": list(self.ventanas_media_feature),
            "intermitencia": self.intermitencia,
            "calendario_ciclico": self.calendario_ciclico,
            "proximidad_calendario": self.proximidad_calendario,
        }


# Columnas de calendario derivadas de la fecha (conocidas a futuro).
FEATURES_CALENDARIO = [
    "g_year",
    "g_month",
    "g_day",
    "g_dayofweek",
    "g_is_weekend",
    "g_is_month_end",
    "g_is_payday",
    "g_weekofyear",
]
# Proximidad a eventos de calendario (efecto quincena/cierre de mes; conocido a futuro).
FEATURES_PROXIMIDAD = [
    "g_dias_a_fin_mes",
    "g_dias_desde_inicio_mes",
    "g_dist_quincena",
]


def _orden(spec: EspecEsquema) -> list[str]:
    """Columnas por las que ordenar (serie + fecha) para que los `shift` sean honestos."""
    cols = list(spec.cols_serie)
    if spec.col_fecha is not None:
        cols.append(spec.col_fecha)
    return cols


def _grupo(df: pd.DataFrame, spec: EspecEsquema):
    """Agrupador por serie. Sin claves de serie → una sola serie global (clave constante)."""
    if spec.cols_serie:
        return df.groupby(list(spec.cols_serie), observed=True)
    return df.groupby(np.zeros(len(df), dtype="int8"))


def _rolling_pasado(serie_grupo, ventana: int, func: str) -> pd.Series:
    """Estadístico móvil sobre **solo el pasado** (``col_base`` ya viene desplazada)."""
    return serie_grupo.transform(
        lambda s: getattr(s.rolling(ventana, min_periods=1), func)()
    )


def _decorar_calendario(df: pd.DataFrame, col_fecha: str) -> pd.DataFrame:
    """Deriva el calendario desde ``col_fecha`` (conocido a futuro). Idempotente."""
    fecha = pd.to_datetime(df[col_fecha])
    df["g_year"] = fecha.dt.year.astype("int16")
    df["g_month"] = fecha.dt.month.astype("int8")
    df["g_day"] = fecha.dt.day.astype("int8")
    df["g_dayofweek"] = fecha.dt.dayofweek.astype("int8")
    df["g_is_weekend"] = df["g_dayofweek"] >= 5
    df["g_is_month_end"] = fecha.dt.is_month_end
    df["g_is_payday"] = (df["g_day"] == 15) | df["g_is_month_end"]
    df["g_weekofyear"] = fecha.dt.isocalendar().week.astype("int16")
    # Proximidad: días hasta fin de mes, desde inicio de mes y distancia a la quincena.
    df["g_dias_a_fin_mes"] = (fecha.dt.days_in_month - fecha.dt.day).astype("int16")
    df["g_dias_desde_inicio_mes"] = (fecha.dt.day - 1).astype("int16")
    df["g_dist_quincena"] = (fecha.dt.day - 15).abs().astype("int16")
    return df


def _dias_desde_positivo(df: pd.DataFrame, spec: EspecEsquema) -> pd.Series:
    """Días desde la última observación con objetivo > 0 (recencia de la demanda positiva).

    Mira SOLO el pasado: para la fila ``t`` devuelve ``t - s`` con ``s`` el día más reciente
    **estrictamente anterior** con objetivo positivo en la misma serie; NaN si no hubo
    ninguno. Vectorizado (sin bucles por fila): marca la posición de los días positivos,
    la desplaza un día y la arrastra hacia delante (`ffill`).
    """
    pos = _grupo(df, spec).cumcount().astype("float64")
    vendio = df[spec.objetivo].to_numpy() > 0
    pp = pd.Series(np.where(vendio, pos.to_numpy(), np.nan), index=df.index, name="_pp")
    tmp = df.assign(_pp=pp)
    if spec.cols_serie:
        ultima = tmp.groupby(list(spec.cols_serie), observed=True)["_pp"].transform(
            lambda s: s.shift(1).ffill()
        )
    else:
        ultima = tmp["_pp"].shift(1).ffill()
    return pos - ultima


def construir_features(
    df: pd.DataFrame, spec: EspecEsquema
) -> tuple[pd.DataFrame, list[str], list[str]]:
    """Genera las features del esquema declarado. Devuelve ``(df, features, categoricas)``.

    No elimina filas: las primeras observaciones de cada serie quedan con NaN en los
    rezagos (calentamiento). El consumidor decide cómo tratarlos (el entrenamiento las
    descarta; el pronóstico recursivo las recalcula día a día).
    """
    obj = spec.objetivo
    df = df.copy()
    if _orden(spec):
        df = df.sort_values(_orden(spec)).reset_index(drop=True)
    features: list[str] = []

    if spec.es_temporal:
        df = _decorar_calendario(df, spec.col_fecha)  # type: ignore[arg-type]
        grupo_obj = _grupo(df, spec)[obj]

        # --- Rezagos del objetivo ---
        for lag in spec.lags_objetivo:
            col = f"{PREFIJO_LAG_OBJETIVO}{lag}"
            df[col] = grupo_obj.shift(lag)
            features.append(col)

        # --- Ventanas móviles del objetivo (shift(1) → solo pasado) ---
        df["_obj_prev"] = grupo_obj.shift(1)
        g_prev = _grupo(df, spec)["_obj_prev"]
        for w in spec.ventanas_media_objetivo:
            col = f"tgt_rmean_{w}"
            df[col] = _rolling_pasado(g_prev, w, "mean")
            features.append(col)
        for w in spec.ventanas_std_objetivo:
            col = f"tgt_rstd_{w}"
            df[col] = _rolling_pasado(g_prev, w, "std")
            features.append(col)
        for w in spec.ventanas_minmax_objetivo:
            cmin, cmax = f"tgt_rmin_{w}", f"tgt_rmax_{w}"
            df[cmin] = _rolling_pasado(g_prev, w, "min")
            df[cmax] = _rolling_pasado(g_prev, w, "max")
            features.extend([cmin, cmax])
        for hl in spec.ewm_halflives:
            col = f"tgt_ewm_{hl}"
            df[col] = g_prev.transform(
                lambda s, hl=hl: s.ewm(halflife=hl, min_periods=1).mean()
            )
            features.append(col)

        # --- Intermitencia (señales de demanda nula reciente; solo pasado) ---
        if spec.intermitencia:
            df["_pos_prev"] = (df["_obj_prev"] > 0).astype("float64")
            df.loc[df["_obj_prev"].isna(), "_pos_prev"] = np.nan
            df["tgt_frac_pos_28"] = _rolling_pasado(
                _grupo(df, spec)["_pos_prev"], 28, "mean"
            )
            df["_cero_prev"] = (df["_obj_prev"] == 0).astype("float64")
            df.loc[df["_obj_prev"].isna(), "_cero_prev"] = np.nan
            df["tgt_ceros_rsum_7"] = _rolling_pasado(
                _grupo(df, spec)["_cero_prev"], 7, "sum"
            )
            # Recencia: días desde la última venta/observación positiva (solo pasado).
            df["tgt_dias_desde_pos"] = _dias_desde_positivo(df, spec)
            features.extend(["tgt_frac_pos_28", "tgt_ceros_rsum_7", "tgt_dias_desde_pos"])
            df = df.drop(columns=["_pos_prev", "_cero_prev"])
        df = df.drop(columns="_obj_prev")

        # --- Numéricas SOLO-pasado: nunca su valor del período, solo rezagos/medias ---
        for nombre in spec.num_solo_pasado:
            g = _grupo(df, spec)[nombre]
            for lag in spec.lags_feature:
                col = f"feat_lag_{nombre}_{lag}"
                df[col] = g.shift(lag)
                features.append(col)
            df["_prev"] = g.shift(1)
            for w in spec.ventanas_media_feature:
                col = f"feat_rmean_{nombre}_{w}"
                df[col] = _rolling_pasado(_grupo(df, spec)["_prev"], w, "mean")
                features.append(col)
            df = df.drop(columns="_prev")

        # --- Numéricas CONOCIDAS-a-futuro: además del valor del día (passthrough abajo),
        #     su HISTORIA reciente (rezagos + intensidad). Para promoción/precio, "cuántos
        #     días lleva en promo" o "el precio de ayer" añaden señal que el valor puntual
        #     no captura. Es leak-safe: el valor del día es conocido, los rezagos son pasado.
        for nombre in spec.num_conocidas_futuro:
            g = _grupo(df, spec)[nombre]
            for lag in spec.lags_feature:
                col = f"featkf_lag_{nombre}_{lag}"
                df[col] = g.shift(lag)
                features.append(col)
            df["_prev"] = g.shift(1)
            for w in spec.ventanas_media_feature:
                col = f"featkf_rmean_{nombre}_{w}"
                df[col] = _rolling_pasado(_grupo(df, spec)["_prev"], w, "mean")
                features.append(col)
            df = df.drop(columns="_prev")

        # --- Calendario cíclico (periodicidad sin orden lineal artificial) ---
        if spec.calendario_ciclico:
            ciclos = {
                "dow": (df["g_dayofweek"].astype("float64"), 7.0),
                "month": (df["g_month"].astype("float64") - 1.0, 12.0),
                "woy": (df["g_weekofyear"].astype("float64") - 1.0, 52.0),
            }
            for nombre, (valor, periodo) in ciclos.items():
                df[f"g_{nombre}_sin"] = np.sin(2 * np.pi * valor / periodo)
                df[f"g_{nombre}_cos"] = np.cos(2 * np.pi * valor / periodo)
                features.extend([f"g_{nombre}_sin", f"g_{nombre}_cos"])

        features.extend(FEATURES_CALENDARIO)
        if spec.proximidad_calendario:
            features.extend(FEATURES_PROXIMIDAD)

    else:
        # Modo tabular: las numéricas solo-pasado no tienen sentido sin orden temporal;
        # se tratan como conocidas (passthrough) para no descartar información.
        pass

    # --- Numéricas conocidas a futuro: passthrough (su valor del período es válido) ---
    extra_pass = list(spec.num_conocidas_futuro)
    if not spec.es_temporal:
        extra_pass = [*extra_pass, *spec.num_solo_pasado]
    for nombre in extra_pass:
        if nombre not in features:
            features.append(nombre)

    # --- Categóricas (claves de serie + extra) ---
    cats = spec.cats
    for c in cats:
        if c not in features:
            features.append(c)

    return df, features, list(cats)


def columnas_calentamiento(features: list[str]) -> list[str]:
    """Features dependientes del pasado (lags/ventanas) — para detectar el calentamiento."""
    return [c for c in features if c.startswith(PREFIJOS_PASADO)]


def columnas_lag_objetivo(features: list[str]) -> list[str]:
    """Solo los rezagos directos del objetivo (definen el calentamiento mínimo a descartar)."""
    return [c for c in features if c.startswith(PREFIJO_LAG_OBJETIVO)]
