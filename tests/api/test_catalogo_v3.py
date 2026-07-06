"""Tests de la API v3 del catálogo (endpoints POST /v3/{modulo}, GET /v3/catalogo, etc.)."""

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from spc.api.main import crear_app


@pytest.fixture
def client():
    """Cliente de prueba sin auth."""
    app = crear_app()
    return TestClient(app)


@pytest.fixture
def datos_ventas():
    """Datos sintéticos para VENTAS (200 filas)."""
    n = 200
    return {
        "rows": [
            {
                "fecha": str((pd.Timestamp("2020-01-01") + pd.Timedelta(days=i)).date()),
                "id_tienda": f"T{(i % 2) + 1}",
                "sku": f"SKU{(i % 5) + 1}",
                "categoria": ["Bebidas", "Abarrotes", "Lacteos"][i % 3],
                "unidades_vendidas": float(np.random.poisson(100) + np.random.randn() * 10),
                "precio_unitario": float(np.random.uniform(50, 200)),
                "ingreso": float(np.random.uniform(5000, 20000)),
                "en_promocion": int(np.random.randint(0, 2)),
                "descuento_pct": float(np.random.uniform(0, 30)),
                "metodo_pago": ["MP1", "MP2"][i % 2],
                "canal_venta": ["Online", "Tienda"][i % 2],
                "es_fin_de_semana": int(i % 7 >= 5),
                "dias_a_proximo_feriado": int(np.random.randint(1, 50)),
            }
            for i in range(n)
        ]
    }


@pytest.fixture
def datos_compras():
    """Datos sintéticos para COMPRAS (100 filas)."""
    n = 100
    return {
        "rows": [
            {
                "fecha_orden": str((pd.Timestamp("2020-01-01") + pd.Timedelta(days=i)).date()),
                "id_proveedor": f"P{(i % 5) + 1}",
                "sku": f"SKU{(i % 3) + 1}",
                "categoria": ["Cat1", "Cat2"][i % 2],
                "cantidad_pedida": float(np.random.randint(10, 100)),
                "precio_unitario_compra": float(np.random.uniform(50, 150)),
                "costo_total": float(np.random.uniform(1000, 10000)),
                "lead_time_dias": int(np.random.randint(1, 30)),
                "cantidad_recibida": float(np.random.randint(10, 100)),
                "cumplimiento": float(np.random.rand()),
                "metodo_pago": ["MP1", "MP2"][i % 2],
                "descuento_volumen": float(np.random.uniform(0, 0.2)),
            }
            for i in range(n)
        ]
    }


@pytest.fixture
def datos_almacen():
    """Datos sintéticos para ALMACEN (150 filas)."""
    n = 150
    return {
        "rows": [
            {
                "fecha": str((pd.Timestamp("2020-01-01") + pd.Timedelta(days=i)).date()),
                "id_tienda": f"T{(i % 2) + 1}",
                "sku": f"SKU{(i % 4) + 1}",
                "categoria": ["Cat1", "Cat2", "Cat3"][i % 3],
                "stock_actual": float(np.random.randint(10, 500)),
                "stock_minimo": float(np.random.randint(5, 50)),
                "stock_maximo": float(np.random.randint(100, 1000)),
                "demanda_dia": float(np.random.poisson(50)),
                "demanda_diaria_promedio": float(np.random.uniform(30, 150)),
                "dias_de_cobertura": float(np.random.uniform(1, 30)),
                "rotacion": float(np.random.uniform(0.1, 5.0)),
                "tiempo_reposicion_dias": int(np.random.randint(1, 15)),
                "zona_almacen": f"Z{(i % 3) + 1}",
            }
            for i in range(n)
        ]
    }


class TestCatalogo:
    """Tests de GET /v3/catalogo."""

    def test_listar_catalogo(self, client):
        """GET /v3/catalogo devuelve 30 consultas (contrato en inglés)."""
        resp = client.get("/v3/catalogo")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_queries"] == 30
        assert len(data["queries"]) == 30
        # Verificar que hay de los 3 módulos (los valores de módulo se mantienen en español)
        modulos = {c["module"] for c in data["queries"]}
        assert modulos == {"ventas", "compras", "almacen"}
        # Verificar tipos (enum en inglés)
        tipos = {c["type"] for c in data["queries"]}
        assert tipos == {"regression", "classification", "clustering"}


class TestPlantillas:
    """Tests de GET /v3/{modulo}/plantilla."""

    def test_descargar_plantilla_ventas(self, client):
        """GET /v3/ventas/plantilla devuelve Excel."""
        resp = client.get("/v3/ventas/plantilla")
        assert resp.status_code == 200
        assert "spreadsheet" in resp.headers.get("content-type", "")

    def test_descargar_plantilla_compras(self, client):
        """GET /v3/compras/plantilla devuelve Excel."""
        resp = client.get("/v3/compras/plantilla")
        assert resp.status_code == 200

    def test_descargar_plantilla_almacen(self, client):
        """GET /v3/almacen/plantilla devuelve Excel."""
        resp = client.get("/v3/almacen/plantilla")
        assert resp.status_code == 200

    def test_plantilla_modulo_inexistente(self, client):
        """GET /v3/modulo_invalido/plantilla falla con 400."""
        resp = client.get("/v3/modulo_invalido/plantilla")
        assert resp.status_code == 400
        assert "Módulo inexistente" in resp.json()["detail"]


class TestAnalisisModulos:
    """Tests de POST /v3/{modulo} — análisis completo."""

    def test_analizar_ventas_10_reportes(self, client, datos_ventas):
        """POST /v3/ventas devuelve exactamente 10 reportes."""
        resp = client.post("/v3/ventas", json=datos_ventas)
        assert resp.status_code == 200
        data = resp.json()
        assert data["module"] == "ventas"
        assert len(data["reports"]) == 10
        # Verificar distribución: 4R, 3C, 3K (enum en inglés)
        tipos = [r["type"] for r in data["reports"]]
        assert tipos.count("regression") == 4
        assert tipos.count("classification") == 3
        assert tipos.count("clustering") == 3

    def test_analizar_compras_10_reportes(self, client, datos_compras):
        """POST /v3/compras devuelve 10 reportes."""
        resp = client.post("/v3/compras", json=datos_compras)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["reports"]) == 10

    def test_analizar_almacen_10_reportes(self, client, datos_almacen):
        """POST /v3/almacen devuelve 10 reportes."""
        resp = client.post("/v3/almacen", json=datos_almacen)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["reports"]) == 10

    def test_respuesta_tiene_estructura_correcta(self, client, datos_ventas):
        """Verifica estructura de cada reporte (contrato en inglés)."""
        resp = client.post("/v3/ventas", json=datos_ventas)
        assert resp.status_code == 200
        data = resp.json()
        assert "executed_at" in data
        assert "trend_analysis" in data
        for reporte in data["reports"]:
            assert "query_id" in reporte
            assert "module" in reporte
            assert "type" in reporte
            assert "question" in reporte
            assert "result" in reporte
            assert "warning" in reporte
            assert "technical_detail" in reporte
            # Detalle técnico tiene tabla de comparación
            dt = reporte["technical_detail"]
            assert "winner_model" in dt
            assert "metric" in dt
            assert "metric_value" in dt
            assert "comparison_table" in dt
            if dt["winner_model"] == "—":
                # Consulta degradada (p. ej. pocas entidades / una sola clase):
                # no hay competencia de modelos, pero sí un aviso claro.
                assert reporte["warning"]
                assert dt["comparison_table"] == []
            else:
                assert len(dt["comparison_table"]) > 0
                # Al menos uno debe ser ganador
                assert any(f["winner"] for f in dt["comparison_table"])

    def test_analizar_modulo_inexistente(self, client, datos_ventas):
        """POST /v3/modulo_invalido falla con 400."""
        resp = client.post("/v3/modulo_invalido", json=datos_ventas)
        assert resp.status_code == 400
        assert "Módulo inexistente" in resp.json()["detail"]

    def test_analizar_sin_filas(self, client):
        """POST /v3/ventas sin rows falla con 422 (validación Pydantic)."""
        resp = client.post("/v3/ventas", json={"rows": []})
        assert resp.status_code == 422  # Pydantic min_length=1

    def test_analizar_columnas_faltantes(self, client):
        """POST /v3/ventas sin columnas requeridas falla con 400 del API."""
        # Con filas válidas pero faltando columnas, el endpoint debe fallar en la lógica
        resp = client.post(
            "/v3/ventas",
            json={
                "rows": [
                    {
                        "fecha": "2020-01-01",
                        "id_tienda": "T1",
                        # Faltan muchas columnas
                    }
                ]
            },
        )
        # Puede ser 422 (validación) o 400 (lógica de negocio)
        assert resp.status_code in (400, 422)


class TestSmokeTest30Consultas:
    """Smoke test: verifica que las 30 consultas se ejecutan sin error."""

    @pytest.mark.slow  # Marca como test lento (~60 segundos)
    def test_todas_30_consultas_ejecutan_sin_error(self, client, datos_ventas, datos_compras, datos_almacen):
        """Ejecuta POST /v3/{modulo} 3 veces y verifica que todas las consultas funcionan."""
        # VENTAS
        resp = client.post("/v3/ventas", json=datos_ventas)
        assert resp.status_code == 200
        ventas_data = resp.json()
        assert len(ventas_data["reports"]) == 10
        for reporte in ventas_data["reports"]:
            assert reporte["type"] in ("regression", "classification", "clustering")
            assert reporte["technical_detail"]["winner_model"]
            assert not np.isnan(reporte["technical_detail"]["metric_value"])

        # COMPRAS
        resp = client.post("/v3/compras", json=datos_compras)
        assert resp.status_code == 200
        compras_data = resp.json()
        assert len(compras_data["reports"]) == 10
        for reporte in compras_data["reports"]:
            assert reporte["type"] in ("regression", "classification", "clustering")

        # ALMACEN
        resp = client.post("/v3/almacen", json=datos_almacen)
        assert resp.status_code == 200
        almacen_data = resp.json()
        assert len(almacen_data["reports"]) == 10
        for reporte in almacen_data["reports"]:
            assert reporte["type"] in ("regression", "classification", "clustering")

        # Total: 30 consultas ejecutadas sin error
        total_reportes = (
            len(ventas_data["reports"]) +
            len(compras_data["reports"]) +
            len(almacen_data["reports"])
        )
        assert total_reportes == 30

    def test_clustering_no_usa_particion_temporal(self, client, datos_ventas):
        """Verifica que clustering se evalúa sobre el conjunto completo."""
        resp = client.post("/v3/ventas", json=datos_ventas)
        assert resp.status_code == 200
        data = resp.json()
        # Encontrar reportes de clustering
        clustering_reportes = [r for r in data["reports"] if r["type"] == "clustering"]
        assert len(clustering_reportes) == 3  # VEN-K1, VEN-K2, VEN-K3
        for reporte in clustering_reportes:
            dt = reporte["technical_detail"]
            # Métrica es silueta
            assert dt["metric"] == "silhouette"
            # Valor entre -1 y 1
            assert -1.0 <= dt["metric_value"] <= 1.0


class TestCalidadReportes:
    """Calidad honesta: predicciones no vacías en el camino feliz y degradación sin romper."""

    def test_reportes_no_degradados_tienen_predicciones(self, client, datos_ventas):
        """Todo reporte con modelo entrenado (winner != '—') debe traer predicciones no vacías."""
        resp = client.post("/v3/ventas", json=datos_ventas)
        assert resp.status_code == 200
        data = resp.json()
        no_degradados = [r for r in data["reports"] if r["technical_detail"]["winner_model"] != "—"]
        # Con 200 filas y 2 clases de canal, la mayoría de reportes entrenan de verdad.
        assert no_degradados, "se esperaba al menos un reporte entrenado"
        for reporte in no_degradados:
            preds = reporte["result"].get("predictions", [])
            assert isinstance(preds, list)
            assert len(preds) > 0, f"{reporte['query_id']} entrenó pero no devolvió predicciones"

    def test_clasificacion_una_sola_clase_degrada_sin_romper(self, client):
        """VEN-C2 (canal multiclase) con un solo canal: degrada con aviso, nunca 500."""
        n = 120
        rows = [
            {
                "fecha": str((pd.Timestamp("2020-01-01") + pd.Timedelta(days=i)).date()),
                "id_tienda": f"T{(i % 2) + 1}",
                "sku": f"SKU{(i % 4) + 1}",
                "categoria": ["Bebidas", "Abarrotes"][i % 2],
                "unidades_vendidas": float(50 + (i % 7)),
                "precio_unitario": float(100 + (i % 5)),
                "ingreso": float(5000 + i),
                "en_promocion": i % 2,
                "descuento_pct": float(i % 30),
                "metodo_pago": ["MP1", "MP2"][i % 2],
                "canal_venta": "Online",  # UNA sola clase → multiclase no entrenable
                "es_fin_de_semana": int(i % 7 >= 5),
                "dias_a_proximo_feriado": int(i % 50) + 1,
            }
            for i in range(n)
        ]
        resp = client.post("/v3/ventas", json={"rows": rows})
        assert resp.status_code == 200  # nunca revienta
        data = resp.json()
        assert len(data["reports"]) == 10
        canal = next(r for r in data["reports"] if r["query_id"] in ("ven-c2", "ven_c2"))
        # Degrada con honestidad: sin modelo ganador, con aviso claro.
        assert canal["technical_detail"]["winner_model"] == "—"
        assert canal["warning"]

    def test_resumen_intensivo_no_suma(self, client, datos_compras, datos_almacen):
        """A2: ninguna magnitud intensiva (%/días/índice) se muestra como SUMA."""
        for mod, datos in [("compras", datos_compras), ("almacen", datos_almacen)]:
            data = client.post(f"/v3/{mod}", json=datos).json()
            for r in data["reports"]:
                s = r.get("summary")
                if s and s["magnitude"] == "intensiva":
                    assert s["aggregation"] != "sum", f"{r['query_id']}: intensivo no debe sumar"
        # COM-R4 (cumplimiento) es promedio y no puede superar 100% (0..1 en escala).
        data = client.post("/v3/compras", json=datos_compras).json()
        com_r4 = next(r for r in data["reports"] if r["query_id"] in ("com-r4", "com_r4"))
        assert com_r4["summary"]["aggregation"] == "mean"
        assert com_r4["summary"]["value"] <= 1.5

    def test_dataset_info_presente(self, client, datos_ventas):
        """A8: la respuesta trae retroalimentación de validación de la carga."""
        data = client.post("/v3/ventas", json=datos_ventas).json()
        info = data["dataset_info"]
        assert info is not None
        assert set(info["recognized_columns"])  # reconoció columnas
        assert info["missing_columns"] == []
        assert info["rows_received"] == len(datos_ventas["rows"])

    def test_baseline_en_comparacion(self, client, datos_ventas):
        """B2: los reportes de regresión comparan contra un baseline en el detalle técnico."""
        data = client.post("/v3/ventas", json=datos_ventas).json()
        regresiones = [r for r in data["reports"] if r["type"] == "regression"
                       and r["technical_detail"]["comparison_table"]]
        assert regresiones
        for r in regresiones:
            modelos = {f["model"] for f in r["technical_detail"]["comparison_table"]}
            assert "baseline" in modelos, f"{r['query_id']} sin baseline"

    def test_tendencia_enriquecida(self, client, datos_ventas):
        """A3: la tendencia trae horizonte y resumen interpretativo."""
        data = client.post("/v3/ventas", json=datos_ventas).json()
        t = data["trend_analysis"]
        assert isinstance(t["horizon"], int) and t["horizon"] > 0
        if t["summary"] is not None:
            assert t["summary"]["direction"] in ("creciente", "estable", "decreciente")
            assert "projection" in t["summary"]
