"""Tests transversales: Swagger/OpenAPI, salud y forma uniforme de los errores."""

from __future__ import annotations

import pytest


def test_swagger_documenta_los_tres_contratos(client):
    """El OpenAPI expone los tres endpoints del contrato y la docs de Swagger carga."""
    oa = client.get("/openapi.json")
    assert oa.status_code == 200
    esquema = oa.json()
    assert {"/sales", "/purchases", "/inventory"} <= set(esquema["paths"])
    # Cada endpoint documenta una respuesta 200 y los errores 400/422.
    for ruta in ("/sales", "/purchases", "/inventory"):
        respuestas = esquema["paths"][ruta]["post"]["responses"]
        assert "200" in respuestas
        assert "422" in respuestas
    # La página de Swagger se sirve.
    assert client.get("/docs").status_code == 200


def test_swagger_incluye_ejemplos_del_contrato(client):
    """Los esquemas de request llevan el ejemplo de la sección 3 del contrato."""
    esquema = client.get("/openapi.json").json()
    componentes = esquema["components"]["schemas"]
    ejemplo = componentes["VentasRequest"].get("example", {})
    assert ejemplo.get("granularity") == "day"
    assert "history" in ejemplo


def test_salud(client):
    """El endpoint de salud responde ok."""
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


@pytest.mark.parametrize(
    "ruta,cuerpo",
    [
        ("/sales", {"horizon": "siete", "history": []}),  # tipo inválido + lista vacía
        ("/purchases", {"history": "no-es-lista"}),  # falta parametros + tipo inválido
        ("/inventory", {}),  # faltan campos obligatorios
        ("/sales", "esto no es json válido para el esquema"),  # cuerpo no-objeto
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
