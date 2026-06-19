"""Política de stock de seguridad: el ÚNICO hogar de las fórmulas (Fase 3.5, ADR-0010).

El stock de seguridad se calcula por uno de dos **métodos**, elegible por dominio con un
knob de configuración (``SPC_{PURCHASES,INVENTORY}_SAFETY_METHOD``):

- ``coverage_days`` — días de cobertura: ``safety = factor × demanda(lead_time)``. Es el
  método por defecto de COMPRAS. El factor es una constante de política configurable.
- ``service_level`` — nivel de servicio: ``safety = z · σ · √lead_time``, con ``σ``
  estimada de la **demanda real** (no inventada). Si ``σ`` no es estimable (serie muy
  corta), recae en ``factor_fallback × demanda(lead_time)``. Es el método por defecto de
  INVENTORY.

**Ningún número vive aquí:** todos los parámetros entran como argumentos, leídos de
``spc.config`` por la capa de servicio. Centralizar la fórmula es lo que permite que
**conmutar INVENTORY a ``coverage_days`` lo deje idéntico a COMPRAS** con solo cambiar
una variable de entorno (la "unificación a un cambio de env" del ADR-0010).
"""

from __future__ import annotations

import math

COVERAGE_DAYS = "coverage_days"
SERVICE_LEVEL = "service_level"
METODOS: tuple[str, ...] = (COVERAGE_DAYS, SERVICE_LEVEL)


def stock_seguridad(
    metodo: str,
    *,
    demanda_lead: float,
    lead: int,
    factor_cobertura: float,
    z: float = 0.0,
    sigma_diaria: float = float("nan"),
    factor_fallback: float = 0.0,
) -> float:
    """Stock de seguridad según ``metodo`` (``coverage_days`` | ``service_level``).

    - ``service_level``: ``z · σ · √lead`` si ``σ`` (``sigma_diaria``) es finita y > 0;
      si no, recae en ``factor_fallback × demanda_lead`` (serie demasiado corta para
      estimar σ).
    - ``coverage_days`` (y, por seguridad, cualquier valor no reconocido):
      ``factor_cobertura × demanda_lead``.
    """
    if metodo == SERVICE_LEVEL:
        if math.isfinite(sigma_diaria) and sigma_diaria > 0:
            return z * sigma_diaria * math.sqrt(lead)
        return factor_fallback * demanda_lead
    return factor_cobertura * demanda_lead
