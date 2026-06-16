"""Tests del adaptador contrato → motor (``spc.service.adaptador``).

Cubre el bug **texto vs número** de ``store_id``: el motor entrenó ``store_nbr``
como categórica de **enteros** (``int16``); si el adaptador entregaba el id como
texto (``"1"``), no casaba con la categoría ``1`` y la tienda **no aportaba** a la
predicción (degradaba a NaN). El adaptador ahora convierte el id entero a ``int``
preservando la identidad de los ids no numéricos.
"""

from __future__ import annotations

import pandas as pd

from spc.service.adaptador import historico_a_analitico


def _hist(store_id, n=2):
    return [
        {
            "date": f"2017-08-0{i + 1}",
            "store_id": store_id,
            "product_id": "BEVERAGES",
            "units_sold": 100 + i,
        }
        for i in range(n)
    ]


def test_store_id_entero_se_mapea_a_int():
    """``store_id`` entero ("1") → ``store_nbr`` ``int`` 1 (tipo del motor)."""
    df = historico_a_analitico(_hist("1"))
    valores = df["store_nbr"].unique().tolist()
    assert valores == [1]
    assert all(isinstance(v, int) for v in valores)


def test_store_id_entero_casa_con_categorica_int_del_motor():
    """Regresión del bug: con el ``CategoricalDtype`` de enteros del artefacto, un
    ``store_id`` entero produce un código de categoría **válido** (no NaN)."""
    df = historico_a_analitico(_hist("1"))
    trained = pd.CategoricalDtype(categories=pd.Index([1, 2, 3], dtype="int16"))
    cat = df["store_nbr"].astype(object).astype(trained)
    # Antes del arreglo (store_nbr = "1" texto) todos caían a NaN (código -1).
    assert not cat.isna().any()
    assert (cat.cat.codes >= 0).all()


def test_store_id_no_numerico_se_mantiene_texto():
    """Un id no numérico ("STORE_A") se deja como texto: cold-start esperado."""
    df = historico_a_analitico(_hist("STORE_A"))
    valores = df["store_nbr"].unique().tolist()
    assert valores == ["STORE_A"]
    assert all(isinstance(v, str) for v in valores)


def test_store_id_preserva_identidad_no_round_trip():
    """``"007"`` NO se convierte a 7: se preserva la identidad del id (para no romper
    el join con replenishment_params/inventory_status ni la salida)."""
    df = historico_a_analitico(_hist("007"))
    assert df["store_nbr"].unique().tolist() == ["007"]


def test_store_id_int_nativo_tambien_se_mapea():
    """El adaptador acepta el id como ``int`` nativo (no solo texto) y lo conserva."""
    hist = [{"date": "2017-08-01", "store_id": 2, "product_id": "BEVERAGES", "units_sold": 100}]
    df = historico_a_analitico(hist)
    assert df["store_nbr"].unique().tolist() == [2]
