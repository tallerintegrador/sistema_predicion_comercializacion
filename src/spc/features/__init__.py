"""Integracion de fuentes y construccion del dataset analitico."""

from __future__ import annotations

from spc.features.holidays import aggregate_holidays
from spc.features.integration import COLUMN_CATALOG, build_analytic_dataset

__all__ = ["aggregate_holidays", "build_analytic_dataset", "COLUMN_CATALOG"]
