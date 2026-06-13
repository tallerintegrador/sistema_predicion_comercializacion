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

from spc.config import Settings
from spc.eda.pipeline import run_pipeline

__version__ = "0.1.0"
__all__ = ["Settings", "run_pipeline", "__version__"]
