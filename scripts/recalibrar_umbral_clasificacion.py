"""Recalibracion POST-HOC del umbral de la clasificacion de ALMACEN (Fase 2b).

Entrypoint **delgado**: importa ``cli_recalibrar`` desde
``spc.models.clasificacion`` (igual que el entrenamiento, por la portabilidad del
artefacto: ``PredictorClasificacion`` se resuelve a ``spc.models.clasificacion``,
no a ``__main__``, asi que el ``.joblib`` carga/guarda desde un proceso limpio).

**No reentrena** el booster de produccion: reproduce las probabilidades held-out
de la estrategia ya elegida (``sin_remuestreo``, CPU determinista, semilla 42),
re-elige el umbral por defecto en VALID (max recall con piso real de precision
0.80, margen +0.02 VALID->TEST), evalua TEST una sola vez y actualiza
artefacto+meta, curva PR, registro de metricas y reporte. El modelo no cambia: solo
su umbral/metadatos.

Uso:
    python scripts/recalibrar_umbral_clasificacion.py            # CPU, subsample 300k
    python scripts/recalibrar_umbral_clasificacion.py --full     # sin tope (lento)
    python scripts/recalibrar_umbral_clasificacion.py --gpu      # reproducir en GPU
"""

from __future__ import annotations

import sys
from pathlib import Path

# Permite ejecutar el script sin instalar el paquete (anade src/ al path).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from spc.models.clasificacion import cli_recalibrar

if __name__ == "__main__":
    cli_recalibrar()
