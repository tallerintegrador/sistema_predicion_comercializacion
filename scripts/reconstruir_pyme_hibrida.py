"""Genera base cruda y reconstruccion SMOTENC de los tres dominios de pyme_hibrida."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ / "src") not in sys.path:
    sys.path.insert(0, str(RAIZ / "src"))

from spc.synthetic.reconstruccion_smote import ejecutar_reconstruccion  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--origen", default="pyme_hibrida")
    parser.add_argument("--destino", default="pyme_hibrida/reconstruccion_smote")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    resultados = ejecutar_reconstruccion(args.origen, args.destino, args.seed)
    for r in resultados:
        a = r.auditoria
        print(
            f"{r.dominio}: retencion={a.retencion_minoria:.0%} k={a.k_neighbors} "
            f"crudo={a.filas_crudo} reconstruido={a.filas_reconstruidas} "
            f"sinteticas={a.sinteticas_agregadas} estadistica={a.cumple} "
            f"modelos={a.metricas_modelos_cumplen}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
