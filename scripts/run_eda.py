"""Entry point de linea de comandos para ejecutar el EDA.

Uso:
    python scripts/run_eda.py            # genera todo en el directorio actual
    python scripts/run_eda.py -v         # con logging DEBUG
    python scripts/run_eda.py --no-notebook
"""

from __future__ import annotations

import sys
from pathlib import Path

# Permite ejecutar el script sin instalar el paquete (anade src/ al path).
_SRC = Path(__file__).resolve().parent.parent / "src"
if _SRC.exists() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from spc.pipeline import cli  # noqa: E402

if __name__ == "__main__":
    cli()
