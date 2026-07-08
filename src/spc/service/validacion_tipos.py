"""Validación de **tipos por columna** de los datos que sube el usuario (canal v3).

El catálogo v3 solo comprobaba la *presencia* de columnas; los tipos se coercían tarde y
en silencio (``pd.to_datetime(errors="coerce")`` → ``NaN``), de modo que una fecha basura
o un texto en una columna numérica se convertían en huecos sin avisar al usuario.

Este módulo cierra ese hueco **antes** de entrar al motor: reutiliza la fuente única de
tipos (``spc.synthetic.esquemas``, dataclass ``Columna.tipo``) y el mismo patrón de
coerción que ya usa el canal por dominio (``motor_3x3.construir_dataframe``), pero en vez
de descartar en silencio **reporta qué columna y qué filas** están mal tipadas.

Lanza ``SolicitudInvalida`` con una lista estructurada en ``.detalles`` (``field``/``problem``)
que la capa API adjunta al cuerpo de error uniforme; el frontend la muestra celda a celda.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from spc.service.errores import SolicitudInvalida
from spc.synthetic.esquemas import esquema_de

# Cuántas filas de ejemplo citar por columna (evita mensajes kilométricos con datasets grandes).
_MAX_FILAS_EJEMPLO = 10

# Etiqueta legible del tipo esperado para el mensaje al usuario.
_ETIQUETA_TIPO = {
    "date": "una fecha (p. ej. 2024-03-15)",
    "int": "un número entero",
    "float": "un número",
}


def _filas_mal_tipadas(original: pd.Series, tipo: str) -> list[int]:
    """Índices (base 0) de las celdas **no vacías** que no se pueden convertir a ``tipo``.

    Una celda vacía/nula no cuenta como error de tipo aquí (falta de dato, no dato mal
    tipado). Solo se marca un valor que el usuario **sí** escribió pero no encaja.
    """
    no_vacia = original.notna() & (original.astype("string").str.strip() != "")
    if tipo == "date":
        convertido = pd.to_datetime(original, errors="coerce")
    else:  # int | float
        convertido = pd.to_numeric(original, errors="coerce")
    malas = no_vacia & convertido.isna()
    return [int(i) for i in original.index[malas]]


def validar_tipos(df: pd.DataFrame, dominio: str) -> None:
    """Valida que cada columna del ``df`` respete el tipo declarado en el esquema del dominio.

    Solo revisa las columnas del esquema que estén presentes (la ausencia de columnas la
    valida antes el catálogo). Si alguna columna tiene valores no vacíos que no encajan con
    su tipo (una fecha que no es fecha, un texto en una columna numérica), lanza
    ``SolicitudInvalida`` con el detalle por columna y las filas afectadas.
    """
    try:
        esquema = esquema_de(dominio)
    except KeyError:
        return  # dominio sin esquema tipado: no hay tipos que validar

    detalles: list[dict[str, str]] = []
    for col in esquema.columnas:
        if col.tipo not in ("date", "int", "float") or col.nombre not in df.columns:
            continue
        malas = _filas_mal_tipadas(df[col.nombre], col.tipo)
        if not malas:
            continue
        # Filas en base 1 para el usuario (más una elipsis si hay muchas).
        muestra = [n + 1 for n in malas[:_MAX_FILAS_EJEMPLO]]
        sufijo = f" (+{len(malas) - _MAX_FILAS_EJEMPLO} más)" if len(malas) > _MAX_FILAS_EJEMPLO else ""
        esperado = _ETIQUETA_TIPO.get(col.tipo, col.tipo)
        detalles.append(
            {
                "field": col.nombre,
                "problem": (
                    f"Se esperaba {esperado} en {len(malas)} fila(s): "
                    f"{', '.join(str(f) for f in muestra)}{sufijo}."
                ),
            }
        )

    if detalles:
        columnas = ", ".join(d["field"] for d in detalles)
        error = SolicitudInvalida(
            f"Hay datos con el tipo incorrecto en la(s) columna(s): {columnas}. "
            "Corrige esas celdas y vuelve a subir el archivo."
        )
        error.detalles = detalles  # type: ignore[attr-defined]
        raise error


def resumen_type_errors(df: pd.DataFrame, dominio: str) -> list[dict[str, Any]]:
    """Variante no lanzadora: devuelve la lista de errores de tipo (vacía si todo bien).

    Útil para poblar ``DatasetInfo.type_errors`` sin abortar (no se usa para rechazar,
    solo para superficie informativa). El rechazo lo hace ``validar_tipos``.
    """
    try:
        validar_tipos(df, dominio)
    except SolicitudInvalida as exc:
        return list(getattr(exc, "detalles", []))
    return []
