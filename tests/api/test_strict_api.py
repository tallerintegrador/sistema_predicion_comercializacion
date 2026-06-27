"""Tests de **validación estricta** (`strict=True`) del contrato v1.0.0.

El contrato prohíbe las **coerciones silenciosas de tipo**: enviar un número como
texto (`units_sold="123"`), un decimal donde va un entero (`on_promotion=5.0`) o un
booleano como texto (`event_active="true"`) **se rechaza** con un 422 controlado que
señala el campo exacto, en vez de convertirse en silencio.

También se fija la **regresión**: la entrada legítima (fecha como cadena ISO,
identificadores como número o texto, enteros que ensanchan a float) **sigue pasando**.
"""

from __future__ import annotations

import pytest


def _item(**override) -> dict:
    """Un elemento válido del bloque ``history`` con campos mutados para el caso."""
    base = {"date": "2017-08-01", "store_id": "1", "product_id": "BEVERAGES", "units_sold": 10}
    base.update(override)
    return base


def _assert_422_validation(r, campo: str) -> None:
    """Afirma 422 controlado (`type=validation`) señalando ``campo`` en los detalles."""
    assert r.status_code == 422, r.text
    cuerpo = r.json()
    assert cuerpo["error"]["type"] == "validation"
    campos = {d["field"] for d in cuerpo["error"]["details"]}
    assert campo in campos, f"esperaba '{campo}' en {campos}"


# ---------------------------------------------------------------------------
# SALES — bloque history y parámetros
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "override,campo",
    [
        ({"units_sold": "123"}, "history.0.units_sold"),       # str numérico → no se coiere
        ({"on_promotion": 5.0}, "history.0.on_promotion"),     # float donde va int
        ({"on_promotion": "5"}, "history.0.on_promotion"),     # str numérico
        ({"transactions": "99"}, "history.0.transactions"),    # str numérico (opcional)
        ({"event_active": "true"}, "history.0.event_active"),  # str donde va bool
    ],
)
def test_sales_strict_rechaza_coercion_en_history(client, override, campo):
    """Cada tipo 'casi válido' del histórico se rechaza en vez de coercionarse."""
    r = client.post("/sales", json={"horizon": 7, "history": [_item(**override)]})
    _assert_422_validation(r, campo)


def test_sales_strict_rechaza_horizon_str(client):
    """``horizon="7"`` (texto) ya no se convierte a 7 → 422."""
    r = client.post("/sales", json={"horizon": "7", "history": [_item()]})
    _assert_422_validation(r, "horizon")


def test_sales_strict_rechaza_horizon_float(client):
    """``horizon=7.0`` (decimal) ya no se trunca a 7 → 422."""
    r = client.post("/sales", json={"horizon": 7.0, "history": [_item()]})
    _assert_422_validation(r, "horizon")


def test_sales_valido_sigue_pasando(client, historico_contrato):
    """Regresión: strict no rompe la entrada legítima.

    Fecha como cadena ISO, ``store_id`` texto, ``units_sold``/``transactions`` con
    enteros y floats correctos: todo debe seguir devolviendo 200.
    """
    r = client.post(
        "/sales", json={"granularity": "day", "horizon": 3, "history": historico_contrato}
    )
    assert r.status_code == 200, r.text


def test_sales_store_id_entero_sigue_aceptado(client):
    """La conversión intencional id número→texto se conserva: ``store_id=1`` (int) pasa."""
    item = {"date": "2017-08-01", "store_id": 1, "product_id": "BEVERAGES", "units_sold": 10}
    # Validación de esquema OK (la lógica de negocio puede luego dar 400 por falta de
    # histórico suficiente, pero NO 422 de validación de tipo).
    r = client.post("/sales", json={"horizon": 1, "history": [item]})
    assert r.status_code != 422, r.text


# ---------------------------------------------------------------------------
# PURCHASES — replenishment_params
# ---------------------------------------------------------------------------
def test_purchases_strict_rechaza_lead_time_float(client, historico_contrato):
    """``lead_time_days=3.0`` (decimal) → 422 en vez de truncar a 3."""
    params = [{
        "store_id": "1", "product_id": "BEVERAGES",
        "current_stock": 900, "lead_time_days": 3.0, "target_coverage_days": 7,
    }]
    r = client.post("/purchases", json={"history": historico_contrato, "replenishment_params": params})
    _assert_422_validation(r, "replenishment_params.0.lead_time_days")


def test_purchases_strict_rechaza_current_stock_str(client, historico_contrato):
    """``current_stock="900"`` (texto) → 422 en vez de coercionar."""
    params = [{
        "store_id": "1", "product_id": "BEVERAGES",
        "current_stock": "900", "lead_time_days": 3, "target_coverage_days": 7,
    }]
    r = client.post("/purchases", json={"history": historico_contrato, "replenishment_params": params})
    _assert_422_validation(r, "replenishment_params.0.current_stock")


# ---------------------------------------------------------------------------
# INVENTORY — inventory_status
# ---------------------------------------------------------------------------
def test_inventory_strict_rechaza_current_stock_str(client, historico_contrato):
    """``current_stock="300"`` (texto) → 422."""
    inv = [{"store_id": "1", "product_id": "BEVERAGES", "current_stock": "300"}]
    r = client.post("/inventory", json={"history": historico_contrato, "inventory_status": inv})
    _assert_422_validation(r, "inventory_status.0.current_stock")


def test_inventory_strict_rechaza_lead_time_float(client, historico_contrato):
    """``lead_time_days=3.0`` (decimal) en el opcional → 422 (no se trunca)."""
    inv = [{"store_id": "1", "product_id": "BEVERAGES", "current_stock": 300, "lead_time_days": 3.0}]
    r = client.post("/inventory", json={"history": historico_contrato, "inventory_status": inv})
    _assert_422_validation(r, "inventory_status.0.lead_time_days")
