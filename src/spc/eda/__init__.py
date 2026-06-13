"""Motor de EDA (Fase 1): analisis, calidad, figuras, reporte y orquestacion.

Agrupa el codigo exploratorio que sustenta las decisiones de modelado
(`analysis`, `quality`, `viz`, `reporting`) y el pipeline que lo orquesta.
Queda separado del motor de produccion (`data`, `features`, `models`, ...).
"""

from __future__ import annotations

from spc.eda.pipeline import run_pipeline

__all__ = ["run_pipeline"]
