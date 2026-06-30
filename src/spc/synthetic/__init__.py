"""Generación de **datos sintéticos por dominio** (rediseño 3×3).

Reemplaza el dataset Corporación Favorita por datos sintéticos realistas y
reproducibles, uno por dominio, con su propio **formato** (ver
``spc.synthetic.esquemas``). Cada dataset alimenta los tres modelos del dominio
(regresión, clasificación, clustering).

Uso programático::

    from spc.synthetic import generar_dominio
    df = generar_dominio("ventas", seed=42)
"""

from __future__ import annotations

from collections.abc import Callable

import pandas as pd

from spc.synthetic import almacen, compras, ventas
from spc.synthetic.esquemas import ALMACEN, COMPRAS, ESQUEMAS, VENTAS, esquema_de, validar_conforme

__all__ = [
    "ALMACEN",
    "COMPRAS",
    "ESQUEMAS",
    "VENTAS",
    "almacen",
    "compras",
    "esquema_de",
    "generar_dominio",
    "validar_conforme",
    "ventas",
]

# Despachador dominio → generador (firma homogénea por kwargs).
_GENERADORES: dict[str, Callable[..., pd.DataFrame]] = {
    "ventas": ventas.generar,
    "compras": compras.generar,
    "almacen": almacen.generar,
}


def generar_dominio(dominio: str, *, seed: int = 42, **kwargs) -> pd.DataFrame:
    """Genera el dataset sintético de un dominio (``ventas``|``compras``|``almacen``)."""
    try:
        generador = _GENERADORES[dominio]
    except KeyError:
        raise KeyError(
            f"Dominio desconocido: {dominio!r}. Use uno de {tuple(_GENERADORES)}."
        ) from None
    return generador(seed=seed, **kwargs)
