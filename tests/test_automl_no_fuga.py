"""Guarda anti-fuga del AutoML agnóstico de regresión (`spc.models.automl`).

La métrica honesta de TEST se calcula con un modelo entrenado **solo con datos previos a
la ventana TEST**. Si se evaluara con el artefacto reajustado sobre TODA la historia (que
ya vio TEST), un modelo de alta capacidad memorizaría esas filas y reportaría un WAPE
falsamente perfecto. Este test fija que, sobre datos con ruido irreducible, la métrica
queda por encima de un piso realista (con la fuga caería a ~0).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from spc.features.generico import EspecEsquema
from spc.models import automl


def _datos_con_ruido(series: int = 8, dias: int = 120, sigma: float = 0.25) -> pd.DataFrame:
    """Series con nivel propio + estacionalidad semanal + ruido multiplicativo irreducible.

    Trae varias categóricas/numéricas conocidas a futuro para que gane un modelo de alta
    capacidad (booster) capaz de memorizar si la evaluación tuviera fuga.
    """
    rng = np.random.default_rng(7)
    filas: list[dict] = []
    inicio = pd.Timestamp("2024-01-01")
    for s in range(series):
        base = 40 + 15 * s
        seg = f"seg{s % 3}"
        prov = f"prov{s % 4}"
        for i in range(dias):
            d = (inicio + pd.Timedelta(days=i)).date().isoformat()
            promo = int(i % 9 < 3)
            precio = round(10.0 * (0.9 if promo else 1.0), 2)
            semanal = 1 + 0.25 * np.sin(2 * np.pi * i / 7)
            ruido = float(rng.lognormal(0, sigma))
            y = max(0.0, base * semanal * (1.1 if promo else 1.0) * ruido)
            filas.append({
                "fecha": d, "tienda": f"T{s}", "precio": precio, "en_promo": promo,
                "segmento": seg, "proveedor": prov, "ventas": round(y, 1),
            })
    return pd.DataFrame(filas)


def test_metrica_test_no_es_perfecta_por_fuga() -> None:
    df = _datos_con_ruido()
    spec = EspecEsquema(
        objetivo="ventas", col_fecha="fecha", cols_serie=("tienda",),
        num_conocidas_futuro=("precio", "en_promo"),
        cats_extra=("segmento", "proveedor"),
    )
    res = automl.entrenar_regresion(df, spec, seed=42)

    wape = res.metricas_test.get("WAPE")  # WAPE en porcentaje (p. ej. 19.6 = 19.6%)
    assert wape is not None, "Debe reportar WAPE honesto en TEST."
    # Con ruido sigma=0.25 el piso irreducible de WAPE es ~15-20%. Si hubiera fuga
    # (evaluar con el modelo reajustado sobre TODO, incluido TEST), caería por debajo de
    # ~5%. Exigimos un piso realista holgado.
    assert wape > 5.0, f"WAPE de TEST sospechosamente bajo ({wape}%); posible fuga de evaluación."
    # Y debe seguir siendo un pronóstico útil (no degenerado).
    assert wape < 60.0, f"WAPE de TEST irrealmente alto ({wape}%)."
