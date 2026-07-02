"""Acumulación de corpus y reentrenamiento con históricos + nuevos (ADR-0026).

Dos responsabilidades, ambas apoyadas en :mod:`spc.service.repositorio_corpus` y
:mod:`spc.service.repositorio_modelos`:

- :func:`acumular` — engancha *best-effort* la persistencia del corpus a los endpoints de
  análisis: cada carga (JSON/Excel) se guarda como observaciones. **Nunca rompe** la
  predicción: si la base falla, se loguea y se sigue.
- :func:`reentrenar` — el flujo que pidió el negocio: carga **todo** el corpus del cliente
  para el dominio (históricos + lo recién subido), reentrena los tres modelos 3×3 sobre ese
  conjunto completo, **versiona** cada uno en el registro (con sus métricas honestas y el
  artefacto en Storage) y lo marca como el que se sirve.

Los metadatos de la serie y la fecha de cada dominio 3×3 salen de
:func:`spc.service.dominios.config_de` (misma fuente que el motor, sin duplicar contratos).
"""

from __future__ import annotations

from typing import Any

from spc.service import dominios, motor_3x3
from spc.service.repositorio_corpus import RepositorioCorpus, ResumenIngesta
from spc.service.repositorio_modelos import ModeloInfo, RepositorioModelos
from spc.utils.logging import get_logger

log = get_logger("service.reentrenamiento")

# Las tres tareas del contrato 3×3 y de qué bloque de la respuesta salen sus métricas.
_TAREAS = ("regresion", "clasificacion", "clustering")


def claves_dominio(dominio: str) -> tuple[list[str], str | None]:
    """Columnas que identifican la serie y la columna de fecha del dominio 3×3."""
    spec = dominios.config_de(dominio).spec_regresion
    return list(spec.cols_serie), spec.col_fecha


def acumular(
    corpus: RepositorioCorpus | None,
    *,
    tenant_id: str,
    dominio: str,
    rows: list[dict[str, Any]],
    channel: str,
    created_by: str | None = None,
) -> ResumenIngesta | None:
    """Guarda ``rows`` en el corpus (best-effort). Devuelve el resumen o ``None`` si falló/omitió."""
    if corpus is None or not rows:
        return None
    try:
        series_keys, date_col = claves_dominio(dominio)
        return corpus.insertar_observaciones(
            tenant_id=tenant_id,
            domain=dominio,
            rows=rows,
            series_keys=series_keys,
            date_col=date_col,
            channel=channel,
            created_by=created_by,
        )
    except Exception as exc:  # noqa: BLE001 - persistencia best-effort: nunca rompe la API
        log.warning("No se pudo acumular el corpus de %s/%s: %s", tenant_id, dominio, exc)
        return None


def acumular_declarado(
    corpus: RepositorioCorpus | None,
    *,
    tenant_id: str,
    dominio: str,
    rows: list[dict[str, Any]],
    series_keys: list[str],
    date_col: str | None,
    channel: str,
    schema_spec: dict | None = None,
) -> ResumenIngesta | None:
    """Como :func:`acumular`, pero con serie/fecha **declaradas** por el cliente (``/auto/*``)."""
    if corpus is None or not rows:
        return None
    try:
        return corpus.insertar_observaciones(
            tenant_id=tenant_id,
            domain=dominio,
            rows=rows,
            series_keys=series_keys,
            date_col=date_col,
            channel=channel,
            schema_spec=schema_spec,
        )
    except Exception as exc:  # noqa: BLE001 - persistencia best-effort: nunca rompe la API
        log.warning("No se pudo acumular el corpus agnóstico de %s/%s: %s", tenant_id, dominio, exc)
        return None


def _algoritmo(bloque: dict[str, Any]) -> str | None:
    return bloque.get("modelo_ganador") or bloque.get("algoritmo")


def _metricas(bloque: dict[str, Any]) -> dict[str, Any]:
    """Extrae las métricas honestas del bloque (silueta para clustering)."""
    if "metricas_honestas" in bloque:
        return dict(bloque["metricas_honestas"])
    if bloque.get("silueta") is not None:
        return {"silueta": bloque["silueta"], "k": bloque.get("k")}
    return {}


def reentrenar(
    corpus: RepositorioCorpus,
    modelos: RepositorioModelos,
    *,
    tenant_id: str,
    dominio: str,
    horizon: int = motor_3x3.HORIZON_DEFAULT,
    seed: int = 42,
) -> dict[str, Any]:
    """Reentrena los 3 modelos del dominio con **todo** el corpus del cliente y los versiona.

    Devuelve un resumen con el nº de filas de entrenamiento, el ``training_run`` y las
    versiones adoptadas por tarea (con sus métricas). Lanza ``ValueError`` si el cliente aún
    no tiene datos acumulados para el dominio.
    """
    df = corpus.leer_corpus(tenant_id, dominio)
    if df.empty:
        raise ValueError(
            f"No hay datos acumulados para '{dominio}'. Sube datos antes de reentrenar."
        )
    rows = df.to_dict(orient="records")

    respuesta, artefactos = motor_3x3.analizar_y_modelos(dominio, rows, horizon=horizon, seed=seed)
    corpus_rows = int(respuesta["n_filas"])

    versiones: list[ModeloInfo] = []
    for tarea in _TAREAS:
        objeto = artefactos.get(tarea)
        if objeto is None:
            continue  # p. ej. clustering por terciles (sin estimador que persistir)
        bloque = respuesta[tarea]
        info = modelos.registrar_version(
            tenant_id=tenant_id,
            domain=dominio,
            task=tarea,
            objeto=objeto,
            algorithm=_algoritmo(bloque),
            metrics=_metricas(bloque),
            status="adopted",
            trained_rows=corpus_rows,
            adoptar=True,
        )
        versiones.append(info)

    resumen = {
        "dominio": dominio,
        "corpus_filas": corpus_rows,
        "versiones": [
            {
                "task": v.task,
                "version": v.version,
                "algorithm": v.algorithm,
                "metrics": v.metrics,
                "is_serving": v.is_serving,
                "storage_uri": v.storage_uri,
            }
            for v in versiones
        ],
    }
    run_id = modelos.registrar_reentrenamiento(
        tenant_id=tenant_id, domain=dominio, status="done", corpus_rows=corpus_rows, result=resumen
    )
    resumen["training_run_id"] = run_id
    log.info(
        "Reentrenamiento %s/%s: filas=%d versiones=%d (run=%d)",
        tenant_id, dominio, corpus_rows, len(versiones), run_id,
    )
    return resumen


# Tareas que SÍ se sirven con artefacto congelado (el clustering se recalcula fresco).
_TAREAS_SERVIBLES = ("regresion", "clasificacion")


def predecir_con_guardado(
    corpus: RepositorioCorpus,
    modelos: RepositorioModelos,
    *,
    tenant_id: str,
    dominio: str,
    rows_nuevas: list[dict[str, Any]] | None = None,
    horizon: int = motor_3x3.HORIZON_DEFAULT,
) -> tuple[dict[str, Any], int | None]:
    """Predice usando el **modelo guardado** (adoptado) del cliente, sin reentrenar.

    Junta el histórico acumulado del corpus con ``rows_nuevas`` (para reconstruir features y
    calendario del forecast), carga los predictores adoptados y delega en
    :func:`motor_3x3.servir`. Devuelve ``(respuesta, model_id_regresion)`` — el id sirve para
    auditar la predicción. Lanza ``ValueError`` si no hay datos o no hay modelo entrenado.
    """
    df_hist = corpus.leer_corpus(tenant_id, dominio)
    rows: list[dict[str, Any]] = df_hist.to_dict(orient="records") if not df_hist.empty else []
    if rows_nuevas:
        rows.extend(rows_nuevas)
    if not rows:
        raise ValueError(
            f"No hay datos para predecir en '{dominio}'. Sube datos o entrena primero."
        )

    predictores: dict[str, tuple[Any, Any]] = {}
    for tarea in _TAREAS_SERVIBLES:
        cargado = modelos.cargar_adoptado(tenant_id, dominio, tarea)
        if cargado is not None:
            predictores[tarea] = cargado

    if "regresion" not in predictores:
        raise ValueError(
            f"No hay un modelo entrenado para '{dominio}'. Usa /entrenar antes de predecir."
        )

    respuesta = motor_3x3.servir(dominio, rows, predictores, horizon=horizon)
    model_id = predictores["regresion"][1].id
    return respuesta, model_id
