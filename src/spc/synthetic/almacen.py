"""Generador sintético del dominio **ALMACÉN** (foto de stock).

Produce un DataFrame conforme a ``spc.synthetic.esquemas.ALMACEN``: una fila por
``(fecha, tienda, sku, día)`` con el estado de inventario. El stock sigue un patrón
de **diente de sierra** (consumo diario + reposiciones), de modo que aparecen casos
reales de cobertura baja y riesgo de quiebre.

Alimenta los tres modelos del dominio:
- **Regresión:** ``demanda_dia`` (demanda futura; ADR-0025 punto e). Antes se predecía
  ``dias_de_cobertura``, que es casi una fórmula (stock÷demanda) y no se "aprende"; ahora
  se predice el consumo diario, que sí tiene señal (estacionalidad semanal + ruido) y del
  que se derivan los KPIs de inventario (cobertura, punto de reposición, stock de seguridad).
- **Clasificación:** ``riesgo_quiebre`` (derivada: stock_actual < demanda × tiempo_reposicion).
- **Clustering:** análisis ABC de ``sku`` por rotación/volumen.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from spc.synthetic import comun
from spc.synthetic.esquemas import ALMACEN, validar_conforme


def generar(
    *,
    seed: int = 42,
    n_tiendas: int = 2,
    n_productos: int = 40,
    n_dias: int = 120,
    fecha_inicio: date = date(2023, 1, 1),
) -> pd.DataFrame:
    """Genera el dataset sintético de ALMACÉN (DataFrame conforme al esquema).

    Default ≈ 2 tiendas × 40 productos × 120 días ≈ 9.600 filas: tamaño de **la demo**.
    Prioriza la **variedad de PRODUCTOS** (40 SKUs para el análisis ABC del clustering)
    con POCAS tiendas a propósito, porque el pronóstico se calcula **serie por serie**
    (tienda×producto) y más tiendas solo harían la demo lenta sin enriquecer el
    clustering. Para experimentos **offline** (Fase 4), súbanse ``n_tiendas``/``n_dias``.
    """
    fechas = comun.fechas_dia(fecha_inicio, n_dias)
    catalogo = comun.productos(n_productos)
    n = len(fechas)
    filas: list[dict[str, object]] = []

    for t in range(1, n_tiendas + 1):
        id_tienda = f"T{t:02d}"
        rng_t = comun.rng_de(seed, 5, t)
        escala_tienda = comun.entre(rng_t, 0.7, 1.5)
        for p, (sku, categoria) in enumerate(catalogo):
            rng = comun.rng_de(seed, 6, t, p)
            demanda_media = comun.entre(rng, 5.0, 120.0) * escala_tienda
            amp_sem = comun.entre(rng, 0.15, 0.35)
            tiempo_repo = int(max(1, round(rng.normal(comun.entre(rng, 3.0, 12.0), 1.5))))
            zona = str(rng.choice(comun.ZONAS_ALMACEN))

            # Política de inventario: máximo cubre ~tiempo_repo+cobertura objetivo. Banda de
            # cobertura ESTRECHA (4-8 d) para que el stock se mueva en una franja acotada: así la
            # cobertura diaria (stock/demanda) deja de oscilar como diente de sierra amplio y se
            # vuelve predecible desde la identidad de serie (objetivo de alm-r2).
            cobertura_obj = comun.entre(rng, 4.0, 8.0)
            stock_max = demanda_media * (tiempo_repo + cobertura_obj)
            stock_min = demanda_media * tiempo_repo * comun.entre(rng, 0.9, 1.1)

            # Consumo diario (estacional, fin de semana, ruido) → diente de sierra.
            f_sem = comun.factor_estacional_semanal(fechas, amp_sem)
            # Ruido de consumo (σ=0.16): demanda diaria predecible con serie+calendario, pero con
            # error creíble (~0.13, en la banda 0.10-0.30) en vez de ~0.07 (demasiado bueno).
            consumo = np.maximum(0.0, demanda_media * f_sem * (1.0 + rng.normal(0.0, 0.16, n)))

            stock = stock_max  # arranca lleno
            stock_serie = np.empty(n, dtype="float64")
            demanda_prom_serie = np.empty(n, dtype="float64")
            ventana: list[float] = []
            for i in range(n):
                stock_serie[i] = stock
                ventana.append(float(consumo[i]))
                if len(ventana) > 28:
                    ventana.pop(0)
                demanda_prom_serie[i] = float(np.mean(ventana))
                stock = stock - consumo[i]
                # Reposición al tocar el mínimo. Realista (no siempre perfecta), para que las
                # alertas de inventario tengan casos que aprender:
                #  - a veces la entrega llega TARDE → el stock cae por debajo del mínimo (stockout).
                #  - a veces se SOBRE-PIDE → el stock supera el máximo (sobrestock).
                if stock <= stock_min:
                    # Reposición mayormente regular (banda acotada → cobertura predecible); se
                    # conservan pocos casos atípicos (tardía/sobre-pedido) para que la alerta de
                    # quiebre no quede sin ejemplos.
                    if rng.random() < 0.04:
                        pass  # reposición tardía: se deja caer bajo el mínimo unos días
                    elif rng.random() < 0.04:
                        stock = stock_max * comun.entre(rng, 1.05, 1.15)  # sobre-pedido
                    else:
                        stock = stock_max * comun.entre(rng, 0.97, 1.0)  # reposición normal
                stock = max(0.0, stock)

            demanda_prom_serie = np.maximum(0.1, demanda_prom_serie)
            dias_cobertura = stock_serie / demanda_prom_serie
            # Rotación anualizada aproximada: consumo medio / stock medio.
            stock_medio = max(1.0, float(np.mean(stock_serie)))
            rotacion = float(demanda_media * 365.0 / stock_medio)
            # Ruido por período en columnas de política (rotación, stock máximo): son casi
            # constantes por serie, así que sin variación el modelo las "adivina" (WAPE ~0). Con
            # dispersión σ=0.17 el error aterriza en un rango creíble (~0.13, en la banda 0.10-0.30).
            # Es ruido de reporte: la dinámica interna de stock usa los valores limpios.
            rot_ruido = 1.0 + rng.normal(0.0, 0.17, n)
            smax_ruido = 1.0 + rng.normal(0.0, 0.17, n)

            for i, f in enumerate(fechas):
                filas.append({
                    "fecha": f,
                    "id_tienda": id_tienda,
                    "sku": sku,
                    "categoria": categoria,
                    "stock_actual": round(float(stock_serie[i]), 2),
                    "stock_minimo": round(float(stock_min), 2),
                    "stock_maximo": round(float(stock_max * smax_ruido[i]), 2),
                    "demanda_dia": int(round(float(consumo[i]))),  # objetivo: unidades enteras consumidas ese día
                    "demanda_diaria_promedio": round(float(demanda_prom_serie[i]), 3),
                    "dias_de_cobertura": round(float(dias_cobertura[i]), 3),  # calculada
                    "rotacion": round(rotacion * rot_ruido[i], 3),
                    "tiempo_reposicion_dias": int(tiempo_repo),
                    "zona_almacen": zona,
                })

    df = pd.DataFrame(filas, columns=ALMACEN.orden)
    validar_conforme(df, "almacen")
    return df
