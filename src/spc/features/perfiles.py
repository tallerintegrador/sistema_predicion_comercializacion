"""Perfiles agregados para clustering/perfilado (Fase 2c).

A diferencia de la 2a/2b (features **por fila** para predecir la venta de un dia),
aqui la serie historica de cada entidad se **agrega a un solo vector**: un perfil
por tienda (``store_nbr``) y un perfil por familia (``family``). Sobre esos perfiles
se entrena KMeans para segmentar.

Funciones **puras y reutilizadas en entrenamiento y en prediccion**: el mismo
calculo que produce los perfiles de entrenamiento asigna una **entidad nueva** a su
segmento (se le pasa su historico ya integrado y se reagrega igual). Esto es lo que
hace portable al perfilador: el scaler + KMeans del artefacto reciben un vector
construido con esta misma logica.

Entrada esperada: un dataframe con el **esquema del dataset analitico integrado**
(salida de ``spc.data.integration.build_analytic_dataset``): al menos ``store_nbr``,
``family``, ``sales``, ``onpromotion``, ``transactions_filled``, ``demanda_alta`` e
``is_weekend``.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Diccionario de features de perfil (documentacion del entregable)
# ---------------------------------------------------------------------------
# Cada entrada: nombre -> (descripcion, senal de negocio). El reporte 2c lo
# imprime tal cual, de modo que la tabla de perfiles sea autoexplicativa.
PERFIL_TIENDAS_DICT: dict[str, str] = {
    "venta_media": "Venta media diaria de la tienda (unidades). Nivel de demanda.",
    "venta_mediana": "Venta mediana diaria (robusta a la cola larga). Nivel tipico.",
    "cv_ventas": "Coef. de variacion (std/media) de la venta. Dispersion/volatilidad.",
    "tasa_ceros": "Fraccion de observaciones tienda-familia-dia con venta 0. Intermitencia.",
    "ventas_total": "Volumen total historico (suma de unidades). Tamano de la tienda.",
    "promo_media": "Intensidad de promocion (`onpromotion` medio). Apoyo comercial.",
    "transacciones_media": "Transacciones medias diarias. Flujo de clientes.",
    "ratio_finde": "Venta media de fin de semana / entre semana. Estacionalidad operativa.",
    "pct_demanda_alta": "Fraccion de filas con `demanda_alta=1` (>P75 de su familia).",
}

PERFIL_FAMILIAS_DICT: dict[str, str] = {
    "venta_media": "Venta media diaria de la familia (unidades). Nivel de demanda.",
    "tasa_ceros": "Fraccion de observaciones con venta 0. Intermitencia de la familia.",
    "cv_ventas": "Coef. de variacion (std/media). Dispersion/volatilidad.",
    "sensibilidad_promo": "Venta media con promo - sin promo (unidades). Respuesta a promocion.",
    "ventas_total": "Volumen total historico de la familia (suma de unidades). Peso/tamano.",
    "promo_media": "Intensidad de promocion (`onpromotion` medio).",
    "pct_demanda_alta": "Fraccion de filas con `demanda_alta=1` (>P75 de su familia).",
}

# --- Set RICO: universo de features que produce la agregacion (perfiles_*) ---
# Es el conjunto del que el diagnostico de contribucion (Fase 2c, refinamiento) elige
# el set DESPLEGADO. perfiles_tiendas/perfiles_familias devuelven estas columnas.
COLS_TIENDAS_RICO: list[str] = list(PERFIL_TIENDAS_DICT)
COLS_FAMILIAS_RICO: list[str] = list(PERFIL_FAMILIAS_DICT)

# --- Set DESPLEGADO: features que entran a KMeans (orden estable) ---
# Elegido por DIAGNOSTICO de contribucion (leave-one-out de silueta + correlacion con
# el volumen + PCA), no por "mas features por defecto". Solo las que SEPARAN; las demas
# bajan la silueta (polizones del volumen) y quedan como co-variables descriptivas.
#  - Tiendas: set depurado -> mejor silueta (0.67 vs 0.46 del set rico), corte limpio
#    por volumen. `cv_ventas`/`tasa_ceros`/`ratio_finde`/`promo_media`/`transacciones_media`
#    suben la silueta al quitarse (LOO delta>0) -> fuera del clustering.
#  - Familias: set alineado al EDA -> a k=3 aisla las familias intermitentes en su
#    propio segmento (accionable). Coincide con `COLS_FAMILIAS_EDA`.
# El perfilador congela estas columnas en el artefacto para construir el vector de una
# entidad nueva en el mismo orden.
COLS_TIENDAS: list[str] = ["venta_media", "venta_mediana", "ventas_total", "pct_demanda_alta"]
COLS_FAMILIAS: list[str] = ["ventas_total", "venta_media", "promo_media", "pct_demanda_alta"]

# --- Co-variables descriptivas: se reportan por segmento pero NO entran a KMeans ---
# Correlacionan con el volumen (son el mismo eje medido distinto) o no separan; el
# diagnostico las descarto del clustering. Se muestran en la tabla de perfiles como
# co-variables para transparencia (la separacion es por volumen, no multidimensional).
COLS_TIENDAS_DESC: list[str] = [c for c in COLS_TIENDAS_RICO if c not in COLS_TIENDAS]
COLS_FAMILIAS_DESC: list[str] = [c for c in COLS_FAMILIAS_RICO if c not in COLS_FAMILIAS]

# --- Sets EXACTOS del EDA (para reproducir la silueta ~0.61 / ~0.71) ---
# El EDA (`spc.eda.analysis.clustering`) agrupo con estas columnas; el reporte 2c
# las recalcula para mostrar que el pipeline recupera el orden de magnitud del EDA.
# Nota: en FAMILIAS el set desplegado (`COLS_FAMILIAS`) coincide con el del EDA
# (`COLS_FAMILIAS_EDA`); la diferencia desplegado vs validacion esta en el **k** (k=3
# desplegado por accionabilidad vs k=2 del EDA), no en las features.
COLS_TIENDAS_EDA: list[str] = [
    "ventas_total",
    "venta_media",
    "venta_mediana",
    "promo_media",
    "transacciones_media",
    "pct_demanda_alta",
]
COLS_FAMILIAS_EDA: list[str] = [
    "ventas_total",
    "venta_media",
    "promo_media",
    "pct_demanda_alta",
]

CLAVE_TIENDA = "store_nbr"
CLAVE_FAMILIA = "family"


# ---------------------------------------------------------------------------
# Agregacion base compartida (una pasada de groupby por clave)
# ---------------------------------------------------------------------------
def _agregados_base(df: pd.DataFrame, clave: str) -> pd.DataFrame:
    """Agrega por ``clave`` las estadisticas comunes a tiendas y familias.

    Devuelve un frame indexado por ``clave`` con: media, mediana, std, total,
    tasa de ceros, promo media, demanda alta y (si existe) transacciones medias.
    """
    # Solo las columnas necesarias (evita copiar el dataset analitico entero: 3M filas).
    usar = [clave, "sales", "onpromotion", "demanda_alta"]
    if "transactions_filled" in df.columns:
        usar.append("transactions_filled")
    base = df[usar].copy()
    base["_es_cero"] = base["sales"].to_numpy() == 0
    agg: dict[str, tuple[str, str]] = {
        "venta_media": ("sales", "mean"),
        "venta_mediana": ("sales", "median"),
        "_venta_std": ("sales", "std"),
        "ventas_total": ("sales", "sum"),
        "tasa_ceros": ("_es_cero", "mean"),
        "promo_media": ("onpromotion", "mean"),
        "pct_demanda_alta": ("demanda_alta", "mean"),
    }
    if "transactions_filled" in base.columns:
        agg["transacciones_media"] = ("transactions_filled", "mean")
    prof = base.groupby(clave, observed=True).agg(**agg)

    # CV = std/media; std NaN (grupo de 1 fila) o media 0 -> CV 0 (sin dispersion util).
    media = prof["venta_media"].to_numpy(dtype="float64")
    std = prof["_venta_std"].fillna(0.0).to_numpy(dtype="float64")
    with np.errstate(divide="ignore", invalid="ignore"):
        cv = np.where(media > 0, std / media, 0.0)
    prof["cv_ventas"] = cv
    prof = prof.drop(columns=["_venta_std"])
    return prof


def _ratio_finde(df: pd.DataFrame, clave: str) -> pd.Series:
    """Venta media de fin de semana / entre semana por ``clave``.

    Si la entidad no tiene dias de una de las dos clases (o la base es 0), el ratio
    cae a 1.0 (neutro: sin efecto de fin de semana medible).
    """
    medias = (
        df.groupby([clave, "is_weekend"], observed=True)["sales"].mean().unstack("is_weekend")
    )
    finde = medias.get(True)
    semana = medias.get(False)
    if finde is None or semana is None:
        return pd.Series(1.0, index=medias.index, name="ratio_finde")
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = finde / semana.where(semana > 0, np.nan)
    return ratio.fillna(1.0).rename("ratio_finde")


def _sensibilidad_promo(df: pd.DataFrame, clave: str) -> pd.Series:
    """Diferencia de venta media con promo vs sin promo por ``clave`` (unidades).

    Si la entidad nunca tiene (o siempre tiene) promocion, la diferencia cae a 0.0
    (sin contraste medible).
    """
    con = df["onpromotion"].to_numpy() > 0
    tmp = df[[clave, "sales"]].copy()
    tmp["_con_promo"] = con
    medias = tmp.groupby([clave, "_con_promo"], observed=True)["sales"].mean().unstack("_con_promo")
    alta = medias.get(True)
    baja = medias.get(False)
    if alta is None or baja is None:
        return pd.Series(0.0, index=medias.index, name="sensibilidad_promo")
    return (alta - baja).fillna(0.0).rename("sensibilidad_promo")


# ---------------------------------------------------------------------------
# Perfiles de produccion (set rico, interpretable)
# ---------------------------------------------------------------------------
def perfiles_tiendas(analytic: pd.DataFrame) -> pd.DataFrame:
    """Un perfil por ``store_nbr`` con el set RICO de features (``COLS_TIENDAS_RICO``).

    Devuelve un frame con la clave ``store_nbr`` como columna mas **todas** las features
    de perfil (universo del diagnostico). El clustering usa solo el subconjunto desplegado
    (``COLS_TIENDAS``); el resto se reporta como co-variables descriptivas. Reutilizable
    en prediccion (1 tienda -> 1 fila): el perfilador selecciona ``COLS_TIENDAS`` de aqui.
    """
    prof = _agregados_base(analytic, CLAVE_TIENDA)
    prof = prof.join(_ratio_finde(analytic, CLAVE_TIENDA))
    prof["ratio_finde"] = prof["ratio_finde"].fillna(1.0)
    prof = prof.reindex(columns=COLS_TIENDAS_RICO)
    return prof.reset_index()


def perfiles_familias(analytic: pd.DataFrame) -> pd.DataFrame:
    """Un perfil por ``family`` con el set RICO de features (``COLS_FAMILIAS_RICO``).

    Incluye ``sensibilidad_promo`` (contraste de venta con/sin promo) y
    ``ventas_total`` (volumen absoluto, **self-contained**: se calcula desde el
    historico de la propia familia, sin depender del catalogo completo, de modo que el
    perfilador asigna una familia nueva sin reagregar el resto). Devuelve todas las
    features; el clustering usa solo el subconjunto desplegado (``COLS_FAMILIAS``) y el
    resto se reporta como co-variables descriptivas. Reutilizable en prediccion.
    """
    prof = _agregados_base(analytic, CLAVE_FAMILIA)
    prof = prof.join(_sensibilidad_promo(analytic, CLAVE_FAMILIA))
    prof["sensibilidad_promo"] = prof["sensibilidad_promo"].fillna(0.0)
    prof = prof.reindex(columns=COLS_FAMILIAS_RICO)
    return prof.reset_index()


# ---------------------------------------------------------------------------
# Perfiles "EDA" (reproduccion del orden de magnitud de la silueta)
# ---------------------------------------------------------------------------
def perfiles_tiendas_eda(analytic: pd.DataFrame) -> pd.DataFrame:
    """Perfil de tiendas con las columnas EXACTAS del EDA (``COLS_TIENDAS_EDA``)."""
    prof = _agregados_base(analytic, CLAVE_TIENDA)
    return prof.reindex(columns=COLS_TIENDAS_EDA).reset_index()


def perfiles_familias_eda(analytic: pd.DataFrame) -> pd.DataFrame:
    """Perfil de familias con las columnas EXACTAS del EDA (``COLS_FAMILIAS_EDA``)."""
    prof = _agregados_base(analytic, CLAVE_FAMILIA)
    return prof.reindex(columns=COLS_FAMILIAS_EDA).reset_index()
