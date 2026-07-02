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


def test_reentrenamiento_acumula_historico_y_versiona(client) -> None:
    """El corpus se acumula (idempotente) y `/entrenar` reentrena con TODO (ADR-0026)."""
    rows = _rows("ventas")
    k = len(rows) // 2
    # Dos lotes con fechas distintas (histórico + nuevos) + un reenvío duplicado del primero.
    assert client.post("/v2/ventas", json={"rows": rows[:k], "horizon": 5}).status_code == 200
    assert client.post("/v2/ventas", json={"rows": rows[k:], "horizon": 5}).status_code == 200
    assert client.post("/v2/ventas", json={"rows": rows[:k], "horizon": 5}).status_code == 200

    r = client.post("/v2/ventas/entrenar", params={"horizon": 5})
    assert r.status_code == 200, r.text
    body = r.json()
    # El reentrenamiento vio el histórico completo, sin duplicar el lote reenviado.
    assert body["corpus_filas"] == len(rows)
    tareas = {v["task"] for v in body["versiones"]}
    assert {"regresion", "clasificacion"} <= tareas
    assert body["training_run_id"] >= 1

    # El registro lista una versión servida por tarea.
    modelos = client.get("/v2/ventas/modelos").json()["modelos"]
    assert any(m["is_serving"] and m["task"] == "regresion" for m in modelos)

    # Reentrenar otra vez sube la versión (histórico intacto, no vuelve a crecer).
    r2 = client.post("/v2/ventas/entrenar", params={"horizon": 5})
    assert r2.status_code == 200, r2.text
    assert r2.json()["corpus_filas"] == len(rows)
    versiones_reg = [m for m in client.get("/v2/ventas/modelos").json()["modelos"] if m["task"] == "regresion"]
    assert max(v["version"] for v in versiones_reg) == 2
    assert sum(1 for v in versiones_reg if v["is_serving"]) == 1  # solo la última se sirve


def test_entrenar_sin_datos_da_error_controlado(client) -> None:
    """Reentrenar sin corpus acumulado devuelve un 400 con mensaje claro (no revienta)."""
    r = client.post("/v2/almacen/entrenar", params={"horizon": 5})
    assert r.status_code == 400, r.text


def _entrenar_ventas(client) -> list[dict]:
    """Acumula corpus de ventas y entrena un modelo (v1). Devuelve las filas usadas."""
    rows = _rows("ventas")
    assert client.post("/v2/ventas", json={"rows": rows, "horizon": 5}).status_code == 200
    r = client.post("/v2/ventas/entrenar", params={"horizon": 5})
    assert r.status_code == 200, r.text
    return rows


def test_predecir_sin_modelo_da_error(client) -> None:
    """`/predecir` sin un modelo entrenado responde 400 pidiendo entrenar primero."""
    r = client.post("/v2/ventas/predecir", json={"rows": _rows("ventas"), "horizon": 5})
    assert r.status_code == 400, r.text
    assert "entrena" in r.json()["error"]["message"].lower()


def test_predecir_usa_modelo_guardado(client) -> None:
    """`/predecir` sirve el modelo adoptado (sin reentrenar) y reporta su versión."""
    rows = _entrenar_ventas(client)
    r = client.post("/v2/ventas/predecir", json={"rows": rows, "horizon": 5})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["servido_desde"] == "modelo_guardado"
    assert body["regresion"]["version_modelo"] == 1
    assert body["regresion"]["prediccion"], "el pronóstico servido no debe estar vacío"
    # Los tres bloques presentes (clustering se recalcula fresco).
    assert {"regresion", "clasificacion", "clustering"} <= set(body)


def test_elegir_version_servida_cambia_el_modelo(client) -> None:
    """El usuario puede escoger qué versión se sirve; `/predecir` la respeta."""
    _entrenar_ventas(client)  # v1
    assert client.post("/v2/ventas/entrenar", params={"horizon": 5}).status_code == 200  # v2

    modelos = client.get("/v2/ventas/modelos").json()["modelos"]
    reg_v1 = next(m for m in modelos if m["task"] == "regresion" and m["version"] == 1)
    assert reg_v1["is_serving"] is False  # por defecto se sirve la última (v2)

    # Elegir explícitamente la v1.
    r = client.post(f"/v2/ventas/modelos/{reg_v1['id']}/servir")
    assert r.status_code == 200, r.text
    assert r.json()["servido"]["version"] == 1

    # El registro refleja que ahora se sirve la v1 (y solo una).
    regs = [m for m in client.get("/v2/ventas/modelos").json()["modelos"] if m["task"] == "regresion"]
    servidas = [m for m in regs if m["is_serving"]]
    assert len(servidas) == 1 and servidas[0]["version"] == 1

    # `/predecir` usa la versión elegida.
    pred = client.post("/v2/ventas/predecir", json={"rows": _rows("ventas"), "horizon": 5})
    assert pred.json()["regresion"]["version_modelo"] == 1


def test_servir_version_ajena_da_error(client) -> None:
    """Elegir un modelo inexistente para el dominio responde 400 (no 500)."""
    _entrenar_ventas(client)
    r = client.post("/v2/ventas/modelos/9999/servir")
    assert r.status_code == 400, r.text


def test_predecir_audita_en_tabla_predictions(client) -> None:
    """Cada predicción servida deja una fila de auditoría en `predictions`."""
    from sqlalchemy import func, select

    from spc.db.orm import Prediction

    rows = _entrenar_ventas(client)
    assert client.post("/v2/ventas/predecir", json={"rows": rows, "horizon": 5}).status_code == 200

    engine = client.app.state.db_engine
    with engine.connect() as conn:
        total = conn.execute(select(func.count()).select_from(Prediction)).scalar_one()
    assert total >= 1


def test_demo_compras(client) -> None:
    resp = client.get("/v2/compras/demo", params={"horizon": 7})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["dominio"] == "compras"
    assert body["clustering"]["k"] >= 2


def test_clustering_expone_caracteristicas_de_grupos(client) -> None:
    # Cada grupo trae sus características promedio (centroides) para poder explicarlo.
    resp = client.post("/v2/compras", json={"rows": _rows("compras"), "horizon": 7})
    assert resp.status_code == 200, resp.text
    grupos = resp.json()["clustering"]["grupos"]
    assert len(grupos) >= 1
    assert {"segmento", "etiqueta", "n", "caracteristicas"} <= set(grupos[0])
    assert len(grupos[0]["caracteristicas"]) >= 1  # p. ej. lead_time_medio, cumplimiento_medio


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


# ---------------------------------------------------------------------------
# Onboarding: diccionario de variables, plantillas y carga por Excel
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("dominio", ["ventas", "compras", "almacen"])
def test_esquema_diccionario(client, dominio: str) -> None:
    resp = client.get(f"/v2/{dominio}/esquema")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["dominio"] == dominio
    assert len(body["columnas"]) >= 1
    # Cada columna trae lo mínimo para mostrarla sin tecnicismos.
    assert {"nombre", "tipo", "rol", "descripcion", "ejemplo"} <= set(body["columnas"][0])
    # Explica qué predicen los tres modelos.
    assert {"regresion", "clasificacion", "clustering"} <= set(body["que_se_predice"])


def test_esquema_dominio_desconocido_400(client) -> None:
    resp = client.get("/v2/inexistente/esquema")
    assert resp.status_code == 400


def test_plantilla_json(client) -> None:
    resp = client.get("/v2/ventas/plantilla", params={"formato": "json", "contenido": "basica"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["rows"], "la plantilla JSON debe traer filas de ejemplo"
    assert {"fecha", "sku", "unidades_vendidas"} <= set(body["rows"][0])


def test_plantilla_excel_descarga(client) -> None:
    resp = client.get("/v2/almacen/plantilla", params={"formato": "excel"})
    assert resp.status_code == 200, resp.text
    assert "spreadsheetml" in resp.headers["content-type"]
    assert resp.content[:2] == b"PK"  # firma de un .xlsx (zip)


def test_subir_excel_corre_analisis(client) -> None:
    # Genera un Excel con historia suficiente (>28 días) y lo sube: debe entrenar y responder.
    from spc.api.ingest import dominios_excel
    from spc.service import onboarding

    df = generar_dominio("ventas", seed=42, n_tiendas=1, n_productos=4, n_dias=120)
    filas = onboarding._filas_jsonables(df, "ventas")
    xlsx = dominios_excel.generar_excel("ventas", filas)
    resp = client.post(
        "/v2/ventas/excel",
        files={"archivo": ("datos.xlsx", xlsx, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        params={"horizon": 5},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert {"regresion", "clasificacion", "clustering"} <= set(body)


def test_subir_excel_malo_devuelve_error(client) -> None:
    resp = client.post(
        "/v2/compras/excel",
        files={"archivo": ("malo.xlsx", b"esto no es un excel", "application/octet-stream")},
    )
    assert resp.status_code == 400
    assert "error" in resp.json()
