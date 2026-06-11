"""Tests del indice estacional mensual (correccion del sesgo tendencia/estacionalidad)."""

from __future__ import annotations

import pandas as pd

from spc.analysis.temporal import seasonal_month_index


def test_indice_estacional_no_depende_del_nivel_anual():
    """Aunque el nivel se duplique entre anios, el indice estacional debe ser estable.

    Es justamente lo que la version anterior (promedio crudo por mes) NO lograba.
    """
    daily = pd.DataFrame(
        {
            "year": [2013, 2013, 2014, 2014],
            "month": [1, 2, 1, 2],
            "sales_total": [100.0, 300.0, 200.0, 600.0],
        }
    )
    idx = seasonal_month_index(daily).set_index("month")["indice_estacional"]
    assert idx.loc[1] == 0.5
    assert idx.loc[2] == 1.5


def test_indice_estacional_plano_es_uno():
    daily = pd.DataFrame(
        {
            "year": [2013, 2013, 2014, 2014],
            "month": [1, 2, 1, 2],
            "sales_total": [50.0, 50.0, 80.0, 80.0],
        }
    )
    idx = seasonal_month_index(daily)
    assert (idx["indice_estacional"] == 1.0).all()
    assert (idx["anios_observados"] == 2).all()
