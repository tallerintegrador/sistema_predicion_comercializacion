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
    assert meta["transformacion_objetivo"] == "log1p"
    assert meta["escala_metricas"] == "unidades"
    assert meta["modelo"] == res.mejor_modelo

    # Predecir sobre un SUBCONJUNTO (una sola serie) debe funcionar: el dtype
    # categorico se reaplica exacto aunque no aparezcan todos los niveles.
    sub = analitico_sintetico[analitico_sintetico["store_nbr"] == 1]
    pred_sub = predictor2.predecir(sub)
    assert len(pred_sub) == len(sub)
    assert (pred_sub >= 0).all()
