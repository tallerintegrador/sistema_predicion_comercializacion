"""Utilidades transversales: logging, metricas, formateadores, serializacion.

Soporte para todas las capas. No dependen del negocio ni de HTTP.
"""

from __future__ import annotations

from spc.utils.logging import configure_logging, get_logger

__all__ = ["configure_logging", "get_logger"]
