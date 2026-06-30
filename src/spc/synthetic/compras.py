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
    """Arquetipo de proveedor: define costo, lead time y cumplimiento típicos.

    Tres arquetipos contrastados garantizan que el clustering encuentre grupos
    separables y que la clasificación de retraso tenga señal.
    """

    nombre: str
    factor_costo: float       # multiplicador del precio de compra
    lead_medio: float         # días promedio de entrega
    lead_sigma: float         # variabilidad del lead time
    cumplimiento_medio: float  # fracción recibida/pedida típica (≤1)


ARQUETIPOS: tuple[PerfilProveedor, ...] = (
    PerfilProveedor("premium", 1.25, 4.0, 1.0, 0.99),     # caro, rápido, confiable
    PerfilProveedor("estandar", 1.00, 9.0, 2.5, 0.95),    # equilibrado
    PerfilProveedor("economico", 0.80, 18.0, 5.0, 0.88),  # barato, lento, irregular
)


def generar(
    *,
    seed: int = 42,
    n_proveedores: int = 6,
    n_productos: int = 8,
    n_ordenes_por_serie: int = 36,
    fecha_inicio: date = date(2023, 1, 1),
    dias_entre_ordenes: int = 10,
) -> pd.DataFrame:
    """Genera el dataset sintético de COMPRAS (DataFrame conforme al esquema).

    Default ≈ 6 proveedores × 8 productos × 36 órdenes ≈ 1.728 filas: suficiente para
    el split temporal y para que el clustering separe los arquetipos.
    """
    catalogo = comun.productos(n_productos)
    filas: list[dict[str, object]] = []

    for pv in range(1, n_proveedores + 1):
        id_proveedor = f"PROV-{pv:02d}"
        perfil = ARQUETIPOS[(pv - 1) % len(ARQUETIPOS)]
        rng_pv = comun.rng_de(seed, 3, pv)
        # Pequeña dispersión del arquetipo por proveedor concreto.
        lead_medio = perfil.lead_medio * comun.entre(rng_pv, 0.9, 1.1)
        cumpl_medio = float(np.clip(perfil.cumplimiento_medio * comun.entre(rng_pv, 0.97, 1.0), 0.6, 1.0))

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
