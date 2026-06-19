"""Ruteo **en línea / por lote** según el número de filas (Fase 3.4).

Este módulo es la **única pieza que decide el modo de ejecución** y el **único hogar
del flujo de predicción** por dominio. Tanto el canal JSON (``POST /sales`` …) como
el canal Excel (``POST /{dominio}/excel``) convergen aquí con la **misma petición ya
validada**, de modo que la decisión en línea/lote es idéntica para ambos y no hay
lógica de predicción duplicada.

Regla (P6): la frontera se mide por ``len(history)`` y es configurable
(``SPC_ONLINE_MAX_ROWS``). Si el envío es chico, se procesa en línea (se devuelve el
dict → la API lo serializa como **200**). Si es grande, se acepta como trabajo por
lote y se devuelve **202** con un ``JobAccepted``.

**El lote llama exactamente al mismo ``procesar`` que el modo en línea** (opción A:
modelo congelado, sin reentrenar ni ajustar por cliente), así que el mismo dato por
ambos modos produce el **mismo resultado**. Lo único que cambia es *cuándo* y *dónde*
se ejecuta. El resultado del lote se serializa con el mismo ``response_model`` y
``exclude_none`` que usa la respuesta en línea, para que sea byte-equivalente.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from fastapi.responses import JSONResponse
from pydantic import BaseModel

from spc.api.jobs import GestorTrabajos
from spc.api.schemas.almacen import AlmacenResponse
from spc.api.schemas.compras import ComprasResponse
from spc.api.schemas.jobs import JobAccepted
from spc.api.schemas.ventas import VentasResponse
from spc.config import online_max_rows
from spc.service import almacen_service, compras_service, ventas_service
from spc.service.artefactos import RegistroArtefactos


# ---------------------------------------------------------------------------
# El flujo de predicción por dominio (el MISMO que usan en línea y lote)
# ---------------------------------------------------------------------------
def _procesar_sales(peticion: Any, registro: RegistroArtefactos) -> dict[str, Any]:
    return ventas_service.pronosticar(
        historico=[h.model_dump() for h in peticion.history],
        horizonte=peticion.horizon,
        granularidad=peticion.granularity,
        registro=registro,
    )


def _procesar_purchases(peticion: Any, registro: RegistroArtefactos) -> dict[str, Any]:
    return compras_service.reponer(
        historico=[h.model_dump() for h in peticion.history],
        parametros_reposicion=[p.model_dump() for p in peticion.replenishment_params],
        registro=registro,
    )


def _procesar_inventory(peticion: Any, registro: RegistroArtefactos) -> dict[str, Any]:
    return almacen_service.alertas(
        historico=[h.model_dump() for h in peticion.history],
        estado_inventario=[e.model_dump() for e in peticion.inventory_status],
        registro=registro,
    )


@dataclass(frozen=True)
class _DominioRuteo:
    """Cómo se procesa y se serializa un dominio (su flujo y su modelo de respuesta)."""

    procesar: Callable[[Any, RegistroArtefactos], dict[str, Any]]
    response_model: type[BaseModel]


_RUTEO: dict[str, _DominioRuteo] = {
    "sales": _DominioRuteo(_procesar_sales, VentasResponse),
    "purchases": _DominioRuteo(_procesar_purchases, ComprasResponse),
    "inventory": _DominioRuteo(_procesar_inventory, AlmacenResponse),
}


def contar_filas(peticion: Any) -> int:
    """Número de filas del envío = filas del bloque ``history`` (uniforme JSON/Excel)."""
    return len(peticion.history)


def responder_segun_volumen(
    dominio: str,
    peticion: Any,
    registro: RegistroArtefactos,
    jobs: GestorTrabajos,
) -> dict[str, Any] | JSONResponse:
    """Decide en línea vs. lote por ``len(history)`` y responde en consecuencia.

    - ``len(history) <= SPC_ONLINE_MAX_ROWS`` → procesa ahora y devuelve el **dict**
      del resultado (la API lo serializa con su ``response_model`` → **200**).
    - en caso contrario → crea un trabajo, lo encola y devuelve **202** con el
      ``JobAccepted`` (job_id + dónde consultar estado y resultado).
    """
    spec = _RUTEO[dominio]
    filas = contar_filas(peticion)

    if filas <= online_max_rows():
        # Modo en línea: comportamiento síncrono de siempre, intacto.
        return spec.procesar(peticion, registro)

    # Modo por lote: el MISMO flujo, ejecutado en segundo plano. La serialización
    # replica la del modo en línea (exclude_none, mode="json") para que el resultado
    # recuperado sea idéntico al que devolvería la petición síncrona.
    def trabajo() -> dict[str, Any]:
        crudo = spec.procesar(peticion, registro)
        modelo = spec.response_model.model_validate(crudo)
        return modelo.model_dump(mode="json", exclude_none=True)

    job = jobs.crear(domain=dominio, rows=filas)
    jobs.enviar(job.id, trabajo)
    acuse = JobAccepted(
        job_id=job.id,
        status=job.status,
        domain=dominio,
        rows=filas,
        status_url=f"/jobs/{job.id}",
        result_url=f"/jobs/{job.id}/result",
    )
    return JSONResponse(status_code=202, content=acuse.model_dump())
