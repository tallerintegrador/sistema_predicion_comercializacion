"""Perfilado general y chequeos de calidad de datos."""

from __future__ import annotations

from spc.eda.quality.checks import build_observations, quality_checks
from spc.eda.quality.profiling import build_profiles, profile_dataframe

__all__ = ["profile_dataframe", "build_profiles", "quality_checks", "build_observations"]
