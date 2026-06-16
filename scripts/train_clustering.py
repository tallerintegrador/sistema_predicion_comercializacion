"""Entrenamiento offline del clustering/perfilado (Fase 2c).

Entrypoint **delgado**: importa ``cli`` desde ``spc.models.clustering`` en lugar de
ejecutar el modulo como script. Es clave para la **portabilidad de los artefactos**:
al entrenar via import, ``PerfiladorClustering`` se resuelve a
``spc.models.clustering`` (no a ``__main__``), de modo que los ``.joblib`` cargan
desde un proceso limpio (capa de servicio/API) sin aliasar ``__main__``.

El clustering opera sobre 54 tiendas / 33 familias: **CPU puro y determinista** (no
usa GPU; la GPU de la 2a/2b era para los boosters sobre millones de filas).

Uso:
    python scripts/train_clustering.py                # entrena tiendas + familias
    python scripts/train_clustering.py --base-dir .   # raiz explicita
"""

from __future__ import annotations

import sys
from pathlib import Path

# Permite ejecutar el script sin instalar el paquete (anade src/ al path).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from spc.models.clustering import cli

if __name__ == "__main__":
    cli()
