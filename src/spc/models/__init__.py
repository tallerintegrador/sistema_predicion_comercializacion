"""Modelos del motor de ML: regresion (VENTAS), clasificacion (ALMACEN), clustering.

El entrenamiento ocurre offline y produce artefactos serializados; en produccion
solo se cargan y predicen. Este paquete no conoce HTTP ni el negocio del cliente.
"""

from __future__ import annotations

__all__: list[str] = []
