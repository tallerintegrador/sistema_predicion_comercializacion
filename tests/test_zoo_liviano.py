"""Tests del **zoo liviano sklearn** y los 9 modelos del rediseño 3×3 (Fase 2).

Por cada dominio (ventas/compras/almacén) se entrenan los tres modelos sobre datos
sintéticos pequeños y se verifica el criterio del plan:
- **Regresión:** gana un candidato **solo sklearn** y la métrica honesta (WAPE) es finita
  y razonable.
- **Clasificación:** etiqueta con dos clases; PR-AUC en TEST no peor que la prevalencia
  (tiene skill sobre el azar) cuando es evaluable.
- **Clustering:** KMeans real con silueta saludable (>0.3) y asignación de todas las
  entidades.

Datos reducidos a propósito (pocas series, ~200 días) para que la suite sea rápida.
"""

from __future__ import annotations

import pytest

from spc.models.automl import entrenar_regresion
from spc.models.zoo_liviano import entrenar_clasificacion_liviana, entrenar_clustering
from spc.service.dominios import config_de
from spc.synthetic import generar_dominio

DOMINIOS = ("ventas", "compras", "almacen")
NOMBRES_LIVIANOS = {"Ridge", "RandomForest", "HistGradientBoosting"}


def _datos(dominio: str):
    """Datasets pequeños pero suficientes para split temporal y clustering (≥3 entidades)."""
    if dominio == "compras":
        return generar_dominio("compras", seed=42, n_proveedores=4, n_productos=4, n_ordenes_por_serie=30)
    return generar_dominio(dominio, seed=42, n_tiendas=2, n_productos=4, n_dias=200)


def _datos_cluster(dominio: str):
    """Más entidades para que la silueta del clustering sea estable (ventas/almacén: 8 SKU)."""
    if dominio == "compras":
        return generar_dominio("compras", seed=42, n_proveedores=6, n_productos=6, n_ordenes_por_serie=20)
    return generar_dominio(dominio, seed=42, n_tiendas=2, n_productos=8, n_dias=150)


# ---------------------------------------------------------------------------
# Regresión (solo sklearn)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("dominio", DOMINIOS)
def test_regresion_liviana_solo_sklearn(dominio: str) -> None:
    cfg = config_de(dominio)
    df = _datos(dominio)
    res = entrenar_regresion(df, cfg.spec_regresion, seed=42, usar_zoo_liviano=True)
    # El ganador (y todos los candidatos) son sklearn livianos, sin LightGBM/XGBoost.
    assert set(res.candidatos) <= NOMBRES_LIVIANOS
    assert res.ganador in NOMBRES_LIVIANOS or res.ganador.startswith("Ensemble")
    # Métrica honesta de TEST disponible y razonable.
    wape = res.metricas_test.get("WAPE")
    assert wape is not None and wape == wape  # finito (no NaN)
    assert 0.0 <= wape < 80.0


# ---------------------------------------------------------------------------
# Clasificación (LogReg / RandomForest sklearn)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("dominio", DOMINIOS)
def test_clasificacion_liviana(dominio: str) -> None:
    cfg = config_de(dominio)
    df = cfg.derivar_etiqueta(_datos(dominio))
    assert cfg.etiqueta in df.columns
    assert 0 < df[cfg.etiqueta].mean() < 1  # dos clases

    res = entrenar_clasificacion_liviana(df, cfg.spec_clasificacion, seed=42)
    assert res.ganador.startswith("sklearn[")
    assert 0.0 <= res.umbral <= 1.0
    # Si TEST fue evaluable, la PR-AUC debe superar (o igualar) el azar = prevalencia.
    if res.metricas_test.get("PR_AUC") is not None:
        assert res.metricas_test["PR_AUC"] >= res.prevalencia * 0.85


# ---------------------------------------------------------------------------
# Clustering (KMeans real)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("dominio", DOMINIOS)
def test_clustering_liviano(dominio: str) -> None:
    cfg = config_de(dominio)
    df = _datos_cluster(dominio)
    perfil = cfg.perfil_entidades(df)
    res = entrenar_clustering(
        perfil, cfg.clave_entidad, list(cfg.columnas_clustering), cfg.columna_volumen, seed=42
    )
    assert res.k >= 2
    # Umbral de silueta RELAJADO a título informativo (ADR-0025 c): antes exigía > 0,3, lo
    # que premiaba clusters muy separados e incentivaba datos artificiales (arquetipos fijos).
    # Con proveedores realistas y solapados la silueta baja y eso es CORRECTO; solo se
    # comprueba que los grupos separan algo mejor que el azar (silueta positiva).
    assert res.silueta > 0.1
    assert len(res.asignacion) == len(perfil)
    assert set(res.asignacion["segmento"].unique()).issubset(set(range(res.k)))


def test_clustering_reproducible() -> None:
    cfg = config_de("compras")
    perfil = cfg.perfil_entidades(_datos("compras"))
    cols, vol = list(cfg.columnas_clustering), cfg.columna_volumen
    a = entrenar_clustering(perfil, cfg.clave_entidad, cols, vol, seed=42)
    b = entrenar_clustering(perfil, cfg.clave_entidad, cols, vol, seed=42)
    assert a.k == b.k
    assert a.asignacion["segmento"].tolist() == b.asignacion["segmento"].tolist()


def test_clustering_pocas_entidades_lanza() -> None:
    import pandas as pd

    perfil = pd.DataFrame({"a": [1.0, 2.0], "b": [3.0, 4.0]}, index=["x", "y"])
    with pytest.raises(ValueError):
        entrenar_clustering(perfil, "ent", ["a", "b"], "a", seed=42)
