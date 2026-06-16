"""Tests del endpoint ``POST /purchases`` (reposición derivada)."""

from __future__ import annotations

CLAVES_RECOMENDACION = {
    "store_id",
    "product_id",
    "expected_demand_horizon",
    "reorder_point",
    "replenishment_quantity",
    "justification",
}


def _params(stock_actual=900, lead=3, cobertura=7):
    return [
        {
            "store_id": "1",
            "product_id": "BEVERAGES",
            "current_stock": stock_actual,
            "lead_time_days": lead,
            "target_coverage_days": cobertura,
        }
    ]


def test_compras_valido_forma_contrato(client, historico_contrato):
    """Caso válido: la respuesta coincide en forma con la sección 3.2."""
    r = client.post(
        "/purchases", json={"history": historico_contrato, "replenishment_params": _params()}
    )
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["field"] == "purchases"
    assert len(cuerpo["recommendation"]) == 1
    item = cuerpo["recommendation"][0]
    assert set(item.keys()) == CLAVES_RECOMENDACION
    assert item["replenishment_quantity"] >= 0
    assert item["expected_demand_horizon"] >= 0
    assert isinstance(item["justification"], str) and item["justification"]
    assert "assumption" in cuerpo["metadata"]


def test_compras_stock_alto_no_repone(client, historico_contrato):
    """Con stock muy alto, la cantidad a reponer es 0 (no negativa)."""
    r = client.post(
        "/purchases",
        json={"history": historico_contrato, "replenishment_params": _params(stock_actual=10**9)},
    )
    assert r.status_code == 200
    assert r.json()["recommendation"][0]["replenishment_quantity"] == 0


def test_compras_producto_sin_historico(client, historico_contrato):
    """Producto sin histórico → 400 (no se puede pronosticar su demanda)."""
    params = [
        {
            "store_id": "99",
            "product_id": "NO_EXISTE",
            "current_stock": 10,
            "lead_time_days": 2,
            "target_coverage_days": 3,
        }
    ]
    r = client.post("/purchases", json={"history": historico_contrato, "replenishment_params": params})
    assert r.status_code == 400
    assert r.json()["error"]["type"] == "invalid_request"


def test_compras_lead_time_invalido(client, historico_contrato):
    """``lead_time_days=0`` viola el contrato (> 0) → 422."""
    r = client.post(
        "/purchases", json={"history": historico_contrato, "replenishment_params": _params(lead=0)}
    )
    assert r.status_code == 422
    assert r.json()["error"]["type"] == "validation"


def test_compras_sin_parametros(client, historico_contrato):
    """Lista de parámetros vacía → 422 (min_length=1)."""
    r = client.post(
        "/purchases", json={"history": historico_contrato, "replenishment_params": []}
    )
    assert r.status_code == 422
