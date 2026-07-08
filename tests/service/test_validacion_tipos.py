"""Tests de la validación de tipos por columna del canal v3 (``spc.service.validacion_tipos``)."""

from __future__ import annotations

import pandas as pd
import pytest

from spc.service.errores import SolicitudInvalida
from spc.service.validacion_tipos import validar_tipos


def _fila_valida() -> dict:
    return {
        "fecha": "2024-01-01",
        "id_tienda": "T1",
        "sku": "A",
        "unidades_vendidas": 5,
        "precio_unitario": 2.0,
    }


def test_dataset_valido_no_lanza() -> None:
    df = pd.DataFrame([_fila_valida(), _fila_valida()])
    validar_tipos(df, "ventas")  # no debe lanzar


def test_fecha_no_parseable_es_rechazada_con_detalle() -> None:
    mala = _fila_valida()
    mala["fecha"] = "no-es-fecha"
    df = pd.DataFrame([_fila_valida(), mala])
    with pytest.raises(SolicitudInvalida) as exc:
        validar_tipos(df, "ventas")
    detalles = getattr(exc.value, "detalles", [])
    assert any(d["field"] == "fecha" for d in detalles)
    # La fila mala es la 2 (base 1).
    assert "2" in detalles[0]["problem"]


def test_numerica_con_texto_es_rechazada() -> None:
    mala = _fila_valida()
    mala["unidades_vendidas"] = "hola"
    df = pd.DataFrame([_fila_valida(), mala])
    with pytest.raises(SolicitudInvalida) as exc:
        validar_tipos(df, "ventas")
    campos = {d["field"] for d in getattr(exc.value, "detalles", [])}
    assert "unidades_vendidas" in campos


def test_celda_vacia_no_cuenta_como_error_de_tipo() -> None:
    # Un hueco (None) es falta de dato, no un dato mal tipado: no debe disparar el rechazo.
    fila = _fila_valida()
    fila["precio_unitario"] = None
    df = pd.DataFrame([_fila_valida(), fila])
    validar_tipos(df, "ventas")  # no lanza


def test_dominio_desconocido_no_lanza() -> None:
    df = pd.DataFrame([{"x": 1}])
    validar_tipos(df, "inexistente")  # sin esquema tipado → no valida, no lanza
