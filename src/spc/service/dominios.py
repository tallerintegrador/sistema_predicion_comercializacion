"""Configuración 3×3 por dominio: cómo cada formato alimenta sus tres modelos.

Traduce el **formato único** de cada dominio (``spc.synthetic.esquemas``) a lo que el
motor de ML necesita, **sin fuga**:

- ``EspecEsquema`` de **regresión** y de **clasificación** (qué es objetivo, qué es
  conocido-a-futuro y qué es solo-pasado). Las columnas que **derivan** del objetivo
  (``ingreso``, ``costo_total``, ``dias_de_cobertura``…) se excluyen como features para
  no filtrar el objetivo.
- La **derivación de la etiqueta** de clasificación con umbral fijado **solo en TRAIN**
  (regla anti-fuga del repo): ``demanda_alta``, ``entrega_con_retraso``, ``riesgo_quiebre``.
- El **perfil por entidad** para el clustering (qué entidad agrupa y con qué columnas).

Es capa de servicio: traduce negocio↔motor, no conoce HTTP.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from spc.features.generico import EspecEsquema
from spc.models.automl import cortes_adaptativos


@dataclass(frozen=True)
class ConfigDominio:
    """Todo lo que el motor necesita para correr los 3 modelos de un dominio."""

    dominio: str
    spec_regresion: EspecEsquema
    spec_clasificacion: EspecEsquema
    etiqueta: str  # nombre de la columna 0/1 que produce `derivar_etiqueta`
    derivar_etiqueta: Callable[[pd.DataFrame], pd.DataFrame]
    clave_entidad: str  # sobre qué entidad agrupa el clustering
    perfil_entidades: Callable[[pd.DataFrame], pd.DataFrame]
    columna_volumen: str  # columna del perfil que ordena los segmentos (bajo→alto)
    columnas_clustering: tuple[str, ...] = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# Helpers de derivación de etiquetas (umbral train-only contra fuga)
# ---------------------------------------------------------------------------
def _mascara_train(df: pd.DataFrame, col_fecha: str) -> np.ndarray:
    """Filas anteriores al holdout (para fijar umbrales sin mirar VALID/TEST)."""
    fechas = pd.to_datetime(df[col_fecha])
    cortes = cortes_adaptativos(fechas)
    return (fechas <= cortes.train_fin).to_numpy()


def _demanda_alta(df: pd.DataFrame) -> pd.DataFrame:
    """``demanda_alta`` = unidades > P75 de su categoría (P75 fijado solo en TRAIN)."""
    out = df.copy()
    train = _mascara_train(out, "fecha")
    p75 = (
        out.loc[train].groupby("categoria")["unidades_vendidas"].quantile(0.75)
    )
    # Categorías no vistas en train → su propio P75 global (degradación elegante).
    p75_global = float(out.loc[train, "unidades_vendidas"].quantile(0.75)) if train.any() else 0.0
    umbral = out["categoria"].map(p75).fillna(p75_global).to_numpy("float64")
    out["demanda_alta"] = (out["unidades_vendidas"].to_numpy() > umbral).astype("int8")
    return out


def _entrega_con_retraso(df: pd.DataFrame) -> pd.DataFrame:
    """``entrega_con_retraso`` = lead time > P75 del lead time (umbral train-only)."""
    out = df.copy()
    train = _mascara_train(out, "fecha_orden")
    umbral = float(out.loc[train, "lead_time_dias"].quantile(0.75)) if train.any() else float(
        out["lead_time_dias"].quantile(0.75)
    )
    out["entrega_con_retraso"] = (out["lead_time_dias"].to_numpy() > umbral).astype("int8")
    return out


def _riesgo_quiebre(df: pd.DataFrame) -> pd.DataFrame:
    """``riesgo_quiebre`` = stock_actual < demanda_diaria × tiempo_reposicion (definición)."""
    out = df.copy()
    cobertura_necesaria = out["demanda_diaria_promedio"] * out["tiempo_reposicion_dias"]
    out["riesgo_quiebre"] = (out["stock_actual"] < cobertura_necesaria).astype("int8")
    return out


# ---------------------------------------------------------------------------
# Helpers de perfil por entidad (entrada al clustering)
# ---------------------------------------------------------------------------
def _perfil_ventas(df: pd.DataFrame) -> pd.DataFrame:
    """Perfil por SKU: volumen y variabilidad de la demanda + intensidad de promo."""
    g = df.groupby("sku")
    perfil = pd.DataFrame({
        "volumen_medio": g["unidades_vendidas"].mean(),
        "variabilidad": g["unidades_vendidas"].std().fillna(0.0),
        "tasa_promo": g["en_promocion"].mean(),
    })
    return perfil


def _perfil_compras(df: pd.DataFrame) -> pd.DataFrame:
    """Perfil por proveedor: lead time, cumplimiento y costo (separa arquetipos)."""
    g = df.groupby("id_proveedor")
    perfil = pd.DataFrame({
        "lead_time_medio": g["lead_time_dias"].mean(),
        "cumplimiento_medio": g["cumplimiento"].mean(),
        "costo_medio": g["precio_unitario_compra"].mean(),
    })
    return perfil


def _perfil_almacen(df: pd.DataFrame) -> pd.DataFrame:
    """Perfil por SKU: rotación y volumen de demanda (apoya el análisis ABC)."""
    g = df.groupby("sku")
    perfil = pd.DataFrame({
        "rotacion_media": g["rotacion"].mean(),
        "demanda_media": g["demanda_diaria_promedio"].mean(),
        "cobertura_media": g["dias_de_cobertura"].mean(),
    })
    return perfil


# ---------------------------------------------------------------------------
# Configuración por dominio
# ---------------------------------------------------------------------------
# Calendario/precio/promo son conocidos a futuro; el objetivo y sus derivadas nunca son
# features (anti-fuga). En VENTAS se EXCLUYE `ingreso` (= unidades×precio) como feature.
_VENTAS_KF = ("precio_unitario", "descuento_pct", "en_promocion", "es_fin_de_semana", "dias_a_proximo_feriado")
_VENTAS_CATS = ("categoria", "metodo_pago", "canal_venta")

# En COMPRAS, `costo_total` (= cantidad×precio) revelaría la cantidad pedida (fuga): se
# excluye. `lead_time`/`cumplimiento`/`cantidad_recibida` son post-entrega (solo pasado).
_COMPRAS_KF = ("precio_unitario_compra", "descuento_volumen")
_COMPRAS_CATS = ("categoria", "metodo_pago")
# COMPRAS es grano de **órdenes** (no días): los rezagos cuentan ÓRDENES, no jornadas, así
# que se usan ventanas cortas (1,2,3,6) en vez de las diarias (1,7,14,21,28). Si no, el
# rezago de 28 órdenes vaciaría el entrenamiento con históricos cortos.
_COMPRAS_TEMPORAL: dict[str, Any] = {
    "lags_objetivo": (1, 2, 3, 6),
    "ventanas_media_objetivo": (3, 6),
    "ventanas_std_objetivo": (3, 6),
    "ventanas_minmax_objetivo": (6,),
    "ewm_halflives": (3, 6),
    "lags_feature": (1, 2),
    "ventanas_media_feature": (3, 6),
}

# En ALMACÉN, `dias_de_cobertura` (objetivo) = stock/demanda: stock y demanda entran como
# SOLO-PASADO (sus valores del día revelarían el objetivo). La política (min/max/repo) es
# conocida a futuro.
_ALMACEN_KF = ("stock_minimo", "stock_maximo", "tiempo_reposicion_dias")
_ALMACEN_SP = ("stock_actual", "demanda_diaria_promedio", "rotacion")
_ALMACEN_CATS = ("categoria", "zona_almacen")


CONFIGS: dict[str, ConfigDominio] = {
    "ventas": ConfigDominio(
        dominio="ventas",
        spec_regresion=EspecEsquema(
            objetivo="unidades_vendidas", col_fecha="fecha",
            cols_serie=("id_tienda", "sku"),
            num_conocidas_futuro=_VENTAS_KF, num_solo_pasado=(), cats_extra=_VENTAS_CATS,
        ),
        spec_clasificacion=EspecEsquema(
            objetivo="demanda_alta", col_fecha="fecha",
            cols_serie=("id_tienda", "sku"),
            num_conocidas_futuro=_VENTAS_KF, num_solo_pasado=("unidades_vendidas",),
            cats_extra=_VENTAS_CATS,
        ),
        etiqueta="demanda_alta",
        derivar_etiqueta=_demanda_alta,
        clave_entidad="sku",
        perfil_entidades=_perfil_ventas,
        columna_volumen="volumen_medio",
        columnas_clustering=("volumen_medio", "variabilidad", "tasa_promo"),
    ),
    "compras": ConfigDominio(
        dominio="compras",
        spec_regresion=EspecEsquema(
            objetivo="cantidad_pedida", col_fecha="fecha_orden",
            cols_serie=("id_proveedor", "sku"),
            num_conocidas_futuro=_COMPRAS_KF, num_solo_pasado=("lead_time_dias",),
            cats_extra=_COMPRAS_CATS, **_COMPRAS_TEMPORAL,
        ),
        spec_clasificacion=EspecEsquema(
            objetivo="entrega_con_retraso", col_fecha="fecha_orden",
            cols_serie=("id_proveedor", "sku"),
            num_conocidas_futuro=("precio_unitario_compra", "descuento_volumen", "cantidad_pedida"),
            num_solo_pasado=(), cats_extra=_COMPRAS_CATS, **_COMPRAS_TEMPORAL,
        ),
        etiqueta="entrega_con_retraso",
        derivar_etiqueta=_entrega_con_retraso,
        clave_entidad="id_proveedor",
        perfil_entidades=_perfil_compras,
        columna_volumen="costo_medio",
        columnas_clustering=("lead_time_medio", "cumplimiento_medio", "costo_medio"),
    ),
    "almacen": ConfigDominio(
        dominio="almacen",
        spec_regresion=EspecEsquema(
            objetivo="dias_de_cobertura", col_fecha="fecha",
            cols_serie=("id_tienda", "sku"),
            num_conocidas_futuro=_ALMACEN_KF, num_solo_pasado=_ALMACEN_SP, cats_extra=_ALMACEN_CATS,
        ),
        spec_clasificacion=EspecEsquema(
            objetivo="riesgo_quiebre", col_fecha="fecha",
            cols_serie=("id_tienda", "sku"),
            num_conocidas_futuro=_ALMACEN_KF, num_solo_pasado=_ALMACEN_SP, cats_extra=_ALMACEN_CATS,
        ),
        etiqueta="riesgo_quiebre",
        derivar_etiqueta=_riesgo_quiebre,
        clave_entidad="sku",
        perfil_entidades=_perfil_almacen,
        columna_volumen="demanda_media",
        columnas_clustering=("rotacion_media", "demanda_media", "cobertura_media"),
    ),
}


def config_de(dominio: str) -> ConfigDominio:
    """Devuelve la configuración 3×3 de un dominio (``ventas``|``compras``|``almacen``)."""
    try:
        return CONFIGS[dominio]
    except KeyError:
        raise KeyError(
            f"Dominio desconocido: {dominio!r}. Use uno de {tuple(CONFIGS)}."
        ) from None
