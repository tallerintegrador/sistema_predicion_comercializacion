"""Agregacion de feriados/eventos por alcance (nacional, regional, local).

Los registros con ``transferred=True`` no cuentan como feriados activos: el feriado
se traslado a otra fecha, por lo que ese dia es laborable normal.
"""

from __future__ import annotations

import pandas as pd


def aggregate_holidays(
    holidays: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Devuelve tres tablas de conteos: nacional (por fecha), regional (fecha-estado)
    y local (fecha-ciudad)."""
    active = holidays.loc[~holidays["transferred"]].copy()
    active["holiday_event_count"] = 1

    national = (
        active.loc[active["locale"].astype(str).eq("National")]
        .groupby("date", observed=True)
        .agg(
            holiday_national=("holiday_event_count", "sum"),
            holiday_national_types=("type", lambda s: ", ".join(sorted(set(map(str, s))))),
        )
        .reset_index()
    )
    regional = (
        active.loc[active["locale"].astype(str).eq("Regional")]
        .rename(columns={"locale_name": "state"})
        .groupby(["date", "state"], observed=True)
        .agg(holiday_regional=("holiday_event_count", "sum"))
        .reset_index()
    )
    local = (
        active.loc[active["locale"].astype(str).eq("Local")]
        .rename(columns={"locale_name": "city"})
        .groupby(["date", "city"], observed=True)
        .agg(holiday_local=("holiday_event_count", "sum"))
        .reset_index()
    )
    return national, regional, local
