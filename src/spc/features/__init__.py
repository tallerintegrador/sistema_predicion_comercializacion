"""Feature engineering del motor de ML (calendario, rezagos, log1p).

La ingenieria de variables reutilizable para el modelado (Fase 2). La
integracion de fuentes y la construccion del dataset analitico viven en
`spc.data` (capa de datos), no aqui.
"""

from __future__ import annotations

from spc.features.temporales import (
    ConfigFeatures,
    columnas_rezago,
    construir_features,
)

__all__ = ["ConfigFeatures", "construir_features", "columnas_rezago"]
