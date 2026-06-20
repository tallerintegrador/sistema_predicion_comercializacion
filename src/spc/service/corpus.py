"""Lectura y **deduplicación** del corpus acumulado (Fase A, ADR-0011 / ADR-0013).

La persistencia (``spc.service.repositorio``) **escribe** cada ``history`` en la tabla
``observations`` y nunca deduplica en caliente (es la ruta best-effort de la predicción).
La deduplicación es responsabilidad de quien **lee** el corpus para reentrenar:

- ``scripts/exportar_corpus.py`` (puente manual de Valentín), y
- el entrenamiento por cliente bajo demanda (``spc.training.cliente``, ADR-0013).

Ambos consumen este módulo, de modo que la **regla de dedup es única** (no se duplica
lógica). La clave natural de una observación es la serie-día ``(store_id, product_id,
date)`` por cliente: si el mismo día de la misma serie se subió varias veces (envíos
repetidos), nos quedamos con la **observación más reciente** (mayor ``id``, último
submission). Así el corpus de entrenamiento refleja el último valor declarado y no
sobre-pondera días repetidos.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Mapping
from typing import Any

import pandas as pd

# Columnas del contrato presentes en ``observations`` (orden estable para el lector).
COLUMNAS = (
    "date",
    "store_id",
    "product_id",
    "units_sold",
    "on_promotion",
    "transactions",
    "event_active",
)

# Clave natural de una observación: una fila por serie-día.
CLAVE_SERIE_DIA = ["store_id", "product_id", "date"]


def leer_observaciones(
    con: sqlite3.Connection,
    client_id: str | None = None,
    *,
    dedup: bool = True,
) -> pd.DataFrame:
    """Lee ``observations`` (opc. de un ``client_id``) como frame, deduplicado por defecto.

    Ordena por ``id`` (orden de inserción = cronología de envíos) para que, al deduplicar
    quedándose con la **última** fila por serie-día, gane la observación más reciente.
    Devuelve las columnas de :data:`COLUMNAS` (sin ``client_id`` ni ``id``).
    """
    sql = f"SELECT id, client_id, {', '.join(COLUMNAS)} FROM observations"  # noqa: S608 - columnas fijas
    params: tuple[str, ...] = ()
    if client_id is not None:
        sql += " WHERE client_id = ?"
        params = (client_id,)
    sql += " ORDER BY id"
    df = pd.read_sql_query(sql, con, params=params)
    if dedup and not df.empty:
        df = df.drop_duplicates(subset=CLAVE_SERIE_DIA, keep="last")
    return df[list(COLUMNAS)].reset_index(drop=True)


def a_contrato(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Convierte filas de ``observations`` a la forma del contrato (``history``)."""
    filas: list[dict[str, Any]] = []
    for r in df.itertuples(index=False):
        filas.append(
            {
                "date": str(r.date),
                "store_id": str(r.store_id),
                "product_id": str(r.product_id),
                "units_sold": float(r.units_sold) if r.units_sold is not None else 0.0,
                "on_promotion": int(r.on_promotion) if r.on_promotion is not None else 0,
                "transactions": (None if pd.isna(r.transactions) else float(r.transactions)),
                "event_active": (None if r.event_active is None else bool(r.event_active)),
            }
        )
    return filas


def dedup_contrato(filas: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Deduplica una lista de observaciones del **contrato** por serie-día (último gana).

    Lo usa el entrenamiento por cliente al **fundir** la ``history`` del Excel subido con
    el corpus acumulado: misma regla de dedup que :func:`leer_observaciones`, aplicada
    sobre dicts del contrato (no sobre la BD). Preserva el orden de aparición; ante
    duplicados, conserva la **última** ocurrencia (la más reciente en la lista fundida).
    """
    por_clave: dict[tuple[str, str, str], dict[str, Any]] = {}
    for f in filas:
        clave = (str(f.get("store_id")), str(f.get("product_id")), str(f.get("date")))
        por_clave[clave] = dict(f)  # la última ocurrencia sobrescribe
    return list(por_clave.values())
