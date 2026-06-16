"""Carga y resolución de los artefactos del motor para la capa de servicio.

Resuelve cada familia de modelo por **glob de versión** (la mayor ``_vN`` presente
en ``models/``) y la carga con `spc.utils.serializacion.cargar_artefacto`, que
devuelve ``(objeto, meta)``. Así la API **sobrevive a un cambio de artefacto sin
tocar código**: si mañana sale ``regresion_v4`` o cambian el umbral, la composición
del ensemble o el ``k`` de los clusters, basta con dejar el nuevo ``.joblib`` +
``.meta.json`` en ``models/``.

El **valor de negocio nunca se reconstruye aquí**: el umbral de clasificación, la
composición/pesos del ensemble y los segmentos del clustering viven **dentro** de
los objetos `Predictor*`/`Perfilador*` (que se cargan tal cual) y, de forma
informativa, en el ``meta`` (que solo se lee para poblar la respuesta y Swagger).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from spc.utils.serializacion import cargar_artefacto

# Prefijos de archivo por familia (sin la versión). La versión la resuelve el glob.
PREFIJO_REGRESION = "regresion"
PREFIJO_CLASIFICACION = "clasificacion"
PREFIJO_CLUSTERING_TIENDAS = "clustering_tiendas"
PREFIJO_CLUSTERING_FAMILIAS = "clustering_familias"

_PATRON_VERSION = re.compile(r"_v(\d+)$")


@dataclass(frozen=True)
class ArtefactoCargado:
    """Un artefacto ya cargado: el objeto que predice + su meta + su ruta."""

    objeto: Any
    meta: dict[str, Any]
    ruta: Path


def resolver_ultima_version(models_dir: Path, prefijo: str) -> Path:
    """Devuelve la ruta del artefacto de mayor versión para ``prefijo``.

    Busca ``{prefijo}_v*.joblib`` y elige la versión numérica más alta. Lanza
    ``FileNotFoundError`` si no hay ninguno (la API no puede arrancar sin el motor).
    """
    candidatos: list[tuple[int, Path]] = []
    for ruta in models_dir.glob(f"{prefijo}_v*.joblib"):
        m = _PATRON_VERSION.search(ruta.stem)
        if m:
            candidatos.append((int(m.group(1)), ruta))
    if not candidatos:
        raise FileNotFoundError(
            f"No se encontró ningún artefacto '{prefijo}_v*.joblib' en {models_dir}. "
            "Entrena el motor (Fase 2) o ajusta el directorio de modelos."
        )
    return max(candidatos, key=lambda par: par[0])[1]


def _cargar(models_dir: Path, prefijo: str) -> ArtefactoCargado:
    ruta = resolver_ultima_version(models_dir, prefijo)
    objeto, meta = cargar_artefacto(ruta)
    return ArtefactoCargado(objeto=objeto, meta=meta, ruta=ruta)


@dataclass(frozen=True)
class RegistroArtefactos:
    """Los artefactos del motor ya cargados, listos para inyectar a los servicios."""

    regresion: ArtefactoCargado
    clasificacion: ArtefactoCargado
    clustering_tiendas: ArtefactoCargado

    @classmethod
    def cargar(cls, models_dir: Path) -> RegistroArtefactos:
        """Carga la última versión de cada familia desde ``models_dir``.

        Regresión (VENTAS/COMPRAS), clasificación (ALMACÉN) y clustering de tiendas
        (``store_segment`` de ALMACÉN). El clustering de familias no se necesita
        para el contrato y no se carga aquí.
        """
        models_dir = Path(models_dir)
        return cls(
            regresion=_cargar(models_dir, PREFIJO_REGRESION),
            clasificacion=_cargar(models_dir, PREFIJO_CLASIFICACION),
            clustering_tiendas=_cargar(models_dir, PREFIJO_CLUSTERING_TIENDAS),
        )
