"""Genera peticiones de ejemplo (JSON) para probar la API de la Fase 3.

Crea, junto a este archivo, tres JSON listos para pegar en Swagger o enviar por
PowerShell/curl: ``ventas_request.json``, ``compras_request.json`` y
``almacen_request.json``. Comparten el mismo bloque ``history`` (70 días, 2
puntos de venta, 1 producto) — suficiente historia para que el pronóstico use sus
rezagos. Reproducible (semilla fija).

Uso:
    venv\\Scripts\\python examples\\api\\generar_ejemplos.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

AQUI = Path(__file__).resolve().parent


def construir_historico() -> list[dict]:
    """Histórico sintético en forma de contrato: 2 puntos de venta, 1 producto, 70 días."""
    rng = np.random.default_rng(2024)
    fechas = [d.date().isoformat() for d in pd.date_range("2017-06-01", periods=70, freq="D")]
    filas: list[dict] = []
    for pv in ("1", "2"):
        prev = rng.uniform(900, 1300)
        for f in fechas:
            promo = int(rng.integers(0, 8))
            valor = max(0.0, 0.8 * prev + 22 * promo + rng.normal(0, 45))
            prev = valor
            filas.append(
                {
                    "date": f,
                    "store_id": pv,
                    "product_id": "BEVERAGES",
                    "units_sold": round(valor, 1),
                    "on_promotion": promo,
                    "transactions": round(valor * 1.5, 0),
                }
            )
    return filas


def main() -> None:
    historico = construir_historico()

    ventas = {"granularity": "day", "horizon": 7, "history": historico}
    compras = {
        "history": historico,
        "replenishment_params": [
            {
                "store_id": "1",
                "product_id": "BEVERAGES",
                "current_stock": 900,
                "lead_time_days": 3,
                "target_coverage_days": 7,
            }
        ],
    }
    almacen = {
        "history": historico,
        "inventory_status": [
            {"store_id": "1", "product_id": "BEVERAGES", "current_stock": 300, "lead_time_days": 3},
            {"store_id": "2", "product_id": "BEVERAGES", "current_stock": 8000},
        ],
    }

    for nombre, cuerpo in (
        ("ventas_request.json", ventas),
        ("compras_request.json", compras),
        ("almacen_request.json", almacen),
    ):
        (AQUI / nombre).write_text(json.dumps(cuerpo, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Escrito {nombre} ({len(json.dumps(cuerpo))} bytes)")


if __name__ == "__main__":
    main()
