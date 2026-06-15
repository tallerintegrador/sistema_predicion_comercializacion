"""Entrenamiento offline de la clasificacion de ALMACEN (Fase 2b).

Entrypoint **delgado**: importa ``cli`` desde ``spc.models.clasificacion`` en lugar
de ejecutar el modulo como script. Es clave para la **portabilidad del artefacto**:
al entrenar via import, ``PredictorClasificacion`` se resuelve a
``spc.models.clasificacion`` (no a ``__main__``), de modo que el ``.joblib`` carga
desde un proceso limpio (capa de servicio/API) sin aliasar ``__main__``.

Por defecto el booster entrena en **GPU** (LightGBM ``device="gpu"``); el artefacto
predice en **CPU** (portable). Usar ``--cpu`` para forzar CPU.

Uso:
    python scripts/train_clasificacion.py                # GPU, subsample 300k
    python scripts/train_clasificacion.py --full         # artefacto sobre todo el historico
    python scripts/train_clasificacion.py --cpu          # sin GPU
    python scripts/train_clasificacion.py --sin-cv       # omitir CV temporal
"""

from __future__ import annotations

import sys
from pathlib import Path

# Permite ejecutar el script sin instalar el paquete (anade src/ al path).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from spc.models.clasificacion import cli

if __name__ == "__main__":
    cli()
