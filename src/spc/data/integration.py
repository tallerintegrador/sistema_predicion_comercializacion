"""Construccion del dataset analitico integrado (tarea H del enunciado).

Une ventas con tiendas, transacciones, petroleo y feriados; deriva variables de
calendario y el objetivo de clasificacion ``demanda_alta``. Devuelve tambien un
catalogo de columnas (documentacion) y un resumen de integracion.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from spc.config import Settings
from spc.data.holidays import aggregate_holidays
from spc.data.loaders import write_csv, write_json
from spc.utils.formatters import pct

# Descripcion (texto, no datos) de cada columna del dataset integrado, por origen.
COLUMN_CATALOG: dict[str, tuple[str, str]] = {
    "id": ("train", "Identificador unico de fila"),
    "date": ("train", "Fecha de la observacion"),
    "store_nbr": ("train", "Numero de tienda"),
    "family": ("train", "Familia de producto"),
    "sales": ("train", "OBJETIVO: ventas (unidades) tienda-familia-dia"),
    "onpromotion": ("train", "Articulos de la familia en promocion ese dia"),
    "city": ("stores", "Ciudad de la tienda"),
    "state": ("stores", "Provincia/estado de la tienda"),
    "type": ("stores", "Tipo de tienda (A-E)"),
    "cluster": ("stores", "Cluster comercial original de la tienda"),
    "transactions": ("transactions", "Transacciones de la tienda ese dia (crudo, con nulos)"),
    "transactions_missing": ("derivada", "Bandera: transacciones ausentes al integrar"),
    "transactions_filled": ("derivada", "Transacciones con faltantes imputados a 0"),
    "dcoilwtico": ("oil", "Precio WTI del petroleo (reindexado + ffill/bfill)"),
    "dcoilwtico_original_missing": ("derivada", "Bandera: cotizacion de petroleo imputada"),
    "holiday_national": ("holidays", "Conteo de feriados nacionales activos ese dia"),
    "holiday_national_types": ("holidays", "Tipos de feriado nacional activos"),
    "holiday_regional": ("holidays", "Feriados regionales activos (por estado)"),
    "holiday_local": ("holidays", "Feriados locales activos (por ciudad)"),
    "holiday_any": ("derivada", "Bandera: algun feriado/evento activo"),
    "holiday_event_count": ("derivada", "Suma de feriados activos de todos los alcances"),
    "year": ("calendario", "Anio"),
    "month": ("calendario", "Mes"),
    "day": ("calendario", "Dia del mes"),
    "dayofweek": ("calendario", "Dia de semana (0=Lun)"),
    "is_weekend": ("calendario", "Bandera fin de semana"),
    "is_month_end": ("calendario", "Bandera fin de mes"),
    "is_payday": ("calendario", "Bandera quincena (dia 15 o fin de mes)"),
    "family_sales_p75": ("derivada", "P75 de sales dentro de la familia"),
    "demanda_alta": ("derivada", "OBJETIVO clasif.: sales > P75 de su familia"),
}


def build_analytic_dataset(
    data: dict[str, pd.DataFrame], settings: Settings
) -> tuple[pd.DataFrame, dict[str, Any], pd.DataFrame]:
    """Integra todas las fuentes y deriva variables. Persiste catalogo y resumen."""
    train = data["train"]
    stores = data["stores"]
    transactions = data["transactions"]
    oil = data["oil"]
    holidays = data["holidays_events"]

    analytic = train.merge(stores, on="store_nbr", how="left", validate="many_to_one")
    analytic = analytic.merge(
        transactions, on=["date", "store_nbr"], how="left", validate="many_to_one"
    )
    analytic["transactions_missing"] = analytic["transactions"].isna()
    analytic["transactions_filled"] = analytic["transactions"].fillna(0).astype("int32")

    full_dates = pd.DataFrame(
        {"date": pd.date_range(train["date"].min(), train["date"].max(), freq="D")}
    )
    oil_full = full_dates.merge(oil, on="date", how="left")
    oil_full["dcoilwtico_original_missing"] = oil_full["dcoilwtico"].isna()
    oil_full["dcoilwtico"] = oil_full["dcoilwtico"].ffill().bfill()
    analytic = analytic.merge(oil_full, on="date", how="left", validate="many_to_one")

    national, regional, local = aggregate_holidays(holidays)
    analytic = analytic.merge(national, on="date", how="left", validate="many_to_one")
    analytic = analytic.merge(regional, on=["date", "state"], how="left", validate="many_to_one")
    analytic = analytic.merge(local, on=["date", "city"], how="left", validate="many_to_one")

    for col in ["holiday_national", "holiday_regional", "holiday_local"]:
        analytic[col] = analytic[col].fillna(0).astype("int16")
    analytic["holiday_any"] = (
        analytic[["holiday_national", "holiday_regional", "holiday_local"]].sum(axis=1) > 0
    )
    analytic["holiday_event_count"] = (
        analytic[["holiday_national", "holiday_regional", "holiday_local"]]
        .sum(axis=1)
        .astype("int16")
    )
    # astype("object") evita el TypeError de pandas 3.0 al rellenar una columna
    # categorica (el resultado del groupby puede heredar el dtype category de `type`).
    analytic["holiday_national_types"] = (
        analytic["holiday_national_types"].astype("object").fillna("Sin evento nacional")
    )

    analytic["year"] = analytic["date"].dt.year.astype("int16")
    analytic["month"] = analytic["date"].dt.month.astype("int8")
    analytic["day"] = analytic["date"].dt.day.astype("int8")
    analytic["dayofweek"] = analytic["date"].dt.dayofweek.astype("int8")
    analytic["is_weekend"] = analytic["dayofweek"].isin([5, 6])
    analytic["is_month_end"] = analytic["date"].dt.is_month_end
    analytic["is_payday"] = analytic["day"].eq(15) | analytic["is_month_end"]

    p75_family = (
        train.groupby("family", observed=True)["sales"].quantile(0.75).rename("family_sales_p75")
    )
    analytic = analytic.merge(
        p75_family.reset_index(), on="family", how="left", validate="many_to_one"
    )
    analytic["demanda_alta"] = analytic["sales"] > analytic["family_sales_p75"]

    catalog = pd.DataFrame(
        [
            {
                "columna": col,
                "tipo": str(analytic[col].dtype),
                "origen": COLUMN_CATALOG.get(col, ("?", ""))[0],
                "descripcion": COLUMN_CATALOG.get(col, ("?", ""))[1],
            }
            for col in analytic.columns
        ]
    )
    write_csv(catalog, settings.processed_dir / "catalogo_columnas.csv")

    integration_info = {
        "filas": int(analytic.shape[0]),
        "columnas": int(analytic.shape[1]),
        "transactions_missing_rows": int(analytic["transactions_missing"].sum()),
        "transactions_missing_pct": pct(analytic["transactions_missing"].sum(), len(analytic)),
        "oil_original_missing_dates_after_reindex": int(
            oil_full["dcoilwtico_original_missing"].sum()
        ),
        "oil_missing_after_fill": int(oil_full["dcoilwtico"].isna().sum()),
        "holiday_any_rows": int(analytic["holiday_any"].sum()),
        "holiday_any_pct": pct(analytic["holiday_any"].sum(), len(analytic)),
        "n_predictoras": int(analytic.shape[1] - 3),  # excluye id, date, sales
    }
    write_json(integration_info, settings.processed_dir / "resumen_integracion.json")
    return analytic, integration_info, catalog
