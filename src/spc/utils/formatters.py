"""Formateadores numericos y de tablas para el reporte Markdown.

Funciones puras (sin I/O) extraidas de `eda.py`. Se testean de forma aislada.
El estilo de numero usa espacio fino como separador de miles (formato es-PE).
"""

from __future__ import annotations

from typing import Any

import pandas as pd


def pct(part: float, total: float) -> float:
    """Porcentaje de ``part`` sobre ``total``, evitando division entre cero."""
    if total == 0:
        return 0.0
    return float(part) / float(total) * 100.0


def fmt_int(value: Any) -> str:
    """Entero con separador de miles; ``NA`` si el valor es nulo."""
    if pd.isna(value):
        return "NA"
    return f"{int(value):,}".replace(",", " ")


def fmt_float(value: Any, digits: int = 4) -> str:
    """Decimal con separador de miles y ``digits`` decimales; ``NA`` si es nulo."""
    if pd.isna(value):
        return "NA"
    return f"{float(value):,.{digits}f}".replace(",", " ")


def fmt_pct(value: Any, digits: int = 2) -> str:
    """Porcentaje formateado con sufijo ``%``; ``NA`` si es nulo."""
    if pd.isna(value):
        return "NA"
    return f"{float(value):.{digits}f}%"


def markdown_table(df: pd.DataFrame, max_rows: int | None = None) -> str:
    """Convierte un DataFrame pequeno en una tabla Markdown."""
    if max_rows is not None:
        df = df.head(max_rows)
    if df.empty:
        return "_Sin registros._"
    text_df = df.copy().astype(str)
    headers = list(text_df.columns)
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for _, row in text_df.iterrows():
        lines.append("| " + " | ".join(row.tolist()) + " |")
    return "\n".join(lines)
