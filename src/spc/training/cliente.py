"""Experimento medido de entrenamiento por cliente (ADR-0013).

Entrena un candidato de regresión con los datos del **propio cliente**, lo compara de
forma **honesta** contra el modelo congelado y un baseline ingenuo sobre la **misma
ventana** de validación temporal, y **adopta** el modelo por cliente **solo si supera al
congelado**. "No mejora" es un resultado válido que se reporta, no se esconde.

Reutiliza el motor sin tocarlo:

- ``adaptador.historico_a_analitico`` — la MISMA traducción contrato→motor de la predicción.
- ``regresion.entrenar_y_comparar`` — el pipeline honesto completo (split temporal, zoo,
  selección estable, WAPE recursivo), con **ventana parametrizable** (adaptativa a la
  historia del cliente, ADR-0013).
- ``regresion.evaluar_recursivo`` — para medir el **congelado** sobre la misma ventana TEST.

No vive en el camino de predicción: lo invoca el servicio, disparado por un endpoint, en
un trabajo asíncrono local (``spc.api.jobs_entrenamiento``).
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from spc.config import (
    Settings,
    client_adj_max_window,
    client_adj_min_days,
    client_adj_min_improvement,
    client_adj_min_rows,
    client_adj_min_series,
    client_adj_min_window,
    client_adj_use_gpu,
    client_adj_valid_frac,
)
from spc.features.temporales import ConfigFeatures
from spc.service import adaptador, corpus
from spc.service.artefactos import ArtefactoCargado
from spc.training import almacen
from spc.utils.logging import get_logger

log = get_logger("training.cliente")

DOMINIO = "sales"
METRICA = "WAPE_recursivo"

# Outcomes honestos del experimento.
OUTCOME_ADOPTED = "adopted"
OUTCOME_NOT_ADOPTED = "not_adopted"
OUTCOME_INSUFFICIENT = "insufficient_data"
OUTCOME_INCONCLUSIVE = "inconclusive"

# Calentamiento de rezagos: el motor descarta las primeras filas de cada serie hasta que
# existe el mayor ``sales_lag_*``. La historia "útil" para validar arranca tras ese tramo.
_WARMUP = max(ConfigFeatures().lags_objetivo)


@dataclass(frozen=True)
class ConfigEntrenamientoCliente:
    """Parámetros del experimento por cliente (de entorno por defecto; inyectables en tests)."""

    min_dias: int
    min_filas: int
    min_series: int
    valid_frac: float
    min_window: int
    max_window: int
    min_improvement: float
    usar_gpu: bool

    @classmethod
    def desde_entorno(cls) -> ConfigEntrenamientoCliente:
        return cls(
            min_dias=client_adj_min_days(),
            min_filas=client_adj_min_rows(),
            min_series=client_adj_min_series(),
            valid_frac=client_adj_valid_frac(),
            min_window=client_adj_min_window(),
            max_window=client_adj_max_window(),
            min_improvement=client_adj_min_improvement(),
            usar_gpu=client_adj_use_gpu(),
        )


def _neutralizar_columnas_vacias(analitico: Any) -> Any:
    """Reemplaza columnas numéricas **íntegramente NaN** por una constante (0.0).

    Un cliente nuevo no aporta petróleo (``dcoilwtico`` siempre NaN en el adaptador) y a
    veces tampoco transacciones; esas columnas quedan todo-NaN. El binner de
    ``HistGradientBoosting`` (sklearn) **falla** ante una feature todo-NaN al entrenar (no
    así al predecir, por eso el congelado no lo sufre). Como una columna constante no
    aporta información a un modelo de un solo cliente, se neutraliza a 0.0: el motor la
    trata como sin-señal. Se aplica al MISMO frame con que se mide candidato y congelado,
    de modo que la comparación sigue siendo justa.
    """
    df = analitico.copy()
    for col in df.columns:
        if df[col].dtype.kind == "f" and df[col].isna().all():
            df[col] = 0.0
    return df


def _stats(history: list[Mapping[str, Any]]) -> dict[str, int]:
    """Cuenta observaciones, días distintos y series (store×product) del histórico."""
    dias = {str(f.get("date")) for f in history}
    series = {(str(f.get("store_id")), str(f.get("product_id"))) for f in history}
    return {"n_obs": len(history), "n_dias": len(dias), "n_series": len(series)}


def _ventana_adaptativa(n_dias: int, cfg: ConfigEntrenamientoCliente) -> int:
    """Días por holdout temporal (valid y test), proporcional a la historia útil.

    ``round(dias_utiles * valid_frac)`` recortado a ``[min_window, max_window]``. Con mucha
    historia llega al máximo (= la ventana del congelado); con poca, a una ventana corta
    pero honesta.
    """
    dias_utiles = max(0, n_dias - _WARMUP)
    w = round(dias_utiles * cfg.valid_frac)
    return int(max(cfg.min_window, min(cfg.max_window, w)))


def _faltantes(stats: dict[str, int], w: int, cfg: ConfigEntrenamientoCliente) -> list[str]:
    """Lista honesta de requisitos incumplidos para entrenar (vacía si todo se cumple)."""
    faltan: list[str] = []
    if stats["n_dias"] < cfg.min_dias:
        faltan.append(f"días de historia: {stats['n_dias']} < {cfg.min_dias} requeridos")
    if stats["n_obs"] < cfg.min_filas:
        faltan.append(f"observaciones: {stats['n_obs']} < {cfg.min_filas} requeridas")
    if stats["n_series"] < cfg.min_series:
        faltan.append(f"series (tienda×producto): {stats['n_series']} < {cfg.min_series} requeridas")
    # Tras descartar el calentamiento, debe quedar al menos 1 día de train + valid + test.
    dias_utiles = max(0, stats["n_dias"] - _WARMUP)
    if dias_utiles < 2 * w + 1:
        faltan.append(
            f"días útiles tras calentamiento ({_WARMUP}d): {dias_utiles} < {2 * w + 1} "
            f"necesarios para validar/probar con ventana de {w}d"
        )
    return faltan


def _metricas3(m: Mapping[str, float]) -> dict[str, float]:
    """Extrae las tres métricas guía (redondeadas) de un dict de ``regression_metrics``."""
    return {
        "WAPE": round(float(m.get("WAPE", float("nan"))), 3),
        "MAE": round(float(m.get("MAE", float("nan"))), 3),
        "RMSE": round(float(m.get("RMSE", float("nan"))), 3),
    }


def _mejor_baseline(baselines: Mapping[str, Mapping[str, float]]) -> tuple[str, dict[str, float]] | None:
    """Baseline ingenuo de menor WAPE recursivo (o ``None`` si no hay)."""
    validos = {
        n: m for n, m in baselines.items()
        if math.isfinite(float(m.get("WAPE", float("nan"))))
    }
    if not validos:
        return None
    nombre = min(validos, key=lambda n: float(validos[n]["WAPE"]))
    return nombre, _metricas3(validos[nombre])


def _resultado(outcome: str, message: str, **extra: Any) -> dict[str, Any]:
    """Arma el cuerpo del resultado del experimento (forma estable para la API)."""
    return {"domain": DOMINIO, "outcome": outcome, "message": message, **extra}


def fundir_historico(
    history_excel: Iterable[Mapping[str, Any]],
    history_corpus: Iterable[Mapping[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Funde la ``history`` del Excel con el corpus del cliente y deduplica por serie-día.

    El Excel subido va **al final** para que, ante un duplicado serie-día, gane lo recién
    declarado por el cliente (la regla "último gana" de ``corpus.dedup_contrato``).
    """
    fundido: list[dict[str, Any]] = []
    if history_corpus:
        fundido.extend(dict(f) for f in history_corpus)
    fundido.extend(dict(f) for f in history_excel)
    return corpus.dedup_contrato(fundido)


def entrenar_para_cliente(
    *,
    client_id: str,
    history: list[Mapping[str, Any]],
    frozen: ArtefactoCargado,
    settings: Settings,
    root: Path,
    cfg: ConfigEntrenamientoCliente | None = None,
    progreso: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Corre el experimento medido y, si mejora, adopta el modelo por cliente.

    Devuelve un dict honesto con la comparación (candidato vs congelado vs baseline) y el
    veredicto (``adopted`` / ``not_adopted`` / ``insufficient_data`` / ``inconclusive``).
    El modelo congelado **no se toca**; solo se lee para medirlo sobre la misma ventana.
    """
    from spc.models.regresion import entrenar_y_comparar, evaluar_recursivo

    cfg = cfg or ConfigEntrenamientoCliente.desde_entorno()

    def _fase(nombre: str) -> None:
        if progreso is not None:
            progreso(nombre)

    _fase("validating")
    history = corpus.dedup_contrato(history)
    stats = _stats(history)
    w = _ventana_adaptativa(stats["n_dias"], cfg)
    faltan = _faltantes(stats, w, cfg)
    requisitos = {
        "min_dias": cfg.min_dias, "min_filas": cfg.min_filas, "min_series": cfg.min_series,
        "tiene": stats,
    }
    if faltan:
        log.info("Cliente %s: datos insuficientes para entrenar (%s)", client_id, faltan)
        return _resultado(
            OUTCOME_INSUFFICIENT,
            "Datos insuficientes para entrenar un modelo por cliente con validación honesta. "
            "Se sigue usando el modelo congelado.",
            missing=faltan,
            requirements=requisitos,
        )

    _fase("training")
    log.info(
        "Cliente %s: entrenando candidato (obs=%d, dias=%d, series=%d, ventana=%dd)...",
        client_id, stats["n_obs"], stats["n_dias"], stats["n_series"], w,
    )
    analitico = adaptador.historico_a_analitico(history)
    analitico = _neutralizar_columnas_vacias(analitico)
    res = entrenar_y_comparar(
        analitico, settings,
        max_train_rows=None, con_cv=False, ensemble=True,
        usar_gpu=cfg.usar_gpu, dias_test=w, dias_valid=w,
    )

    _fase("evaluating")
    # Congelado sobre la MISMA ventana TEST (recursivo honesto): "lo que el cliente
    # obtiene hoy". El candidato ya trae su WAPE honesto de entrenar_y_comparar.
    frozen_metrics, _ = evaluar_recursivo(frozen.objeto, analitico, res.cortes, ventana="test")
    cand = _metricas3(res.metricas_test_recursivo)
    frozen3 = _metricas3(frozen_metrics)
    base = _mejor_baseline(res.metricas_baseline_recursivo or {})

    data: dict[str, Any] = {
        "metric": METRICA,
        "window_days": w,
        "cuts": res.cortes.as_dict(),
        "samples": stats,
        "candidate": cand,
        "frozen": frozen3,
        "baseline": ({"name": base[0], **base[1]} if base else None),
        "candidate_model": res.mejor_modelo,
        "min_improvement_points": cfg.min_improvement,
    }

    # Decisión de adopción (regla fijada de antemano, ADR-0013):
    #   adopta sii  WAPE_candidato < WAPE_congelado - min_improvement  (mejora estricta por
    #   defecto)  Y  WAPE_candidato <= WAPE_baseline (no peor que el ingenuo).
    wape_c, wape_f = cand["WAPE"], frozen3["WAPE"]
    if not (math.isfinite(wape_c) and math.isfinite(wape_f)):
        return _resultado(
            OUTCOME_INCONCLUSIVE,
            "La métrica honesta no es evaluable en esta ventana (p. ej. ventas reales nulas "
            "en el período de prueba). No se adopta; se sigue con el modelo congelado.",
            **data,
        )

    mejora = round(wape_f - wape_c, 3)
    supera_congelado = mejora > cfg.min_improvement
    supera_baseline = base is None or wape_c <= base[1]["WAPE"]
    adoptar = bool(supera_congelado and supera_baseline)

    data["improvement_wape_points"] = mejora
    data["beats_frozen"] = supera_congelado
    data["beats_baseline"] = supera_baseline

    # Persistir SIEMPRE el candidato + su comparación (auditoría/historial); el puntero de
    # adopción solo se mueve si gana (default frozen intacto si no).
    comparacion = _resultado(
        OUTCOME_ADOPTED if adoptar else OUTCOME_NOT_ADOPTED, "", **data
    )
    meta = {
        "fecha_entrenamiento": None,
        "modelo": res.mejor_modelo,
        "transformacion_objetivo": res.predictor.transformacion,
        "espacio_objetivo": res.predictor.espacio,
        "escala_metricas": "unidades",
        "ventana_validacion_dias": w,
        "cortes_temporales": res.cortes.as_dict(),
        "metricas_test_recursivo": res.metricas_test_recursivo,
        "metricas_test_recursivo_congelado": frozen_metrics,
        "criterio_adopcion": comparacion,
        "n_filas_artefacto_final": res.n_artefacto,
        "semilla": settings.random_seed,
        "origen": "entrenamiento_por_cliente",
    }
    version, _ = almacen.guardar_modelo(
        root, client_id, predictor=res.predictor, meta=meta, comparacion=comparacion
    )
    data["model_version"] = almacen.etiqueta_version(client_id, version)
    data["client_version"] = version

    if adoptar:
        almacen.marcar_adopcion(root, client_id, version, servir=True)
        log.info(
            "Cliente %s: ADOPTADO v%d (WAPE %.2f%% vs congelado %.2f%%; mejora %.2f pts)",
            client_id, version, wape_c, wape_f, mejora,
        )
        return _resultado(
            OUTCOME_ADOPTED,
            f"Modelo por cliente adoptado: mejora el WAPE honesto del congelado en "
            f"{mejora:.2f} puntos ({wape_c:.2f}% vs {wape_f:.2f}%). Se sirve a este cliente.",
            **data,
        )

    log.info(
        "Cliente %s: NO adoptado v%d (WAPE %.2f%% vs congelado %.2f%%). Sigue el congelado.",
        client_id, version, wape_c, wape_f,
    )
    motivo = (
        "no supera al congelado" if not supera_congelado else "no supera al baseline ingenuo"
    )
    return _resultado(
        OUTCOME_NOT_ADOPTED,
        f"El modelo por cliente {motivo} en validación honesta (candidato {wape_c:.2f}% vs "
        f"congelado {wape_f:.2f}% WAPE). No se adopta; se sigue con el modelo congelado.",
        **data,
    )
