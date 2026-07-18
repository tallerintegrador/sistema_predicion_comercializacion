"""Tests de la serialización de artefactos (`spc.utils.serializacion`).

El motor entrena offline y produce un artefacto (joblib) + un JSON de metadatos adjunto.
Estos tests verifican el round-trip completo en `tmp_path`: lo guardado se recupera igual,
el `.meta.json` se escribe junto al artefacto, y se inyecta la marca temporal y el nombre
del archivo para trazabilidad.
"""

from __future__ import annotations

import numpy as np

from spc.utils import serializacion


def test_round_trip_objeto_y_metadatos(tmp_path) -> None:
    objeto = {"pesos": np.arange(5), "nombre": "ensemble"}
    meta = {"version": 3, "semilla": 42, "features": ["a", "b"]}
    ruta = tmp_path / "modelo.joblib"

    ruta_art, ruta_meta = serializacion.guardar_artefacto(objeto, ruta, meta)

    assert ruta_art.exists() and ruta_meta.exists()
    assert ruta_meta.name == "modelo.meta.json"

    cargado, meta_cargado = serializacion.cargar_artefacto(ruta_art)
    assert np.array_equal(cargado["pesos"], objeto["pesos"])
    assert cargado["nombre"] == "ensemble"
    assert meta_cargado["version"] == 3
    assert meta_cargado["semilla"] == 42


def test_inyecta_guardado_utc_y_nombre_artefacto(tmp_path) -> None:
    ruta = tmp_path / "sub" / "art.joblib"  # el padre no existe: debe crearlo
    _, ruta_meta = serializacion.guardar_artefacto([1, 2, 3], ruta, {"k": "v"})

    import json

    meta = json.loads(ruta_meta.read_text(encoding="utf-8"))
    assert "guardado_utc" in meta  # inyectado automáticamente
    assert meta["artefacto"] == "art.joblib"
    assert meta["k"] == "v"


def test_no_muta_los_metadatos_del_llamador(tmp_path) -> None:
    meta = {"version": 1}
    serializacion.guardar_artefacto([0], tmp_path / "m.joblib", meta)
    # El dict original no debe recibir las claves inyectadas.
    assert meta == {"version": 1}


def test_cargar_sin_meta_devuelve_dict_vacio(tmp_path) -> None:
    import joblib

    ruta = tmp_path / "solo.joblib"
    joblib.dump({"x": 1}, ruta)  # artefacto sin .meta.json
    objeto, meta = serializacion.cargar_artefacto(ruta)
    assert objeto == {"x": 1}
    assert meta == {}
