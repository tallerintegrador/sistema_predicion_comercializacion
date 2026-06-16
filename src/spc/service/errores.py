"""Errores de dominio de la capa de servicio.

Son **independientes de HTTP**: la capa de servicio no conoce FastAPI. La capa
API (`spc.api.errors`) los captura y los traduce al código HTTP y al cuerpo de
error del contrato. Así una regla de negocio incumplida (p. ej. pedir reposición
de un producto que no está en el histórico) produce un error controlado y claro,
no un 500 sin manejar.
"""

from __future__ import annotations


class SolicitudInvalida(ValueError):
    """La entrada es válida en el esquema pero incumple una regla de negocio.

    Ejemplos: histórico sin filas utilizables, un producto de
    ``replenishment_params``/``inventory_status`` que no aparece en el histórico,
    o un histórico demasiado corto para construir el pronóstico.
    """
