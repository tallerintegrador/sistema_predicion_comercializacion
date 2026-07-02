"""Tests de los **datos sintéticos por dominio** (Fase 1 del rediseño 3×3).

Verifican lo que el plan exige de los generadores:
- **Reproducibilidad:** misma semilla → mismas filas; semilla distinta → datos distintos.
- **Conformidad de esquema:** columnas exactas y en orden (fuente única `esquemas`).
- **Correcciones del docente:** `ingreso`/`costo_total`/`cumplimiento`/`dias_de_cobertura`
  son columnas **calculadas** coherentes; `en_promocion` y `es_fin_de_semana` son
  banderas 0/1; no hay `feriado` binario sino `dias_a_proximo_feriado` ≥ 0.
- **Señal para los 3 modelos:** las etiquetas derivables (`demanda_alta`,
  `entrega_con_retraso`, `riesgo_quiebre`) tienen las DOS clases presentes.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from spc.synthetic import comun, generar_dominio
from spc.synthetic.esquemas import ESQUEMAS, esquema_de, validar_conforme

DOMINIOS = ("ventas", "compras", "almacen")


# ---------------------------------------------------------------------------
# Conformidad de esquema y reproducibilidad (los tres dominios)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("dominio", DOMINIOS)
def test_conforme_al_esquema(dominio: str) -> None:
    df = generar_dominio(dominio, seed=42)
    assert list(df.columns) == esquema_de(dominio).orden
    validar_conforme(df, dominio)  # no debe lanzar
    assert len(df) > 0


@pytest.mark.parametrize("dominio", DOMINIOS)
def test_reproducible_misma_semilla(dominio: str) -> None:
    a = generar_dominio(dominio, seed=42)
    b = generar_dominio(dominio, seed=42)
    pd.testing.assert_frame_equal(a, b)


@pytest.mark.parametrize("dominio", DOMINIOS)
def test_semilla_distinta_cambia_datos(dominio: str) -> None:
    a = generar_dominio(dominio, seed=42)
    c = generar_dominio(dominio, seed=7)
    assert not a.equals(c)


# ---------------------------------------------------------------------------
# Catálogo grande de productos ÚNICOS (punto b): antes eran 8 fijos que se
# reciclaban; ahora se generan N SKUs distintos, deterministas y sin repetir.
# ---------------------------------------------------------------------------
def test_catalogo_40_skus_unicos_y_reproducible() -> None:
    cat = comun.productos(40)
    skus = [sku for sku, _ in cat]
    # 40 SKUs, todos DISTINTOS (no se reciclan como antes).
    assert len(cat) == 40
    assert len(set(skus)) == 40
    # Cada SKU trae una categoría del vocabulario declarado.
    assert all(categoria in comun.CATEGORIAS for _, categoria in cat)
    # Reproducible: la misma llamada da exactamente el mismo catálogo.
    assert comun.productos(40) == cat
    # Retrocompatible: los primeros 8 son los históricos (no rompe tests previos).
    assert cat[:8] == (
        ("SKU-001", "Bebidas"), ("SKU-002", "Abarrotes"), ("SKU-003", "Lacteos"),
        ("SKU-004", "Limpieza"), ("SKU-005", "Snacks"), ("SKU-006", "Cuidado personal"),
        ("SKU-007", "Bebidas"), ("SKU-008", "Abarrotes"),
    )


def test_ventas_default_tiene_40_skus_con_categoria_consistente() -> None:
    # El dataset por defecto (la demo) ejercita el catálogo grande.
    df = generar_dominio("ventas", seed=42)
    assert df["sku"].nunique() == 40
    # Cada SKU mantiene UNA sola categoría en todo el dataset (consistencia).
    assert (df.groupby("sku")["categoria"].nunique() == 1).all()


# ---------------------------------------------------------------------------
# VENTAS — columnas calculadas y banderas
# ---------------------------------------------------------------------------
def test_ventas_correcciones() -> None:
    df = generar_dominio("ventas", seed=42)
    # ingreso es calculada = unidades × precio (corrige el error de la plantilla).
    esperado = (df["unidades_vendidas"] * df["precio_unitario"]).round(2)
    assert np.allclose(df["ingreso"], esperado, atol=0.011)
    # en_promocion y es_fin_de_semana son banderas 0/1 (no cantidades ni 0/1/2/3).
    assert set(df["en_promocion"].unique()) <= {0, 1}
    assert set(df["es_fin_de_semana"].unique()) <= {0, 1}
    # Sin promo => sin descuento.
    assert (df.loc[df["en_promocion"] == 0, "descuento_pct"] == 0).all()
    # Reemplazo de la bandera feriado: días ≥ 0 y "feriado" ya no es columna.
    assert (df["dias_a_proximo_feriado"] >= 0).all()
    assert "feriado" not in df.columns
    # No negativos en las medidas base.
    assert (df["unidades_vendidas"] >= 0).all()
    assert (df["precio_unitario"] > 0).all()


def test_ventas_etiqueta_demanda_alta_dos_clases() -> None:
    df = generar_dominio("ventas", seed=42)
    p75 = df.groupby("categoria")["unidades_vendidas"].transform(lambda s: s.quantile(0.75))
    demanda_alta = (df["unidades_vendidas"] > p75).astype(int)
    assert 0 < demanda_alta.mean() < 1  # ambas clases presentes


# ---------------------------------------------------------------------------
# COMPRAS — esquema de órdenes, columnas calculadas y señal de retraso
# ---------------------------------------------------------------------------
def test_compras_correcciones() -> None:
    df = generar_dominio("compras", seed=42)
    # costo_total = cantidad × precio (calculada).
    esperado = (df["cantidad_pedida"] * df["precio_unitario_compra"]).round(2)
    assert np.allclose(df["costo_total"], esperado, atol=0.011)
    # cumplimiento = recibida / pedida (calculada), en (0, 1].
    cumpl = (df["cantidad_recibida"] / df["cantidad_pedida"]).round(4)
    assert np.allclose(df["cumplimiento"], cumpl, atol=1e-4)
    assert (df["cumplimiento"] > 0).all() and (df["cumplimiento"] <= 1).all()
    assert (df["lead_time_dias"] >= 1).all()


def test_compras_etiqueta_retraso_dos_clases() -> None:
    df = generar_dominio("compras", seed=42)
    umbral = df["lead_time_dias"].quantile(0.75)
    retraso = (df["lead_time_dias"] > umbral).astype(int)
    assert 0 < retraso.mean() < 1


def test_compras_clustering_separa_proveedores() -> None:
    # Los arquetipos deben dar lead times medios distintos por proveedor.
    df = generar_dominio("compras", seed=42)
    medias = df.groupby("id_proveedor")["lead_time_dias"].mean()
    assert medias.max() - medias.min() > 3.0  # arquetipos claramente separados


# ---------------------------------------------------------------------------
# ALMACÉN — KPIs calculados y riesgo de quiebre
# ---------------------------------------------------------------------------
def test_almacen_correcciones() -> None:
    df = generar_dominio("almacen", seed=42)
    # dias_de_cobertura ≈ stock / demanda (calculada; tolera el redondeo de las fuentes).
    ratio = df["stock_actual"] / df["demanda_diaria_promedio"]
    assert np.allclose(df["dias_de_cobertura"], ratio, rtol=0.02, atol=0.05)
    assert (df["stock_actual"] >= 0).all()
    assert (df["tiempo_reposicion_dias"] >= 1).all()
    assert (df["demanda_diaria_promedio"] > 0).all()


def test_almacen_etiqueta_riesgo_quiebre_dos_clases() -> None:
    df = generar_dominio("almacen", seed=42)
    riesgo = (
        df["stock_actual"] < df["demanda_diaria_promedio"] * df["tiempo_reposicion_dias"]
    ).astype(int)
    assert 0 < riesgo.mean() < 1


def test_almacen_objetivo_es_demanda_dia() -> None:
    # ADR-0025 (e): el objetivo de regresión pasa a `demanda_dia` (demanda futura).
    df = generar_dominio("almacen", seed=42)
    assert esquema_de("almacen").objetivo_regresion == "demanda_dia"
    assert "demanda_dia" in df.columns
    assert (df["demanda_dia"] >= 0).all()          # consumo diario, no negativo
    assert df["demanda_dia"].std() > 0             # varía (aprendible, no constante)
    # dias_de_cobertura sobrevive como KPI derivado (ya no es el objetivo).
    assert "dias_de_cobertura" in df.columns


# ---------------------------------------------------------------------------
# Despachador
# ---------------------------------------------------------------------------
def test_dominio_desconocido_lanza() -> None:
    with pytest.raises(KeyError):
        generar_dominio("inexistente", seed=42)
    assert tuple(ESQUEMAS) == DOMINIOS
