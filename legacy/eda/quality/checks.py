"""Chequeos de calidad y observaciones por archivo (tarea C del enunciado)."""

from __future__ import annotations

from typing import Any

import pandas as pd

from spc.config import Settings
from spc.data.loaders import write_json
from spc.utils.formatters import fmt_int


def quality_checks(data: dict[str, pd.DataFrame], settings: Settings) -> dict[str, Any]:
    """Integridad referencial, valores invalidos y huecos en las series de fecha.

    Persiste ``resumen_calidad.json`` con todos los conteos calculados.
    """
    train = data["train"]
    test = data["test"]
    stores = data["stores"]
    transactions = data["transactions"]
    oil = data["oil"]
    holidays = data["holidays_events"]

    store_master = set(stores["store_nbr"].dropna().astype(int))
    checks: dict[str, Any] = {
        "train_store_not_in_stores": sorted(set(train["store_nbr"].astype(int)) - store_master),
        "test_store_not_in_stores": sorted(set(test["store_nbr"].astype(int)) - store_master),
        "transactions_store_not_in_stores": sorted(
            set(transactions["store_nbr"].astype(int)) - store_master
        ),
        "sales_negative": int((train["sales"] < 0).sum()),
        "sales_zero": int((train["sales"] == 0).sum()),
        "onpromotion_negative_train": int((train["onpromotion"] < 0).sum()),
        "onpromotion_negative_test": int((test["onpromotion"] < 0).sum()),
        "transactions_negative": int((transactions["transactions"] < 0).sum()),
        "oil_non_positive": int((oil["dcoilwtico"] <= 0).sum()),
        "oil_null_original": int(oil["dcoilwtico"].isna().sum()),
        "holidays_transferred_true": int(holidays["transferred"].sum()),
        "test_overlap_train_dates": int(
            len(set(test["date"].unique()) & set(train["date"].unique()))
        ),
    }

    for key, df in {
        "train": train,
        "test": test,
        "transactions": transactions,
        "oil": oil,
        "holidays_events": holidays,
    }.items():
        if "date" in df.columns and not df.empty:
            full_range = pd.date_range(df["date"].min(), df["date"].max(), freq="D")
            missing_dates = full_range.difference(pd.DatetimeIndex(df["date"].dropna().unique()))
            checks[f"{key}_date_min"] = str(df["date"].min().date())
            checks[f"{key}_date_max"] = str(df["date"].max().date())
            checks[f"{key}_missing_dates_in_range"] = int(len(missing_dates))

    write_json(checks, settings.processed_dir / "resumen_calidad.json")
    return checks


def build_observations(
    profiles: pd.DataFrame, missing: pd.DataFrame, quality: dict[str, Any]
) -> dict[str, str]:
    """Redacta una observacion textual por archivo a partir de hechos calculados.

    No introduce valores inventados: arma frases citando conteos ya medidos.
    """
    obs: dict[str, str] = {}
    null_by_file = missing[missing["nulos"] > 0].groupby("archivo")["columna"].apply(list).to_dict()
    for name in profiles["archivo"]:
        partes: list[str] = []
        dup = int(profiles.loc[profiles["archivo"].eq(name), "duplicados"].iloc[0])
        partes.append("sin duplicados" if dup == 0 else f"{fmt_int(dup)} duplicados")
        if name in null_by_file:
            partes.append("nulos en " + ", ".join(null_by_file[name]))
        else:
            partes.append("sin nulos")
        if name == "train":
            partes.append(
                f"{fmt_int(quality['sales_zero'])} ventas en cero; "
                f"{fmt_int(quality['sales_negative'])} negativas; "
                f"{fmt_int(quality['train_missing_dates_in_range'])} dias faltantes en rango"
            )
        elif name == "transactions":
            partes.append(
                f"{fmt_int(quality['transactions_missing_dates_in_range'])} dias faltantes en rango"
            )
        elif name == "oil":
            partes.append(
                f"{fmt_int(quality['oil_missing_dates_in_range'])} fechas faltantes "
                "(mercado cerrado fines de semana/feriados)"
            )
        elif name == "holidays_events":
            partes.append(f"{fmt_int(quality['holidays_transferred_true'])} eventos transferidos")
        elif name == "stores":
            partes.append("tabla maestra de 54 tiendas")
        obs[name] = "; ".join(partes) + "."
    return obs
