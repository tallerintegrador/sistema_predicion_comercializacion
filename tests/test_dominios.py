"""Tests de la configuración 3×3 por dominio (`spc.service.dominios`).

Verifican que cada dominio (ventas/compras/almacen) traduzca su formato único a lo que el
motor necesita **sin fuga**: el objetivo nunca es feature, la etiqueta de clasificación se
deriva con umbral train-only y produce las dos clases, y el perfil por entidad alimenta el
clustering. Datos vía `spc.synthetic.generar_dominio` (la misma fuente que las demos).
"""

from __future__ import annotations

import pytest

from spc.service import dominios
from spc.synthetic import generar_dominio

DOMINIOS = ("ventas", "compras", "almacen")


def test_config_de_devuelve_configuracion_por_dominio() -> None:
    for d in DOMINIOS:
        cfg = dominios.config_de(d)
        assert cfg.dominio == d
        assert cfg.spec_regresion.objetivo  # hay objetivo de regresión
        assert cfg.etiqueta  # y etiqueta de clasificación


def test_config_de_dominio_desconocido_lanza() -> None:
    with pytest.raises(KeyError, match="Dominio desconocido"):
        dominios.config_de("inexistente")


def test_objetivo_no_es_feature_anti_fuga() -> None:
    # El objetivo de regresión nunca debe aparecer entre las features conocidas/solo-pasado.
    for d in DOMINIOS:
        spec = dominios.config_de(d).spec_regresion
        features = set(spec.num_conocidas_futuro) | set(spec.num_solo_pasado)
        assert spec.objetivo not in features


@pytest.mark.parametrize("dominio", DOMINIOS)
def test_derivar_etiqueta_produce_dos_clases(dominio: str) -> None:
    cfg = dominios.config_de(dominio)
    df = generar_dominio(dominio, seed=42)
    etiquetado = cfg.derivar_etiqueta(df)
    col = cfg.etiqueta
    assert col in etiquetado.columns
    prop = etiquetado[col].mean()
    assert 0 < prop < 1  # ambas clases presentes (señal para el clasificador)
    assert set(etiquetado[col].unique()) <= {0, 1}


@pytest.mark.parametrize("dominio", DOMINIOS)
def test_perfil_entidades_indexado_por_clave(dominio: str) -> None:
    cfg = dominios.config_de(dominio)
    df = generar_dominio(dominio, seed=42)
    perfil = cfg.perfil_entidades(df)
    # Una fila por entidad y las columnas del clustering presentes.
    assert perfil.index.name == cfg.clave_entidad
    assert set(cfg.columnas_clustering) <= set(perfil.columns)
    assert cfg.columna_volumen in perfil.columns
    assert len(perfil) == df[cfg.clave_entidad].nunique()


def test_almacen_usa_k_fijo_tres_abc() -> None:
    cfg = dominios.config_de("almacen")
    assert cfg.k_fijo == 3  # A/B/C por interpretación de negocio (ADR-0025 c)
    assert cfg.estilo_etiqueta == "abc"
