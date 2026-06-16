"""Servicio de ALMACEN: riesgo de quiebre y stock recomendado.

Ensambla tres piezas (sin conocer sus algoritmos):

1. **Clasificación** (`PredictorClasificacion`): clase de demanda (alta/baja) y su
   probabilidad. El **umbral** que separa alta/baja vive **dentro del artefacto**
   (``predictor.umbral``, ≈0.3185 recalibrado) — no se hard-codea aquí.
2. **Clustering de tiendas** (`PerfiladorClustering`): el ``store_segment`` que
   enriquece la respuesta y **afina la política de stock** (nivel de servicio).
3. **Proxy de demanda** del propio histórico (media/desviación diarias recientes)
   para dimensionar el stock recomendado y el de seguridad. ALMACÉN **no** usa la
   regresión (el contrato lo define como clasificación + perfilado).

No conoce HTTP: recibe/devuelve estructuras de Python.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from typing import Any

import numpy as np
import pandas as pd

from spc.service import adaptador
from spc.service.artefactos import ArtefactoCargado, RegistroArtefactos
from spc.service.errores import SolicitudInvalida

# Lead time por defecto si el cliente no lo envía (días). Constante de negocio.
LEAD_TIME_DEFAULT = 7
# Ventana reciente (días) para estimar la demanda diaria desde el histórico.
VENTANA_DEMANDA = 28
# Niveles de servicio (z) para el stock de seguridad. El segmento de **alto volumen**
# recibe un nivel de servicio más exigente (política afinada por el clustering).
Z_BASE = 1.28  # ~90 %
Z_ALTO_VOLUMEN = 1.65  # ~95 %
# Si no hay desviación (serie demasiado corta), el stock de seguridad cae a este
# porcentaje de la demanda en lead time. Constante de política, no de artefacto.
FACTOR_SEGURIDAD_FALLBACK = 0.5


def _segmento_alto_volumen(meta: Mapping[str, Any]) -> int | None:
    """Identifica el segmento de **mayor volumen** leyendo los centroides del meta.

    No se hard-codea "el segmento 1 es el grande": se lee de ``centroides_unidades``
    del artefacto de clustering y se toma el de mayor ``venta_media``. Si el meta no
    trae centroides, se devuelve ``None`` (no se modula el nivel de servicio).
    """
    centroides = meta.get("centroides_unidades")
    if not isinstance(centroides, Mapping) or not centroides:
        return None
    try:
        return int(
            max(centroides.items(), key=lambda kv: float(kv[1].get("venta_media", 0.0)))[0]
        )
    except (ValueError, AttributeError, TypeError):
        return None


def _clases_por_serie(
    analitico: pd.DataFrame, artefacto_clf: ArtefactoCargado
) -> dict[tuple[str, str], tuple[int, float]]:
    """Clase y probabilidad de demanda alta para la observación **más reciente** de cada serie.

    El clasificador predice por fila (con el umbral propio del artefacto). Se toma la
    última fila por serie ``(store_nbr, family)`` como régimen de demanda actual. La
    alineación es posicional: `construir_features` ordena por ``(store_nbr, family,
    date)`` igual que el adaptador y **no elimina filas**, así que la fila *i* de la
    predicción corresponde a la fila *i* del histórico ordenado.
    """
    pred = artefacto_clf.objeto.predecir(analitico)
    if len(pred) != len(analitico):  # invariante de alineación (no debería romperse)
        raise RuntimeError("La predicción de clasificación no alinea con el histórico.")
    base = analitico[["store_nbr", "family", "date"]].copy()
    base["clase"] = pred["clase_demanda_alta"].to_numpy()
    base["prob"] = pred["probabilidad_demanda_alta"].to_numpy()
    ultimas = base.groupby(["store_nbr", "family"], observed=True).tail(1)
    return {
        (str(r["store_nbr"]), str(r["family"])): (int(r["clase"]), float(r["prob"]))
        for _, r in ultimas.iterrows()
    }


def _demanda_reciente(
    analitico: pd.DataFrame,
) -> dict[tuple[str, str], tuple[float, float]]:
    """Media y desviación de la demanda diaria reciente por serie (proxy de demanda)."""
    proxy: dict[tuple[str, str], tuple[float, float]] = {}
    for (store, fam), g in analitico.groupby(["store_nbr", "family"], observed=True):
        ventas = g.sort_values("date")["sales"].to_numpy(dtype="float64")[-VENTANA_DEMANDA:]
        media = float(np.mean(ventas)) if len(ventas) else 0.0
        std = float(np.std(ventas, ddof=1)) if len(ventas) >= 2 else float("nan")
        proxy[(str(store), str(fam))] = (media, std)
    return proxy


def _segmentos_por_tienda(
    analitico_da: pd.DataFrame, artefacto_clu: ArtefactoCargado
) -> dict[str, int]:
    """Asigna a cada tienda del histórico su ``segmento`` (clustering de tiendas)."""
    perfil = artefacto_clu.objeto.perfilar(analitico_da)
    return {
        str(s): int(seg)
        for s, seg in zip(perfil["store_nbr"], perfil["segmento"], strict=True)
    }


def alertas(
    historico: Iterable[Mapping[str, Any]],
    estado_inventario: Iterable[Mapping[str, Any]],
    registro: RegistroArtefactos,
) -> dict[str, Any]:
    """Construye las alertas de ALMACÉN y devuelve la respuesta del contrato (como dict)."""
    items = list(estado_inventario)
    if not items:
        raise SolicitudInvalida("No se envió estado de inventario.")

    analitico = adaptador.historico_a_analitico(historico)
    disponibles = adaptador.series_disponibles(analitico)

    faltantes = [
        (str(it["store_id"]), str(it["product_id"]))
        for it in items
        if (str(it["store_id"]), str(it["product_id"])) not in disponibles
    ]
    if faltantes:
        detalle = ", ".join(f"({pv}, {prod})" for pv, prod in faltantes)
        raise SolicitudInvalida(
            "No hay histórico para estos productos, no se puede evaluar su demanda: "
            f"{detalle}."
        )

    clases = _clases_por_serie(analitico, registro.clasificacion)
    demanda = _demanda_reciente(analitico)
    analitico_da = adaptador.marcar_demanda_alta(analitico)
    segmentos = _segmentos_por_tienda(analitico_da, registro.clustering_tiendas)
    seg_alto = _segmento_alto_volumen(registro.clustering_tiendas.meta)

    alertas_salida: list[dict[str, Any]] = []
    for it in items:
        pv, prod = str(it["store_id"]), str(it["product_id"])
        clave = (pv, prod)
        stock_actual = float(it["current_stock"])
        lead = int(it["lead_time_days"]) if it.get("lead_time_days") else LEAD_TIME_DEFAULT

        clase, prob = clases[clave]
        media_diaria, std_diaria = demanda[clave]
        segmento = segmentos.get(pv, 0)

        demanda_lead = media_diaria * lead
        # Nivel de servicio afinado por el segmento (el de alto volumen, más exigente).
        z = Z_ALTO_VOLUMEN if (seg_alto is not None and segmento == seg_alto) else Z_BASE
        if math.isfinite(std_diaria) and std_diaria > 0:
            stock_seguridad = z * std_diaria * math.sqrt(lead)
        else:
            stock_seguridad = FACTOR_SEGURIDAD_FALLBACK * demanda_lead
        stock_recomendado = demanda_lead + stock_seguridad
        riesgo = bool(stock_actual < stock_recomendado)

        alertas_salida.append(
            {
                "store_id": pv,
                "product_id": prod,
                "demand_class": "high" if clase == 1 else "low",
                "high_demand_probability": round(prob, 4),
                "stockout_risk": riesgo,
                "recommended_stock": round(stock_recomendado, 2),
                "safety_stock": round(stock_seguridad, 2),
                "store_segment": segmento,
            }
        )

    meta_clf = registro.clasificacion.meta
    umbral_prob = meta_clf.get("umbral")
    return {
        "field": "inventory",
        "alerts": alertas_salida,
        "metadata": {
            "threshold": "high_demand = sales > P75 of its family",
            # Umbral numérico de probabilidad (del meta del artefacto, no hard-codeado).
            "probability_threshold": round(float(umbral_prob), 4) if umbral_prob is not None else None,
        },
    }
