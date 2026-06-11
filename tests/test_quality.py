"""Tests de perfilado y chequeos de calidad sobre data sintetica."""

from __future__ import annotations

from spc.quality.checks import build_observations, quality_checks
from spc.quality.profiling import build_profiles, profile_dataframe


def test_profile_dataframe_cuenta_filas_y_fechas(synthetic_data):
    prof = profile_dataframe("train", synthetic_data["train"])
    assert prof["filas"] == 12
    assert prof["tiendas_unicas"] == 2
    assert prof["familias_unicas"] == 2
    assert prof["rango_fechas"] == "2014-01-01 a 2014-01-03"
    assert prof["duplicados"] == 0


def test_build_profiles_persiste_csv(synthetic_data, settings):
    profiles, missing = build_profiles(synthetic_data, settings)
    assert set(profiles["archivo"]) == set(synthetic_data.keys())
    assert (settings.processed_dir / "resumen_perfil_archivos.csv").exists()
    assert (settings.processed_dir / "resumen_nulos_columnas.csv").exists()
    # oil tiene un nulo? no en la fixture; pero la tabla de nulos debe existir por columna
    assert {"archivo", "columna", "nulos", "pct_nulos"} <= set(missing.columns)


def test_quality_checks_detecta_referencias_y_transferidos(synthetic_data, settings):
    checks = quality_checks(synthetic_data, settings)
    assert checks["train_store_not_in_stores"] == []
    assert checks["sales_negative"] == 0
    assert checks["sales_zero"] == 1  # el id 0 tiene sales=0
    assert checks["holidays_transferred_true"] == 1
    assert checks["test_overlap_train_dates"] == 0
    assert (settings.processed_dir / "resumen_calidad.json").exists()


def test_build_observations_menciona_hechos(synthetic_data, settings):
    profiles, missing = build_profiles(synthetic_data, settings)
    checks = quality_checks(synthetic_data, settings)
    obs = build_observations(profiles, missing, checks)
    assert "ventas en cero" in obs["train"]
    assert "eventos transferidos" in obs["holidays_events"]
    assert obs["train"].endswith(".")
