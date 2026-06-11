"""Entrada/salida: carga de los CSV crudos y escritura de artefactos."""

from __future__ import annotations

from spc.io.loaders import check_files, load_data, write_csv, write_json

__all__ = ["check_files", "load_data", "write_csv", "write_json"]
