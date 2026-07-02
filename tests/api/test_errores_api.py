"""Tests transversales: Swagger/OpenAPI, salud y forma uniforme de los errores."""

from __future__ import annotations

import pytest

_RUTAS_V2 = ("/v2/ventas", "/v2/compras", "/v2/almacen")


def test_swagger_documenta_los_dominios_3x3(client):
    """El OpenAPI expone los tres endpoints 3×3 y la docs de Swagger carga."""
    oa = client.get("/openapi.json")
    assert oa.status_code == 200
    esquema = oa.json()
    assert set(_RUTAS_V2) <= set(esquema["paths"])
    # Cada endpoint documenta una respuesta 200 y los errores 400/422.
    for ruta in _RUTAS_V2:
        respuestas = esquema["paths"][ruta]["post"]["responses"]
        assert "200" in respuestas
        assert "422" in respuestas
    # La página de Swagger se sirve.
    assert client.get("/docs").status_code == 200


def test_swagger_incluye_ejemplo_del_contrato(client):
    """El esquema de request 3×3 lleva el ejemplo (rows + horizon)."""
    esquema = client.get("/openapi.json").json()
    componentes = esquema["components"]["schemas"]
    ejemplo = componentes["Analisis3x3Request"].get("example", {})
    assert ejemplo.get("horizon") == 14
    assert "rows" in ejemplo


def test_salud(client):
    """El endpoint de salud responde ok."""
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


@pytest.mark.parametrize(
    "ruta,cuerpo",
    [
        ("/v2/ventas", {"horizon": "siete", "rows": [{"fecha": "2023-01-01"}]}),  # horizon tipo inválido
        ("/v2/compras", {"rows": "no-es-lista"}),  # tipo inválido
        ("/v2/almacen", {"rows": []}),  # lista vacía (min_length=1)
        ("/v2/ventas", "esto no es json válido para el esquema"),  # cuerpo no-objeto
        ("/v2/ventas", {"rows": [{"fecha": "2023-01-01", "sku": "SKU-001"}], "horizon": 7}),  # faltan columnas → 400
    ],
)
def test_entradas_mal_formadas_no_producen_500(client, ruta, cuerpo):
    """Ninguna entrada mal formada debe producir un 500: siempre error controlado."""
    r = client.post(ruta, json=cuerpo)
    assert r.status_code in (400, 422), r.text
    cuerpo_error = r.json()
    assert "error" in cuerpo_error
    assert cuerpo_error["error"]["type"] in {"validation", "invalid_request"}
    assert isinstance(cuerpo_error["error"]["message"], str)
