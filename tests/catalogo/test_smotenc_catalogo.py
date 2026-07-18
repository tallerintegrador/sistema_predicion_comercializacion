"""Pruebas del flujo mixto de desbalance del catálogo v3."""

from __future__ import annotations

import numpy as np
from imblearn.over_sampling import SMOTENC

from spc.catalogo import motor_catalogo
from spc.synthetic import generar_dominio


def test_smotenc_y_umbral_reciben_solo_train_y_valid(monkeypatch) -> None:
    df = generar_dominio("ventas", seed=42, n_tiendas=2, n_productos=8, n_dias=100)
    longitudes_smote: list[int] = []
    longitudes_umbral: list[int] = []
    fit_resample_original = SMOTENC.fit_resample
    seleccionar_original = motor_catalogo.seleccionar_umbral

    def fit_resample_spy(self, X, y):
        longitudes_smote.append(len(y))
        return fit_resample_original(self, X, y)

    def seleccionar_spy(y_true: np.ndarray, y_prob: np.ndarray):
        longitudes_umbral.append(len(y_true))
        return seleccionar_original(y_true, y_prob)

    monkeypatch.setattr(SMOTENC, "fit_resample", fit_resample_spy)
    monkeypatch.setattr(motor_catalogo, "seleccionar_umbral", seleccionar_spy)
    resultado = motor_catalogo.ejecutar_consulta("ven-c1", df)

    detalle = resultado.meta["resampling"]
    assert detalle["applied_split"] == "train"
    assert longitudes_smote == [sum(detalle["class_counts_before"].values())]
    assert longitudes_umbral
    assert set(longitudes_umbral) == {detalle["validation_rows"]}
    assert detalle["smotenc_counts_after"]["0"] == detalle["smotenc_counts_after"]["1"]
    assert detalle["test_rows"] != len(df)


def test_seleccion_usa_pr_auc_valid_y_desempata_por_simplicidad() -> None:
    df = generar_dominio("ventas", seed=7, n_tiendas=2, n_productos=8, n_dias=100)
    resultado = motor_catalogo.ejecutar_consulta("ven-c1", df)
    filas = [f for f in resultado.tabla_comparacion if not f.modelo.startswith("baseline")]
    ganador = next(f for f in filas if f.ganador)
    mejor = max(f.valor for f in filas)

    assert ganador.valor >= mejor - 0.005
    estrategias_empatadas = {
        f.modelo.rsplit("[", 1)[1].rstrip("]")
        for f in filas
        if f.valor >= mejor - 0.005
    }
    orden = {"sin_remuestreo": 0, "costo_sensible": 1, "smotenc": 2}
    estrategia_ganadora = ganador.modelo.rsplit("[", 1)[1].rstrip("]")
    assert orden[estrategia_ganadora] == min(orden[e] for e in estrategias_empatadas)
    assert resultado.meta["resampling"]["selection_metric"] == "pr_auc_validation"


def test_prediccion_binaria_aplica_el_umbral_fijado_en_valid() -> None:
    df = generar_dominio("ventas", seed=11, n_tiendas=2, n_productos=8, n_dias=100)
    resultado = motor_catalogo.ejecutar_consulta("ven-c1", df)
    umbral = resultado.meta["resampling"]["threshold"]
    for fila in resultado.predicciones:
        # La probabilidad del contrato está redondeada a cuatro decimales; se excluye
        # únicamente el estrecho borde donde ese redondeo puede cruzar el umbral.
        if abs(fila["probability"] - umbral) > 0.0001:
            assert fila["class"] == int(fila["probability"] >= umbral)

