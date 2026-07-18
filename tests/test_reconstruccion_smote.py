"""Aceptación estadística y de negocio de la reconstrucción inferida."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from spc.synthetic.esquemas import validar_conforme
from spc.synthetic.reconstruccion_smote import CONFIGS, reconstruir_dominio

RAIZ = Path("pyme_hibrida")
SALIDA = RAIZ / "reconstruccion_smote"


def _leer_json(path: Path) -> pd.DataFrame:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return pd.DataFrame(payload["rows"])


@pytest.mark.parametrize("dominio", list(CONFIGS))
def test_archivos_reconstruidos_cumplen_esquema_claves_y_reglas(dominio: str) -> None:
    if not SALIDA.exists():
        pytest.skip("Primero ejecute scripts/reconstruir_pyme_hibrida.py")
    target = _leer_json(RAIZ / f"{dominio}_v3.json")
    crudo = _leer_json(SALIDA / "crudo" / f"{dominio}_crudo.json")
    reconstruido = _leer_json(SALIDA / "reconstruido" / f"{dominio}_smotenc.json")
    cfg = CONFIGS[dominio]

    assert list(reconstruido.columns) == list(target.columns)
    assert len(reconstruido) == len(target)
    assert len(crudo) < len(target)
    assert reconstruido.duplicated(list(cfg.claves)).sum() == 0
    assert validar_conforme(reconstruido, dominio) is None

    if dominio == "ventas":
        ingreso = reconstruido["unidades_vendidas"] * reconstruido["precio_unitario"]
        assert (reconstruido["ingreso"] - ingreso).abs().max() <= 0.011
        assert (reconstruido.loc[reconstruido["en_promocion"] == 0, "descuento_pct"] == 0).all()
    elif dominio == "compras":
        costo = (
            reconstruido["cantidad_pedida"]
            * reconstruido["precio_unitario_compra"]
        )
        assert (reconstruido["costo_total"] - costo).abs().max() <= 0.011
        assert (reconstruido["cantidad_recibida"] <= reconstruido["cantidad_pedida"]).all()
    else:
        assert (reconstruido["stock_minimo"] <= reconstruido["stock_maximo"]).all()
        assert (reconstruido.select_dtypes("number") >= 0).all().all()


@pytest.mark.slow
def test_reconstruccion_es_reproducible_con_semilla_42() -> None:
    if not (RAIZ / "ventas_v3.json").exists():
        pytest.skip("No está disponible el dataset canónico de pyme_hibrida")
    target = _leer_json(RAIZ / "ventas_v3.json")
    primera = reconstruir_dominio(target, "ventas", seed=42)
    segunda = reconstruir_dominio(target, "ventas", seed=42)
    pd.testing.assert_frame_equal(primera.crudo, segunda.crudo, check_dtype=True)
    pd.testing.assert_frame_equal(primera.reconstruido, segunda.reconstruido, check_dtype=True)
    assert primera.auditoria == segunda.auditoria
