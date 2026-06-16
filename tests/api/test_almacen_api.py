"""Tests del endpoint ``POST /inventory`` (riesgo de quiebre y stock)."""

from __future__ import annotations

CLAVES_ALERTA = {
    "store_id",
    "product_id",
    "demand_class",
    "high_demand_probability",
    "stockout_risk",
    "recommended_stock",
    "safety_stock",
    "store_segment",
}


def test_almacen_valido_forma_contrato(client, historico_contrato):
    """Caso válido: la respuesta coincide en forma con la sección 3.3."""
    r = client.post(
        "/inventory",
        json={
            "history": historico_contrato,
            "inventory_status": [
                {"store_id": "1", "product_id": "BEVERAGES", "current_stock": 300, "lead_time_days": 3}
            ],
        },
    )
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["field"] == "inventory"
    item = cuerpo["alerts"][0]
    assert set(item.keys()) == CLAVES_ALERTA
    assert item["demand_class"] in {"high", "low"}
    assert 0.0 <= item["high_demand_probability"] <= 1.0
    assert isinstance(item["stockout_risk"], bool)
    assert isinstance(item["store_segment"], int)
    assert item["recommended_stock"] >= 0 and item["safety_stock"] >= 0
    assert "threshold" in cuerpo["metadata"]


def test_almacen_lead_time_opcional(client, historico_contrato):
    """``lead_time_days`` es opcional: la alerta se calcula igual (con el default)."""
    r = client.post(
        "/inventory",
        json={
            "history": historico_contrato,
            "inventory_status": [{"store_id": "2", "product_id": "BEVERAGES", "current_stock": 50}],
        },
    )
    assert r.status_code == 200
    assert len(r.json()["alerts"]) == 1


def test_almacen_producto_sin_historico(client, historico_contrato):
    """Producto sin histórico → 400 (no se puede evaluar su demanda)."""
    r = client.post(
        "/inventory",
        json={
            "history": historico_contrato,
            "inventory_status": [{"store_id": "1", "product_id": "NO_EXISTE", "current_stock": 10}],
        },
    )
    assert r.status_code == 400
    assert r.json()["error"]["type"] == "invalid_request"


def test_almacen_stock_negativo(client, historico_contrato):
    """``current_stock`` negativo → 422 controlado."""
    r = client.post(
        "/inventory",
        json={
            "history": historico_contrato,
            "inventory_status": [{"store_id": "1", "product_id": "BEVERAGES", "current_stock": -10}],
        },
    )
    assert r.status_code == 422
    assert r.json()["error"]["type"] == "validation"


def test_almacen_sin_inventario(client, historico_contrato):
    """Inventario vacío → 422 (min_length=1)."""
    r = client.post("/inventory", json={"history": historico_contrato, "inventory_status": []})
    assert r.status_code == 422
