"""Esquemas Pydantic que implementan el contrato de datos (seccion 3).

Un modulo por dominio (`ventas`, `compras`, `almacen`) con su *request* y su
*response*, mas `comunes` con el bloque `history` compartido y el esquema de
error unico. Los nombres son los **genericos del contrato** (`store_id`,
`product_id`, `units_sold`, ...), nunca los del motor (`store_nbr`,
`family`, `sales`).
"""
