"""Tests del modelo de regresion: supera al baseline y el artefacto recarga."""

from __future__ import annotations

import numpy as np

from spc.config import Settings
from spc.models.regresion import entrenar_y_comparar, serializar_artefacto
from spc.utils.serializacion import cargar_artefacto


def test_modelo_supera_al_baseline(analitico_sintetico):
    """En una muestra aprendible el ganador supera al mejor baseline (MAE y RMSE)."""
    res = entrenar_y_comparar(
        analitico_sintetico, Settings(), max_train_rows=None, con_cv=False
    )
    base_mae = min(v["MAE"] for v in res.metricas_baseline.values())
    base_rmse = min(v["RMSE"] for v in res.metricas_baseline.values())
    assert res.metricas_test_mejor["MAE"] < base_mae
    assert res.metricas_test_mejor["RMSE"] < base_rmse


def test_artefacto_serializa_recarga_y_predice_igual(analitico_sintetico, tmp_path):
    """El artefacto debe poder cargarse y predecir lo mismo sin reentrenar."""
    settings = Settings(base_dir=tmp_path)
    res = entrenar_y_comparar(
        analitico_sintetico, settings, max_train_rows=None, con_cv=False
    )
    pred_antes = res.predictor.predecir(analitico_sintetico).to_numpy()

    ruta_art, ruta_meta = serializar_artefacto(res, settings)
    assert ruta_art.exists() and ruta_meta.exists()

    predictor2, meta = cargar_artefacto(ruta_art)
    pred_despues = predictor2.predecir(analitico_sintetico).to_numpy()

    assert np.allclose(pred_antes, pred_despues)
    assert meta["transformacion_objetivo"] in ("log1p", "identidad")
    assert meta["escala_metricas"] == "unidades"
    assert meta["modelo"] == res.mejor_modelo

    # Predecir sobre un SUBCONJUNTO (una sola serie) debe funcionar: el dtype
    # categorico se reaplica exacto aunque no aparezcan todos los niveles.
    sub = analitico_sintetico[analitico_sintetico["store_nbr"] == 1]
    pred_sub = predictor2.predecir(sub)
    assert len(pred_sub) == len(sub)
    assert (pred_sub >= 0).all()


def test_ridge_pipeline_no_explota(analitico_sintetico):
    """Ridge en pipeline (one-hot + escala) ya no dispara `expm1` a valores absurdos."""
    res = entrenar_y_comparar(
        analitico_sintetico, Settings(), max_train_rows=None, con_cv=False
    )
    ridge = res.metricas[
        (res.metricas["modelo"] == "Ridge") & (res.metricas["split"] == "test")
    ]
    assert not ridge.empty
    mae = float(ridge["MAE"].iloc[0])
    r2 = float(ridge["R2"].iloc[0])
    assert np.isfinite(mae) and np.isfinite(r2)
    # Sin explosion exponencial: MAE del orden de las ventas y R2 no catastrofico.
    assert mae < 1e3
    assert r2 > 0.0


def test_metadatos_artefacto_completos(analitico_sintetico, tmp_path):
    """Los metadatos del artefacto incluyen todo lo exigido por el criterio de hecho."""
    settings = Settings(base_dir=tmp_path)
    res = entrenar_y_comparar(
        analitico_sintetico, settings, max_train_rows=None, con_cv=False
    )
    _, ruta_meta = serializar_artefacto(res, settings)
    import json

    meta = json.loads(ruta_meta.read_text(encoding="utf-8"))
    for clave in (
        "version",
        "fecha_entrenamiento",
        "modelo",
        "semilla",
        "features",
        "transformacion_objetivo",
        "criterio_seleccion",
        "n_filas_artefacto_final",
        "metricas_test",
    ):
        assert clave in meta, clave
    assert meta["features"]  # lista de features no vacia
    assert meta["semilla"] == settings.random_seed
    assert meta["n_filas_artefacto_final"] >= meta["n_filas_comparacion"]


def test_metrica_honesta_recursiva_supera_baseline(analitico_sintetico):
    """La metrica guia (WAPE recursivo honesto) existe y mejora al mejor baseline."""
    res = entrenar_y_comparar(
        analitico_sintetico, Settings(), max_train_rows=None, con_cv=False
    )
    rec = res.metricas_test_recursivo
    base = res.metricas_baseline_recursivo
    assert rec and "WAPE" in rec
    wape_modelo = rec["WAPE"]
    assert np.isfinite(wape_modelo)
    # Sobre datos AR(1) aprendibles el pronostico recursivo bate a los baselines
    # honestos (naive t-7 y media movil 7) evaluados de la misma forma.
    mejor_baseline = min(v["WAPE"] for v in base.values())
    assert wape_modelo < mejor_baseline


def test_pronostico_recursivo_multihorizonte(analitico_sintetico, tmp_path):
    """El artefacto expone un forecast recursivo multi-paso reutilizable y sano."""
    settings = Settings(base_dir=tmp_path)
    res = entrenar_y_comparar(
        analitico_sintetico, settings, max_train_rows=None, con_cv=False
    )
    fechas = analitico_sintetico["date"]
    inicio = fechas.max() - np.timedelta64(6, "D")
    fin = fechas.max()
    fc = res.predictor.pronosticar_horizonte(analitico_sintetico, inicio, fin)
    assert not fc.empty
    assert {"date", "store_nbr", "family", "demanda_pronosticada"}.issubset(fc.columns)
    # Pronostico en unidades, no negativo y finito.
    vals = fc["demanda_pronosticada"].to_numpy()
    assert np.isfinite(vals).all()
    assert (vals >= 0).all()


def test_ensemble_no_degrada_metrica_honesta(analitico_sintetico):
    """Activar el ensemble nunca empeora el WAPE honesto frente a desactivarlo."""
    base = entrenar_y_comparar(
        analitico_sintetico, Settings(), max_train_rows=None,
        con_cv=False, ensemble=False,
    )
    con_ens = entrenar_y_comparar(
        analitico_sintetico, Settings(), max_train_rows=None,
        con_cv=False, ensemble=True,
    )
    # El ensemble solo reemplaza al ganador si baja el WAPE honesto: por
    # construccion la metrica guia no puede empeorar.
    assert (
        con_ens.metricas_test_recursivo["WAPE"]
        <= base.metricas_test_recursivo["WAPE"] + 1e-9
    )
