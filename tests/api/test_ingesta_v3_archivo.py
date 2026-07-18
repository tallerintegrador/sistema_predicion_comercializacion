"""Tests E2E del canal de **archivo** y **demo** del catálogo v3 (ADR-0028).

Cubren los caminos del router v3 que el resto de la suite no ejercita: subir datos como
archivo (``POST /v3/{modulo}/archivo``, Excel y JSON) y el análisis de demostración
(``GET /v3/{modulo}/demo``). Los datos salen del mismo generador sintético del sistema, así
que respetan el esquema del módulo (fuente única). Recorren la app entera vía ``TestClient``
con base SQLite temporal (fixture ``client``).
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pandas as pd
import pytest

from spc.synthetic import generar_dominio


def _df_ventas() -> pd.DataFrame:
    """Dataset de ventas pequeño (JSON-safe) conforme al esquema del módulo."""
    df = generar_dominio("ventas", seed=42, n_tiendas=2, n_productos=6, n_dias=90)
    df["fecha"] = df["fecha"].astype(str)
    return df


def _excel_bytes(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="datos")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# POST /v3/{modulo}/archivo — Excel
# ---------------------------------------------------------------------------
def test_archivo_excel_valido_ejecuta_analisis(client) -> None:
    xlsx = _excel_bytes(_df_ventas())
    resp = client.post(
        "/v3/ventas/archivo",
        files={"file": ("datos.xlsx", xlsx,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["module"] == "ventas"
    assert len(body["reports"]) >= 1  # las 10 consultas del catálogo
    assert body["dataset_info"]["rows_received"] > 0


# ---------------------------------------------------------------------------
# POST /v3/{modulo}/archivo — JSON
# ---------------------------------------------------------------------------
def test_archivo_json_valido_equivale_al_excel(client) -> None:
    rows = _df_ventas().to_dict(orient="records")
    contenido = json.dumps({"rows": rows}).encode("utf-8")
    resp = client.post(
        "/v3/ventas/archivo",
        files={"file": ("datos.json", contenido, "application/json")},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["module"] == "ventas"


# ---------------------------------------------------------------------------
# Errores controlados (nunca 500)
# ---------------------------------------------------------------------------
def test_archivo_modulo_inexistente_400(client) -> None:
    resp = client.post(
        "/v3/inexistente/archivo",
        files={"file": ("datos.json", b"[]", "application/json")},
    )
    assert resp.status_code == 400
    assert "inexistente" in json.dumps(resp.json()).lower()


def test_archivo_formato_no_soportado_400(client) -> None:
    resp = client.post(
        "/v3/ventas/archivo",
        files={"file": ("datos.csv", b"a,b,c\n1,2,3", "text/csv")},
    )
    assert resp.status_code == 400  # solo .xlsx/.xls/.json


def test_archivo_vacio_422(client) -> None:
    resp = client.post(
        "/v3/ventas/archivo",
        files={"file": ("vacio.json", b"[]", "application/json")},
    )
    assert resp.status_code == 422
    assert "filas" in json.dumps(resp.json()).lower()


def test_archivo_columnas_faltantes_422(client) -> None:
    # JSON con filas pero sin las columnas del módulo → validación clara, no 500.
    contenido = json.dumps([{"foo": 1, "bar": 2}]).encode("utf-8")
    resp = client.post(
        "/v3/ventas/archivo",
        files={"file": ("malo.json", contenido, "application/json")},
    )
    assert resp.status_code == 422


def test_archivo_excel_corrupto_422(client) -> None:
    resp = client.post(
        "/v3/ventas/archivo",
        files={"file": ("roto.xlsx", b"no soy un excel",
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /v3/{modulo}/demo
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("modulo", ["ventas", "compras", "almacen"])
def test_demo_v3_devuelve_reportes(client, modulo: str) -> None:
    resp = client.get(f"/v3/{modulo}/demo")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["module"] == modulo
    assert len(body["reports"]) >= 1
    assert body["trend_analysis"] is not None


def test_demo_v3_modulo_inexistente_400(client) -> None:
    resp = client.get("/v3/inexistente/demo")
    assert resp.status_code == 400


@pytest.mark.slow
@pytest.mark.parametrize("modulo", ["ventas", "compras", "almacen"])
@pytest.mark.parametrize("extension,mime", [
    ("json", "application/json"),
    ("xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
])
def test_archivos_reconstruidos_e2e_tienen_diez_reportes_y_remuestreo(
    client, modulo: str, extension: str, mime: str
) -> None:
    path = Path("pyme_hibrida/reconstruccion_smote/reconstruido") / f"{modulo}_smotenc.{extension}"
    if not path.exists():
        pytest.skip("Primero ejecute scripts/reconstruir_pyme_hibrida.py")
    resp = client.post(
        f"/v3/{modulo}/archivo",
        files={"file": (path.name, path.read_bytes(), mime)},
    )
    assert resp.status_code == 200, resp.text
    reportes = resp.json()["reports"]
    assert len(reportes) == 10
    detalles = [
        r["technical_detail"]["resampling"]
        for r in reportes
        if r["type"] == "classification" and r["technical_detail"]["resampling"] is not None
    ]
    assert detalles
    assert all(d["applied_split"] == "train" for d in detalles)
