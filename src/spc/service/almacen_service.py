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

from collections.abc import Iterable, Mapping
from typing import Any

import numpy as np
import pandas as pd

from spc import config
from spc.service import adaptador, politica
from spc.service.artefactos import ArtefactoCargado, RegistroArtefactos
from spc.service.errores import SolicitudInvalida

# Nivel del cuantil que define "demanda alta" (P75). Es **model-adjacent**: debe coincidir
# con el cuantil contra el que se entrenó el clasificador. [PENDIENTE] La metadata del
# artefacto aún NO lo expone como número (solo lo menciona en prosa en su campo
# "objetivo"); mientras tanto se usa este fallback documentado y se lee de
# meta["objetivo_cuantil"] en cuanto el equipo de modelado lo agregue (ver ADR-0010).
CUANTIL_DEMANDA_ALTA_FALLBACK = 0.75
META_CLAVE_CUANTIL = "objetivo_cuantil"


def _cuantil_demanda_alta(meta: Mapping[str, Any]) -> float:
    """Nivel del cuantil de "demanda alta", leído del meta del artefacto si lo expone.

    Igual que el ``umbral`` de probabilidad: se prefiere la metadata. [PENDIENTE /
    model-adjacent] Hoy la metadata del clasificador NO expone el nivel como número, así
    que cae al fallback documentado ``0.75``. En cuanto el artefacto exponga
    ``objetivo_cuantil`` (coordinación con el equipo de modelado), se leerá de ahí.
    """
    valor = meta.get(META_CLAVE_CUANTIL)
    if isinstance(valor, int | float) and not isinstance(valor, bool) and 0.0 < float(valor) < 1.0:
        return float(valor)
    return CUANTIL_DEMANDA_ALTA_FALLBACK


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
    analitico: pd.DataFrame, ventana: int
) -> dict[tuple[str, str], tuple[float, float]]:
    """Media y desviación de la demanda diaria reciente por serie (proxy de demanda).

    ``ventana`` es el nº de días recientes considerados (constante de política
    configurable, ``SPC_INVENTORY_DEMAND_WINDOW``).
    """
    proxy: dict[tuple[str, str], tuple[float, float]] = {}
    for (store, fam), g in analitico.groupby(["store_nbr", "family"], observed=True):
        ventas = g.sort_values("date")["sales"].to_numpy(dtype="float64")[-ventana:]
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

    # Política leída de config (defaults = comportamiento histórico; ADR-0010).
    metodo = config.inventory_safety_method()
    lead_default = config.inventory_lead_time_default()
    ventana = config.inventory_demand_window()
    z_base = config.inventory_z_base()
    z_alto = config.inventory_z_high_volume()
    factor_fallback = config.inventory_safety_fallback_factor()
    factor_cobertura = config.inventory_coverage_factor()
    cuantil = _cuantil_demanda_alta(registro.clasificacion.meta)

    clases = _clases_por_serie(analitico, registro.clasificacion)
    demanda = _demanda_reciente(analitico, ventana)
    analitico_da = adaptador.marcar_demanda_alta(analitico, cuantil)
    segmentos = _segmentos_por_tienda(analitico_da, registro.clustering_tiendas)
    seg_alto = _segmento_alto_volumen(registro.clustering_tiendas.meta)

    alertas_salida: list[dict[str, Any]] = []
    for it in items:
        pv, prod = str(it["store_id"]), str(it["product_id"])
        clave = (pv, prod)
        stock_actual = float(it["current_stock"])
        lead = int(it["lead_time_days"]) if it.get("lead_time_days") else lead_default

        clase, prob = clases[clave]
        media_diaria, std_diaria = demanda[clave]
        segmento = segmentos.get(pv, 0)

        demanda_lead = media_diaria * lead
        # Nivel de servicio afinado por el segmento (el de alto volumen, más exigente).
        z = z_alto if (seg_alto is not None and segmento == seg_alto) else z_base
        stock_seguridad = politica.stock_seguridad(
            metodo,
            demanda_lead=demanda_lead,
            lead=lead,
            factor_cobertura=factor_cobertura,
            z=z,
            sigma_diaria=std_diaria,
            factor_fallback=factor_fallback,
        )
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
    pct = int(round(cuantil * 100))
    return {
        "field": "inventory",
        "alerts": alertas_salida,
        "metadata": {
            "threshold": f"high_demand = sales > P{pct} of its family",
            # Umbral numérico de probabilidad (del meta del artefacto, no hard-codeado).
            "probability_threshold": round(float(umbral_prob), 4) if umbral_prob is not None else None,
        },
    }
