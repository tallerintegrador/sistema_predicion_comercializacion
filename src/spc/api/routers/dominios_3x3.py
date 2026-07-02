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

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile

from spc.api.dependencies import (
    obtener_client_id,
    obtener_corpus,
    obtener_corpus_opcional,
    obtener_modelos,
)
from spc.api.errors import AccesoDenegado
from spc.api.ingest import dominios_excel
from spc.api.schemas.auth import SessionUser
from spc.api.schemas.comunes import ErrorResponse
from spc.api.schemas.dominios_3x3 import Analisis3x3Request
from spc.api.seguridad import requiere, usuario_requerido
from spc.config import auth_enabled, excel_max_bytes
from spc.service import motor_3x3, onboarding, reentrenamiento
from spc.service.errores import SolicitudInvalida
from spc.service.repositorio_corpus import RepositorioCorpus
from spc.service.repositorio_modelos import RepositorioModelos

router = APIRouter(prefix="/v2", tags=["3X3"])

ClientIdDep = Annotated[str, Depends(obtener_client_id)]
CorpusOpcDep = Annotated[RepositorioCorpus | None, Depends(obtener_corpus_opcional)]
CorpusDep = Annotated[RepositorioCorpus, Depends(obtener_corpus)]
ModelosDep = Annotated[RepositorioModelos, Depends(obtener_modelos)]

_RESPUESTAS_ERR: dict[int | str, dict[str, Any]] = {
    400: {"model": ErrorResponse, "description": "Datos inválidos o insuficientes para entrenar"},
    422: {"model": ErrorResponse, "description": "Entrada mal formada"},
}
_XLSX_MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

# Permiso por dominio (reusa el modelo de roles existente: sales/purchases/inventory).
_PERMISO = {
    "ventas": ("module:sales", "action:forecast"),
    "compras": ("module:purchases", "action:forecast"),
    "almacen": ("module:inventory", "action:forecast"),
}


def _acceso_dominio(
    dominio: str,
    sesion: Annotated[SessionUser | None, Depends(usuario_requerido)],
) -> SessionUser | None:
    """Permiso del dominio leído de la URL (evita repetir un endpoint por dominio).

    Valida el dominio y exige su permiso de módulo + ``action:forecast`` (igual que los
    endpoints por dominio). Con el control de acceso inactivo, deja pasar.
    """
    if dominio not in _PERMISO:
        raise SolicitudInvalida(f"Dominio desconocido: {dominio!r}. Use ventas, compras o almacen.")
    if not auth_enabled():
        return None
    assert sesion is not None  # usuario_requerido ya garantizó la sesión
    faltantes = set(_PERMISO[dominio]) - set(sesion.permissions)
    if faltantes:
        raise AccesoDenegado(
            "Su rol no tiene permiso para esta acción: " + ", ".join(sorted(faltantes)) + "."
        )
    return sesion


# ---------------------------------------------------------------------------
# VENTAS
# ---------------------------------------------------------------------------
@router.post("/ventas", summary="Análisis 3×3 de VENTAS (regresión + clasificación + clustering)", responses=_RESPUESTAS_ERR)
def analizar_ventas(
    peticion: Analisis3x3Request,
    _auth: Annotated[SessionUser | None, Depends(requiere(*_PERMISO["ventas"]))],
    client_id: ClientIdDep,
    corpus: CorpusOpcDep,
) -> dict[str, Any]:
    """Entrena al vuelo y devuelve: pronóstico de ``unidades_vendidas``, alerta de
    ``demanda_alta`` por serie y segmento (clustering) por SKU."""
    reentrenamiento.acumular(corpus, tenant_id=client_id, dominio="ventas", rows=peticion.rows, channel="json")
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
    client_id: ClientIdDep,
    corpus: CorpusOpcDep,
) -> dict[str, Any]:
    """Entrena al vuelo y devuelve: pronóstico de ``cantidad_pedida``, alerta de
    ``entrega_con_retraso`` por serie y segmento de proveedor (clustering)."""
    reentrenamiento.acumular(corpus, tenant_id=client_id, dominio="compras", rows=peticion.rows, channel="json")
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
    client_id: ClientIdDep,
    corpus: CorpusOpcDep,
) -> dict[str, Any]:
    """Entrena al vuelo y devuelve: pronóstico de ``demanda_dia`` (demanda futura) con
    ``indicadores_inventario`` derivados (cobertura, punto de reposición, stock de
    seguridad), alerta de ``riesgo_quiebre`` por serie y segmento ABC (clustering) por SKU."""
    reentrenamiento.acumular(corpus, tenant_id=client_id, dominio="almacen", rows=peticion.rows, channel="json")
    return motor_3x3.analizar("almacen", peticion.rows, horizon=peticion.horizon)


@router.get("/almacen/demo", summary="Demo de ALMACÉN con datos sintéticos", responses=_RESPUESTAS_ERR)
def demo_almacen(
    _auth: Annotated[SessionUser | None, Depends(requiere(*_PERMISO["almacen"]))],
    horizon: Annotated[int, Query(gt=0, le=90)] = 14,
) -> dict[str, Any]:
    """Corre el análisis 3×3 sobre datos sintéticos de ALMACÉN."""
    return motor_3x3.analizar_demo("almacen", horizon=horizon)


# ---------------------------------------------------------------------------
# ONBOARDING: diccionario de variables, plantillas/ejemplos y carga por Excel
# (un solo endpoint por función usando {dominio} en la URL)
# ---------------------------------------------------------------------------
@router.get(
    "/{dominio}/esquema",
    summary="Diccionario de variables del dominio (qué datos pedir y qué se predice)",
    responses=_RESPUESTAS_ERR,
)
def esquema_dominio(
    dominio: str,
    _auth: Annotated[SessionUser | None, Depends(_acceso_dominio)],
) -> dict[str, Any]:
    """Devuelve, en lenguaje simple, las columnas que pide el dominio (con ejemplo) y qué
    predice cada uno de los tres modelos. Es la fuente para mostrar el catálogo de
    variables en la interfaz, sin tecnicismos."""
    return onboarding.diccionario_de(dominio)


@router.get(
    "/{dominio}/plantilla",
    summary="Descargar plantilla vacía o ejemplo con datos, en Excel o JSON",
    responses=_RESPUESTAS_ERR,
)
def plantilla_dominio(
    dominio: str,
    _auth: Annotated[SessionUser | None, Depends(_acceso_dominio)],
    formato: Annotated[str, Query(pattern="^(excel|json)$", description="excel | json")] = "excel",
    contenido: Annotated[str, Query(pattern="^(basica|rica)$", description="basica (pocas filas de muestra) | rica (datos ricos listos para subir)")] = "basica",
):
    """Entrega el formato del dominio listo para llenar/subir:

    - ``contenido=basica`` → pocas filas de muestra (para ver el formato).
    - ``contenido=rica`` → un conjunto **rico** y realista, listo para subir tal cual.
    - ``formato=excel`` → archivo ``.xlsx`` (con hoja de instrucciones); ``formato=json`` →
      cuerpo JSON ``{rows, horizon}`` listo para el POST.
    """
    ricas = contenido == "rica"
    filas = onboarding.filas_ejemplo(dominio, ricas=ricas)
    if formato == "json":
        return {"rows": filas, "horizon": 14}
    etiqueta = "ejemplo" if ricas else "plantilla"
    xlsx = dominios_excel.generar_excel(dominio, filas)
    return Response(
        content=xlsx,
        media_type=_XLSX_MEDIA,
        headers={"Content-Disposition": f'attachment; filename="{etiqueta}_{dominio}.xlsx"'},
    )


@router.post(
    "/{dominio}/excel",
    summary="Subir un Excel con tus datos y correr el análisis 3×3",
    responses=_RESPUESTAS_ERR,
)
async def analizar_excel(
    dominio: str,
    _auth: Annotated[SessionUser | None, Depends(_acceso_dominio)],
    archivo: Annotated[UploadFile, File(description="Archivo .xlsx en el formato del dominio")],
    client_id: ClientIdDep,
    corpus: CorpusOpcDep,
    horizon: Annotated[int, Query(gt=0, le=90)] = 14,
) -> dict[str, Any]:
    """Lee las filas del ``.xlsx`` (misma cabecera que la plantilla) y devuelve los tres
    modelos entrenados al momento. Es la vía **amigable** para una PYME: subir un Excel en
    vez de pegar JSON."""
    tope = excel_max_bytes()
    datos = await archivo.read(tope + 1)
    if len(datos) > tope:
        raise SolicitudInvalida(
            f"El archivo supera el tamaño máximo permitido ({tope / (1024 * 1024):.0f} MB)."
        )
    filas = dominios_excel.leer_excel(datos, dominio)
    reentrenamiento.acumular(corpus, tenant_id=client_id, dominio=dominio, rows=filas, channel="excel")
    return motor_3x3.analizar(dominio, filas, horizon=horizon)


# ---------------------------------------------------------------------------
# REENTRENAMIENTO y REGISTRO DE MODELOS (ADR-0026)
# ---------------------------------------------------------------------------
@router.post(
    "/{dominio}/entrenar",
    summary="Reentrenar el modelo del dominio con TODO el histórico acumulado + lo nuevo",
    responses=_RESPUESTAS_ERR,
)
def entrenar_dominio(
    dominio: str,
    _auth: Annotated[SessionUser | None, Depends(_acceso_dominio)],
    client_id: ClientIdDep,
    corpus: CorpusDep,
    modelos: ModelosDep,
    horizon: Annotated[int, Query(gt=0, le=90)] = 14,
) -> dict[str, Any]:
    """Carga **todo** el corpus acumulado del cliente para el dominio (históricos + datos
    recién subidos), reentrena los tres modelos sobre ese conjunto completo, versiona cada
    uno en el registro (con sus métricas y el artefacto en Storage) y lo marca como el que
    se sirve. Devuelve el resumen del reentrenamiento (filas, versiones, métricas)."""
    try:
        return reentrenamiento.reentrenar(
            corpus, modelos, tenant_id=client_id, dominio=dominio, horizon=horizon
        )
    except ValueError as exc:
        raise SolicitudInvalida(str(exc)) from exc


@router.get(
    "/{dominio}/modelos",
    summary="Listar las versiones de modelos entrenadas del cliente para el dominio",
    responses=_RESPUESTAS_ERR,
)
def listar_modelos_dominio(
    dominio: str,
    _auth: Annotated[SessionUser | None, Depends(_acceso_dominio)],
    client_id: ClientIdDep,
    modelos: ModelosDep,
) -> dict[str, Any]:
    """Registro de modelos del cliente para el dominio: versión, tarea, algoritmo, métricas
    y cuál se está sirviendo. Es la fuente para mostrar el historial en la interfaz."""
    versiones = modelos.listar(client_id, dominio)
    return {
        "dominio": dominio,
        "modelos": [
            {
                "id": v.id,
                "task": v.task,
                "version": v.version,
                "algorithm": v.algorithm,
                "metrics": v.metrics,
                "status": v.status,
                "is_serving": v.is_serving,
                "trained_rows": v.trained_rows,
                "trained_at": v.trained_at,
            }
            for v in versiones
        ],
    }
