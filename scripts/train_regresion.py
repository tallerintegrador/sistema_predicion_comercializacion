"""Entrenamiento offline de la regresion de VENTAS (Fase 2a).

Entrypoint **delgado**: importa ``cli`` desde ``spc.models.regresion`` en lugar
de ejecutar el modulo como script. Es clave para la **portabilidad del artefacto**:
al entrenar via import, las clases serializadas (``PredictorRegresion``,
``ModeloEnsemble``) se resuelven a ``spc.models.regresion`` y no a ``__main__``,
de modo que el ``.joblib`` carga desde un proceso limpio (capa de servicio/API)
sin necesidad de aliasar ``__main__``.

Por defecto los boosters entrenan en **GPU** (XGBoost ``device="cuda"``, LightGBM
``device="gpu"``); el artefacto resultante predice en **CPU** (portable). Usar
``--cpu`` para forzar CPU.

Uso:
    python scripts/train_regresion.py                 # GPU, subsample 250k para comparar
    python scripts/train_regresion.py --full          # artefacto sobre todo el historico
    python scripts/train_regresion.py --cpu            # sin GPU
    python scripts/train_regresion.py --sin-ensemble   # solo modelos individuales
"""

from __future__ import annotations

import sys
from pathlib import Path

# Permite ejecutar el script sin instalar el paquete (anade src/ al path).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from spc.models.regresion import cli

if __name__ == "__main__":
    cli()
