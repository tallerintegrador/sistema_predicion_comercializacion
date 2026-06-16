"""Piezas compartidas del contrato: bloque `historico` y esquema de error.

VENTAS, COMPRAS y ALMACEN **reutilizan el mismo bloque `historico`** (seccion 1
del contrato), de modo que el cliente integra una sola vez. Aqui vive ese bloque
(`HistoricoItem`), los tipos auxiliares (identificadores que admiten str/int) y el
**esquema de error unico** (`ErrorResponse`) que devuelve toda la API ante una
entrada mal formada o una regla de negocio incumplida.
"""

from __future__ import annotations

from datetime import date as Date
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field


# ---------------------------------------------------------------------------
# Tipo auxiliar: identificador del contrato (admite str o int -> normaliza a str)
# ---------------------------------------------------------------------------
def _a_id_contrato(valor: Any) -> Any:
    """Normaliza un identificador a ``str``.

    El contrato declara ``store_id`` como ``str/int``: el cliente puede
    enviar ``1`` o ``"1"`` y deben tratarse igual. Convertimos enteros a texto
    aqui (antes de validar el tipo) para que el resto de la API trabaje siempre
    con ``str``. Los ``bool`` se dejan pasar tal cual para que la validacion de
    tipo los rechace (``True`` no es un identificador valido).
    """
    if isinstance(valor, bool):
        return valor
    if isinstance(valor, int):
        return str(valor)
    return valor


# Identificador generico del contrato: acepta str/int, normaliza a str no vacio.
IdContrato = Annotated[str, BeforeValidator(_a_id_contrato), Field(min_length=1)]


# ---------------------------------------------------------------------------
# Bloque `historico` compartido (seccion 2 del contrato)
# ---------------------------------------------------------------------------
class HistoricoItem(BaseModel):
    """Una observacion del histórico de una serie ``(date, store_id, product_id)``.

    Campos minimos: ``date``, ``store_id``, ``product_id`` y ``units_sold``.
    ``on_promotion`` y ``transactions`` mejoran la señal (corr ~0.43 y ~0.23 segun
    el EDA) pero son opcionales; ``event_active`` marca un feriado/evento relevante.
    Los campos opcionales ausentes **degradan con elegancia** (el motor usa lo que
    tenga).
    """

    model_config = ConfigDict(extra="forbid")

    date: Date = Field(description="Fecha de la observación (ISO YYYY-MM-DD).")
    store_id: IdContrato = Field(description="Local, tienda o sucursal.")
    product_id: IdContrato = Field(description="Producto o familia/categoría.")
    units_sold: float = Field(
        ge=0, description="Demanda observada (unidades, ≥ 0)."
    )
    on_promotion: int = Field(
        default=0, ge=0, description="Ítems en promoción (0 si no aplica)."
    )
    transactions: float | None = Field(
        default=None, ge=0, description="Flujo de clientes/tickets (opcional)."
    )
    event_active: bool | None = Field(
        default=None, description="Feriado/evento relevante (opcional)."
    )


# Ejemplo de bloque `history` reutilizado en los ejemplos de Swagger de cada
# dominio (coincide con la seccion 3 del contrato).
EJEMPLO_HISTORICO: list[dict[str, Any]] = [
    {
        "date": "2017-08-01",
        "store_id": "1",
        "product_id": "BEVERAGES",
        "units_sold": 1820,
        "on_promotion": 5,
        "transactions": 1543,
    },
    {
        "date": "2017-08-02",
        "store_id": "1",
        "product_id": "BEVERAGES",
        "units_sold": 1675,
        "on_promotion": 0,
        "transactions": 1490,
    },
]


# ---------------------------------------------------------------------------
# Esquema de error unico (seccion 6 del contrato)
# ---------------------------------------------------------------------------
class DetalleError(BaseModel):
    """Detalle por campo de un error de validación (qué campo falló y por qué)."""

    field: str = Field(description="Ruta del campo que falló (p. ej. 'history.0.units_sold').")
    problem: str = Field(description="Descripción legible del problema.")


class CuerpoError(BaseModel):
    """Cuerpo del error: tipo, mensaje claro y detalles opcionales por campo."""

    type: str = Field(description="Categoría del error (p. ej. 'validation', 'invalid_request').")
    message: str = Field(description="Mensaje claro y accionable para el cliente.")
    details: list[DetalleError] | None = Field(
        default=None, description="Lista de problemas por campo (si aplica)."
    )


class ErrorResponse(BaseModel):
    """Respuesta de error controlada y uniforme para toda la API.

    Una entrada mal formada (tipo inválido, campo faltante, rango fuera de límite)
    o una regla de negocio incumplida devuelven **este** cuerpo, nunca un 500 sin
    manejar ni un volcado de pila.
    """

    error: CuerpoError

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "error": {
                    "type": "validation",
                    "message": "La entrada no cumple el contrato de datos.",
                    "details": [
                        {
                            "field": "history.0.units_sold",
                            "problem": "Input should be greater than or equal to 0",
                        }
                    ],
                }
            }
        }
    )
