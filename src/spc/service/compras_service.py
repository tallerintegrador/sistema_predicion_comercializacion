"""Servicio de COMPRAS: reposición derivada del pronóstico (sin modelo propio).

COMPRAS no entrena nada: es **lógica de negocio**. Reutiliza el pronóstico diario
de VENTAS (`ventas_service.forecast_diario`) y lo combina con los parámetros
logísticos del cliente (`current_stock`, `lead_time_days`, `target_coverage_days`)
para derivar, por producto: la demanda esperada en la ventana, el punto de reorden
y la cantidad a reponer.

Política implementada (decidida con la validadora): **días de cobertura**. El stock
de seguridad es un porcentaje de la demanda durante el *lead time*. La política por
**nivel de servicio** (z-score sobre la variabilidad) queda diferida y documentada
en el ADR.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from spc.service import adaptador, ventas_service
from spc.service.artefactos import RegistroArtefactos
from spc.service.errores import SolicitudInvalida

# Stock de seguridad = este factor x demanda esperada durante el lead time. Es una
# CONSTANTE DE POLÍTICA DE NEGOCIO (no un valor de artefacto): un colchón del 30 %
# de la demanda del lead time. El cliente puede ajustar su política; SPC documenta
# el supuesto en la respuesta.
FACTOR_STOCK_SEGURIDAD = 0.30


def reponer(
    historico: Iterable[Mapping[str, Any]],
    parametros_reposicion: Iterable[Mapping[str, Any]],
    registro: RegistroArtefactos,
) -> dict[str, Any]:
    """Deriva la reposición y devuelve la respuesta del contrato de COMPRAS (como dict).

    Para cada producto de ``replenishment_params`` pronostica la demanda diaria sobre
    ``lead_time_days + target_coverage_days`` días y aplica la aritmética de
    inventario. Un producto que no aparezca en el histórico es un error de negocio
    (no se puede pronosticar sin historia) → ``SolicitudInvalida`` (HTTP 400).
    """
    parametros = list(parametros_reposicion)
    if not parametros:
        raise SolicitudInvalida("No se enviaron parámetros de reposición.")

    analitico = adaptador.historico_a_analitico(historico)
    disponibles = adaptador.series_disponibles(analitico)

    faltantes = [
        (str(p["store_id"]), str(p["product_id"]))
        for p in parametros
        if (str(p["store_id"]), str(p["product_id"])) not in disponibles
    ]
    if faltantes:
        detalle = ", ".join(f"({pv}, {prod})" for pv, prod in faltantes)
        raise SolicitudInvalida(
            "No hay histórico para estos productos, no se puede pronosticar su demanda: "
            f"{detalle}."
        )

    # Pronóstico diario hasta cubrir el horizonte más largo pedido (lead + cobertura).
    horizonte_max = max(int(p["lead_time_days"]) + int(p["target_coverage_days"]) for p in parametros)
    pred = ventas_service.forecast_diario(analitico, horizonte_max, registro.regresion)
    pred = pred.sort_values(["store_nbr", "family", "date"]).reset_index(drop=True)

    recomendacion: list[dict[str, Any]] = []
    for p in parametros:
        pv, prod = str(p["store_id"]), str(p["product_id"])
        lead = int(p["lead_time_days"])
        cobertura = int(p["target_coverage_days"])
        stock_actual = float(p["current_stock"])

        serie = pred[(pred["store_nbr"].astype(str) == pv) & (pred["family"].astype(str) == prod)]
        serie = serie.sort_values("date")
        demanda_diaria = serie["demanda_pronosticada"].to_numpy()

        demanda_lead = float(demanda_diaria[:lead].sum())
        demanda_horizonte = float(demanda_diaria[: lead + cobertura].sum())
        stock_seguridad = FACTOR_STOCK_SEGURIDAD * demanda_lead
        punto_reorden = demanda_lead + stock_seguridad
        cantidad = max(0.0, demanda_horizonte + stock_seguridad - stock_actual)

        recomendacion.append(
            {
                "store_id": pv,
                "product_id": prod,
                "expected_demand_horizon": round(demanda_horizonte, 2),
                "reorder_point": round(punto_reorden, 2),
                "replenishment_quantity": round(cantidad, 2),
                "justification": (
                    "forecast_demand(lead_time + coverage) + safety_stock "
                    "- current_stock"
                ),
            }
        )

    return {
        "field": "purchases",
        "recommendation": recomendacion,
        "metadata": {
            "assumption": (
                "stock de seguridad = "
                f"{FACTOR_STOCK_SEGURIDAD:.0%} de la demanda en lead time; demanda y "
                "lead time aproximados; revisar política del cliente"
            ),
            "policy": "coverage_days",
        },
    }
