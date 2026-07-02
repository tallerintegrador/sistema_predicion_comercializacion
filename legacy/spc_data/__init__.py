"""Capa de datos: carga de fuentes, validacion de esquema e integracion.

Reune lo que antes vivia en `spc.io` (carga/escritura) y la integracion de las
7 fuentes en el dataset analitico (antes en `spc.features`). Es la frontera de
entrada del motor: produce el dataset de 30 columnas que consumen features y
modelos.
"""

from __future__ import annotations

from spc.data.holidays import aggregate_holidays
from spc.data.integration import COLUMN_CATALOG, build_analytic_dataset
from spc.data.loaders import check_files, load_data, write_csv, write_json

__all__ = [
    "aggregate_holidays",
    "build_analytic_dataset",
    "COLUMN_CATALOG",
    "check_files",
    "load_data",
    "write_csv",
    "write_json",
]
