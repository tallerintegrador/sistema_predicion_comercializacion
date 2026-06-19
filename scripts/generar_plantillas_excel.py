"""Genera las plantillas Excel de los tres dominios (DESDE el contrato).

Escribe ``sales_template.xlsx``, ``purchases_template.xlsx`` e
``inventory_template.xlsx`` en el directorio indicado. Cada archivo ya trae una **fila
de ejemplo** lista para usar, así que la plantilla descargada se puede subir tal cual a
``POST /{dominio}/excel`` para comprobar el flujo.

Uso:
    python scripts/generar_plantillas_excel.py                  # ./plantillas_excel/
    python scripts/generar_plantillas_excel.py -o docs/fase-3/plantillas
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Permite ejecutar el script sin instalar el paquete (anade src/ al path).
_SRC = Path(__file__).resolve().parent.parent / "src"
if _SRC.exists() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from spc.api.ingest.esquema_excel import DOMINIOS, plantilla_de  # noqa: E402
from spc.api.ingest.plantilla import generar_workbook  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Genera las plantillas Excel del SPC.")
    parser.add_argument(
        "-o",
        "--out",
        type=Path,
        default=Path("plantillas_excel"),
        help="Directorio de salida (por defecto ./plantillas_excel).",
    )
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    for dominio in DOMINIOS:
        archivo = plantilla_de(dominio).archivo
        ruta = args.out / archivo
        generar_workbook(dominio).save(ruta)
        print(f"  [OK] {ruta}")
    print(f"Listo. {len(DOMINIOS)} plantillas en {args.out.resolve()}")


if __name__ == "__main__":
    main()
