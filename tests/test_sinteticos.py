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

from spc.synthetic import generar_dominio
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


# ---------------------------------------------------------------------------
# Despachador
# ---------------------------------------------------------------------------
def test_dominio_desconocido_lanza() -> None:
    with pytest.raises(KeyError):
        generar_dominio("inexistente", seed=42)
    assert tuple(ESQUEMAS) == DOMINIOS
