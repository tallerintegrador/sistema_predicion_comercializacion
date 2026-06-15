"""Tests del motor de clasificacion (Fase 2b): etiqueta honesta, SMOTE-en-fold,
seleccion-en-VALID, supera al baseline trivial en PR-AUC, artefacto y metadatos."""

from __future__ import annotations

import json

import numpy as np

from spc.models.clasificacion import (
    construir_estrategia,
    entrenar_y_comparar,
    serializar_artefacto,
)
from spc.utils.serializacion import cargar_artefacto


def _entrenar(analitico, settings, **kw):
    return entrenar_y_comparar(
        analitico, settings, max_train_rows=None, usar_gpu=False, **kw
    )


def test_excluye_familias_degeneradas(analitico_clasificacion, settings):
    """La familia degenerada (P75 train = 0, etiqueta 'vendio algo') se excluye y reporta."""
    res = _entrenar(analitico_clasificacion, settings, con_cv=False)
    assert "BOOKS" in res.info_etiqueta.familias_degeneradas
    # El predictor registra las familias excluidas (trazabilidad).
    assert "BOOKS" in res.predictor.familias_excluidas


def test_seleccion_se_decide_en_valid(analitico_clasificacion, settings):
    """La estrategia se elige sobre VALID, nunca sobre TEST."""
    res = _entrenar(analitico_clasificacion, settings, con_cv=False)
    crit = res.criterio_seleccion
    assert crit["decision_en"] == "valid"
    assert crit["metrica_principal"] == "PR_AUC"
    # Las PR-AUC por estrategia que justifican la decision son de VALID.
    assert set(crit["pr_auc_valid"]) == {"sin_remuestreo", "costo_sensible", "smote"}
    assert res.estrategia_elegida in crit["pr_auc_valid"]


def test_supera_baseline_trivial_en_pr_auc(analitico_clasificacion, settings):
    """El modelo elegido supera la linea sin-skill (prevalencia) y al Dummy en PR-AUC."""
    res = _entrenar(analitico_clasificacion, settings, con_cv=False)
    pr_modelo = res.metricas_test["PR_AUC"]
    sin_skill = res.info_etiqueta.prevalencia_train
    pr_dummy = res.metricas_referencia["Dummy(estratificado)"]["PR_AUC"]
    assert np.isfinite(pr_modelo)
    assert pr_modelo > sin_skill, (pr_modelo, sin_skill)
    assert pr_modelo > pr_dummy, (pr_modelo, pr_dummy)


def test_smote_es_pipeline_imblearn_con_smotenc():
    """La estrategia SMOTE es un Pipeline de imblearn con SMOTENC como primer paso
    (el sampler solo actua en fit -> nunca remuestrea valid/test)."""
    from imblearn.over_sampling import SMOTENC
    from imblearn.pipeline import Pipeline as ImbPipeline

    est = construir_estrategia("smote", 42, usar_gpu=False, scale_pos_weight=3.0)
    assert isinstance(est, ImbPipeline)
    assert list(est.named_steps) == ["smote", "clf"]
    assert isinstance(est.named_steps["smote"], SMOTENC)


def test_smote_solo_actua_en_el_fold_de_train(analitico_clasificacion, settings):
    """SMOTE remuestrea SOLO el train de cada fold; el val del fold conserva su
    prevalencia original (si filtrara, la prevalencia del val seria ~0.5)."""
    res = _entrenar(analitico_clasificacion, settings, con_cv=True)
    m = res.metricas
    cv_smote = m[(m["estrategia"] == "smote") & m["split"].str.startswith("cv_")]
    assert not cv_smote.empty, "no se registraron folds de CV para SMOTE"
    # La prevalencia del val de cada fold NO fue balanceada por SMOTE.
    assert (cv_smote["prevalencia"] < 0.45).all()
    # Y es coherente con la prevalencia global desbalanceada del problema.
    assert res.info_etiqueta.prevalencia_train < 0.4


def test_umbral_elegido_en_valid_marco_negocio(analitico_clasificacion, settings):
    """El umbral se elige en VALID con criterio de recall (no el 0.5 por defecto)."""
    res = _entrenar(analitico_clasificacion, settings, con_cv=False)
    assert 0.0 < res.umbral < 1.0
    assert "recall" in res.criterio_umbral["criterio"].lower()


def test_artefacto_recarga_y_predice(analitico_clasificacion, settings):
    """El artefacto se carga sin reentrenar y devuelve clase + probabilidad sanas."""
    res = _entrenar(analitico_clasificacion, settings, con_cv=False)
    ruta_art, ruta_meta = serializar_artefacto(res, settings)
    assert ruta_art.exists() and ruta_meta.exists()

    predictor, meta = cargar_artefacto(ruta_art)
    salida = predictor.predecir(analitico_clasificacion)
    assert {"clase_demanda_alta", "probabilidad_demanda_alta"}.issubset(salida.columns)
    prob = salida["probabilidad_demanda_alta"].to_numpy()
    assert np.isfinite(prob).all()
    assert ((prob >= 0) & (prob <= 1)).all()
    assert set(np.unique(salida["clase_demanda_alta"].to_numpy())).issubset({0, 1})
    assert meta["estrategia_desbalance"] == res.estrategia_elegida


def test_metadatos_completos(analitico_clasificacion, settings):
    """Los metadatos incluyen todo lo exigido por el criterio de hecho de la 2b."""
    res = _entrenar(analitico_clasificacion, settings, con_cv=False)
    _, ruta_meta = serializar_artefacto(res, settings)
    meta = json.loads(ruta_meta.read_text(encoding="utf-8"))
    for clave in (
        "version",
        "estrategia_desbalance",
        "usa_smote",
        "umbral",
        "criterio_umbral",
        "criterio_seleccion",
        "semilla",
        "features",
        "metricas_valid",
        "metricas_test",
        "matriz_confusion_test",
        "familias_degeneradas_excluidas",
        "linea_sin_skill_pr_auc",
        "n_filas_artefacto_final",
    ):
        assert clave in meta, clave
    assert meta["features"]
    assert meta["semilla"] == settings.random_seed
    for k in ("PR_AUC", "Recall", "F1", "Precision"):
        assert k in meta["metricas_test"]


def test_registro_metricas_una_fila_por_estrategia_split(analitico_clasificacion, settings):
    """El registro persistente tiene una fila por estrategia x split (efecto SMOTE)."""
    from spc.models.clasificacion import persistir_metricas

    res = _entrenar(analitico_clasificacion, settings, con_cv=False)
    ruta = persistir_metricas(res, settings)
    assert ruta.exists()
    df = res.metricas
    for estr in ("sin_remuestreo", "costo_sensible", "smote"):
        for split in ("valid", "test"):
            sel = df[(df["estrategia"] == estr) & (df["split"] == split)]
            assert len(sel) == 1, (estr, split)
