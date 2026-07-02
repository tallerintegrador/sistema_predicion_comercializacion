"""No-fuga de futuro **y de etiqueta** en las features de la clasificacion (2b).

La cantidad que define la etiqueta (`sales` del periodo actual) no puede ser
feature, ni `family_sales_p75` ni `demanda_alta`. Se reutilizan exactamente las
mismas features leak-safe de la 2a (`spc.features.temporales`).
"""

from __future__ import annotations

import numpy as np

from spc.features.temporales import columnas_rezago, construir_features

# Columnas que filtrarian la etiqueta del periodo actual.
PROHIBIDAS = {"sales", "family_sales_p75", "demanda_alta"}


def test_etiqueta_y_sales_actual_no_son_features(analitico_clasificacion):
    """Ninguna feature es `sales` actual, `family_sales_p75` ni `demanda_alta`."""
    _df, features, _cats, _cfg = construir_features(analitico_clasificacion)
    assert PROHIBIDAS.isdisjoint(set(features)), (
        f"feature(s) que filtran la etiqueta: {PROHIBIDAS & set(features)}"
    )
    # Si, en cambio, deben existir rezagos pasados de sales (señal valida).
    assert any(c.startswith("sales_lag_") for c in features)


def test_transacciones_solo_como_rezago(analitico_clasificacion):
    """Transacciones del mismo periodo no son feature (igual que la 2a)."""
    _df, features, _cats, _cfg = construir_features(analitico_clasificacion)
    assert "transactions" not in features
    assert "transactions_filled" not in features
    assert any(c.startswith("trans_lag_") for c in features)
    assert "onpromotion" in features  # promocion del dia: planificada, valida


def test_inflar_sales_actual_no_altera_features(analitico_clasificacion):
    """No-fuga fuerte: inflar la venta del periodo (la que define la etiqueta) no
    cambia ninguna feature de rezago/ventana (solo miran al pasado)."""
    base = analitico_clasificacion
    df_a, features, _c, _cfg = construir_features(base)
    cols = columnas_rezago(features)

    mod = base.copy()
    fecha_max = mod.groupby(["store_nbr", "family"], observed=True)["date"].transform("max")
    mod.loc[mod["date"] == fecha_max, "sales"] = mod["sales"] + 1e6
    df_b, _f, _c2, _cfg2 = construir_features(mod)

    a = df_a[cols].fillna(-1).to_numpy()
    b = df_b[cols].fillna(-1).to_numpy()
    assert np.array_equal(a, b)
