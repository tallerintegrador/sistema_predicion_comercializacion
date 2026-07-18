"""Tests del núcleo de regresión (`spc.models.nucleo`).

Cubren las primitivas ligeras del motor sin entrenar boosters pesados: el zoo de modelos
(inventario y espacios de objetivo), la conversión cruda→unidades en ambos espacios
(``log`` y ``unidades``), el ensamble ponderado con submodelos de mentira, y los pesos
convexos que minimizan el MAE en VALID (≥0 y suman 1).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from spc.models import nucleo


class _FakeModelo:
    """Submodelo mínimo con ``predict`` fijo (evita entrenar sklearn en el test)."""

    def __init__(self, valores: np.ndarray) -> None:
        self._v = np.asarray(valores, dtype="float64")

    def predict(self, X) -> np.ndarray:  # noqa: ARG002 - firma sklearn-like
        return self._v


# ---------------------------------------------------------------------------
# Cortes temporales
# ---------------------------------------------------------------------------
def test_cortes_temporales_as_dict() -> None:
    c = nucleo.CortesTemporales(
        train_fin=pd.Timestamp("2024-06-30"),
        valid_ini=pd.Timestamp("2024-07-01"),
        valid_fin=pd.Timestamp("2024-07-15"),
        test_ini=pd.Timestamp("2024-07-16"),
        test_fin=pd.Timestamp("2024-07-31"),
    )
    d = c.as_dict()
    assert d["train"] == "<= 2024-06-30"
    assert d["valid"] == "2024-07-01 .. 2024-07-15"
    assert d["test"] == "2024-07-16 .. 2024-07-31"


# ---------------------------------------------------------------------------
# Zoo de modelos
# ---------------------------------------------------------------------------
def test_construir_zoo_inventario_y_espacios() -> None:
    zoo = nucleo.construir_zoo(seed=42, features=["a", "b"], cats=["a"])
    # Ocho regresores: cinco en log-espacio + tres objetivos de conteo en unidades.
    assert len(zoo) == 8
    assert set(zoo) == {
        "Ridge", "RandomForest", "HistGradientBoosting", "LightGBM", "XGBoost",
        "LightGBM_Tweedie", "LightGBM_Poisson", "XGBoost_Tweedie",
    }
    # Los objetivos Tweedie/Poisson predicen en unidades; los demás en log.
    assert zoo["LightGBM_Tweedie"].espacio == "unidades"
    assert zoo["LightGBM_Poisson"].espacio == "unidades"
    assert zoo["XGBoost_Tweedie"].espacio == "unidades"
    assert zoo["Ridge"].espacio == "log"


def test_zoo_construir_devuelve_estimador_sklearn() -> None:
    zoo = nucleo.construir_zoo(seed=42, features=["a"], cats=[])
    modelo = zoo["RandomForest"].construir()
    assert hasattr(modelo, "fit") and hasattr(modelo, "predict")


# ---------------------------------------------------------------------------
# Conversión a unidades
# ---------------------------------------------------------------------------
def test_a_unidades_espacio_log_invierte_expm1_y_recorta() -> None:
    crudo = np.log1p(np.array([0.0, 10.0, 100.0]))
    out = nucleo._a_unidades(crudo, "log", techo_log=None, techo_unidades=None)
    assert np.allclose(out, [0.0, 10.0, 100.0], atol=1e-6)
    assert (out >= 0).all()


def test_a_unidades_espacio_unidades_recorta_negativos() -> None:
    out = nucleo._a_unidades(np.array([-5.0, 3.0, 200.0]), "unidades", None, techo_unidades=100.0)
    # Negativos → 0, y techo de unidades aplicado.
    assert out[0] == 0.0
    assert out[2] == 100.0


# ---------------------------------------------------------------------------
# ModeloEnsemble
# ---------------------------------------------------------------------------
def test_ensemble_promedia_ponderado_en_unidades() -> None:
    # Dos submodelos ya en unidades; pesos 0.25/0.75 → combinación convexa exacta.
    m1 = _FakeModelo([10.0, 20.0])
    m2 = _FakeModelo([30.0, 40.0])
    ens = nucleo.ModeloEnsemble(
        modelos=[m1, m2],
        espacios=["unidades", "unidades"],
        pesos=np.array([0.25, 0.75]),
        techo_log=None,
        techo_unidades=None,
    )
    pred = ens.predict(X=np.zeros((2, 1)))
    assert np.allclose(pred, [0.25 * 10 + 0.75 * 30, 0.25 * 20 + 0.75 * 40])
    assert pred.shape == (2,)


# ---------------------------------------------------------------------------
# Pesos convexos
# ---------------------------------------------------------------------------
def test_mejores_pesos_son_convexos() -> None:
    rng = np.random.default_rng(42)
    y = rng.uniform(0, 100, 50)
    # Miembro 0 = casi perfecto; miembro 1 = ruidoso → debe pesar más el bueno.
    M = np.column_stack([y + rng.normal(0, 0.5, 50), rng.uniform(0, 100, 50)])
    w = nucleo._mejores_pesos(M, y)
    assert np.all(w >= 0)
    assert abs(w.sum() - 1.0) < 1e-9
    assert w[0] > w[1]  # el miembro fiel pesa más
