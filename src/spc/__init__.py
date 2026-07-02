"""Sistema Predictivo de Comercializacion (SPC).

Arquitectura por capas (las dependencias apuntan hacia adentro):
- `config`  : configuracion y constantes.
- `data`    : carga de fuentes, validacion de esquema, integracion (dataset 30 col).
- `features`: feature engineering del motor de ML (calendario, rezagos, log1p).
- `models`  : regresion (VENTAS), clasificacion (ALMACEN), zoo liviano/automl.
- `synthetic`: generacion sintetica (datos 3x3 por dominio).
- `service` : logica de negocio (agnostico, motor 3x3, persistencia) — agnostica al algoritmo.
- `utils`   : logging, metricas, formateadores, serializacion.

El motor exploratorio de la Fase 1 (EDA sobre Favorita) se archivo en `legacy/`
fuera del backend; ya no forma parte del paquete `spc`.
"""

from __future__ import annotations

from spc.config import Settings

__version__ = "0.1.0"
__all__ = ["Settings", "__version__"]
