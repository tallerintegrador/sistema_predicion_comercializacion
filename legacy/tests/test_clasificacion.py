"""Tests del motor de clasificacion (Fase 2b): etiqueta honesta, SMOTE-en-fold,
seleccion-en-VALID, supera al baseline trivial en PR-AUC, artefacto y metadatos."""

from __future__ import annotations

import json

import numpy as np

from spc.models.clasificacion import (
    MARGEN_VALID,
    PRECISION_FLOOR,
    _candidatos_pr,
    _max_recall_con_piso,
    agregar_puntos_a_registro,
    aplicar_recalibracion,
    construir_estrategia,
    curva_pr,
    entrenar_y_comparar,
    persistir_curva_pr,
    persistir_metricas,
    puntos_de_operacion,
    recalibrar_umbral,
    seleccionar_umbral,
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
    """El umbral se elige en VALID con piso REAL de precision 0.80 (no 0.5, no 0.50)."""
    res = _entrenar(analitico_clasificacion, settings, con_cv=False)
    assert 0.0 < res.umbral < 1.0
    assert res.criterio_umbral["precision_floor"] == 0.80
    assert "0.80" in res.criterio_umbral["criterio"]


# ---------------------------------------------------------------------------
# Seleccion de umbral: piso REAL de precision + margen (unit, sin modelo)
# ---------------------------------------------------------------------------
def _probs_separables(seed: int = 0, n: int = 500):
    """y_true balanceado y probas con buena separacion (precision 0.80 alcanzable a
    recall < 1, precision colapsa hacia 0.5 al bajar el umbral)."""
    rng = np.random.default_rng(seed)
    y = np.concatenate([np.ones(n), np.zeros(n)]).astype(int)
    prob = np.concatenate(
        [rng.uniform(0.40, 1.00, n), rng.uniform(0.00, 0.60, n)]
    )
    return y, prob


def test_seleccionar_umbral_usa_piso_real_080_con_margen():
    """El default exige precision >= 0.80 (piso real) con piso efectivo 0.80+margen."""
    y, prob = _probs_separables()
    _, info = seleccionar_umbral(y, prob)
    assert info["precision_floor"] == PRECISION_FLOOR == 0.80
    assert info["piso_efectivo_valid"] == round(0.80 + MARGEN_VALID, 4)
    # El punto elegido respeta el piso real (no 0.50).
    assert info["precision_en_umbral"] >= 0.80


def test_default_retrocede_recall_vs_recall_prioritario():
    """El piso 0.80 alcanza MENOS recall que el viejo piso 0.50 (retroceder recall
    mejora precision): el operativo deja de ser degenerado."""
    y, prob = _probs_separables()
    _, info = seleccionar_umbral(y, prob)
    cand = _candidatos_pr(y, prob)
    rp = _max_recall_con_piso(cand, 0.50)  # punto recall-prioritario (default viejo)
    assert rp is not None
    assert rp[2] >= info["recall_en_umbral"]  # recall(p>=0.50) >= recall(p>=0.80)


def test_curva_pr_columnas_y_rango():
    """La curva PR persistible tiene (umbral, precision, recall) en rango [0,1]."""
    y, prob = _probs_separables()
    df = curva_pr(y, prob)
    assert list(df.columns) == ["umbral", "precision", "recall"]
    assert len(df) >= 2
    assert ((df["precision"] >= 0) & (df["precision"] <= 1)).all()
    assert ((df["recall"] >= 0) & (df["recall"] <= 1)).all()


def test_puntos_de_operacion_tres_puntos_un_default():
    """Tres puntos (default p>=0.80, max F1, recall-prioritario); exactamente 1 default;
    el default marca <= filas que el recall-prioritario."""
    yv, pv = _probs_separables(seed=1)
    yt, pt = _probs_separables(seed=2)
    umbrales, detalle = puntos_de_operacion(yv, pv, yt, pt)
    assert len(umbrales) == 3
    defaults = [d for d in detalle.values() if d["es_default"]]
    assert len(defaults) == 1
    rp_key = next(k for k in detalle if k.startswith("recall_prioritario"))
    assert defaults[0]["n_pos_pred_test"] <= detalle[rp_key]["n_pos_pred_test"]


# ---------------------------------------------------------------------------
# Recalibracion POST-HOC del umbral (sin reentrenar el booster de produccion)
# ---------------------------------------------------------------------------
def test_recalibracion_default_en_valid_no_degenerado(analitico_clasificacion, settings):
    """El nuevo default se elige en VALID (piso 0.80) y NO opera en el regimen
    degenerado (marca menos filas que el recall-prioritario; respeta el piso si es
    alcanzable)."""
    res = recalibrar_umbral(
        analitico_clasificacion, settings, max_train_rows=None, usar_gpu=False
    )
    assert 0.0 < res.umbral < 1.0
    assert res.criterio_umbral["precision_floor"] == 0.80
    assert len(res.umbrales_punto) == 3
    default = next(d for d in res.detalle_puntos.values() if d["es_default"])
    rp_key = next(k for k in res.detalle_puntos if k.startswith("recall_prioritario"))
    rp = res.detalle_puntos[rp_key]
    # Operativo accionable: el default marca <= filas que el recall-prioritario.
    assert default["n_pos_pred_test"] <= rp["n_pos_pred_test"]
    # Si el piso es alcanzable (no hubo fallback), la precision VALID lo respeta.
    if "fallback" not in res.criterio_umbral["criterio"]:
        assert res.metricas_valid["Precision"] >= PRECISION_FLOOR - 1e-9


def test_recalibracion_actualiza_umbral_sin_cambiar_el_booster(
    analitico_clasificacion, settings
):
    """La recalibracion cambia SOLO el umbral del artefacto + sus metadatos; el booster
    de produccion no cambia (mismas probabilidades) y persiste curva PR + registro."""
    import pandas as pd

    # 1) Artefacto base + registro base (entrenamiento completo).
    base = _entrenar(analitico_clasificacion, settings, con_cv=False)
    ruta_art, _ = serializar_artefacto(base, settings)
    persistir_metricas(base, settings)
    pred_antes, _ = cargar_artefacto(ruta_art)
    p_antes = pred_antes.predecir_proba(analitico_clasificacion).to_numpy()

    # 2) Recalibracion post-hoc + aplicacion.
    res = recalibrar_umbral(
        analitico_clasificacion, settings, max_train_rows=None, usar_gpu=False
    )
    ruta_art2, _ = aplicar_recalibracion(res, settings)
    ruta_curva = persistir_curva_pr(res, settings)
    ruta_reg = agregar_puntos_a_registro(res, settings)

    pred_despues, meta_despues = cargar_artefacto(ruta_art2)
    # Umbral actualizado en artefacto y meta.
    assert pred_despues.umbral == res.umbral
    assert meta_despues["umbral"] == res.umbral
    assert "puntos_operacion" in meta_despues
    assert meta_despues["curva_pr_ref"].endswith("curva_pr_clasificacion_2b.csv")
    # El booster NO cambio: mismas probabilidades (modelo intacto).
    p_despues = pred_despues.predecir_proba(analitico_clasificacion).to_numpy()
    np.testing.assert_allclose(p_antes, p_despues)

    # Curva PR persistida con (umbral, precision, recall).
    curva = pd.read_csv(ruta_curva)
    assert list(curva.columns) == ["umbral", "precision", "recall"]
    assert len(curva) > 0

    # Registro: 3 puntos x 2 splits = 6 filas de operacion; comparacion conservada.
    reg = pd.read_csv(ruta_reg)
    assert "punto" in reg.columns
    op = reg[reg["punto"].notna()]
    assert len(op) == 6
    assert set(op["split"]) == {"op_valid", "op_test"}
    assert reg["punto"].isna().sum() > 0


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
