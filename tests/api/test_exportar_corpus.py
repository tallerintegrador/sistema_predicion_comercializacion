"""Tests del **script de exportación del corpus** (``scripts/exportar_corpus.py``, ADR-0011).

Anclan que el export:

- **deduplica** por identidad de serie (``client_id``, ``date``, ``store_id``,
  ``product_id``) — imprescindible antes de reentrenar (filas repetidas sesgarían el
  modelo);
- en conjunto con la **idempotencia** del repositorio, dos envíos idénticos producen un
  corpus sin duplicar;
- devuelve un código de salida claro cuando el corpus está vacío.

El script vive en ``scripts/`` (no es paquete); se carga por ruta con ``importlib``.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd

from spc.service.repositorio import RepositorioPredicciones

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "exportar_corpus.py"


def _cargar_script():
    """Carga ``scripts/exportar_corpus.py`` como módulo (no es un paquete instalable)."""
    spec = importlib.util.spec_from_file_location("exportar_corpus", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


exportar = _cargar_script()


def _history(n_dias: int = 3, store: str = "1") -> list[dict]:
    """Histórico sintético de una serie (``store``/``BEVERAGES``) de ``n_dias`` fechas."""
    fechas = [f"2017-04-{d:02d}" for d in range(1, n_dias + 1)]
    return [
        {
            "date": f,
            "store_id": store,
            "product_id": "BEVERAGES",
            "units_sold": 10.0 + i,
            "on_promotion": 0,
            "transactions": 5.0,
            "event_active": None,
        }
        for i, f in enumerate(fechas)
    ]


def test_deduplicar_quita_repetidos_por_serie_y_fecha():
    """``_deduplicar`` colapsa filas con misma (client_id, date, store_id, product_id)."""
    df = pd.DataFrame(
        [
            {"client_id": "a", "date": "2017-04-01", "store_id": "1", "product_id": "X", "units_sold": 1.0},
            {"client_id": "a", "date": "2017-04-01", "store_id": "1", "product_id": "X", "units_sold": 9.0},
            {"client_id": "a", "date": "2017-04-02", "store_id": "1", "product_id": "X", "units_sold": 2.0},
        ]
    )
    out = exportar._deduplicar(df)
    assert len(out) == 2  # la repetida se descartó
    assert out.iloc[0]["units_sold"] == 1.0  # keep-first (coincide con el repositorio)


def test_export_raw_escribe_corpus_unico(tmp_path):
    """Dos envíos idénticos → corpus idempotente → el export escribe filas únicas."""
    db = tmp_path / "spc.db"
    repo = RepositorioPredicciones.crear(db)
    hist = _history(3)
    for _ in range(2):  # mismo history dos veces: el corpus no debe duplicarse
        repo.registrar(
            client_id="default",
            domain="sales",
            channel="json",
            mode="online",
            model_version="t",
            history=hist,
            request_payload={"horizon": 3, "history": hist},
            response_payload={"field": "sales"},
        )
    assert repo.contar_observaciones() == 3  # idempotencia en la base
    repo.cerrar()

    out = tmp_path / "corpus.csv"
    rc = exportar.main(["--out", str(out), "--db", str(db), "--raw"])
    assert rc == 0
    df = pd.read_csv(out)
    assert len(df) == 3
    assert {"date", "store_id", "product_id"}.issubset(df.columns)


def test_export_corpus_vacio_devuelve_1(tmp_path):
    """Un corpus vacío no escribe nada y devuelve código 1."""
    db = tmp_path / "vacia.db"
    RepositorioPredicciones.crear(db).cerrar()
    rc = exportar.main(["--out", str(tmp_path / "x.csv"), "--db", str(db), "--raw"])
    assert rc == 1
