"""Serializacion de artefactos del motor de ML (entrenamiento offline).

El entrenamiento ocurre offline (Fase 2) y produce un artefacto serializado que
en produccion solo se **carga y predice** (nunca se reentrena en caliente). Se
usa ``joblib`` para el objeto entrenado y un JSON adjunto con los metadatos
(version, fecha, features, transformacion, metricas, semilla) para trazabilidad.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib


def _ruta_metadatos(ruta_artefacto: Path) -> Path:
    """Devuelve la ruta del JSON de metadatos adjunto al artefacto."""
    return ruta_artefacto.with_suffix(".meta.json")


def guardar_artefacto(
    objeto: Any, ruta_artefacto: Path, metadatos: dict[str, Any]
) -> tuple[Path, Path]:
    """Serializa ``objeto`` y escribe sus ``metadatos`` en un JSON adjunto.

    Devuelve ``(ruta_artefacto, ruta_metadatos)``. Inyecta ``guardado_utc`` si no
    viene en los metadatos.
    """
    ruta_artefacto = Path(ruta_artefacto)
    ruta_artefacto.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(objeto, ruta_artefacto)

    metadatos = dict(metadatos)
    metadatos.setdefault("guardado_utc", datetime.now(UTC).isoformat())
    metadatos["artefacto"] = ruta_artefacto.name

    ruta_meta = _ruta_metadatos(ruta_artefacto)
    ruta_meta.write_text(
        json.dumps(metadatos, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    return ruta_artefacto, ruta_meta


def cargar_artefacto(ruta_artefacto: Path) -> tuple[Any, dict[str, Any]]:
    """Carga el objeto serializado y sus metadatos (si existe el JSON adjunto)."""
    ruta_artefacto = Path(ruta_artefacto)
    objeto = joblib.load(ruta_artefacto)
    ruta_meta = _ruta_metadatos(ruta_artefacto)
    metadatos: dict[str, Any] = {}
    if ruta_meta.exists():
        metadatos = json.loads(ruta_meta.read_text(encoding="utf-8"))
    return objeto, metadatos
