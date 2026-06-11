"""Tests de los formateadores (funciones puras)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from spc.reporting.formatters import fmt_float, fmt_int, fmt_pct, markdown_table, pct


def test_pct_evita_division_cero():
    assert pct(5, 0) == 0.0
    assert pct(1, 4) == 25.0


def test_fmt_int_separador_y_na():
    assert fmt_int(1234567) == "1 234 567"
    assert fmt_int(np.nan) == "NA"


def test_fmt_float_decimales_y_na():
    assert fmt_float(1234.5, 2) == "1 234.50"
    assert fmt_float(None) == "NA"


def test_fmt_pct():
    assert fmt_pct(31.2987, 2) == "31.30%"
    assert fmt_pct(np.nan) == "NA"


def test_markdown_table_vacio():
    assert markdown_table(pd.DataFrame()) == "_Sin registros._"


def test_markdown_table_basico():
    df = pd.DataFrame({"a": [1, 2], "b": ["x", "y"]})
    out = markdown_table(df)
    assert out.splitlines()[0] == "| a | b |"
    assert "| 1 | x |" in out
    assert "| 2 | y |" in out


def test_markdown_table_max_rows():
    df = pd.DataFrame({"a": range(10)})
    out = markdown_table(df, max_rows=3)
    # cabecera + separador + 3 filas
    assert len(out.splitlines()) == 5
