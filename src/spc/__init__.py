"""Sistema Predictivo de Comercializacion (SPC).

Arquitectura por capas (las dependencias apuntan hacia adentro):
- `config`  : configuracion y constantes.
- `data`    : carga de fuentes, validacion de esquema, integracion (dataset 30 col).
- `features`: feature engineering del motor de ML (calendario, rezagos, log1p).
- `models`  : regresion (VENTAS), clasificacion (ALMACEN), clustering.
- `synthetic`: generacion sintetica (SMOTE).
- `service` : logica de negocio (compras, almacen) — agnostica al algoritmo.
- `utils`   : logging, metricas, formateadores, serializacion.
- `eda`     : motor exploratorio de la Fase 1 (analisis, calidad, viz, reporte).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from spc.config import Settings

if TYPE_CHECKING:
    from spc.eda.pipeline import run_pipeline

__version__ = "0.1.0"
__all__ = ["Settings", "run_pipeline", "__version__"]


def __getattr__(name: str) -> Any:
    """Carga perezosa de `run_pipeline` (PEP 562).

    El EDA (Fase 1) depende de matplotlib/seaborn/nbformat; la API (Fase 3) no.
    Importarlo de forma eager haria que un simple ``import spc`` —el que hace la
    API al cargar ``spc.api.main``— arrastrase todas las deps de EDA. Se difiere
    hasta que alguien acceda de verdad a ``spc.run_pipeline``.
    """
    if name == "run_pipeline":
        from spc.eda.pipeline import run_pipeline

        return run_pipeline
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
