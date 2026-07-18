"""Tests del registro de modelos (`spc.service.repositorio_modelos`, ADR-0026).

Verifican el versionado y la adopción sobre la tabla ``models`` con el artefacto en **disco
local** (fallback, sin Supabase): cada versión incrementa, solo una se sirve por
``(tenant, dominio, tarea)``, el objeto entrenado se recupera igual (round-trip joblib), y
la auditoría de predicciones (tabla ``predictions``) se lee del más reciente al más antiguo.
"""

from __future__ import annotations

from spc.service.repositorio_modelos import RepositorioModelos


def _repo(engine, tmp_path) -> RepositorioModelos:
    # dir_artefactos temporal → nunca escribe en models/clientes del repo.
    return RepositorioModelos(engine, tmp_path / "artefactos")


def test_registrar_incrementa_version(engine, tmp_path) -> None:
    repo = _repo(engine, tmp_path)
    v1 = repo.registrar_version(
        tenant_id="c1", domain="ventas", task="regresion", objeto={"m": 1},
        algorithm="Ensemble", metrics={"WAPE": 12.0}, status="adopted",
        trained_rows=100, adoptar=True,
    )
    v2 = repo.registrar_version(
        tenant_id="c1", domain="ventas", task="regresion", objeto={"m": 2},
        algorithm="LightGBM", metrics={"WAPE": 11.0}, status="adopted",
        trained_rows=120, adoptar=True,
    )
    assert v1.version == 1
    assert v2.version == 2


def test_solo_una_version_servida_por_tarea(engine, tmp_path) -> None:
    repo = _repo(engine, tmp_path)
    repo.registrar_version(
        tenant_id="c1", domain="ventas", task="regresion", objeto={"m": 1},
        algorithm="a", metrics={}, status="adopted", trained_rows=1, adoptar=True,
    )
    repo.registrar_version(
        tenant_id="c1", domain="ventas", task="regresion", objeto={"m": 2},
        algorithm="b", metrics={}, status="adopted", trained_rows=1, adoptar=True,
    )
    servidas = [m for m in repo.listar("c1", "ventas") if m.is_serving]
    assert len(servidas) == 1
    assert servidas[0].version == 2  # la última adoptada


def test_cargar_adoptado_round_trip(engine, tmp_path) -> None:
    repo = _repo(engine, tmp_path)
    objeto = {"pesos": [0.3, 0.7], "nombre": "ens"}
    repo.registrar_version(
        tenant_id="c1", domain="ventas", task="regresion", objeto=objeto,
        algorithm="Ensemble", metrics={"WAPE": 10.0}, status="adopted",
        trained_rows=200, adoptar=True,
    )
    cargado = repo.cargar_adoptado("c1", "ventas", "regresion")
    assert cargado is not None
    obj, info = cargado
    assert obj == objeto  # el objeto se recupera igual desde el artefacto en disco
    assert info.is_serving is True


def test_cargar_adoptado_sin_modelo_devuelve_none(engine, tmp_path) -> None:
    repo = _repo(engine, tmp_path)
    assert repo.cargar_adoptado("c1", "ventas", "regresion") is None


def test_marcar_adopcion_conmuta_version_servida(engine, tmp_path) -> None:
    repo = _repo(engine, tmp_path)
    v1 = repo.registrar_version(
        tenant_id="c1", domain="ventas", task="regresion", objeto={"m": 1},
        algorithm="a", metrics={}, status="adopted", trained_rows=1, adoptar=True,
    )
    repo.registrar_version(
        tenant_id="c1", domain="ventas", task="regresion", objeto={"m": 2},
        algorithm="b", metrics={}, status="adopted", trained_rows=1, adoptar=True,
    )
    # Volver a servir la v1.
    info = repo.marcar_adopcion(v1.id, servir=True)
    assert info is not None and info.is_serving
    _, servida = repo.cargar_adoptado("c1", "ventas", "regresion")
    assert servida.version == 1


def test_registrar_y_listar_predicciones(engine, tmp_path) -> None:
    repo = _repo(engine, tmp_path)
    repo.registrar_prediccion(
        tenant_id="c1", domain="ventas", model_id=None, horizon=7,
        request={"n": 1}, response={"ok": True},
    )
    pid = repo.registrar_prediccion(
        tenant_id="c1", domain="ventas", model_id=None, horizon=14,
        request={"n": 2}, response={"ok": True},
    )
    listado = repo.listar_predicciones(tenant_id="c1", domain="ventas")
    assert len(listado) == 2
    assert listado[0].horizon == 14  # más reciente primero
    detalle = repo.obtener_prediccion(pid)
    assert detalle is not None and detalle.request == {"n": 2}
