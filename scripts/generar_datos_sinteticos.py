"""Genera los **datos sintéticos por dominio** del rediseño 3×3 (reemplazo de Favorita).

Escribe un CSV por dominio en la carpeta de salida (default ``data/synthetic/``, ya
gitignored) más un ``MANIFIESTO.csv`` que deja explícito que los datos son sintéticos.
Todo deriva de ``--seed`` (default 42): mismas entradas → mismas filas.

Uso::

    python scripts/generar_datos_sinteticos.py --out data/synthetic --seed 42
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

# Permite ejecutar el script directamente con layout `src/`.
_RAIZ = Path(__file__).resolve().parent.parent
if str(_RAIZ / "src") not in sys.path:
    sys.path.insert(0, str(_RAIZ / "src"))

from spc.synthetic import comun, generar_dominio  # noqa: E402
from spc.synthetic.esquemas import ESQUEMAS  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Genera los datasets sintéticos por dominio (ventas/compras/almacén)."
    )
    parser.add_argument("--out", default="data/synthetic", help="Carpeta de salida (default: data/synthetic).")
    parser.add_argument("--seed", type=int, default=42, help="Semilla global (default: 42).")
    args = parser.parse_args(argv)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"Generando datos sintéticos en {out_dir} con semilla {args.seed}\n")

    manifiesto: list[dict[str, object]] = []
    for dominio in ESQUEMAS:
        df = generar_dominio(dominio, seed=args.seed)
        ruta = out_dir / f"{dominio}_sintetico.csv"
        df.to_csv(ruta, index=False)
        manifiesto.append(comun.manifiesto_fila(dominio, df, args.seed))
        print(f"  [ok] {ruta.name:28s} {len(df):>6d} filas  ×  {df.shape[1]} columnas")

    ruta_man = out_dir / "MANIFIESTO.csv"
    with ruta_man.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(manifiesto[0].keys()))
        w.writeheader()
        w.writerows(manifiesto)
    print(f"\n  [ok] {ruta_man.name} (datos SINTÉTICOS, {len(manifiesto)} dominios)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
