"""Benchmark del modo en línea para fijar el default de SPC_ONLINE_MAX_ROWS.

Entrena solo el artefacto de regresión (rápido) y mide el tiempo del MISMO flujo de
predicción (`responder_segun_volumen`, camino síncrono de SALES) con históricos de
~1k / ~10k / ~50k filas. Imprime una tabla; el default se elige para que una respuesta
síncrona quede cómodamente por debajo de unos pocos segundos. No es producción: usa el
artefacto diminuto y la máquina de desarrollo, así que da el ORDEN DE MAGNITUD y el
escalado, no una cifra de SLA. Uso:

    ./venv/Scripts/python.exe scripts/bench_umbral_online.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, "src")
sys.path.insert(0, "tests")

import pandas as pd  # noqa: E402

from sintetico import construir_analitico_sintetico  # noqa: E402
from spc.api import ruteo  # noqa: E402
from spc.config import Settings  # noqa: E402
from spc.models.regresion import entrenar_y_comparar, serializar_artefacto  # noqa: E402
from spc.service.artefactos import PREFIJO_REGRESION, _cargar  # noqa: E402


class _RegistroSoloRegresion:
    """Registro con solo el artefacto de regresión (lo único que usa SALES)."""

    def __init__(self, regresion) -> None:
        self.regresion = regresion


def _entrenar_registro(tmp: Path) -> _RegistroSoloRegresion:
    settings = Settings(base_dir=tmp)
    res = entrenar_y_comparar(
        construir_analitico_sintetico(), settings, max_train_rows=None, con_cv=False
    )
    serializar_artefacto(res, settings)
    return _RegistroSoloRegresion(_cargar(tmp / "models", PREFIJO_REGRESION))


def _history(n_series: int, n_dias: int) -> list[dict]:
    """Histórico en forma de contrato: ``n_series`` series de ``n_dias`` días."""
    fechas = [d.date().isoformat() for d in pd.date_range("2017-01-01", periods=n_dias, freq="D")]
    filas: list[dict] = []
    for s in range(n_series):
        for f in fechas:
            filas.append(
                {
                    "date": f,
                    "store_id": str(s + 1),
                    "product_id": "BEVERAGES",
                    "units_sold": 100.0,
                    "on_promotion": 0,
                }
            )
    return filas


def main() -> None:
    import tempfile

    from spc.api.schemas.ventas import VentasRequest

    with tempfile.TemporaryDirectory() as d:
        registro = _entrenar_registro(Path(d))
        procesar = ruteo._RUTEO["sales"].procesar

        n_dias = 180
        print(f"{'filas':>8}  {'series':>7}  {'horizon':>7}  {'segundos':>9}")
        for objetivo in (1_000, 2_000, 5_000, 10_000, 50_000):
            n_series = max(1, round(objetivo / n_dias))
            hist = _history(n_series, n_dias)
            pet = VentasRequest.model_validate({"granularity": "day", "horizon": 7, "history": hist})
            t0 = time.perf_counter()
            res = procesar(pet, registro)
            dt = time.perf_counter() - t0
            print(f"{len(hist):>8}  {n_series:>7}  {7:>7}  {dt:>9.3f}   (forecast items={len(res['forecast'])})")


if __name__ == "__main__":
    main()
