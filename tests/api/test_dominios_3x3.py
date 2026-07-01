"""Tests del router **3×3 por dominio** (Fase 3): un formato, tres modelos en el momento.

Verifican el contrato del rediseño: cada endpoint ``/v2/{dominio}`` devuelve los tres
bloques (regresión, clasificación, clustering) entrenados al vuelo, y las entradas mal
formadas devuelven el error uniforme.
"""

from __future__ import annotations

import pytest

from spc.synthetic import generar_dominio


def _rows(dominio: str) -> list[dict]:
    """Filas pequeñas (JSON-safe) del dominio para una petición rápida."""
    if dominio == "compras":
        df = generar_dominio("compras", seed=42, n_proveedores=4, n_productos=4, n_ordenes_por_serie=25)
        col_fecha = "fecha_orden"
    else:
        df = generar_dominio(dominio, seed=42, n_tiendas=2, n_productos=4, n_dias=120)
        col_fecha = "fecha"
    df[col_fecha] = df[col_fecha].astype(str)
    return df.to_dict(orient="records")


@pytest.mark.parametrize("dominio", ["ventas", "compras", "almacen"])
def test_analisis_3x3_tres_bloques(client, dominio: str) -> None:
    resp = client.post(f"/v2/{dominio}", json={"rows": _rows(dominio), "horizon": 7})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["dominio"] == dominio
    # Los tres modelos presentes.
    assert {"regresion", "clasificacion", "clustering"} <= set(body)
    assert body["regresion"]["modelo_ganador"]
    assert body["clasificacion"]["etiqueta"]
    assert body["clustering"]["k"] >= 2
    # Clasificación produce una alerta por serie.
    assert len(body["clasificacion"]["alertas"]) >= 1


def test_ventas_pronostica_horizonte(client) -> None:
    resp = client.post("/v2/ventas", json={"rows": _rows("ventas"), "horizon": 5})
    assert resp.status_code == 200, resp.text
    reg = resp.json()["regresion"]
    # Pronóstico no vacío y con la forma esperada.
    assert reg["prediccion"], "el pronóstico de ventas no debe estar vacío"
    item = reg["prediccion"][0]
    assert {"fecha", "prediccion", "sku", "id_tienda"} <= set(item)


def test_demo_compras(client) -> None:
    resp = client.get("/v2/compras/demo", params={"horizon": 7})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["dominio"] == "compras"
    assert body["clustering"]["k"] >= 2


def test_almacen_predice_demanda_y_muestra_indicadores(client) -> None:
    # ADR-0025 (e): la regresión de almacén predice `demanda_dia` y los KPIs de inventario
    # (cobertura, punto de reposición, stock de seguridad) se MUESTRAN derivados.
    resp = client.post("/v2/almacen", json={"rows": _rows("almacen"), "horizon": 7})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["regresion"]["objetivo"] == "demanda_dia"
    ind = body["indicadores_inventario"]
    assert len(ind) >= 1
    assert {
        "sku", "demanda_diaria_prevista", "stock_seguridad",
        "punto_reposicion", "dias_cobertura_proyectada", "alerta_reposicion",
    } <= set(ind[0])


def test_rows_invalidas_devuelve_error(client) -> None:
    # Faltan columnas del formato → 400 con el error uniforme.
    resp = client.post("/v2/ventas", json={"rows": [{"fecha": "2023-01-01", "sku": "SKU-001"}], "horizon": 7})
    assert resp.status_code == 400
    assert "error" in resp.json()


def test_rows_vacias_devuelve_422(client) -> None:
    resp = client.post("/v2/almacen", json={"rows": [], "horizon": 7})
    assert resp.status_code == 422
