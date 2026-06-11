"""Tests de integracion de fuentes y agregacion de feriados."""

from __future__ import annotations

from spc.features.holidays import aggregate_holidays
from spc.features.integration import build_analytic_dataset


def test_aggregate_holidays_excluye_transferidos(synthetic_data):
    national, regional, local = aggregate_holidays(synthetic_data["holidays_events"])
    # solo el 2014-01-01 cuenta; el 2014-01-02 esta transferido
    assert len(national) == 1
    assert national["holiday_national"].iloc[0] == 1
    assert regional.empty
    assert local.empty


def test_build_analytic_dataset_merges_y_derivadas(synthetic_data, settings):
    analytic, info, catalog = build_analytic_dataset(synthetic_data, settings)

    # mismas filas que train
    assert len(analytic) == len(synthetic_data["train"])
    # columnas geograficas integradas
    assert {"city", "state", "type", "cluster"} <= set(analytic.columns)

    # transacciones faltantes marcadas: falta (tienda 2, dia 3) -> 2 filas (familias A y B)
    assert analytic["transactions_missing"].sum() == 2
    assert (analytic["transactions_filled"] >= 0).all()

    # petroleo reindexado y rellenado: sin nulos tras el fill
    assert analytic["dcoilwtico"].isna().sum() == 0
    assert analytic["dcoilwtico_original_missing"].sum() >= 1

    # feriado nacional activo solo el 2014-01-01
    activos = analytic.loc[analytic["holiday_national"] > 0, "date"].dt.date.unique()
    assert list(activos) == [__import__("datetime").date(2014, 1, 1)]

    # objetivo de clasificacion derivado
    assert analytic["demanda_alta"].dtype == bool
    assert "family_sales_p75" in analytic.columns

    # resumen y catalogo coherentes
    assert info["filas"] == len(analytic)
    assert info["columnas"] == analytic.shape[1]
    assert info["n_predictoras"] == analytic.shape[1] - 3
    assert set(catalog["columna"]) == set(analytic.columns)
    assert (settings.processed_dir / "catalogo_columnas.csv").exists()
    assert (settings.processed_dir / "resumen_integracion.json").exists()
