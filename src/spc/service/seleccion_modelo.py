"""Selección **quédate-con-el-mejor** entre el candidato recién entrenado y el campeón
persistido del cliente (ADR-0023 + filosofía ADR-0013).

La predicción agnóstica reentrena cuando llega data nueva. Antes, ese reentrenamiento
**sobrescribía** el modelo guardado aunque fuera peor. Aquí se compara, con la **misma**
ventana TEST de los datos nuevos (base honesta), la métrica del candidato contra la del
campeón evaluado sobre esos mismos datos, y se conserva el mejor. Si ninguno gana de forma
clara, se mantiene el campeón (estabilidad). El veredicto viaja en ``info["seleccion"]``
para mostrarlo en lenguaje claro al usuario.

No conoce HTTP ni el algoritmo: solo orquesta la comparación honesta.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from spc.features.generico import EspecEsquema
from spc.models import automl
from spc.models.automl import (
    PredictorGenericoClasificacion,
    PredictorGenericoRegresion,
    ResultadoAutoMLClasificacion,
    ResultadoAutoMLRegresion,
)
from spc.utils.logging import get_logger

log = get_logger("service.seleccion_modelo")


def _finito(x: Any) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if np.isfinite(v) else None


def _metricas_finitas(metrics: dict[str, Any]) -> dict[str, float]:
    return {k: round(float(v), 4) for k, v in (metrics or {}).items()
            if _finito(v) is not None}


def _adoptado(cand: float | None, champ: float | None, *, mayor_mejor: bool) -> str:
    """Quién gana: 'candidato' o 'campeon'. Empate o métrica ausente del rival → estabilidad."""
    if champ is None:
        return "candidato"
    if cand is None:
        return "campeon"
    if mayor_mejor:
        return "candidato" if cand > champ else "campeon"
    return "candidato" if cand < champ else "campeon"


def _veredicto(metrica: str, mayor_mejor: bool, cand: float | None, champ: float | None,
               adoptado: str) -> dict[str, Any]:
    return {
        "comparado": True,
        "metrica": metrica,
        "mejor_es": "mayor" if mayor_mejor else "menor",
        "candidato": round(cand, 4) if cand is not None else None,
        "campeon": round(champ, 4) if champ is not None else None,
        "adoptado": adoptado,
    }


# ===========================================================================
# REGRESIÓN (ventas / compras): menor WAPE es mejor
# ===========================================================================
def elegir_mejor_regresion(
    *,
    candidato_info: dict[str, Any],
    res: ResultadoAutoMLRegresion,
    campeon: tuple[PredictorGenericoRegresion, dict[str, Any]],
    spec: EspecEsquema,
) -> tuple[Any, dict[str, Any]]:
    """Compara el candidato (``res``) contra el campeón persistido sobre la ventana TEST de
    los datos nuevos y devuelve ``(predictor, info)`` del que se conserva, con veredicto."""
    champ_predictor, champ_info = campeon
    cand_wape = _finito(candidato_info.get("honest_metrics", {}).get("WAPE"))
    try:
        champ_metrics = automl.evaluar_regresion_en_test(champ_predictor, res.df_model, spec, res.cortes)
    except Exception as exc:  # noqa: BLE001 - si el campeón no evalúa, gana el candidato
        log.warning("No se pudo evaluar el campeón de regresión en TEST: %s", exc)
        champ_metrics = {}
    champ_wape = _finito(champ_metrics.get("WAPE"))

    adoptado = _adoptado(cand_wape, champ_wape, mayor_mejor=False)
    seleccion = _veredicto("WAPE", False, cand_wape, champ_wape, adoptado)

    if adoptado == "campeon":
        info = {
            "winner_algorithm": champ_info.get("winner_algorithm", "modelo anterior"),
            "trained_rows": int(champ_info.get("trained_rows", 0)),
            "honest_metrics": _metricas_finitas(champ_metrics) or _metricas_finitas(
                champ_info.get("honest_metrics", {})
            ),
            "candidates": champ_info.get("candidates"),
            "reused_cached_model": False,
            "schema_signature": candidato_info["schema_signature"],
            "seleccion": seleccion,
        }
        log.info("Selección regresión: se mantiene el campeón (WAPE cand=%s vs champ=%s)", cand_wape, champ_wape)
        return champ_predictor, info

    log.info("Selección regresión: se adopta el candidato (WAPE cand=%s vs champ=%s)", cand_wape, champ_wape)
    return res.predictor, {**candidato_info, "seleccion": seleccion}


# ===========================================================================
# CLASIFICACIÓN (almacén): mayor ROC-AUC es mejor
# ===========================================================================
def _auc(metrics: dict[str, Any]) -> float | None:
    return _finito(metrics.get("ROC_AUC")) or _finito(metrics.get("PR_AUC"))


def elegir_mejor_clasificacion(
    *,
    candidato_info: dict[str, Any],
    res: ResultadoAutoMLClasificacion,
    campeon: tuple[PredictorGenericoClasificacion, dict[str, Any]],
    spec: EspecEsquema,
) -> tuple[Any, dict[str, Any]]:
    """Análogo a {@link elegir_mejor_regresion} para el clasificador de demanda alta."""
    champ_predictor, champ_info = campeon
    cand_auc = _auc(candidato_info.get("honest_metrics", {}))
    try:
        champ_metrics = automl.evaluar_clasificacion_en_test(champ_predictor, res.df_model, spec, res.cortes)
    except Exception as exc:  # noqa: BLE001
        log.warning("No se pudo evaluar el campeón de clasificación en TEST: %s", exc)
        champ_metrics = {}
    champ_auc = _auc(champ_metrics)

    adoptado = _adoptado(cand_auc, champ_auc, mayor_mejor=True)
    seleccion = _veredicto("ROC_AUC", True, cand_auc, champ_auc, adoptado)

    if adoptado == "campeon":
        info = {
            "winner_algorithm": champ_info.get("winner_algorithm", "modelo anterior"),
            "trained_rows": int(champ_info.get("trained_rows", 0)),
            "honest_metrics": _metricas_finitas(champ_metrics) or _metricas_finitas(
                champ_info.get("honest_metrics", {})
            ),
            "candidates": champ_info.get("candidates"),
            "reused_cached_model": False,
            "schema_signature": candidato_info["schema_signature"],
            "threshold_probability": round(float(champ_predictor.umbral), 4),
            "seleccion": seleccion,
        }
        log.info("Selección clasificación: se mantiene el campeón (AUC cand=%s vs champ=%s)", cand_auc, champ_auc)
        return champ_predictor, info

    log.info("Selección clasificación: se adopta el candidato (AUC cand=%s vs champ=%s)", cand_auc, champ_auc)
    return res.predictor, {**candidato_info, "seleccion": seleccion}
