"""Adaptador contrato → motor: la frontera donde se traduce.

El cliente envía el bloque ``history`` con **nombres genéricos** del contrato
(``date``, ``store_id``, ``product_id``, ``units_sold``, ...). El
motor de ML, en cambio, consume el **esquema del dataset analítico integrado**
(``date``, ``store_nbr``, ``family``, ``sales``, ``onpromotion``,
``transactions_filled``, calendario, feriados y categóricas). Este módulo hace esa
traducción y deja el frame listo para `construir_features` (regresión/clasificación)
y para `perfiles_*` (clustering).

Decisiones de diseño (documentadas, degradan con elegancia):

- El **calendario** (``year``..``is_payday``) se **deriva de ``fecha``**, igual que
  en el dataset analítico real.
- ``event_active`` → ``holiday_any``; los feriados por alcance
  (``holiday_national/regional/local/event_count``) se ponen a 0 (el cliente no los
  envía y el contrato no los pide).
- ``dcoilwtico`` (petróleo) y los metadatos de tienda (``type``, ``city``,
  ``state``, ``cluster``) **no están en el contrato** (sector-agnóstico): se rellenan
  como **desconocidos**. Bajo el ``CategoricalDtype`` fijo del artefacto, las
  categóricas desconocidas caen a ``NaN`` (los modelos de árbol lo toleran). El
  pronóstico se sostiene sobre los rezagos/calendario; la pérdida de nivel categórico
  es la degradación esperada del *cold-start* de un cliente nuevo.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

import numpy as np
import pandas as pd

from spc.service.errores import SolicitudInvalida

# Columnas categóricas del motor que el contrato no provee: se marcan desconocidas.
_SENTINEL_TEXTO = "DESCONOCIDO"
_SENTINEL_CLUSTER = -1


def historico_a_analitico(historico: Iterable[Mapping[str, Any]]) -> pd.DataFrame:
    """Traduce el bloque ``historico`` del contrato al esquema del dataset analítico.

    ``historico`` es una secuencia de mapeos con las claves del contrato
    (``date``, ``store_id``, ``product_id``, ``units_sold`` y, opc.,
    ``on_promotion``, ``transactions``, ``event_active``). Devuelve un ``DataFrame``
    con **todas** las columnas que `construir_features`/`perfiles_*` esperan,
    ordenado por serie y fecha.
    """
    filas = list(historico)
    if not filas:
        raise SolicitudInvalida("El histórico no contiene observaciones.")

    df = pd.DataFrame(
        {
            "date": pd.to_datetime([f["date"] for f in filas]),
            # Identificadores como texto: el contrato los admite str/int y la API ya
            # los normalizó a str. El motor agrupa la serie por (store_nbr, family).
            "store_nbr": [str(f["store_id"]) for f in filas],
            "family": [str(f["product_id"]) for f in filas],
            "sales": np.asarray([float(f["units_sold"]) for f in filas], dtype="float64"),
            "onpromotion": np.asarray(
                [int(f.get("on_promotion") or 0) for f in filas], dtype="int64"
            ),
            "transactions_filled": [
                (float(f["transactions"]) if f.get("transactions") is not None else np.nan)
                for f in filas
            ],
            # Petróleo desconocido (no está en el contrato): NaN -> features de oil neutras.
            "dcoilwtico": np.nan,
            # Feriado/evento: el contrato solo trae un booleano agregado.
            "holiday_any": [bool(f.get("event_active")) for f in filas],
        }
    )
    df["transactions_filled"] = df["transactions_filled"].astype("float64")

    # Metadatos de tienda desconocidos (no están en el contrato): categóricas que el
    # artefacto mapeará a NaN bajo su CategoricalDtype fijo.
    df["type"] = _SENTINEL_TEXTO
    df["city"] = _SENTINEL_TEXTO
    df["state"] = _SENTINEL_TEXTO
    df["cluster"] = _SENTINEL_CLUSTER

    df = _decorar_calendario(df)
    return df.sort_values(["store_nbr", "family", "date"]).reset_index(drop=True)


def _decorar_calendario(df: pd.DataFrame) -> pd.DataFrame:
    """Deriva las columnas de calendario/feriados desde ``date`` (conocidas a futuro).

    Replica las columnas del dataset analítico: ``year``..``is_payday`` y los feriados
    por alcance a 0 (el contrato solo trae ``holiday_any`` vía ``event_active``).
    """
    fecha = df["date"]
    df["year"] = fecha.dt.year.astype("int16")
    df["month"] = fecha.dt.month.astype("int8")
    df["day"] = fecha.dt.day.astype("int8")
    df["dayofweek"] = fecha.dt.dayofweek.astype("int8")
    df["is_weekend"] = df["dayofweek"] >= 5
    df["is_month_end"] = fecha.dt.is_month_end
    df["is_payday"] = (df["day"] == 15) | df["is_month_end"]
    for c in ("holiday_national", "holiday_regional", "holiday_local", "holiday_event_count"):
        df[c] = np.int16(0)
    if "holiday_any" not in df.columns:
        df["holiday_any"] = False
    return df


def agregar_esqueleto_futuro(
    analitico: pd.DataFrame, horizonte: int
) -> tuple[pd.DataFrame, pd.Timestamp, pd.Timestamp]:
    """Añade las filas futuras del horizonte por serie (calendario conocido, ``sales``=NaN).

    El pronóstico recursivo del motor (`pronosticar_horizonte`) necesita las filas del
    horizonte ya presentes con el calendario y la promoción planificada conocidos; el
    valor de ``sales`` se ignora y se sobreescribe. El horizonte arranca el día
    **siguiente a la fecha máxima** del histórico y es contiguo. La promoción futura
    no la trae el contrato → se asume 0.
    """
    if horizonte <= 0:
        raise SolicitudInvalida("El horizonte debe ser un entero positivo.")
    ultima = pd.Timestamp(analitico["date"].max())
    inicio = ultima + pd.Timedelta(days=1)
    fin = ultima + pd.Timedelta(days=horizonte)
    fechas_futuras = pd.date_range(inicio, fin, freq="D")

    # Una fila futura por cada serie (store_nbr, family) presente en el histórico.
    series = analitico[["store_nbr", "family"]].drop_duplicates()
    futuro = series.merge(pd.DataFrame({"date": fechas_futuras}), how="cross")
    futuro["sales"] = np.nan
    futuro["onpromotion"] = np.int64(0)
    futuro["transactions_filled"] = np.nan
    futuro["dcoilwtico"] = np.nan
    futuro["type"] = _SENTINEL_TEXTO
    futuro["city"] = _SENTINEL_TEXTO
    futuro["state"] = _SENTINEL_TEXTO
    futuro["cluster"] = _SENTINEL_CLUSTER
    futuro["holiday_any"] = False
    futuro = _decorar_calendario(futuro)

    completo = pd.concat([analitico, futuro[analitico.columns]], ignore_index=True)
    completo = completo.sort_values(["store_nbr", "family", "date"]).reset_index(drop=True)
    return completo, inicio, fin


def marcar_demanda_alta(analitico: pd.DataFrame) -> pd.DataFrame:
    """Añade ``demanda_alta = sales > P75 de su familia`` (definición del contrato).

    El clustering/perfilado usa ``pct_demanda_alta`` como feature, así que la columna
    debe existir antes de perfilar. Se calcula sobre el histórico recibido (P75 por
    familia), tal como define el contrato de ALMACÉN.
    """
    df = analitico.copy()
    p75 = df.groupby("family", observed=True)["sales"].transform(lambda s: s.quantile(0.75))
    df["demanda_alta"] = (df["sales"].to_numpy() > p75.to_numpy()).astype("int8")
    return df


def series_disponibles(analitico: pd.DataFrame) -> set[tuple[str, str]]:
    """Conjunto de series ``(store_nbr, family)`` presentes en el histórico."""
    pares = analitico[["store_nbr", "family"]].drop_duplicates()
    return {(str(s), str(f)) for s, f in zip(pares["store_nbr"], pares["family"], strict=True)}
