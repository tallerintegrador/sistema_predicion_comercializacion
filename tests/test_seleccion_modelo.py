"""Tests de **quédate-con-el-mejor** (Fase 4, ADR-0023/0013).

Verifican que, al reentrenar con datos nuevos, el sistema compara el candidato contra el
campeón persistido sobre la misma ventana TEST y conserva el mejor — y que un modelo peor
nunca reemplaza a uno bueno. El veredicto viaja en ``training.seleccion``.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from spc.api.schemas.agnostico import AutoSalesRequest, FeatureSpec, SchemaSpec
from spc.models import automl
from spc.service import seleccion_modelo
from spc.service.agnostico import a_dataframe, construir_spec, pronosticar_ventas
from spc.service.cache_agnostico import CacheModelosAgnosticos

_SCHEMA = SchemaSpec(
    target="ventas",
    date="fecha",
    series_keys=["sucursal"],
    features=[
        FeatureSpec(name="descuento", type="numeric", known_future=True),
        FeatureSpec(name="region", type="categorical", known_future=True),
    ],
)


def _filas(series=("L1", "L2"), dias: int = 120) -> list[dict]:
    rng = np.random.default_rng(7)
    filas: list[dict] = []
    for si, s in enumerate(series):
        base = 130 if si == 0 else 60
        for i in range(dias):
            d = (pd.Timestamp("2024-01-01") + pd.Timedelta(days=i)).date().isoformat()
            ventas = max(0.0, base * (1 + 0.3 * np.sin(2 * np.pi * i / 7)) + rng.normal(0, 5))
            filas.append({
                "fecha": d, "sucursal": s, "ventas": round(ventas, 1),
                "descuento": int(rng.integers(0, 3)),
                "region": "norte" if si == 0 else "sur",
            })
    return filas


def test_adoptado_reglas():
    # menor-mejor (WAPE): el candidato gana solo si es estrictamente menor; empate → campeón.
    assert seleccion_modelo._adoptado(10.0, 12.0, mayor_mejor=False) == "candidato"
    assert seleccion_modelo._adoptado(12.0, 10.0, mayor_mejor=False) == "campeon"
    assert seleccion_modelo._adoptado(10.0, 10.0, mayor_mejor=False) == "campeon"
    # mayor-mejor (AUC): el candidato gana si es estrictamente mayor.
    assert seleccion_modelo._adoptado(0.9, 0.8, mayor_mejor=True) == "candidato"
    assert seleccion_modelo._adoptado(0.8, 0.9, mayor_mejor=True) == "campeon"
    # rival sin métrica → gana quien sí la tiene / estabilidad.
    assert seleccion_modelo._adoptado(0.9, None, mayor_mejor=True) == "candidato"
    assert seleccion_modelo._adoptado(None, 0.9, mayor_mejor=True) == "campeon"


def test_modelo_peor_no_reemplaza_al_campeon():
    """Con un candidato artificialmente malo (WAPE altísimo), se mantiene el campeón."""
    df = a_dataframe(_filas(), _SCHEMA)
    spec = construir_spec(_SCHEMA)
    res = automl.entrenar_regresion(df, spec, seed=42)
    info = {
        "winner_algorithm": res.ganador, "trained_rows": res.n_filas,
        "honest_metrics": dict(res.metricas_test), "candidates": res.candidatos,
        "reused_cached_model": False, "schema_signature": "sig",
    }
    campeon = (res.predictor, info)

    malo = {**info, "honest_metrics": {**info["honest_metrics"], "WAPE": 999.0}}
    pred, out = seleccion_modelo.elegir_mejor_regresion(
        candidato_info=malo, res=res, campeon=campeon, spec=spec
    )
    assert out["seleccion"]["adoptado"] == "campeon"
    assert out["seleccion"]["comparado"] is True
    assert pred is res.predictor


def test_modelo_mejor_se_adopta():
    """Con un candidato mejor (WAPE 0), se adopta el candidato."""
    df = a_dataframe(_filas(), _SCHEMA)
    spec = construir_spec(_SCHEMA)
    res = automl.entrenar_regresion(df, spec, seed=42)
    info = {
        "winner_algorithm": res.ganador, "trained_rows": res.n_filas,
        "honest_metrics": dict(res.metricas_test), "candidates": res.candidatos,
        "reused_cached_model": False, "schema_signature": "sig",
    }
    campeon = (res.predictor, info)

    bueno = {**info, "honest_metrics": {**info["honest_metrics"], "WAPE": 0.0}}
    _, out = seleccion_modelo.elegir_mejor_regresion(
        candidato_info=bueno, res=res, campeon=campeon, spec=spec
    )
    assert out["seleccion"]["adoptado"] == "candidato"


def test_flujo_servicio_emite_veredicto(tmp_path):
    """Integración: la 1ª predicción no compara; la 2ª (data nueva) emite veredicto."""
    cache = CacheModelosAgnosticos(tmp_path)
    req1 = AutoSalesRequest(schema=_SCHEMA, horizon=7, rows=_filas(dias=120))
    r1 = pronosticar_ventas(req1, client_id="c1", cache=cache)
    assert r1["training"].get("seleccion") is None  # primera vez: no hay campeón

    req2 = AutoSalesRequest(schema=_SCHEMA, horizon=7, rows=_filas(dias=140))
    r2 = pronosticar_ventas(req2, client_id="c1", cache=cache)
    sel = r2["training"]["seleccion"]
    assert sel is not None
    assert sel["comparado"] is True
    assert sel["adoptado"] in {"campeon", "candidato"}
    assert sel["metrica"] == "WAPE"
