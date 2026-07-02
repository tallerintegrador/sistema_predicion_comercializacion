"""Estrategias de desbalance + selección de umbral (agnóstico al dominio).

Núcleo de clasificación compartido por el AutoML agnóstico (`spc.models.automl`): el
booster base, las tres estrategias de desbalance (sin remuestreo / costo-sensible / SMOTE),
la selección del umbral por defecto en VALID (máx recall con piso real de precisión) y la
elección de la estrategia más simple que empata en PR-AUC. **No** conoce el esquema retail
(`temporales`), ni `Settings`, ni serialización: solo numpy/scikit-learn (+ LightGBM e
imbalanced-learn importados de forma perezosa). El entrenamiento retail 2b Favorita que
antes convivía aquí se archivó en ``legacy/models/clasificacion.py``.

Capa de motor de ML: no conoce HTTP ni el negocio del cliente.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from sklearn.metrics import precision_recall_curve

# Marco de negocio para el umbral por defecto. `demanda_alta` senala riesgo de
# quiebre; fallar un positivo (no detectar demanda alta) cuesta mas que una falsa
# alarma, asi que el default prioriza **recall**. Pero el operativo debe ser
# **accionable**: un piso de precision demasiado debil (0.50, lift de solo ~1.44x
# sobre la prevalencia ~0.346) degenera en "marcar casi todo" -inutil para
# priorizar un almacen-. Por eso el default usa un **piso REAL de precision (0.80)**
# y toma el maximo recall que lo respeta.
PRECISION_FLOOR = 0.80

# Margen anadido al piso al elegir en VALID (robustez VALID->TEST). En la corrida
# vieja la precision se deslizo de 0.50 (valid) a 0.484 (test); con un piso mas
# alto ese deslizamiento importa mas, asi que en VALID se apunta a
# precision >= PRECISION_FLOOR + MARGEN_VALID para que el piso aguante en TEST.
MARGEN_VALID = 0.02

# Piso del punto de operacion **recall-prioritario**, que se reporta SOLO como
# alternativa informativa (es el default viejo, operativo degenerado): no es el
# default del artefacto.
PISO_RECALL_PRIORITARIO = 0.50

# Tolerancia absoluta de PR-AUC en VALID para considerar dos estrategias
# "empatadas". Entre las empatadas se elige la **mas simple** (sin remuestreo <
# costo-sensible < SMOTE): SMOTE solo gana si SUPERA por mas de esta tolerancia.
TOL_PRAUC = 0.005

# Orden de simplicidad de las estrategias (menor = mas simple).
ORDEN_SIMPLICIDAD = {"sin_remuestreo": 0, "costo_sensible": 1, "smote": 2}
ESTRATEGIAS = tuple(ORDEN_SIMPLICIDAD)


def _lgbm(seed: int, *, usar_gpu: bool, scale_pos_weight: float | None = None) -> Any:
    """Booster base de produccion (LightGBM, coherente con la 2a).

    Entrena en GPU si ``usar_gpu`` (``device="gpu"`` via OpenCL); la prediccion de
    LightGBM corre en **CPU** de forma nativa, asi que el artefacto es portable.
    """
    from lightgbm import LGBMClassifier

    return LGBMClassifier(
        n_estimators=400,
        learning_rate=0.05,
        num_leaves=63,
        subsample=0.8,
        colsample_bytree=0.8,
        subsample_freq=1,
        scale_pos_weight=scale_pos_weight,
        objective="binary",
        device="gpu" if usar_gpu else "cpu",
        random_state=seed,
        n_jobs=-1,
        verbose=-1,
    )


def construir_estrategia(
    nombre: str, seed: int, *, usar_gpu: bool, scale_pos_weight: float
) -> Any:
    """Devuelve el estimador de una estrategia (sklearn-like con ``predict_proba``).

    - ``sin_remuestreo``: booster tal cual.
    - ``costo_sensible``: booster con ``scale_pos_weight = n_neg/n_pos``.
    - ``smote``: ``imblearn.Pipeline([SMOTENC, booster])``. El sampler **solo actua
      en ``fit``** (sobre el train del fold/split); en ``predict`` se omite, de modo
      que valid/test nunca se remuestrean. SMOTENC interpola las numericas y
      muestrea categorias validas (respeta ``store_nbr``/``family``/...). Regla de
      fuga innegociable: SMOTE va **despues** del corte temporal, solo sobre train.
    """
    if nombre == "sin_remuestreo":
        return _lgbm(seed, usar_gpu=usar_gpu)
    if nombre == "costo_sensible":
        return _lgbm(seed, usar_gpu=usar_gpu, scale_pos_weight=scale_pos_weight)
    if nombre == "smote":
        from imblearn.over_sampling import SMOTENC
        from imblearn.pipeline import Pipeline as ImbPipeline

        return ImbPipeline(
            [
                ("smote", SMOTENC(categorical_features="auto", random_state=seed)),
                ("clf", _lgbm(seed, usar_gpu=usar_gpu)),
            ]
        )
    raise ValueError(f"Estrategia desconocida: {nombre}")


def _proba(modelo: Any, X: Any) -> np.ndarray:
    """Probabilidad de la clase positiva (``demanda_alta=1``)."""
    return np.asarray(modelo.predict_proba(X), dtype="float64")[:, 1]


# ---------------------------------------------------------------------------
# Seleccion de umbral en VALID (marco de negocio: max recall con piso REAL de precision)
# ---------------------------------------------------------------------------
def _candidatos_pr(
    y_true: np.ndarray, y_prob: np.ndarray
) -> list[tuple[float, float, float]]:
    """Lista de ``(umbral, precision, recall)`` de la curva PR (sin el punto final
    sin umbral que devuelve ``precision_recall_curve``)."""
    prec, rec, thr = precision_recall_curve(y_true, y_prob)
    return [(float(thr[i]), float(prec[i]), float(rec[i])) for i in range(len(thr))]


def _max_recall_con_piso(
    cand: list[tuple[float, float, float]], piso: float
) -> tuple[float, float, float] | None:
    """Entre los umbrales con ``precision >= piso``, el de **mayor recall** (desempate:
    mayor umbral). ``None`` si ninguno alcanza el piso."""
    viables = [c for c in cand if c[1] >= piso]
    if not viables:
        return None
    return max(viables, key=lambda c: (c[2], c[0]))


def _max_f1(cand: list[tuple[float, float, float]]) -> tuple[float, float, float]:
    """Umbral de **maximo F1** sobre los candidatos."""
    def f1(c: tuple[float, float, float]) -> float:
        p_, r_ = c[1], c[2]
        return (2 * p_ * r_ / (p_ + r_)) if (p_ + r_) > 0 else 0.0

    return max(cand, key=f1)


def seleccionar_umbral(
    y_true: np.ndarray,
    y_prob: np.ndarray,
    precision_floor: float = PRECISION_FLOOR,
    margen: float = MARGEN_VALID,
) -> tuple[float, dict[str, Any]]:
    """Elige el umbral por defecto en VALID: **max recall sujeto a un piso REAL de
    precision** (default 0.80), con margen de robustez VALID->TEST.

    Marco de negocio: no detectar demanda alta cuesta mas que una falsa alarma, asi
    que se prioriza recall; pero el operativo debe ser accionable, asi que se exige
    un piso real de precision (0.80, no 0.50). El piso efectivo en VALID es
    ``precision_floor + margen`` (se apunta un poco mas alto en valid para que el
    piso aguante en test). Si ningun umbral alcanza el piso efectivo se intenta sin
    margen; si tampoco, se cae a **max F1** (operativo equilibrado, no degenerado).
    Se decide SOLO sobre VALID.
    """
    cand = _candidatos_pr(y_true, y_prob)
    if not cand:
        return 0.5, {
            "criterio": "sin variabilidad de probabilidad; umbral por defecto 0.5",
            "precision_floor": precision_floor,
            "margen_valid": margen,
        }
    piso_efectivo = precision_floor + margen
    punto = _max_recall_con_piso(cand, piso_efectivo)
    if punto is not None:
        umbral, p, r = punto
        criterio = (
            f"max recall sujeto a precision >= {precision_floor:.2f} "
            f"(piso de negocio REAL, no 0.50; margen +{margen:.2f} en VALID -> piso "
            f"efectivo {piso_efectivo:.2f}- para que el piso aguante en TEST)"
        )
    elif (punto := _max_recall_con_piso(cand, precision_floor)) is not None:
        umbral, p, r = punto
        criterio = (
            f"max recall sujeto a precision >= {precision_floor:.2f} "
            f"(sin margen: ningun umbral alcanza el piso efectivo {piso_efectivo:.2f})"
        )
    else:
        umbral, p, r = _max_f1(cand)
        criterio = (
            f"ningun umbral alcanza precision {precision_floor:.2f}; "
            "fallback a max F1 (operativo equilibrado, no degenerado)"
        )
    return float(umbral), {
        "criterio": criterio,
        "precision_floor": precision_floor,
        "margen_valid": margen,
        "piso_efectivo_valid": round(piso_efectivo, 4),
        "precision_en_umbral": round(float(p), 4),
        "recall_en_umbral": round(float(r), 4),
    }


def _elegir_estrategia(
    metricas_valid: dict[str, dict[str, float]]
) -> tuple[str, dict[str, Any]]:
    """Elige la estrategia **mas simple** que maximice la PR-AUC en VALID.

    Regla de decision (held-out, VALID): se toma la mejor PR-AUC; las estrategias
    dentro de ``TOL_PRAUC`` de esa mejor se consideran empatadas y entre ellas gana
    la **mas simple** (sin remuestreo < costo-sensible < SMOTE). Asi **SMOTE solo
    "gana" si supera** a la costo-sensible (y a la base) por mas de la tolerancia en
    la metrica principal de la minoritaria. Mostrar que SMOTE no aporta es un
    resultado valido.
    """
    pr = {e: metricas_valid[e]["PR_AUC"] for e in metricas_valid}
    mejor_prauc = max(pr.values())
    empatadas = [e for e, v in pr.items() if v >= mejor_prauc - TOL_PRAUC]
    elegida = min(empatadas, key=lambda e: ORDEN_SIMPLICIDAD[e])
    criterio = {
        "decision_en": "valid",
        "metrica_principal": "PR_AUC",
        "tol_prauc": TOL_PRAUC,
        "pr_auc_valid": {e: round(float(v), 4) for e, v in pr.items()},
        "recall_valid": {
            e: round(float(metricas_valid[e].get("Recall", float("nan"))), 4)
            for e in metricas_valid
        },
        "empatadas_dentro_tol": sorted(empatadas, key=lambda e: ORDEN_SIMPLICIDAD[e]),
        "regla": (
            "estrategia mas simple (sin_remuestreo < costo_sensible < smote) cuya "
            f"PR-AUC en VALID esta dentro de {TOL_PRAUC} de la mejor; SMOTE solo se "
            "adopta si SUPERA a la costo-sensible por mas de esa tolerancia"
        ),
    }
    return elegida, criterio
