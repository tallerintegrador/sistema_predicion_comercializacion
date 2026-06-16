"""Manejo de errores de la capa API: traduce excepciones al contrato de error.

Toda salida de error usa el **mismo cuerpo** (`ErrorResponse`): nunca un 500 sin
manejar ni un volcado de pila. Mapea:

- Validación de entrada (Pydantic/FastAPI) → **422** con el detalle por campo.
- Reglas de negocio (`SolicitudInvalida`) → **400**.
- Motor no cargado (`ServicioNoDisponible`) → **503**.
- Cualquier error inesperado → **500** controlado (se registra en el log interno).
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from spc.api.schemas.comunes import CuerpoError, DetalleError, ErrorResponse
from spc.service.errores import SolicitudInvalida
from spc.utils.logging import get_logger

log = get_logger("api.errors")


class ServicioNoDisponible(RuntimeError):
    """El motor de ML aún no está cargado (arranque incompleto o fallido)."""


def _ruta_campo(loc: tuple[Any, ...]) -> str:
    """Convierte la ubicación de un error de Pydantic en una ruta legible.

    Quita el prefijo ``body`` y une el resto con puntos
    (p. ej. ``('body','history',0,'units_sold')`` → ``'history.0.units_sold'``).
    """
    partes = [str(p) for p in loc if p != "body"]
    return ".".join(partes) if partes else "(body)"


def _json_error(status: int, tipo: str, mensaje: str, detalles: list[DetalleError] | None = None) -> JSONResponse:
    cuerpo = ErrorResponse(error=CuerpoError(type=tipo, message=mensaje, details=detalles))
    return JSONResponse(status_code=status, content=cuerpo.model_dump())


async def _manejar_validacion(_: Request, exc: RequestValidationError) -> JSONResponse:
    """Entrada mal formada → 422 con el campo y el porqué de cada fallo."""
    detalles = [
        DetalleError(field=_ruta_campo(tuple(e.get("loc", ()))), problem=str(e.get("msg", "")))
        for e in exc.errors()
    ]
    return _json_error(
        422, "validation", "La entrada no cumple el contrato de datos.", detalles
    )


async def _manejar_solicitud_invalida(_: Request, exc: SolicitudInvalida) -> JSONResponse:
    """Regla de negocio incumplida → 400 con mensaje claro."""
    return _json_error(400, "invalid_request", str(exc))


async def _manejar_servicio_no_disponible(_: Request, exc: ServicioNoDisponible) -> JSONResponse:
    """Motor no cargado → 503."""
    return _json_error(503, "service_unavailable", str(exc))


async def _manejar_inesperado(_: Request, exc: Exception) -> JSONResponse:
    """Error inesperado → 500 controlado (sin filtrar detalles internos)."""
    log.exception("Error inesperado procesando la solicitud: %s", exc)
    return _json_error(
        500, "internal_error", "Ocurrió un error interno al procesar la solicitud."
    )


def registrar_manejadores(app: FastAPI) -> None:
    """Registra todos los manejadores de error en la app."""
    app.add_exception_handler(RequestValidationError, _manejar_validacion)
    app.add_exception_handler(SolicitudInvalida, _manejar_solicitud_invalida)
    app.add_exception_handler(ServicioNoDisponible, _manejar_servicio_no_disponible)
    app.add_exception_handler(Exception, _manejar_inesperado)
