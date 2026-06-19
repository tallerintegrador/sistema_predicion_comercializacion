"""Router del **catálogo de predicciones** — ``GET /catalog`` (solo lectura).

Expone la "lista de servicios" del producto: por dominio, qué entra, qué sale y qué
limitaciones tiene, más la versión del contrato y la disponibilidad de canales/modos.
No toca el motor ni la lógica de negocio: solo describe lo que la API ya entrega hoy,
derivado de los esquemas reales (`spc.api.catalog`).
"""

from __future__ import annotations

from fastapi import APIRouter

from spc.api.catalog import construir_catalogo
from spc.api.schemas.catalog import CatalogResponse

router = APIRouter(tags=["catalog"])


@router.get(
    "/catalog",
    response_model=CatalogResponse,
    response_model_exclude_none=True,
    summary="Catálogo de predicciones por dominio",
    description=(
        "Devuelve, por dominio (sales/purchases/inventory), la descripción del servicio, "
        "sus **entradas**, sus **salidas reales** y sus **notas/limitaciones honestas**, "
        "junto con la versión del contrato vigente. Las entradas y salidas se derivan de "
        "los esquemas reales de cada endpoint, de modo que el catálogo no puede "
        "desincronizarse de lo que la API entrega."
    ),
)
def obtener_catalogo() -> CatalogResponse:
    """Construye y devuelve el catálogo de predicciones (solo lectura)."""
    return construir_catalogo()
