"""Genera plantillas y ejemplos del contrato **3×3** (para subir a ``/v2``).

Por cada dominio (ventas/compras/almacén) escribe, en la carpeta de salida:

- ``plantilla_{dominio}.xlsx`` / ``.json`` — pocas filas, para ver el **formato**.
- ``ejemplo_{dominio}.xlsx``  / ``.json`` — datos **ricos** y realistas, listos para
  subir tal cual al sistema y ver los tres modelos en acción.

Todo es reproducible (semilla 42). Los mismos contenidos se pueden descargar en vivo
desde ``GET /v2/{dominio}/plantilla?formato=excel|json&contenido=vacia|ejemplo``.

Uso::

    python scripts/generar_ejemplos_v2.py                 # -> ejemplos/v2/
    python scripts/generar_ejemplos_v2.py -o docs/demo
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_RAIZ = Path(__file__).resolve().parent.parent
if str(_RAIZ / "src") not in sys.path:
    sys.path.insert(0, str(_RAIZ / "src"))

from spc.api.ingest import dominios_excel  # noqa: E402
from spc.service import onboarding  # noqa: E402
from spc.synthetic.esquemas import ESQUEMAS  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Genera plantillas y ejemplos del contrato 3×3.")
    parser.add_argument("-o", "--out", default="ejemplos/v2", help="Carpeta de salida (default: ejemplos/v2).")
    args = parser.parse_args(argv)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    print(f"Generando plantillas y ejemplos en {out}\n")

    for dominio in ESQUEMAS:
        for etiqueta, ricas in (("plantilla", False), ("ejemplo", True)):
            filas = onboarding.filas_ejemplo(dominio, ricas=ricas)
            # JSON (cuerpo listo para POST /v2/{dominio})
            ruta_json = out / f"{etiqueta}_{dominio}.json"
            ruta_json.write_text(
                json.dumps({"rows": filas, "horizon": 14}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            # Excel (con hoja de instrucciones)
            ruta_xlsx = out / f"{etiqueta}_{dominio}.xlsx"
            ruta_xlsx.write_bytes(dominios_excel.generar_excel(dominio, filas))
            print(f"  [ok] {ruta_xlsx.name:26s} y {ruta_json.name:26s} ({len(filas):>5d} filas)")

    print("\nListo. Súbelos en la interfaz (o con POST /v2/{dominio}/excel).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
