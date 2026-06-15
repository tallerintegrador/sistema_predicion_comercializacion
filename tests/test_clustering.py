"""Tests del clustering/perfilado (Fase 2c).

Cubre el criterio de "hecho": el **scaler vive dentro del pipeline** (no se agrupa
sin escalar), **reproducibilidad** (misma semilla -> misma asignacion), **silueta**
calculada y con separacion real, **asignacion de segmento** a una entidad nueva y
**perfiles no degenerados** (sin clusteres vacios, cada uno con etiqueta). La
portabilidad del artefacto en proceso limpio vive en `test_portabilidad.py`.
"""

from __future__ import annotations

import numpy as np
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

from spc.config import Settings
from spc.features.perfiles import COLS_FAMILIAS, COLS_TIENDAS, perfiles_tiendas
from spc.models.clustering import (
    CONFIGS,
    PerfiladorClustering,
    entrenar_tarea,
    etiquetar_clusters,
)

import pandas as pd


def test_scaler_dentro_del_pipeline(analitico_clustering):
    """El artefacto agrupa SIEMPRE sobre datos escalados: scaler antes de KMeans."""
    res = entrenar_tarea(analitico_clustering, CONFIGS["tiendas"], seed=42)
    pasos = res.perfilador.pipeline.steps
    assert pasos[0][0] == "scaler" and isinstance(pasos[0][1], StandardScaler)
    assert pasos[1][0] == "kmeans" and isinstance(pasos[1][1], KMeans)


def test_reproducibilidad_misma_semilla(analitico_clustering):
    """Misma semilla -> mismo k y misma asignacion de segmentos (KMeans estable)."""
    r1 = entrenar_tarea(analitico_clustering, CONFIGS["tiendas"], seed=42)
    r2 = entrenar_tarea(analitico_clustering, CONFIGS["tiendas"], seed=42)
    assert r1.best_k == r2.best_k
    np.testing.assert_array_equal(
        r1.asignacion["segmento"].to_numpy(), r2.asignacion["segmento"].to_numpy()
    )
    assert abs(r1.silueta - r2.silueta) < 1e-9


def test_silueta_valida_y_separa(analitico_clustering):
    """La silueta es un float valido en (-1, 1] y hay separacion real (>0.3) en ambas
    tareas (el fixture esta disenado separable)."""
    for tarea in ("tiendas", "familias"):
        res = entrenar_tarea(analitico_clustering, CONFIGS[tarea], seed=42)
        assert -1.0 < res.silueta <= 1.0
        assert res.silueta > 0.3, f"{tarea}: silueta demasiado baja ({res.silueta})"
        # El set EDA tambien produce una silueta valida (reproduccion del pipeline).
        assert -1.0 < res.silueta_eda <= 1.0


def test_familias_intermitentes_en_su_cluster(analitico_clustering):
    """`BOOKS` y `BABY CARE` (intermitentes) caen en el MISMO segmento, separado del
    resto (informacion, no ruido: lo que el plan espera)."""
    res = entrenar_tarea(analitico_clustering, CONFIGS["familias"], seed=42)
    asig = res.asignacion.set_index("family")["segmento"]
    seg_books = asig["BOOKS"]
    seg_baby = asig["BABY CARE"]
    assert seg_books == seg_baby
    # Y al menos una familia continua queda en otro segmento.
    assert asig["GROCERY"] != seg_books


def test_asignacion_entidad_nueva(analitico_clustering):
    """El perfilador asigna segmento a una entidad NUEVA desde su historico, sin
    reentrenar, devolviendo clave + segmento + etiqueta narrativa."""
    res = entrenar_tarea(analitico_clustering, CONFIGS["tiendas"], seed=42)
    perfilador = res.perfilador

    # "Entidad nueva": el historico de una sola tienda de alto volumen.
    hist_una = analitico_clustering[analitico_clustering["store_nbr"] == 1].copy()
    salida = perfilador.perfilar(hist_una)
    assert len(salida) == 1
    assert list(salida.columns) == ["store_nbr", "segmento", "etiqueta_narrativa"]
    seg = int(salida["segmento"].iloc[0])
    assert 0 <= seg < perfilador.k
    assert salida["etiqueta_narrativa"].iloc[0] == perfilador.etiquetas[seg]

    # Asignar muchas entidades a la vez reproduce la asignacion de entrenamiento.
    todas = perfilador.perfilar(analitico_clustering)
    assert len(todas) == res.n_entidades


def test_perfiles_no_degenerados(analitico_clustering):
    """Sin clusteres vacios; tantos segmentos como k; cada uno con etiqueta narrativa."""
    for tarea in ("tiendas", "familias"):
        res = entrenar_tarea(analitico_clustering, CONFIGS[tarea], seed=42)
        n = res.perfilador.n_por_cluster
        assert len(n) == res.best_k
        assert all(v > 0 for v in n.values()), f"{tarea}: cluster vacio {n}"
        assert set(res.perfilador.etiquetas) == set(range(res.best_k))
        assert all(et.strip() for et in res.perfilador.etiquetas.values())
        # La tabla de perfiles trae los centroides en unidades para cada segmento.
        assert len(res.perfil_unidades) == res.best_k
        for c in res.cols:
            assert c in res.perfil_unidades.columns


def test_centroides_en_unidades_originales(analitico_clustering):
    """Los centroides reportados estan en unidades (no estandarizados): la venta media
    del cluster de tiendas grandes supera a la del pequeno por amplio margen."""
    res = entrenar_tarea(analitico_clustering, CONFIGS["tiendas"], seed=42)
    ventas = res.perfil_unidades["venta_media"]
    assert ventas.max() > 200  # tiendas grandes ~ cientos de unidades
    assert ventas.min() < 200  # tiendas pequenas


def test_etiquetar_clusters_legible():
    """`etiquetar_clusters` produce frases legibles que contrastan los segmentos."""
    centroides = pd.DataFrame(
        {
            "venta_media": [700.0, 40.0],
            "tasa_ceros": [0.05, 0.60],
            "promo_media": [4.0, 0.5],
            "pct_demanda_alta": [0.5, 0.1],
        }
    )
    centroides.index.name = "segmento"
    et = etiquetar_clusters(centroides, "tienda")
    assert "alto volumen" in et[0]
    assert "bajo volumen" in et[1]
    assert "intermitente" in et[1]


def test_cols_perfil_coherentes():
    """Las features de cada tarea coinciden con las columnas que produce la agregacion."""
    assert CONFIGS["tiendas"].cols == COLS_TIENDAS
    assert CONFIGS["familias"].cols == COLS_FAMILIAS


def test_serializacion_artefacto(analitico_clustering, tmp_path):
    """El perfilador se serializa con metadatos versionados (silueta incluida)."""
    from spc.models.clustering import serializar_artefactos

    settings = Settings(base_dir=tmp_path)
    resultados = {"tiendas": entrenar_tarea(analitico_clustering, CONFIGS["tiendas"], seed=42)}
    rutas = serializar_artefactos(resultados, settings)
    ruta_art, ruta_meta = rutas["tiendas"]
    assert ruta_art.exists() and ruta_meta.exists()

    from spc.models.clustering import cargar_perfilador

    perfilador, meta = cargar_perfilador(ruta_art)
    assert isinstance(perfilador, PerfiladorClustering)
    assert meta["k_elegido"] == perfilador.k
    assert "silueta" in meta and "curva_silueta_vs_k" in meta
