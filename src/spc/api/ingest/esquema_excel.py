"""Definición de la plantilla Excel por dominio, **derivada del contrato**.

Esta es la **fuente única** que comparten el generador de plantillas
(`plantilla.py`) y el lector de subidas (`lector.py`): si mañana cambia un campo en
los modelos Pydantic, la plantilla y el parseo cambian con él (no hay un "esquema de
Excel" escrito a mano que pueda desincronizarse).

**Mapeo contrato (anidado) → Excel (tabular).** El contrato es anidado (`history[]`
más parámetros/listas por dominio); Excel es tabular, así que cada bloque va a su
propia **hoja**:

- una hoja `history` (bloque común, una fila por observación),
- SALES: **solo datos** (`history`). La configuración del pronóstico
  (`granularity`, `horizon`) **no** viaja en el archivo: se toma de la petición en
  pantalla (ADR-0022); por eso la plantilla de Ventas no tiene hoja de parámetros.
- PURCHASES: una hoja `replenishment_params` (una fila por producto),
- INVENTORY: una hoja `inventory_status` (una fila por producto).

Los **encabezados de columna van en inglés** (nombres canónicos del contrato); la
hoja de instrucciones (en `plantilla.py`) va en español.
"""

from __future__ import annotations

import types
import typing
from dataclasses import dataclass
from datetime import date as Date
from typing import Any

from pydantic import BaseModel

from spc.api.schemas.almacen import EstadoInventarioItem
from spc.api.schemas.compras import ParametroReposicion
from spc.api.schemas.comunes import EJEMPLO_HISTORICO, HistoricoItem

# Tipos de conversión explícita célula → contrato (ver `lector.convertir_celda`).
Conversor = str  # uno de: "date" | "id" | "number" | "integer" | "boolean" | "enum"


# ---------------------------------------------------------------------------
# Inferencia del tipo de conversión y de los valores permitidos desde el modelo
# ---------------------------------------------------------------------------
def _sin_none(anotacion: Any) -> Any:
    """Quita ``None`` de una anotación opcional (``X | None`` → ``X``)."""
    origen = typing.get_origin(anotacion)
    if origen in (typing.Union, types.UnionType):
        partes = [a for a in typing.get_args(anotacion) if a is not type(None)]
        if len(partes) == 1:
            return partes[0]
    return anotacion


def _conversor(anotacion: Any) -> Conversor:
    """Decide cómo convertir la celda según el tipo del campo en el contrato.

    Excel entrega texto/decimales; cada campo se convierte al tipo exacto que el
    modelo ``strict`` exige (entero real, float, bool, fecha ISO o id de texto).
    """
    base = _sin_none(anotacion)
    if base is Date:
        return "date"
    if typing.get_origin(base) is typing.Literal:
        return "enum"  # p. ej. granularity: day/week/month
    if base is bool:
        return "boolean"
    if base is int:
        return "integer"
    if base is float:
        return "number"
    if base is str:
        return "id"  # store_id / product_id (número o texto → texto)
    return "enum"


def _valores_permitidos(anotacion: Any) -> tuple[str, ...]:
    """Valores admitidos (para la hoja de instrucciones): enums y booleanos."""
    base = _sin_none(anotacion)
    if typing.get_origin(base) is typing.Literal:
        return tuple(str(v) for v in typing.get_args(base))
    if base is bool:
        return ("true", "false")
    return ()


# ---------------------------------------------------------------------------
# Estructuras de la plantilla
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ColumnaExcel:
    """Una columna de una hoja, derivada de un campo del modelo del contrato."""

    nombre: str  # encabezado en inglés (nombre canónico del contrato)
    conversor: Conversor
    requerido: bool
    descripcion: str | None
    valores: tuple[str, ...] = ()


@dataclass(frozen=True)
class HojaExcel:
    """Una hoja de la plantilla.

    - ``es_lista=True``: cada fila es un ítem de una lista del contrato (`history`,
      `replenishment_params`, `inventory_status`); va a ``peticion[clave]``.
    - ``es_lista=False``: una sola fila de escalares que se **funden en la raíz** de la
      petición. Hoy ningún dominio la usa: la configuración escalar de SALES
      (`granularity`, `horizon`) viaja en la petición en pantalla, no en el archivo
      (ADR-0022). El mecanismo se conserva por si un dominio futuro lo necesita.
    """

    nombre: str
    es_lista: bool
    clave_peticion: str | None  # clave en la petición si es lista; None si se funde en raíz
    columnas: tuple[ColumnaExcel, ...]
    ejemplos: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class PlantillaDominio:
    """La plantilla de un dominio: el archivo y sus hojas (sin la de instrucciones)."""

    dominio: str  # "sales" | "purchases" | "inventory"
    archivo: str  # nombre del .xlsx descargable
    titulo: str  # título humano para la hoja de instrucciones
    hojas: tuple[HojaExcel, ...]


# ---------------------------------------------------------------------------
# Derivación de columnas desde un modelo Pydantic
# ---------------------------------------------------------------------------
def _columnas(modelo: type[BaseModel], *, excluir: tuple[str, ...] = ()) -> tuple[ColumnaExcel, ...]:
    """Deriva las columnas de una hoja desde los campos del modelo (en su orden)."""
    cols: list[ColumnaExcel] = []
    for nombre, info in modelo.model_fields.items():
        if nombre in excluir:
            continue
        cols.append(
            ColumnaExcel(
                nombre=nombre,
                conversor=_conversor(info.annotation),
                requerido=info.is_required(),
                descripcion=info.description,
                valores=_valores_permitidos(info.annotation),
            )
        )
    return tuple(cols)


def _hoja_history() -> HojaExcel:
    """Hoja del bloque común `history` (compartida por los tres dominios)."""
    return HojaExcel(
        nombre="history",
        es_lista=True,
        clave_peticion="history",
        columnas=_columnas(HistoricoItem),
        ejemplos=tuple(EJEMPLO_HISTORICO),
    )


# ---------------------------------------------------------------------------
# Las tres plantillas (derivadas del contrato)
# ---------------------------------------------------------------------------
PLANTILLAS: dict[str, PlantillaDominio] = {
    "sales": PlantillaDominio(
        dominio="sales",
        archivo="sales_template.xlsx",
        titulo="SALES — pronóstico de demanda",
        # Solo datos: la configuración (granularity/horizon) se envía desde la
        # petición en pantalla, no en el archivo (ADR-0022).
        hojas=(_hoja_history(),),
    ),
    "purchases": PlantillaDominio(
        dominio="purchases",
        archivo="purchases_template.xlsx",
        titulo="PURCHASES — reposición sugerida",
        hojas=(
            _hoja_history(),
            HojaExcel(
                nombre="replenishment_params",
                es_lista=True,
                clave_peticion="replenishment_params",
                columnas=_columnas(ParametroReposicion),
                ejemplos=(
                    {
                        "store_id": "1",
                        "product_id": "BEVERAGES",
                        "current_stock": 900,
                        "lead_time_days": 3,
                        "target_coverage_days": 7,
                    },
                ),
            ),
        ),
    ),
    "inventory": PlantillaDominio(
        dominio="inventory",
        archivo="inventory_template.xlsx",
        titulo="INVENTORY — riesgo de quiebre y stock recomendado",
        hojas=(
            _hoja_history(),
            HojaExcel(
                nombre="inventory_status",
                es_lista=True,
                clave_peticion="inventory_status",
                columnas=_columnas(EstadoInventarioItem),
                ejemplos=(
                    {
                        "store_id": "1",
                        "product_id": "BEVERAGES",
                        "current_stock": 300,
                        "lead_time_days": 3,
                    },
                ),
            ),
        ),
    ),
}

# Nombre de la hoja de ayuda (estructura en inglés; su contenido va en español).
HOJA_INSTRUCCIONES = "instructions"

# Dominios soportados por el canal Excel (orden estable).
DOMINIOS: tuple[str, ...] = tuple(PLANTILLAS.keys())


def plantilla_de(dominio: str) -> PlantillaDominio:
    """Devuelve la definición de plantilla de un dominio (``KeyError`` si no existe)."""
    return PLANTILLAS[dominio]


__all__ = [
    "ColumnaExcel",
    "HojaExcel",
    "PlantillaDominio",
    "PLANTILLAS",
    "DOMINIOS",
    "HOJA_INSTRUCCIONES",
    "plantilla_de",
]
