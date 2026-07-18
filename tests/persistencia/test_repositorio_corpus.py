"""Tests del corpus acumulativo (`spc.service.repositorio_corpus`, ADR-0026).

Verifican lo que sostiene el reentrenamiento: cada carga acumula observaciones, la inserción
es **idempotente** (reenviar la misma serie+fecha no duplica, política keep-first) y
`leer_corpus` reconstruye el histórico completo del cliente para el dominio.
"""

from __future__ import annotations

from spc.service.repositorio_corpus import RepositorioCorpus

SERIES = ["id_tienda", "sku"]
FECHA = "fecha"


def _filas() -> list[dict]:
    return [
        {"id_tienda": "T1", "sku": "SKU-001", "fecha": "2024-01-01", "unidades_vendidas": 10},
        {"id_tienda": "T1", "sku": "SKU-001", "fecha": "2024-01-02", "unidades_vendidas": 12},
        {"id_tienda": "T1", "sku": "SKU-002", "fecha": "2024-01-01", "unidades_vendidas": 5},
    ]


def test_insertar_acumula_y_cuenta(engine) -> None:
    repo = RepositorioCorpus(engine)
    resumen = repo.insertar_observaciones(
        tenant_id="c1", domain="ventas", rows=_filas(),
        series_keys=SERIES, date_col=FECHA, channel="json",
    )
    assert resumen.recibidas == 3
    assert resumen.insertadas == 3
    assert resumen.duplicadas == 0
    assert repo.contar("c1", "ventas") == 3


def test_reinsertar_es_idempotente(engine) -> None:
    repo = RepositorioCorpus(engine)
    repo.insertar_observaciones(
        tenant_id="c1", domain="ventas", rows=_filas(),
        series_keys=SERIES, date_col=FECHA, channel="json",
    )
    # Reenvío exacto: misma serie+fecha → nada nuevo (keep-first).
    r2 = repo.insertar_observaciones(
        tenant_id="c1", domain="ventas", rows=_filas(),
        series_keys=SERIES, date_col=FECHA, channel="json",
    )
    assert r2.insertadas == 0
    assert r2.duplicadas == 3
    assert repo.contar("c1", "ventas") == 3  # sigue en 3, no se duplicó


def test_leer_corpus_reconstruye_dataframe(engine) -> None:
    repo = RepositorioCorpus(engine)
    repo.insertar_observaciones(
        tenant_id="c1", domain="ventas", rows=_filas(),
        series_keys=SERIES, date_col=FECHA, channel="json",
    )
    df = repo.leer_corpus("c1", "ventas")
    assert len(df) == 3
    assert set(SERIES + [FECHA, "unidades_vendidas"]) <= set(df.columns)


def test_corpus_aislado_por_tenant_y_dominio(engine) -> None:
    repo = RepositorioCorpus(engine)
    repo.insertar_observaciones(
        tenant_id="c1", domain="ventas", rows=_filas(),
        series_keys=SERIES, date_col=FECHA, channel="json",
    )
    # Otro cliente y otro dominio no ven nada.
    assert repo.contar("c2", "ventas") == 0
    assert repo.contar("c1", "compras") == 0
    assert repo.leer_corpus("c2", "ventas").empty


def test_leer_corpus_vacio_devuelve_dataframe_vacio(engine) -> None:
    repo = RepositorioCorpus(engine)
    assert repo.leer_corpus("nadie", "ventas").empty
