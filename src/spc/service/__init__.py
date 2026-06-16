"""Capa de servicio / orquestacion: logica de negocio agnostica al algoritmo.

Traduce el contrato de datos al esquema del motor (`adaptador`), carga los
artefactos por version (`artefactos`) y orquesta cada campo: VENTAS
(`ventas_service`, regresion), COMPRAS (`compras_service`, reposicion derivada del
pronostico) y ALMACEN (`almacen_service`, clasificacion + segmento del clustering).
Conoce el contrato y las reglas de negocio, **no el algoritmo ni HTTP**.
"""

from __future__ import annotations

__all__: list[str] = []
