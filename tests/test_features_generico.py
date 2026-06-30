"""Tests del motor de features **agnóstico** (`spc.features.generico`): no-fuga y forma.

La garantía crítica es la misma que en el motor retail: la fila del día ``t`` solo ve
información de días ``< t``. Aquí se verifica de forma agnóstica al nombre de las columnas.
"""

from __future__ import annotations

import pandas as pd

from spc.features.generico import (
    EspecEsquema,
    columnas_lag_objetivo,
    construir_features,
)


def _df(n: int = 40) -> pd.DataFrame:
    fechas = pd.date_range("2024-01-01", periods=n, freq="D")
    filas = []
    for serie in ("A", "B"):
        for i, f in enumerate(fechas):
            filas.append({"fecha": f, "serie": serie, "y": float(10 + i),
                          "promo": i % 3, "trafico": float(20 + i), "zona": "z" + serie})
    return pd.DataFrame(filas)


_SPEC = EspecEsquema(
    objetivo="y", col_fecha="fecha", cols_serie=("serie",),
    num_conocidas_futuro=("promo",), num_solo_pasado=("trafico",), cats_extra=("zona",),
)


def test_objetivo_no_es_feature() -> None:
    _, features, cats = construir_features(_df(), _SPEC)
    assert "y" not in features
    assert "serie" in cats and "zona" in cats
    # Las claves de serie y categóricas son features categóricas.
    assert {"serie", "zona", "promo"} <= set(features)


def test_features_enriquecidas_presentes() -> None:
    """Proximidad de calendario, recencia y rezagos de conocidas-a-futuro están presentes."""
    _, features, _ = construir_features(_df(), _SPEC)
    assert {"g_dias_a_fin_mes", "g_dias_desde_inicio_mes", "g_dist_quincena"} <= set(features)
    assert "tgt_dias_desde_pos" in features
    # `promo` es conocida a futuro → además del valor del día, sus rezagos/intensidad.
    assert {"featkf_lag_promo_1", "featkf_rmean_promo_7"} <= set(features)
    assert "promo" in features  # el valor del día (passthrough) se conserva


def test_sin_fuga_de_futuro() -> None:
    """Cambiar el objetivo del ÚLTIMO día no debe alterar las features de días previos."""
    df = _df()
    feat1, features, _ = construir_features(df, _SPEC)
    cols_calc = [c for c in features if c.startswith(("tgt_", "feat_", "featkf_", "g_"))]

    df2 = df.copy()
    ultimo = df2["fecha"].max()
    df2.loc[df2["fecha"] == ultimo, "y"] = 9999.0  # perturba solo el futuro
    feat2, _, _ = construir_features(df2, _SPEC)

    previas = feat1["fecha"] < ultimo
    a = feat1.loc[previas, cols_calc].reset_index(drop=True)
    b = feat2.loc[previas.values, cols_calc].reset_index(drop=True)
    pd.testing.assert_frame_equal(a, b)


def test_lags_calentamiento_nan() -> None:
    """La primera fila de cada serie no tiene pasado: sus rezagos del objetivo son NaN."""
    feat, features, _ = construir_features(_df(), _SPEC)
    cols_lag = columnas_lag_objetivo(features)
    assert cols_lag
    primeras = feat.groupby("serie", observed=True).head(1)
    assert primeras[cols_lag].isna().all().all()


def test_modo_tabular_sin_fecha() -> None:
    """Sin fecha declarada: sin rezagos, las features se usan tal cual."""
    spec = EspecEsquema(objetivo="y", col_fecha=None, cols_serie=("serie",),
                        num_conocidas_futuro=("promo",), num_solo_pasado=("trafico",),
                        cats_extra=("zona",))
    _, features, _ = construir_features(_df(), spec)
    assert not columnas_lag_objetivo(features)
    # En tabular, las "solo-pasado" se tratan como conocidas (passthrough).
    assert "trafico" in features and "promo" in features
