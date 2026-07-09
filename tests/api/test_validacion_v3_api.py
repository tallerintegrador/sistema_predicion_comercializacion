"""Tests de la validación de tipos en el canal v3 a nivel de API (rechazo con detalle)."""

from __future__ import annotations

from spc.synthetic import generar_dominio


def _cuerpo_ventas() -> dict:
    df = generar_dominio("ventas", seed=42, n_tiendas=2, n_productos=4, n_dias=120)
    df["fecha"] = df["fecha"].astype(str)
    return {"rows": df.to_dict(orient="records")}


def test_fecha_invalida_devuelve_400_con_detalle(client) -> None:
    cuerpo = _cuerpo_ventas()
    cuerpo["rows"][0]["fecha"] = "esto-no-es-fecha"
    r = client.post("/v3/ventas", json=cuerpo)
    assert r.status_code == 400, r.text
    error = r.json()["error"]
    assert error["type"] == "invalid_request"
    campos = {d["field"] for d in (error.get("details") or [])}
    assert "fecha" in campos


def test_numerica_invalida_devuelve_400(client) -> None:
    cuerpo = _cuerpo_ventas()
    cuerpo["rows"][0]["unidades_vendidas"] = "muchas"
    r = client.post("/v3/ventas", json=cuerpo)
    assert r.status_code == 400, r.text
    campos = {d["field"] for d in (r.json()["error"].get("details") or [])}
    assert "unidades_vendidas" in campos


def test_dataset_valido_sigue_devolviendo_200(client) -> None:
    r = client.post("/v3/ventas", json=_cuerpo_ventas())
    assert r.status_code == 200, r.text
