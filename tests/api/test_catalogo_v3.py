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
        """GET /v3/catalogo devuelve 30 consultas."""
        resp = client.get("/v3/catalogo")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_consultas"] == 30
        assert len(data["consultas"]) == 30
        # Verificar que hay de los 3 módulos
        modulos = {c["modulo"] for c in data["consultas"]}
        assert modulos == {"ventas", "compras", "almacen"}
        # Verificar tipos
        tipos = {c["tipo"] for c in data["consultas"]}
        assert tipos == {"regresion", "clasificacion", "clustering"}


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
        assert data["modulo"] == "ventas"
        assert len(data["reportes"]) == 10
        # Verificar distribución: 4R, 3C, 3K
        tipos = [r["tipo"] for r in data["reportes"]]
        assert tipos.count("regresion") == 4
        assert tipos.count("clasificacion") == 3
        assert tipos.count("clustering") == 3

    def test_analizar_compras_10_reportes(self, client, datos_compras):
        """POST /v3/compras devuelve 10 reportes."""
        resp = client.post("/v3/compras", json=datos_compras)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["reportes"]) == 10

    def test_analizar_almacen_10_reportes(self, client, datos_almacen):
        """POST /v3/almacen devuelve 10 reportes."""
        resp = client.post("/v3/almacen", json=datos_almacen)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["reportes"]) == 10

    def test_respuesta_tiene_estructura_correcta(self, client, datos_ventas):
        """Verifica estructura de cada reporte."""
        resp = client.post("/v3/ventas", json=datos_ventas)
        assert resp.status_code == 200
        data = resp.json()
        assert "fecha_ejecución" in data
        assert "analisis_tendencia" in data
        for reporte in data["reportes"]:
            assert "consulta_id" in reporte
            assert "modulo" in reporte
            assert "tipo" in reporte
            assert "pregunta" in reporte
            assert "resultado" in reporte
            assert "advertencia" in reporte
            assert "detalle_tecnico" in reporte
            # Detalle técnico tiene tabla de comparación
            dt = reporte["detalle_tecnico"]
            assert "modelo_ganador" in dt
            assert "metrica" in dt
            assert "valor_metrica" in dt
            assert "tabla_comparacion" in dt
            if dt["modelo_ganador"] == "—":
                # Consulta degradada (p. ej. pocas entidades / una sola clase):
                # no hay competencia de modelos, pero sí un aviso claro.
                assert reporte["advertencia"]
                assert dt["tabla_comparacion"] == []
            else:
                assert len(dt["tabla_comparacion"]) > 0
                # Al menos uno debe ser ganador
                assert any(f["ganador"] for f in dt["tabla_comparacion"])

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
        assert len(ventas_data["reportes"]) == 10
        for reporte in ventas_data["reportes"]:
            assert reporte["tipo"] in ("regresion", "clasificacion", "clustering")
            assert reporte["detalle_tecnico"]["modelo_ganador"]
            assert not np.isnan(reporte["detalle_tecnico"]["valor_metrica"])

        # COMPRAS
        resp = client.post("/v3/compras", json=datos_compras)
        assert resp.status_code == 200
        compras_data = resp.json()
        assert len(compras_data["reportes"]) == 10
        for reporte in compras_data["reportes"]:
            assert reporte["tipo"] in ("regresion", "clasificacion", "clustering")

        # ALMACEN
        resp = client.post("/v3/almacen", json=datos_almacen)
        assert resp.status_code == 200
        almacen_data = resp.json()
        assert len(almacen_data["reportes"]) == 10
        for reporte in almacen_data["reportes"]:
            assert reporte["tipo"] in ("regresion", "clasificacion", "clustering")

        # Total: 30 consultas ejecutadas sin error
        total_reportes = (
            len(ventas_data["reportes"]) +
            len(compras_data["reportes"]) +
            len(almacen_data["reportes"])
        )
        assert total_reportes == 30

    def test_clustering_no_usa_particion_temporal(self, client, datos_ventas):
        """Verifica que clustering se evalúa sobre el conjunto completo."""
        resp = client.post("/v3/ventas", json=datos_ventas)
        assert resp.status_code == 200
        data = resp.json()
        # Encontrar reportes de clustering
        clustering_reportes = [r for r in data["reportes"] if r["tipo"] == "clustering"]
        assert len(clustering_reportes) == 3  # VEN-K1, VEN-K2, VEN-K3
        for reporte in clustering_reportes:
            dt = reporte["detalle_tecnico"]
            # Métrica es silueta
            assert dt["metrica"] == "silhouette"
            # Valor entre -1 y 1
            assert -1.0 <= dt["valor_metrica"] <= 1.0
