"""Tests del **CORS** de la API (Fase 3): el navegador del frontend puede llamarla.

El ``client`` del conftest arma la app con ``cors_origins=["http://localhost:5173"]``
(el origen típico de un frontend Vite en desarrollo). Estos tests fijan que el
middleware está **realmente activo**:

- el origen permitido se **refleja** tanto en el preflight (OPTIONS) como en una
  petición simple;
- un origen **no** permitido no recibe ese permiso.

En producción el origen se fija con ``SPC_CORS_ORIGINS`` (ver checklist de despliegue);
el default es ``*``. Aquí se inyecta un origen concreto para poder afirmar el reflejo.
"""

from __future__ import annotations

# Debe coincidir con el cors_origins inyectado por el fixture `client` del conftest.
ORIGEN = "http://localhost:5173"
ORIGEN_AJENO = "http://evil.example.com"
ALLOW_ORIGIN = "access-control-allow-origin"


def test_preflight_refleja_el_origen_permitido(client):
    """El preflight (OPTIONS) de POST /sales desde el origen permitido lo autoriza."""
    r = client.options(
        "/sales",
        headers={
            "Origin": ORIGEN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert r.status_code == 200, r.text
    assert r.headers.get(ALLOW_ORIGIN) == ORIGEN
    assert "POST" in r.headers.get("access-control-allow-methods", "")


def test_peticion_simple_refleja_el_origen_permitido(client):
    """Una petición simple con Origin permitido recibe la cabecera de permiso."""
    r = client.get("/health", headers={"Origin": ORIGEN})
    assert r.status_code == 200
    assert r.headers.get(ALLOW_ORIGIN) == ORIGEN


def test_origen_no_permitido_no_se_refleja(client):
    """Un origen fuera de la lista no recibe permiso para ese origen."""
    r = client.get("/health", headers={"Origin": ORIGEN_AJENO})
    # La petición se sirve igual (CORS lo aplica el navegador), pero NO se autoriza
    # el origen ajeno: la cabecera está ausente o no es ese origen.
    assert r.headers.get(ALLOW_ORIGIN) != ORIGEN_AJENO
