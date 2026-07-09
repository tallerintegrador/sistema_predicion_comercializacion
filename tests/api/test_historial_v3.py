"""Tests del historial de predicciones v3 (persistencia best-effort + endpoints de lectura).

Usa el fixture ``client`` de ``conftest`` (auth desactivada + base SQLite temporal con el
registro de modelos montado), de modo que el enganche best-effort de ``/v3/{modulo}`` sí
persiste en la tabla ``predictions``.
"""

from __future__ import annotations

from spc.synthetic import generar_dominio


def _cuerpo_ventas() -> dict:
    df = generar_dominio("ventas", seed=42, n_tiendas=2, n_productos=4, n_dias=120)
    df["fecha"] = df["fecha"].astype(str)
    return {"rows": df.to_dict(orient="records")}


def test_analisis_v3_queda_en_el_historial(client) -> None:
    h = {"X-Client-Id": "cli-hist"}
    # Antes de analizar, el historial está vacío.
    r0 = client.get("/v3/ventas/historial", headers=h)
    assert r0.status_code == 200, r0.text
    assert r0.json()["total"] == 0

    # Ejecuta un análisis.
    r1 = client.post("/v3/ventas", json=_cuerpo_ventas(), headers=h)
    assert r1.status_code == 200, r1.text

    # Ahora aparece una entrada con metadatos.
    r2 = client.get("/v3/ventas/historial", headers=h)
    assert r2.status_code == 200
    items = r2.json()["items"]
    assert len(items) == 1
    assert items[0]["module"] == "ventas"
    assert items[0]["rows"] > 0
    assert items[0]["reports"] == 10


def test_detalle_guarda_valores_predichos(client) -> None:
    h = {"X-Client-Id": "cli-hist2"}
    client.post("/v3/ventas", json=_cuerpo_ventas(), headers=h)
    pid = client.get("/v3/ventas/historial", headers=h).json()["items"][0]["id"]

    d = client.get(f"/v3/historial/{pid}", headers=h)
    assert d.status_code == 200, d.text
    cuerpo = d.json()
    assert cuerpo["module"] == "ventas"
    assert cuerpo["response"]["n_reportes"] == 10
    assert len(cuerpo["response"]["reports"]) == 10


def test_historial_aislado_por_cliente(client) -> None:
    client.post("/v3/ventas", json=_cuerpo_ventas(), headers={"X-Client-Id": "cli-A"})
    # Otro cliente no ve las predicciones del primero.
    r = client.get("/v3/ventas/historial", headers={"X-Client-Id": "cli-B"})
    assert r.status_code == 200
    assert r.json()["total"] == 0


def test_detalle_de_otro_cliente_es_404(client) -> None:
    client.post("/v3/ventas", json=_cuerpo_ventas(), headers={"X-Client-Id": "cli-A"})
    pid = client.get("/v3/ventas/historial", headers={"X-Client-Id": "cli-A"}).json()["items"][0]["id"]
    r = client.get(f"/v3/historial/{pid}", headers={"X-Client-Id": "cli-B"})
    assert r.status_code == 404


def test_filtro_por_categoria(client) -> None:
    h = {"X-Client-Id": "cli-mix"}
    client.post("/v3/ventas", json=_cuerpo_ventas(), headers=h)
    # El historial de compras sigue vacío para este cliente (solo hizo ventas).
    r = client.get("/v3/compras/historial", headers=h)
    assert r.status_code == 200
    assert r.json()["total"] == 0
