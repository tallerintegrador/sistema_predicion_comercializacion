"""Sistema Predictivo de Comercializacion (SPC) - EDA reproducible.

Paquete que migra el antiguo script monolitico `eda.py` a una arquitectura modular:
carga (`io`), calidad (`quality`), integracion (`features`), analisis (`analysis`),
figuras (`viz`) y redaccion de reporte/notebook (`reporting`), orquestados por
`pipeline.run_pipeline`.
"""

from __future__ import annotations

from spc.config import Settings
from spc.pipeline import run_pipeline

__version__ = "0.1.0"
__all__ = ["Settings", "run_pipeline", "__version__"]
