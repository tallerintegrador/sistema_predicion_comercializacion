"""Inyección de dependencias de la API.

Los artefactos se cargan **una sola vez** al arranque (lifespan en `main.py`) y se
guardan en ``app.state.registro``. Los routers reciben ese registro vía
``Depends(obtener_registro)``: no cargan nada por petición. En los tests, el
registro se inyecta directamente (artefactos diminutos) sin tocar el disco real.
"""

from __future__ import annotations

from fastapi import Request

from spc.api.errors import ServicioNoDisponible
from spc.service.artefactos import RegistroArtefactos


def obtener_registro(request: Request) -> RegistroArtefactos:
    """Devuelve el registro de artefactos cargado en el arranque.

    Lanza ``ServicioNoDisponible`` (→ HTTP 503) si el motor no se cargó (arranque
    incompleto). Es la única vía por la que los routers acceden al motor.
    """
    registro = getattr(request.app.state, "registro", None)
    if registro is None:
        raise ServicioNoDisponible("El motor de ML no está cargado.")
    return registro
