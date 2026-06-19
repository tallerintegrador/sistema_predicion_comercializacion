"""Tests de la **capa de política configurable** (Fase 3.5, ADR-0010).

Fijan tres cosas:

1. **Configurabilidad:** cambiar una constante de política por entorno cambia el
   resultado de forma esperable (factor, z, lead time por defecto, ventana, método).
2. **Regresión:** con los **defaults** (sin configurar nada, o poniendo las variables a
   su valor por defecto) la salida **NO cambia** respecto al comportamiento histórico.
3. **Puente de unificación:** poner el método de INVENTORY en ``coverage_days`` lo
   alinea con PURCHASES (días de cobertura), y el cuantil P75 (model-adjacent) se lee de
   la metadata si existe o cae a un fallback documentado.

Todo con los artefactos diminutos del ``conftest`` (sin GPU ni datos reales). Las
constantes se leen en **tiempo de petición**, así que basta con ``monkeypatch.setenv``
antes de cada ``client.post``.
"""

from __future__ import annotations

import pandas as pd
import pytest

from spc.service.adaptador import marcar_demanda_alta
from spc.service.almacen_service import CUANTIL_DEMANDA_ALTA_FALLBACK, _cuantil_demanda_alta


def _compras(historico, *, stock=100, lead=4, cobertura=7):
    return {
        "history": historico,
        "replenishment_params": [
            {
                "store_id": "1",
                "product_id": "BEVERAGES",
                "current_stock": stock,
                "lead_time_days": lead,
                "target_coverage_days": cobertura,
            }
        ],
    }


def _inventory(historico, *, stock=100, lead=4):
    estado = {"store_id": "1", "product_id": "BEVERAGES", "current_stock": stock}
    if lead is not None:
        estado["lead_time_days"] = lead
    return {"history": historico, "inventory_status": [estado]}


# ---------------------------------------------------------------------------
# Regresión: con los defaults, la salida NO cambia
# ---------------------------------------------------------------------------
def test_defaults_no_cambian_salida_compras(client, historico_contrato, monkeypatch):
    """PURCHASES sin configurar == configurando las variables a su valor por defecto."""
    r_default = client.post("/purchases", json=_compras(historico_contrato))
    assert r_default.status_code == 200, r_default.text

    monkeypatch.setenv("SPC_PURCHASES_SAFETY_METHOD", "coverage_days")
    monkeypatch.setenv("SPC_PURCHASES_SAFETY_FACTOR", "0.30")
    r_explicit = client.post("/purchases", json=_compras(historico_contrato))
    assert r_explicit.json() == r_default.json()

    # Y el supuesto por defecto sigue siendo el histórico (colchón 30%, coverage_days).
    meta = r_default.json()["metadata"]
    assert meta["policy"] == "coverage_days"
    assert "30%" in meta["assumption"]


def test_defaults_no_cambian_salida_inventory(client, historico_contrato, monkeypatch):
    """INVENTORY sin configurar == configurando las variables a su valor por defecto."""
    r_default = client.post("/inventory", json=_inventory(historico_contrato))
    assert r_default.status_code == 200, r_default.text

    monkeypatch.setenv("SPC_INVENTORY_SAFETY_METHOD", "service_level")
    monkeypatch.setenv("SPC_INVENTORY_LEAD_TIME_DEFAULT", "7")
    monkeypatch.setenv("SPC_INVENTORY_DEMAND_WINDOW", "28")
    monkeypatch.setenv("SPC_INVENTORY_Z_BASE", "1.28")
    monkeypatch.setenv("SPC_INVENTORY_Z_HIGH_VOLUME", "1.65")
    monkeypatch.setenv("SPC_INVENTORY_SAFETY_FALLBACK_FACTOR", "0.5")
    r_explicit = client.post("/inventory", json=_inventory(historico_contrato))
    assert r_explicit.json() == r_default.json()


# ---------------------------------------------------------------------------
# Configurabilidad: cambiar la config cambia el resultado de forma esperable
# ---------------------------------------------------------------------------
def test_compras_factor_configurable_sube_reorder(client, historico_contrato, monkeypatch):
    """Subir el factor de colchón sube el punto de reorden (safety = factor × demanda_lead)."""
    monkeypatch.setenv("SPC_PURCHASES_SAFETY_FACTOR", "0.30")
    bajo = client.post("/purchases", json=_compras(historico_contrato)).json()["recommendation"][0]

    monkeypatch.setenv("SPC_PURCHASES_SAFETY_FACTOR", "0.90")
    alto = client.post("/purchases", json=_compras(historico_contrato)).json()
    item = alto["recommendation"][0]
    assert item["reorder_point"] > bajo["reorder_point"] > 0
    assert "90%" in alto["metadata"]["assumption"]


def test_compras_metodo_service_level_cambia_policy(client, historico_contrato, monkeypatch):
    """Conmutar PURCHASES a service_level cambia policy y assumption (knob por dominio)."""
    monkeypatch.setenv("SPC_PURCHASES_SAFETY_METHOD", "service_level")
    cuerpo = client.post("/purchases", json=_compras(historico_contrato)).json()
    assert cuerpo["metadata"]["policy"] == "service_level"
    assert "σ" in cuerpo["metadata"]["assumption"]


def test_inventory_z_configurable_escala_safety(client, historico_contrato, monkeypatch):
    """En service_level, duplicar z (base y alto volumen) duplica el safety_stock."""
    monkeypatch.setenv("SPC_INVENTORY_Z_BASE", "1.0")
    monkeypatch.setenv("SPC_INVENTORY_Z_HIGH_VOLUME", "1.0")
    s1 = client.post("/inventory", json=_inventory(historico_contrato)).json()["alerts"][0]
    assert s1["safety_stock"] > 0  # σ estimable (hay variabilidad en el histórico)

    monkeypatch.setenv("SPC_INVENTORY_Z_BASE", "2.0")
    monkeypatch.setenv("SPC_INVENTORY_Z_HIGH_VOLUME", "2.0")
    s2 = client.post("/inventory", json=_inventory(historico_contrato)).json()["alerts"][0]
    assert s2["safety_stock"] == pytest.approx(2 * s1["safety_stock"], rel=1e-3, abs=0.02)


def test_inventory_lead_time_default_configurable(client, historico_contrato, monkeypatch):
    """El lead time por defecto (cuando el cliente no lo envía) es configurable y sube el stock."""
    payload = _inventory(historico_contrato, lead=None)  # sin lead_time_days → usa el default

    monkeypatch.setenv("SPC_INVENTORY_LEAD_TIME_DEFAULT", "7")
    corto = client.post("/inventory", json=payload).json()["alerts"][0]

    monkeypatch.setenv("SPC_INVENTORY_LEAD_TIME_DEFAULT", "30")
    largo = client.post("/inventory", json=payload).json()["alerts"][0]
    assert largo["recommended_stock"] > corto["recommended_stock"] > 0


def test_inventory_demand_window_configurable_cambia_salida(client, historico_contrato, monkeypatch):
    """Cambiar la ventana de estimación de μ/σ cambia el stock recomendado."""
    monkeypatch.setenv("SPC_INVENTORY_DEMAND_WINDOW", "3")
    corta = client.post("/inventory", json=_inventory(historico_contrato)).json()["alerts"][0]

    monkeypatch.setenv("SPC_INVENTORY_DEMAND_WINDOW", "120")
    larga = client.post("/inventory", json=_inventory(historico_contrato)).json()["alerts"][0]
    assert corta["recommended_stock"] != larga["recommended_stock"]


# ---------------------------------------------------------------------------
# Puente de unificación: INVENTORY en coverage_days == COMPRAS
# ---------------------------------------------------------------------------
def test_inventory_coverage_days_unifica_con_compras(client, historico_contrato, monkeypatch):
    """Con método coverage_days, safety = factor × demanda_lead (igual fórmula que COMPRAS).

    Bajo coverage_days: ``recommended = demanda_lead·(1+factor)`` y
    ``safety = factor·demanda_lead`` ⇒ ``safety/recommended = factor/(1+factor)``,
    invariante independiente de la demanda. Con el factor puente por defecto (0.30) eso
    es 0.30/1.30 ≈ 0.2308.
    """
    monkeypatch.setenv("SPC_INVENTORY_SAFETY_METHOD", "coverage_days")
    alerta = client.post("/inventory", json=_inventory(historico_contrato)).json()["alerts"][0]
    assert alerta["recommended_stock"] > 0
    ratio = alerta["safety_stock"] / alerta["recommended_stock"]
    assert ratio == pytest.approx(0.30 / 1.30, rel=1e-3)


def test_inventory_coverage_factor_puente_configurable(client, historico_contrato, monkeypatch):
    """El factor de cobertura del puente también es configurable (SPC_INVENTORY_COVERAGE_FACTOR)."""
    monkeypatch.setenv("SPC_INVENTORY_SAFETY_METHOD", "coverage_days")
    monkeypatch.setenv("SPC_INVENTORY_COVERAGE_FACTOR", "0.50")
    alerta = client.post("/inventory", json=_inventory(historico_contrato)).json()["alerts"][0]
    assert alerta["recommended_stock"] > 0
    ratio = alerta["safety_stock"] / alerta["recommended_stock"]
    assert ratio == pytest.approx(0.50 / 1.50, rel=1e-3)


# ---------------------------------------------------------------------------
# Q2 — cuantil P75 (model-adjacent): se lee de la metadata o cae al fallback
# ---------------------------------------------------------------------------
def test_cuantil_demanda_alta_fallback_si_meta_no_lo_expone():
    """Si la metadata no expone el cuantil (caso actual), se usa el fallback documentado."""
    assert _cuantil_demanda_alta({}) == CUANTIL_DEMANDA_ALTA_FALLBACK
    assert _cuantil_demanda_alta({"version": "clasificacion_v1"}) == CUANTIL_DEMANDA_ALTA_FALLBACK


def test_cuantil_demanda_alta_se_lee_de_metadata_si_existe():
    """Si la metadata expone objetivo_cuantil válido, se lee de ahí (como el umbral)."""
    assert _cuantil_demanda_alta({"objetivo_cuantil": 0.9}) == 0.9
    # Valores inválidos (fuera de (0,1) o booleanos) caen al fallback, no se inventan.
    assert _cuantil_demanda_alta({"objetivo_cuantil": 1.5}) == CUANTIL_DEMANDA_ALTA_FALLBACK
    assert _cuantil_demanda_alta({"objetivo_cuantil": True}) == CUANTIL_DEMANDA_ALTA_FALLBACK


def test_marcar_demanda_alta_respeta_el_cuantil():
    """Un cuantil más alto sube el umbral por familia y marca menos 'demanda alta'."""
    df = pd.DataFrame({"family": ["A"] * 5, "sales": [1.0, 2.0, 3.0, 4.0, 100.0]})
    bajo = marcar_demanda_alta(df, cuantil=0.50)["demanda_alta"].sum()
    alto = marcar_demanda_alta(df, cuantil=0.95)["demanda_alta"].sum()
    assert alto < bajo
