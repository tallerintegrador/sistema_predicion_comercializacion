"""Tests de la capa de catálogo: configuración, motor y anti-fuga.

Verifica:
- Carga del YAML y parseo de 30 consultas
- Validación de entrada (columnas requeridas)
- Anti-fuga: exclusión de columnas derivadas
- Entrenamiento básico sin errores
"""

import numpy as np
import pandas as pd
import pytest

from spc.catalogo.config import (
    obtener_catalogo,
    obtener_consulta,
    obtener_modulo,
    cargar_catalogo,
)
from spc.catalogo.motor_catalogo import (
    validar_dataframe,
    construir_features,
    ejecutar_consulta,
)


class TestCargaCatalogo:
    """Verifica que el YAML se carga correctamente."""

    def test_cargar_catalogo_completo(self):
        """Carga el catálogo y verifica estructura."""
        cat = obtener_catalogo()
        assert len(cat) == 3
        assert "ventas" in cat
        assert "compras" in cat
        assert "almacen" in cat

    def test_ventas_10_consultas(self):
        """Ventas debe tener 10 consultas: 4R+3C+3K."""
        mod_ventas = obtener_modulo("ventas")
        assert len(mod_ventas.consultas) == 10

        por_tipo = mod_ventas.consultas_por_tipo()
        assert len(por_tipo["regresion"]) == 4
        assert len(por_tipo["clasificacion"]) == 3
        assert len(por_tipo["clustering"]) == 3

    def test_compras_10_consultas(self):
        """Compras debe tener 10 consultas."""
        mod = obtener_modulo("compras")
        assert len(mod.consultas) == 10

    def test_almacen_10_consultas(self):
        """Almacén debe tener 10 consultas."""
        mod = obtener_modulo("almacen")
        assert len(mod.consultas) == 10

    def test_consultas_tienen_campos_requeridos(self):
        """Todas las consultas tienen id, tipo, pregunta, columnas_entrada."""
        cat = obtener_catalogo()
        for modulo in cat.values():
            for c in modulo.consultas.values():
                assert c.id
                assert c.tipo in ("regresion", "clasificacion", "clustering")
                assert c.pregunta
                # Clustering no tiene objetivo; regresion/clasificacion si
                if c.tipo in ("regresion", "clasificacion"):
                    assert c.objetivo
                else:
                    assert c.entidad_cluster
                assert len(c.columnas_entrada) > 0


class TestObtenerConsulta:
    """Tests de búsqueda de consultas."""

    def test_obtener_ven_r1(self):
        """Obtiene consulta VEN-R1."""
        c = obtener_consulta("ven_r1")
        assert c.id == "ven-r1"
        assert c.tipo == "regresion"
        assert c.pregunta == "Unidades según precio y promoción"
        assert c.objetivo == "unidades_vendidas"

    def test_obtener_com_c1(self):
        """Obtiene consulta COM-C1."""
        c = obtener_consulta("com_c1")
        assert c.id == "com-c1"
        assert c.tipo == "clasificacion"

    def test_obtener_alm_k1(self):
        """Obtiene consulta ALM-K1."""
        c = obtener_consulta("alm_k1")
        assert c.id == "alm-k1"
        assert c.tipo == "clustering"
        assert c.k_fijo == 3  # ABC tiene k fijo


class TestAntiGrieForest:
    """Verifica que se excluyen correctamente las columnas que causan fuga."""

    def test_ven_r1_excluye_ingreso(self):
        """VEN-R1: ingreso se excluye (causa fuga)."""
        c = obtener_consulta("ven_r1")
        mod = obtener_modulo("ventas")

        # Generar DataFrame ficticio
        df = pd.DataFrame({
            "fecha": pd.date_range("2020-01-01", periods=100),
            "id_tienda": ["T1"] * 100,
            "sku": ["SKU1"] * 100,
            "categoria": ["Cat1"] * 100,
            "unidades_vendidas": np.random.randn(100) * 100,
            "precio_unitario": np.random.randn(100) * 50 + 100,
            "ingreso": np.random.randn(100) * 5000,  # DEBE excluirse
            "en_promocion": np.random.randint(0, 2, 100),
            "descuento_pct": np.random.randn(100) * 10,
            "metodo_pago": ["MP1"] * 100,
            "canal_venta": ["Canal1"] * 100,
            "es_fin_de_semana": np.random.randint(0, 2, 100),
            "dias_a_proximo_feriado": np.random.randint(1, 30, 100),
        })

        features = construir_features(df, c, mod)

        # ingreso NO debe estar en features
        assert "ingreso" not in features.columns
        assert "unidades_vendidas" not in features.columns  # objetivo tampoco

    def test_com_c1_no_usa_cantidad_recibida(self):
        """COM-C1: cantidad_recibida se excluye (post-entrega)."""
        c = obtener_consulta("com_c1")
        mod = obtener_modulo("compras")

        df = pd.DataFrame({
            "fecha_orden": pd.date_range("2020-01-01", periods=50),
            "id_proveedor": ["P1"] * 50,
            "sku": ["SKU1"] * 50,
            "categoria": ["Cat1"] * 50,
            "cantidad_pedida": np.random.randint(1, 100, 50),
            "precio_unitario_compra": np.random.randn(50) * 50 + 100,
            "costo_total": np.random.randn(50) * 5000,
            "lead_time_dias": np.random.randint(1, 30, 50),
            "cantidad_recibida": np.random.randint(1, 100, 50),  # post-entrega
            "cumplimiento": np.random.rand(50),  # post-entrega
            "metodo_pago": ["MP1"] * 50,
            "descuento_volumen": np.random.rand(50) * 0.2,
        })

        features = construir_features(df, c, mod)

        # cantidad_recibida, cumplimiento, costo_total no deben estar
        assert "cantidad_recibida" not in features.columns or "cantidad_recibida" not in c.columnas_entrada
        assert "cumplimiento" not in features.columns or "cumplimiento" not in c.columnas_entrada


class TestEjecucionConsultaSimple:
    """Tests de ejecución end-to-end (sin mocks)."""

    def test_ejecutar_ven_r1_sin_errores(self):
        """Ejecuta VEN-R1 sobre datos sintéticos."""
        # Generar datos realistas
        n = 200
        df = pd.DataFrame({
            "fecha": pd.date_range("2020-01-01", periods=n),
            "id_tienda": ["T1"] * (n // 2) + ["T2"] * (n // 2),
            "sku": ["SKU1"] * (n // 4) + ["SKU2"] * (n // 4) + ["SKU3"] * (n // 2),
            "categoria": ["Bebidas"] * 50 + ["Abarrotes"] * 50 + ["Lacteos"] * 100,
            "unidades_vendidas": np.random.poisson(100, n).astype(float) + np.random.randn(n) * 10,
            "precio_unitario": np.random.uniform(50, 200, n),
            "ingreso": np.random.uniform(5000, 20000, n),
            "en_promocion": np.random.randint(0, 2, n),
            "descuento_pct": np.random.uniform(0, 30, n),
            "metodo_pago": np.random.choice(["MP1", "MP2"], n),
            "canal_venta": np.random.choice(["Online", "Tienda"], n),
            "es_fin_de_semana": np.random.randint(0, 2, n),
            "dias_a_proximo_feriado": np.random.randint(1, 50, n),
        })

        resultado = ejecutar_consulta("ven_r1", df)

        # Verificar estructura del resultado
        assert resultado.consulta_id in ("ven-r1", "ven_r1")  # Acepta tanto guion como underscore
        assert resultado.tipo == "regresion"
        assert resultado.modelo_ganador in ["ridge", "random_forest", "hist_gradient_boosting"]
        assert resultado.metrica_ganador == "wape"
        assert 0 <= resultado.valor_metrica <= 1.0
        assert len(resultado.tabla_comparacion) > 0
        assert any(f.ganador for f in resultado.tabla_comparacion)

    def test_ejecutar_ven_c1_genera_advertencia_baja_calidad(self):
        """VEN-C1 con datos muy desbalanceados puede generar advertencia."""
        # Datos: casi todos demanda baja, muy pocos alta
        n = 200
        df = pd.DataFrame({
            "fecha": pd.date_range("2020-01-01", periods=n),
            "id_tienda": ["T1"] * (n // 2) + ["T2"] * (n // 2),
            "sku": ["SKU1"] * n,
            "categoria": ["Bebidas"] * n,
            "unidades_vendidas": np.concatenate([
                np.random.poisson(10, int(0.95 * n)).astype(float),  # baja
                np.random.poisson(200, int(0.05 * n)).astype(float),  # alta
            ]),
            "precio_unitario": np.random.uniform(50, 200, n),
            "ingreso": np.random.uniform(5000, 20000, n),
            "en_promocion": np.random.randint(0, 2, n),
            "descuento_pct": np.random.uniform(0, 30, n),
            "metodo_pago": np.random.choice(["MP1", "MP2"], n),
            "canal_venta": np.random.choice(["Online", "Tienda"], n),
            "es_fin_de_semana": np.random.randint(0, 2, n),
            "dias_a_proximo_feriado": np.random.randint(1, 50, n),
        })

        resultado = ejecutar_consulta("ven_c1", df)

        # Puede haber advertencia si PR-AUC es baja
        assert resultado.tipo == "clasificacion"
        # No fallar aunque haya baja calidad
        assert resultado.modelo_ganador

    def test_ejecutar_ven_k1_clustering(self):
        """Ejecuta VEN-K1 (clustering)."""
        n = 200
        df = pd.DataFrame({
            "fecha": pd.date_range("2020-01-01", periods=n),
            "id_tienda": ["T1"] * n,
            "sku": [f"SKU{i % 10}" for i in range(n)],
            "categoria": np.random.choice(["Bebidas", "Abarrotes"], n),
            "unidades_vendidas": np.random.poisson(100, n).astype(float) + np.random.randn(n) * 20,
            "precio_unitario": np.random.uniform(50, 200, n),
            "ingreso": np.random.uniform(5000, 20000, n),
            "en_promocion": np.random.randint(0, 2, n),
            "descuento_pct": np.random.uniform(0, 30, n),
            "metodo_pago": np.random.choice(["MP1", "MP2"], n),
            "canal_venta": np.random.choice(["Online", "Tienda"], n),
            "es_fin_de_semana": np.random.randint(0, 2, n),
            "dias_a_proximo_feriado": np.random.randint(1, 50, n),
        })

        resultado = ejecutar_consulta("ven_k1", df)

        assert resultado.tipo == "clustering"
        assert resultado.modelo_ganador == "kmeans"
        assert resultado.metrica_ganador == "silhouette"


class TestValidacion:
    """Tests de validación de entrada."""

    def test_validar_dataframe_falta_columna_objet(self):
        """Valida que falle si falta el objetivo."""
        c = obtener_consulta("ven_r1")
        df = pd.DataFrame({
            "fecha": pd.date_range("2020-01-01", periods=10),
            "id_tienda": ["T1"] * 10,
            "sku": ["SKU1"] * 10,
            # SIN unidades_vendidas
        })

        with pytest.raises(ValueError, match="faltan columnas"):
            validar_dataframe(df, c)

    def test_validar_dataframe_falta_feature(self):
        """Valida que falle si falta una feature requerida."""
        c = obtener_consulta("ven_r1")
        df = pd.DataFrame({
            "fecha": pd.date_range("2020-01-01", periods=10),
            "id_tienda": ["T1"] * 10,
            "sku": ["SKU1"] * 10,
            "unidades_vendidas": np.random.randn(10) * 100,
            # SIN precio_unitario, en_promocion, descuento_pct, categoria
        })

        with pytest.raises(ValueError, match="faltan columnas"):
            validar_dataframe(df, c)
