"""Tests del reentrenamiento con persistencia (`spc.service.reentrenamiento`, ADR-0026).

Flujo completo pedido por el negocio: acumular corpus → reentrenar los 3 modelos 3×3 sobre
**todo** el histórico → servir el modelo guardado sin reentrenar. Entrena modelos reales
(sklearn liviano), así que se marca ``slow``. Sin Supabase: los artefactos van a disco.
"""

from __future__ import annotations

import json

import pytest

from spc.service import reentrenamiento
from spc.service.repositorio_corpus import RepositorioCorpus
from spc.service.repositorio_modelos import RepositorioModelos
from spc.synthetic import generar_dominio


def _filas_json(dominio: str) -> list[dict]:
    """Filas JSON-safe del generador (fechas ISO), como llegarían por el canal JSON de la API."""
    df = generar_dominio(dominio, seed=42)
    return json.loads(df.to_json(orient="records", date_format="iso"))


def _sembrar_corpus(engine, tmp_path) -> tuple[RepositorioCorpus, RepositorioModelos]:
    corpus = RepositorioCorpus(engine)
    modelos = RepositorioModelos(engine, tmp_path / "artefactos")
    series_keys, date_col = reentrenamiento.claves_dominio("ventas")
    corpus.insertar_observaciones(
        tenant_id="c1", domain="ventas", rows=_filas_json("ventas"),
        series_keys=series_keys, date_col=date_col, channel="json",
    )
    return corpus, modelos


def test_reentrenar_sin_corpus_lanza(engine, tmp_path) -> None:
    corpus = RepositorioCorpus(engine)
    modelos = RepositorioModelos(engine, tmp_path / "artefactos")
    with pytest.raises(ValueError, match="No hay datos acumulados"):
        reentrenamiento.reentrenar(corpus, modelos, tenant_id="c1", dominio="ventas")


@pytest.mark.slow
def test_reentrenar_versiona_y_sirve(engine, tmp_path) -> None:
    corpus, modelos = _sembrar_corpus(engine, tmp_path)
    resumen = reentrenamiento.reentrenar(
        corpus, modelos, tenant_id="c1", dominio="ventas", seed=42
    )
    assert resumen["corpus_filas"] > 0
    assert resumen["training_run_id"] > 0
    # Se versionó al menos regresión y clasificación, y quedaron adoptadas.
    tareas = {v["task"] for v in resumen["versiones"]}
    assert {"regresion", "clasificacion"} <= tareas
    assert all(v["is_serving"] for v in resumen["versiones"])
    # El registro tiene la versión servida de regresión.
    assert modelos.cargar_adoptado("c1", "ventas", "regresion") is not None


@pytest.mark.slow
def test_predecir_con_guardado_usa_modelo_adoptado(engine, tmp_path) -> None:
    corpus, modelos = _sembrar_corpus(engine, tmp_path)
    reentrenamiento.reentrenar(corpus, modelos, tenant_id="c1", dominio="ventas", seed=42)
    respuesta, model_id = reentrenamiento.predecir_con_guardado(
        corpus, modelos, tenant_id="c1", dominio="ventas"
    )
    assert isinstance(respuesta, dict)
    assert model_id is not None  # id del modelo de regresión servido (para auditar)


@pytest.mark.slow
def test_predecir_sin_modelo_entrenado_lanza(engine, tmp_path) -> None:
    corpus, modelos = _sembrar_corpus(engine, tmp_path)
    # Hay corpus pero nunca se entrenó → no hay modelo adoptado.
    with pytest.raises(ValueError, match="modelo entrenado"):
        reentrenamiento.predecir_con_guardado(
            corpus, modelos, tenant_id="c1", dominio="ventas"
        )
