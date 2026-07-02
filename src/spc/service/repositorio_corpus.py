"""Corpus acumulativo por cliente y dominio (ADR-0026, reemplaza el corpus de ADR-0011).

Cada carga de datos (JSON o Excel) se **acumula** en la base: una fila en ``datasets``
(auditoría del envío) y N filas en ``observations`` (el histórico de entrenamiento). La
inserción es **idempotente**: reenviar la misma serie+fecha no duplica (política
*keep-first*, vía ``ON CONFLICT DO NOTHING``). Al reentrenar, :meth:`leer_corpus` devuelve
**todo** el histórico del cliente para ese dominio (históricos + lo recién subido).

El repositorio es agnóstico al dominio: el llamador (router) le pasa qué columnas forman la
**serie** y cuál es la **fecha**. Para los dominios fijos 3×3 esos metadatos salen de
:func:`spc.service.dominios.config_de`; para ``/auto/*`` salen del ``schema_spec`` del
cliente.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

import pandas as pd
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from spc.db.orm import Dataset, Observation
from spc.utils.logging import get_logger

log = get_logger("service.repositorio_corpus")


@dataclass(frozen=True)
class ResumenIngesta:
    """Cuántas filas llegaron, cuántas se guardaron y cuántas eran duplicadas."""

    dataset_id: int
    recibidas: int
    insertadas: int
    duplicadas: int


def _ahora_iso() -> str:
    return datetime.now(UTC).isoformat()


def _a_fecha(valor: Any) -> date | None:
    """Convierte un valor ISO (o date) a ``date``; ``None`` si no se puede parsear."""
    if valor is None or valor == "":
        return None
    if isinstance(valor, date) and not isinstance(valor, datetime):
        return valor
    if isinstance(valor, datetime):
        return valor.date()
    try:
        return date.fromisoformat(str(valor)[:10])
    except ValueError:
        return None


class RepositorioCorpus:
    """Almacén del corpus acumulativo (observaciones) por ``(tenant, dominio)``."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._Session: sessionmaker[Session] = sessionmaker(
            bind=engine, expire_on_commit=False, future=True
        )

    # -- Escritura ---------------------------------------------------------
    def insertar_observaciones(
        self,
        *,
        tenant_id: str,
        domain: str,
        rows: list[dict[str, Any]],
        series_keys: list[str],
        date_col: str | None,
        channel: str = "json",
        schema_spec: dict | None = None,
        created_by: str | None = None,
    ) -> ResumenIngesta:
        """Acumula ``rows`` en el corpus (dedup idempotente) y registra el ``dataset``."""
        recibidas = len(rows)
        with self._Session() as s, s.begin():
            dataset = Dataset(
                tenant_id=tenant_id,
                domain=domain,
                channel=channel,
                schema_spec=schema_spec,
                n_rows=recibidas,
                created_by=created_by,
                created_at=_ahora_iso(),
            )
            s.add(dataset)
            s.flush()  # asigna dataset.id
            dataset_id = int(dataset.id)

            antes = self._contar(s, tenant_id, domain)
            valores = [
                {
                    "tenant_id": tenant_id,
                    "domain": domain,
                    "dataset_id": dataset_id,
                    "series_key": self._clave_serie(fila, series_keys),
                    "event_date": _a_fecha(fila.get(date_col)) if date_col else None,
                    "payload": fila,
                    "created_at": _ahora_iso(),
                }
                for fila in rows
            ]
            if valores:
                s.execute(self._insert_ignore(), valores)
            despues = self._contar(s, tenant_id, domain)

        insertadas = max(0, despues - antes)
        duplicadas = max(0, recibidas - insertadas)
        log.info(
            "Corpus %s/%s: recibidas=%d insertadas=%d duplicadas=%d (dataset=%d)",
            tenant_id, domain, recibidas, insertadas, duplicadas, dataset_id,
        )
        return ResumenIngesta(dataset_id, recibidas, insertadas, duplicadas)

    def _insert_ignore(self):
        """``INSERT ... ON CONFLICT DO NOTHING`` portátil (SQLite y Postgres)."""
        cols = ["tenant_id", "domain", "series_key", "event_date"]
        if self._engine.dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import insert as pg_insert

            return pg_insert(Observation).on_conflict_do_nothing(index_elements=cols)
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert

        return sqlite_insert(Observation).on_conflict_do_nothing(index_elements=cols)

    @staticmethod
    def _clave_serie(fila: dict[str, Any], series_keys: list[str]) -> str:
        """Clave textual de la serie (concatena los valores de las columnas identificadoras)."""
        if not series_keys:
            return "_"
        return "|".join(str(fila.get(k, "")) for k in series_keys)

    # -- Lectura -----------------------------------------------------------
    def leer_corpus(self, tenant_id: str, domain: str) -> pd.DataFrame:
        """Devuelve **todo** el histórico acumulado del cliente para el dominio.

        Reconstruye el DataFrame a partir de los ``payload`` (una fila por observación),
        ordenado por fecha. DataFrame vacío si el cliente aún no tiene corpus.
        """
        with self._Session() as s:
            filas = s.scalars(
                select(Observation.payload)
                .where(Observation.tenant_id == tenant_id, Observation.domain == domain)
                .order_by(Observation.event_date)
            ).all()
        if not filas:
            return pd.DataFrame()
        return pd.DataFrame(list(filas))

    def contar(self, tenant_id: str, domain: str) -> int:
        """Nº de observaciones acumuladas del cliente para el dominio."""
        with self._Session() as s:
            return self._contar(s, tenant_id, domain)

    @staticmethod
    def _contar(s: Session, tenant_id: str, domain: str) -> int:
        n = s.scalar(
            select(func.count())
            .select_from(Observation)
            .where(Observation.tenant_id == tenant_id, Observation.domain == domain)
        )
        return int(n or 0)
