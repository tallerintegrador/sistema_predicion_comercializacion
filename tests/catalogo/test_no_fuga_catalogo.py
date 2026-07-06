"""Guarda anti-fuga del catálogo v3: corre las 30 consultas sobre datos sintéticos.

Objetivo (auditoría 2026-07-03): que NINGUNA consulta reporte una métrica sospechosamente
perfecta sin aviso, y que el modelo ganador nunca quede por debajo del baseline en la
selección (VALID). Es la contraparte automatizada de `tests/test_automl_no_fuga.py`, pero
para el motor ACTIVO (`spc.catalogo.motor_catalogo`), no para el /v2 deprecado.

Datos: `spc.synthetic.generar_dominio` (reproducible, seed=42). El near-leak de ALM-R2
(rotacion) ya se cerró en el YAML; este test lo mantiene cerrado (rotacion no es feature).
"""

from __future__ import annotations

import math

import pandas as pd
import pytest

from spc.catalogo.config import obtener_modulo, obtener_umbrales
from spc.catalogo.motor_catalogo import ejecutar_consulta
from spc.synthetic import generar_dominio

# Parámetros modestos por dominio: suficientes para split temporal y varias entidades de
# clustering, pero acotados para que el test corra rápido.
_PARAMS = {
    "ventas": dict(n_tiendas=2, n_productos=15, n_dias=200),
    "almacen": dict(n_tiendas=2, n_productos=15, n_dias=200),
    "compras": dict(n_proveedores=10, n_productos=6, n_ordenes_por_serie=40),
}


@pytest.fixture(scope="module")
def datasets() -> dict[str, pd.DataFrame]:
    return {dom: generar_dominio(dom, seed=42, **params) for dom, params in _PARAMS.items()}


def _consultas():
    for dominio in ("ventas", "compras", "almacen"):
        for consulta in obtener_modulo(dominio).consultas.values():
            yield dominio, consulta


@pytest.mark.parametrize(
    "dominio,consulta",
    [(d, c) for d, c in _consultas()],
    ids=[c.id for _, c in _consultas()],
)
def test_consulta_no_fuga(dominio, consulta, datasets):
    """Cada consulta: métrica finita, no degenerada y honesta (sin métrica perfecta muda)."""
    df = datasets[dominio]
    res = ejecutar_consulta(consulta.id, df)
    u = obtener_umbrales()

    # 1) Métrica siempre finita.
    assert res.valor_metrica is not None
    assert math.isfinite(res.valor_metrica), f"{consulta.id}: métrica no finita"

    if consulta.tipo == "regresion":
        # 2) WAPE no degenerado (un WAPE ~1 indicaría predicción inútil / objetivo mal escalado).
        assert 0.0 <= res.valor_metrica <= 0.95, (
            f"{consulta.id}: WAPE fuera de rango honesto ({res.valor_metrica:.3f})"
        )
        # 3) El ganador no puede ser PEOR que el baseline en la selección (VALID).
        filas = {f.modelo: f.valor for f in res.tabla_comparacion if math.isfinite(f.valor)}
        if "baseline" in filas:
            ganador = next((f.valor for f in res.tabla_comparacion if f.ganador), None)
            if ganador is not None and math.isfinite(ganador):
                assert ganador <= filas["baseline"] + 1e-9, (
                    f"{consulta.id}: el ganador ({ganador:.4f}) es peor que el baseline "
                    f"({filas['baseline']:.4f})"
                )
        # 4) Debe emitir predicciones sobre datos reales.
        assert res.predicciones, f"{consulta.id}: regresión sin predicciones"

    elif consulta.tipo == "clasificacion":
        # 5) Honestidad: una métrica casi perfecta en clasificación DERIVADA (regla/percentil)
        #    debe venir SIEMPRE acompañada de nota técnica honesta, nunca cruda.
        derivada = consulta.derivacion_etiqueta is not None
        if derivada and res.valor_metrica >= u.metrica_casi_perfecta and res.tabla_comparacion:
            assert res.nota_tecnica, (
                f"{consulta.id}: métrica casi perfecta ({res.valor_metrica:.3f}) sin nota honesta"
            )

    elif consulta.tipo == "clustering":
        # 6) Silueta / value_share en rango válido de su métrica.
        if res.metrica_ganador == "silhouette":
            assert -1.0 <= res.valor_metrica <= 1.0, (
                f"{consulta.id}: silueta fuera de [-1,1] ({res.valor_metrica:.3f})"
            )
        else:  # ABC → value_share_a
            assert 0.0 <= res.valor_metrica <= 1.0


def test_alm_r2_no_usa_rotacion():
    """Regresión anti-regresión del cierre de near-leak: rotacion NO es feature de ALM-R2."""
    from spc.catalogo.config import obtener_consulta

    c = obtener_consulta("alm_r2")
    assert "rotacion" not in c.columnas_entrada, (
        "ALM-R2 volvió a incluir rotacion (near-leak con dias_de_cobertura)"
    )
