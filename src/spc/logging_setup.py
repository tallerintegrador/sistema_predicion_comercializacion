"""Logging del paquete: reemplaza los `print` dispersos por un logger configurable."""

from __future__ import annotations

import logging

_CONFIGURED = False


def configure_logging(verbose: bool = False) -> None:
    """Configura el logging raiz una sola vez (idempotente)."""
    global _CONFIGURED
    if _CONFIGURED:
        return
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Devuelve un logger con el namespace del paquete."""
    return logging.getLogger(f"spc.{name}")
