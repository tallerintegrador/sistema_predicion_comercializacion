"""Tests de la política de stock de seguridad (`spc.service.politica`).

`stock_seguridad` es el único hogar de las fórmulas (ADR-0010). Se verifican los dos
métodos, el fallback cuando σ no es estimable, y que ningún número viva dentro (todo entra
por argumento). Propiedades exactas y de monotonía.
"""

from __future__ import annotations

import math

from spc.service import politica


def test_coverage_days_es_factor_por_demanda() -> None:
    # safety = factor × demanda(lead)
    val = politica.stock_seguridad(
        politica.COVERAGE_DAYS, demanda_lead=100.0, lead=5, factor_cobertura=1.5
    )
    assert val == 150.0


def test_service_level_usa_z_sigma_raiz_lead() -> None:
    # safety = z · σ · √lead
    val = politica.stock_seguridad(
        politica.SERVICE_LEVEL,
        demanda_lead=100.0,
        lead=4,
        factor_cobertura=1.5,
        z=1.65,
        sigma_diaria=10.0,
    )
    assert abs(val - 1.65 * 10.0 * math.sqrt(4)) < 1e-9


def test_service_level_cae_a_fallback_si_sigma_no_estimable() -> None:
    # σ NaN (serie muy corta) → factor_fallback × demanda_lead.
    val = politica.stock_seguridad(
        politica.SERVICE_LEVEL,
        demanda_lead=80.0,
        lead=3,
        factor_cobertura=1.5,
        z=1.65,
        sigma_diaria=float("nan"),
        factor_fallback=2.0,
    )
    assert val == 160.0


def test_service_level_sigma_cero_tambien_cae_a_fallback() -> None:
    val = politica.stock_seguridad(
        politica.SERVICE_LEVEL,
        demanda_lead=50.0,
        lead=2,
        factor_cobertura=1.0,
        z=1.65,
        sigma_diaria=0.0,
        factor_fallback=1.0,
    )
    assert val == 50.0


def test_metodo_desconocido_recae_en_coverage() -> None:
    # Cualquier método no reconocido usa la fórmula de cobertura (seguro por defecto).
    val = politica.stock_seguridad(
        "inexistente", demanda_lead=10.0, lead=1, factor_cobertura=3.0
    )
    assert val == 30.0


def test_service_level_crece_con_sigma() -> None:
    def s(sigma: float) -> float:
        return politica.stock_seguridad(
            politica.SERVICE_LEVEL,
            demanda_lead=100.0,
            lead=4,
            factor_cobertura=1.0,
            z=1.65,
            sigma_diaria=sigma,
        )

    assert s(5.0) < s(10.0) < s(20.0)  # monotonía en σ
