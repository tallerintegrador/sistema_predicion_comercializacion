"""Generador sintético del dominio **COMPRAS** (esquema propio de órdenes).

Produce un DataFrame conforme a ``spc.synthetic.esquemas.COMPRAS``: una fila por
``(fecha_orden, proveedor, sku)``. A diferencia de ventas/almacén, el grano es la
**orden de compra**, no el día calendario.

El realismo clave está en el **perfil del proveedor** (costo, lead time medio,
cumplimiento), porque de ahí salen las tres señales:
- **Regresión:** ``cantidad_pedida`` (planificación de compra).
- **Clasificación:** ``entrega_con_retraso`` (derivada: lead_time > P75, train-only).
- **Clustering:** agrupa ``id_proveedor`` por costo/lead time/cumplimiento.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd

from spc.synthetic import comun
from spc.synthetic.esquemas import COMPRAS, validar_conforme


@dataclass(frozen=True)
class PerfilProveedor:
    """Perfil de un proveedor concreto: costo, lead time y cumplimiento típicos.

    ADR-0025 (c): antes había **3 arquetipos fijos** (premium/estándar/económico) y el
    clustering "descubría" esas mismas 3 cajas — validación **circular**. Ahora cada
    proveedor se muestrea desde **rangos continuos** a lo largo de un eje latente de
    "calidad de servicio" con **ruido/solape moderado** (ver ``_perfil_continuo``), de modo
    que el nº de grupos **emerge** de los datos y no está impuesto de fábrica.
    """

    nombre: str
    factor_costo: float       # multiplicador del precio de compra
    lead_medio: float         # días promedio de entrega
    lead_sigma: float         # variabilidad del lead time
    cumplimiento_medio: float  # fracción recibida/pedida típica (≤1)


def _perfil_continuo(rng: np.random.Generator, pv: int) -> PerfilProveedor:
    """Muestrea un proveedor desde un **continuo** con solape (reemplaza los 3 arquetipos).

    Se parte de un ``q`` latente en [0,1] ("calidad": alto = rápido, caro, confiable) que
    correlaciona lead time, costo y cumplimiento —una estructura latente que **sabemos que
    existe**—, pero se le añade **ruido** a cada dimensión para que los grupos se **solapen**
    y no formen cajas nítidas. El lead time conserva un rango amplio (~3–20 días) para que la
    clasificación de "entrega con retraso" siga teniendo señal.
    """
    q = float(rng.uniform(0.0, 1.0))
    lead_medio = float(np.clip(np.interp(q, [0.0, 1.0], [19.0, 4.0]) + rng.normal(0.0, 2.6), 2.0, 24.0))
    factor_costo = float(np.clip(np.interp(q, [0.0, 1.0], [0.80, 1.28]) + rng.normal(0.0, 0.07), 0.70, 1.40))
    cumpl_medio = float(np.clip(np.interp(q, [0.0, 1.0], [0.86, 0.99]) + rng.normal(0.0, 0.02), 0.60, 1.0))
    lead_sigma = float(np.clip(0.25 * lead_medio + rng.uniform(0.0, 1.5), 1.0, 6.0))
    return PerfilProveedor(f"prov-{pv:02d}", factor_costo, lead_medio, lead_sigma, cumpl_medio)


def generar(
    *,
    seed: int = 42,
    n_proveedores: int = 20,
    n_productos: int = 4,
    n_ordenes_por_serie: int = 24,
    fecha_inicio: date = date(2023, 1, 1),
    dias_entre_ordenes: int = 10,
) -> pd.DataFrame:
    """Genera el dataset sintético de COMPRAS (DataFrame conforme al esquema).

    Default ≈ 20 proveedores × 4 productos × 24 órdenes ≈ 1.920 filas: tamaño de **la
    demo**. Prioriza la **variedad de PROVEEDORES** (20 entidades, que es lo que agrupa
    el clustering de compras) con POCOS productos a propósito: el pronóstico se calcula
    **serie por serie** (proveedor×producto), así que muchos productos solo harían la
    demo lenta sin enriquecer el clustering de proveedores. Para experimentos
    **offline** (Fase 4), súbanse ``n_productos``/``n_ordenes_por_serie``.
    """
    catalogo = comun.productos(n_productos)
    filas: list[dict[str, object]] = []

    for pv in range(1, n_proveedores + 1):
        id_proveedor = f"PROV-{pv:02d}"
        rng_pv = comun.rng_de(seed, 3, pv)
        # Proveedor muestreado desde el continuo (con solape): sus costo/lead/cumplimiento.
        perfil = _perfil_continuo(rng_pv, pv)
        lead_medio = perfil.lead_medio
        cumpl_medio = perfil.cumplimiento_medio

        for p, (sku, categoria) in enumerate(catalogo):
            rng = comun.rng_de(seed, 4, pv, p)
            base_pedido = comun.entre(rng, 80.0, 900.0)
            tendencia = comun.entre(rng, -0.05, 0.20)
            precio_base = comun.entre(rng, 1.0, 28.0) * perfil.factor_costo

            f0 = fecha_inicio
            for o in range(n_ordenes_por_serie):
                fecha_orden = f0 + timedelta(days=o * dias_entre_ordenes)
                frac = o / max(1, n_ordenes_por_serie - 1)
                cantidad = base_pedido * (1.0 + tendencia * frac) * comun.entre(rng, 0.8, 1.2)
                cantidad = float(max(1.0, round(cantidad)))

                precio = round(precio_base * comun.entre(rng, 0.95, 1.08), 2)
                descuento_volumen = round(min(15.0, cantidad / 100.0) * comun.entre(rng, 0.5, 1.0), 2)

                lead = int(max(1, round(rng.normal(lead_medio, perfil.lead_sigma))))
                cumplimiento = float(np.clip(rng.normal(cumpl_medio, 0.04), 0.5, 1.0))
                recibida = float(round(cantidad * cumplimiento))

                filas.append({
                    "fecha_orden": fecha_orden,
                    "id_proveedor": id_proveedor,
                    "sku": sku,
                    "categoria": categoria,
                    "cantidad_pedida": cantidad,
                    "precio_unitario_compra": precio,
                    "costo_total": round(cantidad * precio, 2),  # calculada
                    "lead_time_dias": lead,
                    "cantidad_recibida": recibida,
                    "cumplimiento": round(recibida / cantidad, 4),  # calculada
                    "metodo_pago": str(rng.choice(comun.CONDICIONES_PAGO)),
                    "descuento_volumen": descuento_volumen,
                })

    df = pd.DataFrame(filas, columns=COMPRAS.orden)
    validar_conforme(df, "compras")
    return df
