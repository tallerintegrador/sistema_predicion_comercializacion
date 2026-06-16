"""Shim de compatibilidad del antiguo script monolitico.

El EDA se migro al paquete `spc` (ver `src/spc/`). Este archivo se conserva para
que `python eda.py` e `import eda; eda.main()` sigan funcionando. La logica real
vive en `spc.eda.pipeline.run_pipeline`.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# Permite usar el shim sin instalar el paquete (anade src/ al path).
_SRC = Path(__file__).resolve().parent / "src"
if _SRC.exists() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from spc.eda.pipeline import run_pipeline  # noqa: E402


def main() -> dict[str, Any]:
    """Ejecuta el pipeline completo y devuelve el resumen (compatibilidad)."""
    summary = run_pipeline()
    import json

    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    return summary


if __name__ == "__main__":
    main()
