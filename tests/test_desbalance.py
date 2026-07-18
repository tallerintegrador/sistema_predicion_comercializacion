"""Tests del núcleo de desbalance (`spc.models.desbalance`).

Cubren las tres piezas agnósticas al dominio: la construcción de las estrategias
(sin remuestreo / costo-sensible / SMOTE) sin entrenar, la selección del umbral por
defecto en VALID (máx recall sujeto a un piso REAL de precisión) y la regla de elegir la
estrategia **más simple** que empata en PR-AUC (SMOTE solo gana si supera la tolerancia).
"""

from __future__ import annotations

import numpy as np
import pytest

from spc.models import desbalance


# ---------------------------------------------------------------------------
# construir_estrategia — sin entrenar (solo tipo/config del estimador)
# ---------------------------------------------------------------------------
def test_sin_remuestreo_es_booster_desnudo() -> None:
    est = desbalance.construir_estrategia(
        "sin_remuestreo", seed=42, usar_gpu=False, scale_pos_weight=2.0
    )
    from lightgbm import LGBMClassifier

    assert isinstance(est, LGBMClassifier)
    assert est.scale_pos_weight is None  # sin remuestreo → sin peso


def test_costo_sensible_inyecta_scale_pos_weight() -> None:
    est = desbalance.construir_estrategia(
        "costo_sensible", seed=42, usar_gpu=False, scale_pos_weight=3.5
    )
    assert est.scale_pos_weight == 3.5


def test_smote_es_pipeline_con_sampler_y_clf() -> None:
    est = desbalance.construir_estrategia(
        "smote", seed=42, usar_gpu=False, scale_pos_weight=2.0
    )
    from imblearn.pipeline import Pipeline as ImbPipeline

    assert isinstance(est, ImbPipeline)
    assert [nombre for nombre, _ in est.steps] == ["smote", "clf"]


def test_estrategia_desconocida_lanza() -> None:
    with pytest.raises(ValueError, match="Estrategia desconocida"):
        desbalance.construir_estrategia("otra", seed=42, usar_gpu=False, scale_pos_weight=1.0)


# ---------------------------------------------------------------------------
# seleccionar_umbral — máx recall con piso real de precisión (decidido en VALID)
# ---------------------------------------------------------------------------
def test_umbral_respeta_piso_de_precision_con_separacion_perfecta() -> None:
    # Clases perfectamente separables: existe umbral con precisión 1.0 ≥ piso 0.80.
    rng = np.random.default_rng(42)
    y_true = np.array([0] * 60 + [1] * 40)
    y_prob = np.concatenate([rng.uniform(0.0, 0.4, 60), rng.uniform(0.6, 1.0, 40)])
    umbral, info = desbalance.seleccionar_umbral(y_true, y_prob)
    assert 0.0 < umbral < 1.0
    assert info["precision_en_umbral"] >= desbalance.PRECISION_FLOOR
    assert "max recall" in info["criterio"]


def test_umbral_devuelve_metadatos_del_piso() -> None:
    y_true = np.array([0, 0, 0, 1, 1, 1])
    y_prob = np.array([0.1, 0.2, 0.3, 0.7, 0.8, 0.9])
    _, info = desbalance.seleccionar_umbral(y_true, y_prob)
    assert info["precision_floor"] == desbalance.PRECISION_FLOOR
    assert info["margen_valid"] == desbalance.MARGEN_VALID


# ---------------------------------------------------------------------------
# _elegir_estrategia — la más simple dentro de la tolerancia de PR-AUC
# ---------------------------------------------------------------------------
def test_empate_elige_la_mas_simple() -> None:
    # Las tres empatan dentro de TOL_PRAUC → gana sin_remuestreo (la más simple).
    metricas = {
        "sin_remuestreo": {"PR_AUC": 0.930, "Recall": 0.70},
        "costo_sensible": {"PR_AUC": 0.932, "Recall": 0.72},
        "smote": {"PR_AUC": 0.933, "Recall": 0.75},
    }
    elegida, criterio = desbalance._elegir_estrategia(metricas)
    assert elegida == "sin_remuestreo"
    assert criterio["metrica_principal"] == "PR_AUC"
    assert "sin_remuestreo" in criterio["empatadas_dentro_tol"]


def test_smote_gana_solo_si_supera_la_tolerancia() -> None:
    # SMOTE supera a las demás por MÁS que TOL_PRAUC → se adopta SMOTE.
    metricas = {
        "sin_remuestreo": {"PR_AUC": 0.900, "Recall": 0.60},
        "costo_sensible": {"PR_AUC": 0.902, "Recall": 0.62},
        "smote": {"PR_AUC": 0.950, "Recall": 0.80},
    }
    elegida, _ = desbalance._elegir_estrategia(metricas)
    assert elegida == "smote"


def test_costo_sensible_gana_a_smote_en_empate() -> None:
    # costo_sensible y smote empatan arriba; sin_remuestreo queda lejos → gana costo_sensible.
    metricas = {
        "sin_remuestreo": {"PR_AUC": 0.80, "Recall": 0.50},
        "costo_sensible": {"PR_AUC": 0.94, "Recall": 0.78},
        "smote": {"PR_AUC": 0.942, "Recall": 0.80},
    }
    elegida, _ = desbalance._elegir_estrategia(metricas)
    assert elegida == "costo_sensible"
