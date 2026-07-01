"""Router del contrato **3×3 por dominio** (rediseño: un formato, tres modelos).

Tres endpoints bajo ``/v2`` (``/v2/ventas``, ``/v2/compras``, ``/v2/almacen``): el cliente
envía las filas en el **formato único** del dominio y recibe, en una sola respuesta, los
tres modelos —regresión, clasificación y clustering— **entrenados en el momento** con
scikit-learn liviano (lo que pidió el docente). Cada dominio expone además un endpoint
``/demo`` que corre sobre **datos sintéticos** del propio sistema, para verlo funcionar sin
tener que aportar datos.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from spc.api.schemas.auth import SessionUser
from spc.api.schemas.comunes import ErrorResponse
from spc.api.schemas.dominios_3x3 import Analisis3x3Request
from spc.api.seguridad import requiere
from spc.service import motor_3x3

router = APIRouter(prefix="/v2", tags=["3X3"])

_RESPUESTAS_ERR: dict[int | str, dict[str, Any]] = {
    400: {"model": ErrorResponse, "description": "Datos inválidos o insuficientes para entrenar"},
    422: {"model": ErrorResponse, "description": "Entrada mal formada"},
}

# Permiso por dominio (reusa el modelo de roles existente: sales/purchases/inventory).
_PERMISO = {
    "ventas": ("module:sales", "action:forecast"),
    "compras": ("module:purchases", "action:forecast"),
    "almacen": ("module:inventory", "action:forecast"),
}


# ---------------------------------------------------------------------------
# VENTAS
# ---------------------------------------------------------------------------
@router.post("/ventas", summary="Análisis 3×3 de VENTAS (regresión + clasificación + clustering)", responses=_RESPUESTAS_ERR)
def analizar_ventas(
    peticion: Analisis3x3Request,
    _auth: Annotated[SessionUser | None, Depends(requiere(*_PERMISO["ventas"]))],
) -> dict[str, Any]:
    """Entrena al vuelo y devuelve: pronóstico de ``unidades_vendidas``, alerta de
    ``demanda_alta`` por serie y segmento (clustering) por SKU."""
    return motor_3x3.analizar("ventas", peticion.rows, horizon=peticion.horizon)


@router.get("/ventas/demo", summary="Demo de VENTAS con datos sintéticos", responses=_RESPUESTAS_ERR)
def demo_ventas(
    _auth: Annotated[SessionUser | None, Depends(requiere(*_PERMISO["ventas"]))],
    horizon: Annotated[int, Query(gt=0, le=90)] = 14,
) -> dict[str, Any]:
    """Corre el análisis 3×3 sobre datos sintéticos de VENTAS (sin aportar datos)."""
    return motor_3x3.analizar_demo("ventas", horizon=horizon)


# ---------------------------------------------------------------------------
# COMPRAS
# ---------------------------------------------------------------------------
@router.post("/compras", summary="Análisis 3×3 de COMPRAS (regresión + clasificación + clustering)", responses=_RESPUESTAS_ERR)
def analizar_compras(
    peticion: Analisis3x3Request,
    _auth: Annotated[SessionUser | None, Depends(requiere(*_PERMISO["compras"]))],
) -> dict[str, Any]:
    """Entrena al vuelo y devuelve: pronóstico de ``cantidad_pedida``, alerta de
    ``entrega_con_retraso`` por serie y segmento de proveedor (clustering)."""
    return motor_3x3.analizar("compras", peticion.rows, horizon=peticion.horizon)


@router.get("/compras/demo", summary="Demo de COMPRAS con datos sintéticos", responses=_RESPUESTAS_ERR)
def demo_compras(
    _auth: Annotated[SessionUser | None, Depends(requiere(*_PERMISO["compras"]))],
    horizon: Annotated[int, Query(gt=0, le=90)] = 14,
) -> dict[str, Any]:
    """Corre el análisis 3×3 sobre datos sintéticos de COMPRAS."""
    return motor_3x3.analizar_demo("compras", horizon=horizon)


# ---------------------------------------------------------------------------
# ALMACÉN
# ---------------------------------------------------------------------------
@router.post("/almacen", summary="Análisis 3×3 de ALMACÉN (regresión + clasificación + clustering)", responses=_RESPUESTAS_ERR)
def analizar_almacen(
    peticion: Analisis3x3Request,
    _auth: Annotated[SessionUser | None, Depends(requiere(*_PERMISO["almacen"]))],
) -> dict[str, Any]:
    """Entrena al vuelo y devuelve: pronóstico de ``demanda_dia`` (demanda futura) con
    ``indicadores_inventario`` derivados (cobertura, punto de reposición, stock de
    seguridad), alerta de ``riesgo_quiebre`` por serie y segmento ABC (clustering) por SKU."""
    return motor_3x3.analizar("almacen", peticion.rows, horizon=peticion.horizon)


@router.get("/almacen/demo", summary="Demo de ALMACÉN con datos sintéticos", responses=_RESPUESTAS_ERR)
def demo_almacen(
    _auth: Annotated[SessionUser | None, Depends(requiere(*_PERMISO["almacen"]))],
    horizon: Annotated[int, Query(gt=0, le=90)] = 14,
) -> dict[str, Any]:
    """Corre el análisis 3×3 sobre datos sintéticos de ALMACÉN."""
    return motor_3x3.analizar_demo("almacen", horizon=horizon)
