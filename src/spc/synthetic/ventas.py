"""Generador sintético del dominio **VENTAS** (reemplaza Favorita).

Produce un DataFrame conforme a ``spc.synthetic.esquemas.VENTAS``: una fila por
``(fecha, tienda, sku, día)`` con demanda realista (nivel, tendencia, estacionalidad
semanal/anual, promociones y efecto de cercanía a feriado). Reproducible por semilla.

Alimenta los tres modelos del dominio:
- **Regresión:** ``unidades_vendidas``.
- **Clasificación:** ``demanda_alta`` (derivada: unidades > P75 de su categoría, train-only).
- **Clustering:** segmenta ``sku`` por volumen/variabilidad.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from spc.synthetic import comun
from spc.synthetic.esquemas import VENTAS, validar_conforme


def generar(
    *,
    seed: int = 42,
    n_tiendas: int = 2,
    n_productos: int = 40,
    n_dias: int = 120,
    fecha_inicio: date = date(2023, 1, 1),
) -> pd.DataFrame:
    """Genera el dataset sintético de VENTAS (DataFrame conforme al esquema).

    El default (2 tiendas × 40 productos × 120 días ≈ 9.600 filas) es el tamaño de
    **la demo**: prioriza la **variedad de PRODUCTOS** (40 SKUs distintos) —que es lo
    que hace creíble el clustering (agrupa SKUs) y la clasificación— y mantiene POCAS
    tiendas a propósito. Motivo (medido): el pronóstico se calcula **serie por serie**
    (tienda×producto), así que el tiempo de la demo crece con el nº de series, no con
    los productos del clustering; más tiendas solo la harían lenta sin mejorar el
    clustering. Para experimentos **offline** sin límite de tiempo (Fase 4), súbanse
    ``n_tiendas``/``n_dias`` desde el llamador.
    """
    fechas = comun.fechas_dia(fecha_inicio, n_dias)
    finde = comun.es_fin_de_semana(fechas)
    dias_feriado = comun.dias_a_proximo_feriado(fechas)
    catalogo = comun.productos(n_productos)
    filas: list[dict[str, object]] = []

    for t in range(1, n_tiendas + 1):
        id_tienda = f"T{t:02d}"
        # Cada tienda tiene un tamaño relativo (multiplica el nivel base).
        rng_t = comun.rng_de(seed, 1, t)
        escala_tienda = comun.entre(rng_t, 0.6, 1.6)
        for p, (sku, categoria) in enumerate(catalogo):
            rng = comun.rng_de(seed, 2, t, p)
            nivel = comun.entre(rng, 20.0, 220.0) * escala_tienda
            tendencia = comun.entre(rng, -0.10, 0.35)
            amp_sem = comun.entre(rng, 0.3, 0.8)
            amp_anu = comun.entre(rng, 0.10, 0.30)
            fase = float(rng.uniform(0, 2 * np.pi))
            ruido = comun.entre(rng, 0.05, 0.18)
            precio_base = comun.entre(rng, 1.5, 35.0)
            prob_promo = comun.entre(rng, 0.05, 0.25)
            # Cercanía a feriado: a menos días, más empuje (hasta +25% al borde).
            empuje_feriado = np.clip(1.0 + 0.25 * (1.0 - dias_feriado / 30.0), 1.0, 1.25)

            n = len(fechas)
            t_idx = np.arange(n, dtype="float64")
            f_tend = 1.0 + tendencia * (t_idx / max(1, n - 1))
            f_sem = comun.factor_estacional_semanal(fechas, amp_sem)
            f_anu = comun.factor_estacional_anual(fechas, amp_anu, fase)
            f_ruido = 1.0 + rng.normal(0.0, ruido, n)

            en_promo = (rng.random(n) < prob_promo).astype("int64")
            descuento = np.where(en_promo == 1, rng.uniform(5.0, 35.0, n), 0.0)
            boost_promo = 1.0 + (descuento / 100.0) * comun.entre(rng, 1.5, 3.0)

            demanda = nivel * f_tend * f_sem * f_anu * f_ruido * empuje_feriado * boost_promo
            demanda = np.maximum(0.0, np.round(demanda)).astype("float64")

            # Precio con leve dispersión diaria; baja un poco en promoción.
            precio = precio_base * (1.0 - descuento / 100.0 * 0.5)
            precio = np.round(precio + rng.normal(0.0, 0.05 * precio_base, n), 2)
            precio = np.maximum(0.1, precio)

            metodo = rng.choice(comun.METODOS_PAGO, n)
            canal = rng.choice(comun.CANALES_VENTA, n, p=[0.8, 0.2])

            for i, f in enumerate(fechas):
                u = float(demanda[i])
                pr = float(precio[i])
                filas.append({
                    "fecha": f,
                    "id_tienda": id_tienda,
                    "sku": sku,
                    "categoria": categoria,
                    "unidades_vendidas": u,
                    "precio_unitario": pr,
                    "ingreso": round(u * pr, 2),  # columna calculada
                    "en_promocion": int(en_promo[i]),
                    "descuento_pct": round(float(descuento[i]), 2),
                    "metodo_pago": str(metodo[i]),
                    "canal_venta": str(canal[i]),
                    "es_fin_de_semana": int(finde[i]),
                    "dias_a_proximo_feriado": int(dias_feriado[i]),
                })

    df = pd.DataFrame(filas, columns=VENTAS.orden)
    validar_conforme(df, "ventas")
    return df
