"""Tests de no-fuga de futuro en el feature engineering de la regresion."""

from __future__ import annotations

import numpy as np

from spc.features.temporales import construir_features


def test_lags_no_usan_el_valor_actual(analitico_sintetico):
    """Los rezagos del objetivo deben ser el valor real desplazado, nunca el actual."""
    df_feat, features, _cats, _cfg = construir_features(analitico_sintetico)
    sub = df_feat[df_feat["store_nbr"] == 1].sort_values("date").reset_index(drop=True)
    sales = sub["sales"].to_numpy("float64")

    # La primera observacion de la serie no tiene pasado -> lag NaN.
    assert np.isnan(sub["sales_lag_1"].iloc[0])

    # lag_1 y lag_7 == ventas reales de t-1 y t-7.
    for k in range(1, len(sub)):
        assert float(sub["sales_lag_1"].iloc[k]) == sales[k - 1]
    for k in range(7, len(sub)):
        assert float(sub["sales_lag_7"].iloc[k]) == sales[k - 7]

    # La media movil de 7 usa SOLO el pasado [t-7, t-1], jamas incluye t.
    for k in range(7, len(sub)):
        esperado = sales[k - 7 : k].mean()
        assert abs(float(sub["sales_rmean_7"].iloc[k]) - esperado) < 1e-3


def test_transacciones_solo_como_rezago(analitico_sintetico):
    """Las transacciones del mismo periodo no pueden ser feature (fuga real)."""
    _df, features, _cats, _cfg = construir_features(analitico_sintetico)
    assert "transactions" not in features
    assert "transactions_filled" not in features
    assert any(c.startswith("trans_lag_") for c in features)
    # La promocion del dia SI es valida: es planificada/conocida de antemano.
    assert "onpromotion" in features
