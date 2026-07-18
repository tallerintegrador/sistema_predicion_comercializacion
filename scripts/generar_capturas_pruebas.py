"""Genera las capturas de evidencia de las pruebas (unitarias, E2E y experimentación).

Ejecuta las suites de pytest, guarda la salida como ``.txt`` (log completo) y como ``.png``
(captura estilo consola, vía ``render_captura``), y reúne la evidencia gráfica de los
experimentos copiando las figuras clave de ``figures/``. Todo va a
``final/evidencias/pruebas/{unitarias,e2e,experimentacion}/``.

Uso:
    python scripts/generar_capturas_pruebas.py

Requiere Pillow (``pip install Pillow``). Sin Pillow, guarda solo los ``.txt``.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
EVID = RAIZ / "final" / "evidencias" / "pruebas"

sys.path.insert(0, str(Path(__file__).resolve().parent))


def _render_disponible() -> bool:
    try:
        import PIL  # noqa: F401

        return True
    except Exception:
        return False


def _correr_pytest(args: list[str]) -> str:
    """Corre pytest con el intérprete actual (venv) y devuelve la salida combinada."""
    cmd = [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-o", "addopts=", *args]
    proc = subprocess.run(cmd, cwd=str(RAIZ), capture_output=True, text=True)
    return (proc.stdout or "") + (proc.stderr or "")


def _guardar(nombre: str, subdir: str, texto: str, titulo: str, usar_png: bool) -> None:
    carpeta = EVID / subdir
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / f"{nombre}.txt").write_text(texto, encoding="utf-8")
    if usar_png:
        from render_captura import render_png

        render_png(texto, carpeta / f"{nombre}.png", titulo=titulo)
    print(f"OK  ->  {carpeta / nombre}.txt" + ("  (+ .png)" if usar_png else ""))


def _copiar_figuras() -> None:
    """Copia las figuras de apoyo de los experimentos a la carpeta de evidencia."""
    destino = EVID / "experimentacion"
    destino.mkdir(parents=True, exist_ok=True)
    figuras = RAIZ / "figures"
    claves = [
        "11_balance_clases_demanda.png",
        "18_segmentacion_tiendas_kmeans.png",
        "19_silueta_k_tiendas.png",
    ]
    copiadas = 0
    for nombre in claves:
        src = figuras / nombre
        if src.exists():
            shutil.copy2(src, destino / nombre)
            copiadas += 1
    # Si faltan las nombradas, copia hasta 3 PNG cualesquiera de figures/ como respaldo.
    if copiadas == 0 and figuras.exists():
        for src in sorted(figuras.glob("*.png"))[:3]:
            shutil.copy2(src, destino / src.name)
            copiadas += 1
    print(f"OK  ->  {copiadas} figura(s) de experimentación copiadas a {destino}")


def main() -> None:
    usar_png = _render_disponible()
    if not usar_png:
        print("AVISO: Pillow no está instalado; se guardan solo los .txt (sin .png).")

    print("== Ejecutando pruebas unitarias / persistencia ==")
    unit = _correr_pytest(["tests", "--ignore=tests/api", "-v", "-m", "not slow"])
    _guardar("pytest_unitarias", "unitarias", unit,
             "pytest tests (unitarias + persistencia)  -v  -m 'not slow'", usar_png)

    print("== Ejecutando cobertura ==")
    cov = _correr_pytest(["tests", "--ignore=tests/api", "-m", "not slow",
                          "--cov=spc", "--cov-report=term-missing:skip-covered", "-q"])
    _guardar("cobertura", "unitarias", cov, "pytest --cov=spc (cobertura)", usar_png)

    print("== Ejecutando pruebas E2E (API) ==")
    e2e = _correr_pytest(["tests/api", "-v"])
    _guardar("pytest_e2e", "e2e", e2e, "pytest tests/api  -v  (End to End)", usar_png)

    print("== Reuniendo evidencia de experimentación ==")
    _copiar_figuras()

    print("\nListo. Evidencia en:", EVID)


if __name__ == "__main__":
    main()
