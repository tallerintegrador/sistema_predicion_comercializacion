"""Tests del endpoint ``POST /sales`` (pronóstico de demanda)."""

from __future__ import annotations

from spc.service import adaptador

CLAVES_PRONOSTICO = {"date", "store_id", "product_id", "forecast_demand"}


def test_store_id_casa_con_categorica_del_artefacto(registro, historico_contrato):
    """Regresión del bug texto vs número: el ``store_id`` del contrato casa con la
    categórica de tienda **entrenada en el artefacto real**, así que la tienda
    aporta (no degrada a NaN). Antes del arreglo, ``store_nbr`` viajaba como texto
    ("1") y no casaba con la categoría entera ``1`` → todas las filas caían a NaN.
    """
    analitico = adaptador.historico_a_analitico(historico_contrato)
    dtype_store = registro.regresion.objeto.categorias["store_nbr"]
    casteado = analitico["store_nbr"].astype(object).astype(dtype_store)
    # Las tiendas "1" y "2" existen en el set sintético de entrenamiento → sin NaN.
    assert not casteado.isna().any()
    assert (casteado.cat.codes >= 0).all()


def test_ventas_valido_forma_contrato(client, historico_contrato):
    """Caso válido: la respuesta coincide en forma y campos con la sección 3.1."""
    r = client.post(
        "/sales", json={"granularity": "day", "horizon": 7, "history": historico_contrato}
    )
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["field"] == "sales"
    assert cuerpo["model"]  # versión real leída del meta (p. ej. regresion_v3)
    # 2 series x 7 días.
    assert len(cuerpo["forecast"]) == 2 * 7
    for item in cuerpo["forecast"]:
        assert set(item.keys()) == CLAVES_PRONOSTICO  # interval_80 se omite (diferido)
        assert item["forecast_demand"] >= 0
    assert cuerpo["metadata"]["scale"] == "units"


def test_ventas_agrega_por_semana(client, historico_contrato):
    """Granularidad semanal: agrega (suma) el pronóstico diario en menos filas."""
    diario = client.post(
        "/sales", json={"granularity": "day", "horizon": 14, "history": historico_contrato}
    ).json()
    semanal = client.post(
        "/sales", json={"granularity": "week", "horizon": 14, "history": historico_contrato}
    ).json()
    assert len(semanal["forecast"]) < len(diario["forecast"])
    # La demanda total agregada se conserva (suma de días); la pequeña diferencia es
    # solo ruido de redondeo a 2 decimales (diario: 28 filas; semanal: pocas).
    total_diario = sum(p["forecast_demand"] for p in diario["forecast"])
    total_semanal = sum(p["forecast_demand"] for p in semanal["forecast"])
    assert abs(total_diario - total_semanal) < 1.0


def test_ventas_horizonte_cero_rechazado(client, historico_contrato):
    """``horizon=0`` viola el contrato (> 0) → 422 controlado."""
    r = client.post(
        "/sales", json={"granularity": "day", "horizon": 0, "history": historico_contrato}
    )
    assert r.status_code == 422
    assert r.json()["error"]["type"] == "validation"


def test_ventas_falta_historico(client):
    """Falta el campo obligatorio ``history`` → 422 con detalle del campo."""
    r = client.post("/sales", json={"granularity": "day", "horizon": 7})
    assert r.status_code == 422
    campos = {d["field"] for d in r.json()["error"]["details"]}
    assert "history" in campos


def test_ventas_unidades_negativas(client):
    """``units_sold`` negativo → 422 señalando el campo exacto."""
    r = client.post(
        "/sales",
        json={
            "granularity": "day",
            "horizon": 7,
            "history": [
                {
                    "date": "2017-08-01",
                    "store_id": "1",
                    "product_id": "BEVERAGES",
                    "units_sold": -5,
                }
            ],
        },
    )
    assert r.status_code == 422
    campos = {d["field"] for d in r.json()["error"]["details"]}
    assert "history.0.units_sold" in campos
