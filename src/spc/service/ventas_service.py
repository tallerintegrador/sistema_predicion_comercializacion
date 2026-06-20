"""Servicio de VENTAS: orquesta el pronóstico de demanda (regresión).

Traduce el histórico del contrato al dataset analítico (`adaptador`), llama al
**pronóstico recursivo multi-horizonte** del artefacto de regresión y devuelve la
demanda en unidades por ``(date, store_id, product_id)``. La granularidad
``week``/``month`` se obtiene **agregando** (sumando) el pronóstico diario.

No conoce el algoritmo: usa la interfaz estable `pronosticar_horizonte` del motor.
No conoce HTTP: recibe/devuelve estructuras de Python; la API hace el mapeo.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

import pandas as pd

from spc.service import adaptador
from spc.service.artefactos import ArtefactoCargado, RegistroArtefactos

# El meta del artefacto guarda la escala en español ("unidades"); el contrato de la
# API la expone en inglés. Normalizamos el valor conocido sin reentrenar el modelo.
_ESCALA_A_INGLES = {"unidades": "units"}


def forecast_diario(
    analitico: pd.DataFrame, horizonte: int, artefacto: ArtefactoCargado
) -> pd.DataFrame:
    """Pronóstico **diario** recursivo para ``horizonte`` días por serie.

    Devuelve un frame ``(date, store_nbr, family, demanda_pronosticada)``. Es la
    pieza reutilizable: VENTAS la agrega por granularidad y COMPRAS la usa para
    derivar la reposición. Construye el esqueleto futuro y delega en el motor.
    """
    completo, inicio, fin = adaptador.agregar_esqueleto_futuro(analitico, horizonte)
    pred = artefacto.objeto.pronosticar_horizonte(completo, inicio, fin)
    return pred


def _agregar_por_granularidad(pred: pd.DataFrame, granularidad: str) -> pd.DataFrame:
    """Agrega el pronóstico diario a ``week``/``month`` (suma); ``day`` lo deja igual.

    Para week/month, la ``date`` de salida es el **inicio del período** (lunes de la
    semana ISO; primer día del mes) y la demanda es la **suma** de los días del período.
    """
    if granularidad == "day":
        return pred
    fechas = pd.to_datetime(pred["date"])
    if granularidad == "week":
        periodo = fechas.dt.to_period("W").dt.start_time
    else:  # "month"
        periodo = fechas.dt.to_period("M").dt.start_time
    agregado = (
        pred.assign(date=periodo)
        .groupby(["store_nbr", "family", "date"], observed=True, as_index=False)[
            "demanda_pronosticada"
        ]
        .sum()
    )
    return agregado


def pronosticar(
    historico: Iterable[Mapping[str, Any]],
    horizonte: int,
    granularidad: str,
    registro: RegistroArtefactos,
    artefacto: ArtefactoCargado | None = None,
) -> dict[str, Any]:
    """Pronostica la demanda y devuelve la respuesta del contrato de VENTAS (como dict).

    El dict tiene exactamente la forma de ``VentasResponse``: ``field``, ``model``
    (versión leída del meta), ``forecast`` y ``metadata`` (escala y transformación
    interna, también del meta — nunca constantes en el código).

    ``artefacto`` permite servir un modelo de regresión **por cliente** ya adoptado
    (ADR-0013); si es ``None`` se usa el **congelado** (``registro.regresion``), el camino
    por defecto intacto. El ``model`` de la respuesta sale del meta del artefacto servido,
    de modo que refleja honestamente si se sirvió el congelado o el del cliente.
    """
    reg = artefacto or registro.regresion
    analitico = adaptador.historico_a_analitico(historico)
    pred = forecast_diario(analitico, horizonte, reg)
    pred = _agregar_por_granularidad(pred, granularidad)
    pred = pred.sort_values(["store_nbr", "family", "date"]).reset_index(drop=True)

    pronostico = [
        {
            "date": pd.Timestamp(row["date"]).date(),
            "store_id": str(row["store_nbr"]),
            "product_id": str(row["family"]),
            "forecast_demand": round(float(row["demanda_pronosticada"]), 2),
        }
        for _, row in pred.iterrows()
    ]

    meta = reg.meta
    escala = meta.get("escala_metricas", "units")
    return {
        "field": "sales",
        "model": meta.get("version", registro.regresion.ruta.stem),
        "forecast": pronostico,
        "metadata": {
            "scale": _ESCALA_A_INGLES.get(escala, escala),
            # Transformación que el motor aplica internamente (informativo, del meta).
            "internal_transform": meta.get("transformacion_objetivo", "log1p"),
        },
    }
