"""Persistencia incremental del corpus (Fase A MEJORADO, ADR-0011).

Cada predicción que sirve la API guarda dos cosas en una base **SQLite** (biblioteca
estándar, cero dependencias nuevas):

- ``submissions``: una fila por petición (auditoría/replay) — cliente, dominio, canal
  (``json``/``excel``), modo (``online``/``batch``), versión del modelo, nº de filas, los
  **parámetros** de la petición (``horizon``, ``granularity``, ``replenishment_params``…)
  y la respuesta serializada. El bloque ``history`` **no** se duplica aquí (ya vive
  normalizado en ``observations``); así la base no crece dos veces con el mismo dato.
- ``observations``: el ``history`` del cliente **normalizado y deduplicado** — el
  **corpus** que crece con cada uso. Un índice UNIQUE sobre la identidad de la serie
  (``client_id``, ``store_id``, ``product_id``, ``date``) + ``INSERT OR IGNORE`` hace la
  acumulación **idempotente**: reenviar el mismo ``history`` no infla el corpus. Es lo que
  después alimenta el reentrenamiento (``scripts/exportar_corpus.py`` → ``scripts/train_*``).

El modelo se entrega **congelado** y solo predice (ADR-0009); aquí no se reentrena nada.
Lo nuevo es la **acumulación** que hace posible mejorar el modelo más adelante.

**Best-effort por diseño:** esta capa nunca debe romper una predicción. El *hogar* del
flujo de predicción (``spc.api.ruteo``) llama a ``registrar`` envuelto en ``try/except``;
aun así, este módulo evita sorpresas (transacción atómica, conexión thread-safe).

**Thread-safe:** el modo por lote escribe desde el hilo del executor, así que la conexión
se abre con ``check_same_thread=False`` y todo acceso pasa por un ``threading.Lock`` (mismo
criterio que ``GestorTrabajos`` en ``spc.api.jobs``).
"""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from spc.utils.logging import get_logger

log = get_logger("service.repositorio")

# DDL idempotente: crear la base es seguro de repetir en cada arranque.
_DDL = """
CREATE TABLE IF NOT EXISTS submissions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            TEXT NOT NULL,
    client_id     TEXT NOT NULL,
    domain        TEXT NOT NULL,
    channel       TEXT NOT NULL,
    mode          TEXT NOT NULL,
    model_version TEXT,
    n_rows        INTEGER NOT NULL,
    request_json  TEXT NOT NULL,
    response_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS observations (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    submission_id INTEGER NOT NULL REFERENCES submissions(id),
    client_id     TEXT NOT NULL,
    date          TEXT NOT NULL,
    store_id      TEXT NOT NULL,
    product_id    TEXT NOT NULL,
    units_sold    REAL,
    on_promotion  INTEGER,
    transactions  REAL,
    event_active  INTEGER
);

CREATE INDEX IF NOT EXISTS ix_observations_client ON observations(client_id);
CREATE INDEX IF NOT EXISTS ix_observations_serie  ON observations(store_id, product_id, date);
"""

# Índice UNIQUE de deduplicación del corpus (ADR-0011). La identidad de una observación
# es su serie + fecha por cliente; con `INSERT OR IGNORE`, reenviar el mismo `history` no
# crea filas nuevas (idempotencia). Política ante misma serie+fecha repetida: se conserva
# la PRIMERA (una corrección posterior del mismo punto se ignora). Va aparte del DDL
# principal porque una base PREVIA con duplicados haría fallar su creación: en ese caso se
# registra y se sigue (el export deduplica como red de seguridad).
_DDL_DEDUP = (
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_observations_dedup "
    "ON observations(client_id, store_id, product_id, date)"
)


def _ahora_iso() -> str:
    """Marca de tiempo UTC en ISO-8601 (texto, para la columna ``ts``)."""
    return datetime.now(UTC).isoformat()


def _a_json(payload: Any) -> str:
    """Serializa a JSON tolerando ``date``/``datetime`` (``default=str``)."""
    return json.dumps(payload, default=str, ensure_ascii=False)


def _bool_a_int(valor: Any) -> int | None:
    """Convierte un booleano opcional a 0/1 para SQLite (``None`` se preserva)."""
    return None if valor is None else int(bool(valor))


def _sin_history(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Copia del cuerpo de la petición **sin** el bloque ``history``.

    El ``history`` ya se guarda normalizado (y deduplicado) en ``observations``; volver a
    serializarlo crudo en ``submissions`` solo haría crecer la base con el mismo dato. Se
    conserva el resto de parámetros de la petición (``horizon``, ``granularity``,
    ``replenishment_params``, ``inventory_status`` …), que sí hacen falta —junto con
    ``observations``— para reconstruir la petición en una auditoría.
    """
    return {k: v for k, v in payload.items() if k != "history"}


class RepositorioPredicciones:
    """Almacén SQLite del corpus incremental + auditoría de predicciones.

    Vive en ``app.state.repositorio`` (como ``registro`` y ``jobs``) para que sea
    inyectable y testeable. Use :meth:`crear` para abrirlo (archivo o ``":memory:"``).
    """

    def __init__(self, conexion: sqlite3.Connection) -> None:
        self._con = conexion
        self._lock = threading.Lock()
        with self._lock:
            self._con.executescript(_DDL)
            self._asegurar_indice_dedup()
            self._con.commit()

    def _asegurar_indice_dedup(self) -> None:
        """Crea el índice UNIQUE de deduplicación (best-effort; ver ``_DDL_DEDUP``).

        Si una base previa ya trae duplicados, crear el índice falla: se registra y se
        continúa (la base sigue usable; el export deduplica como red de seguridad).
        """
        try:
            self._con.execute(_DDL_DEDUP)
        except sqlite3.Error as exc:  # base previa con duplicados, p. ej.
            log.warning(
                "Sin índice de deduplicación del corpus (¿duplicados previos?): %s", exc
            )

    # -- Construcción ------------------------------------------------------
    @classmethod
    def crear(cls, db_path: str | Path) -> RepositorioPredicciones:
        """Abre (o crea) la base en ``db_path`` y garantiza el esquema.

        Acepta una ruta de archivo —se crean las carpetas intermedias— o ``":memory:"``
        para una base efímera (tests). La conexión permite uso multihilo (el lote escribe
        desde el executor); la concurrencia se serializa con el lock interno.
        """
        ruta = str(db_path)
        if ruta != ":memory:":
            Path(ruta).parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(ruta, check_same_thread=False)
        con.execute("PRAGMA foreign_keys = ON")
        return cls(con)

    # -- Escritura ---------------------------------------------------------
    def registrar(
        self,
        *,
        client_id: str,
        domain: str,
        channel: str,
        mode: str,
        model_version: str | None,
        history: Iterable[Mapping[str, Any]],
        request_payload: Mapping[str, Any],
        response_payload: Mapping[str, Any],
    ) -> int:
        """Guarda una predicción: 1 fila en ``submissions`` + N filas en ``observations``.

        ``history`` son las observaciones del contrato (claves ``date``, ``store_id``,
        ``product_id``, ``units_sold`` y opcionales). Las observaciones se insertan con
        ``INSERT OR IGNORE``: una serie+fecha ya presente (del mismo cliente) **no** se
        duplica. ``submissions`` guarda el resto de la petición **sin** el ``history``
        (ya está en ``observations``). Todo va en **una sola transacción**: o se guardan
        ambas tablas o ninguna. Devuelve el ``submission_id``.
        """
        filas = list(history)
        with self._lock:
            cur = self._con.execute(
                """
                INSERT INTO submissions
                    (ts, client_id, domain, channel, mode, model_version, n_rows,
                     request_json, response_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _ahora_iso(),
                    client_id,
                    domain,
                    channel,
                    mode,
                    model_version,
                    len(filas),
                    _a_json(_sin_history(request_payload)),
                    _a_json(response_payload),
                ),
            )
            submission_id = int(cur.lastrowid or 0)
            if filas:
                # OR IGNORE: las observaciones ya presentes (misma serie+fecha del cliente)
                # se omiten gracias al índice UNIQUE — el corpus es idempotente (ADR-0011).
                self._con.executemany(
                    """
                    INSERT OR IGNORE INTO observations
                        (submission_id, client_id, date, store_id, product_id,
                         units_sold, on_promotion, transactions, event_active)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            submission_id,
                            client_id,
                            str(f.get("date")),
                            str(f.get("store_id")),
                            str(f.get("product_id")),
                            f.get("units_sold"),
                            f.get("on_promotion"),
                            f.get("transactions"),
                            _bool_a_int(f.get("event_active")),
                        )
                        for f in filas
                    ],
                )
            self._con.commit()
        return submission_id

    # -- Lectura (auditoría / export) -------------------------------------
    def contar_observaciones(self, *, client_id: str | None = None) -> int:
        """Nº de filas en ``observations`` (opcionalmente filtrado por ``client_id``)."""
        with self._lock:
            if client_id is None:
                fila = self._con.execute("SELECT COUNT(*) FROM observations").fetchone()
            else:
                fila = self._con.execute(
                    "SELECT COUNT(*) FROM observations WHERE client_id = ?", (client_id,)
                ).fetchone()
        return int(fila[0])

    def conexion(self) -> sqlite3.Connection:
        """Conexión subyacente (para lectura en scripts de export). Úsese con cuidado."""
        return self._con

    # -- Ciclo de vida -----------------------------------------------------
    def cerrar(self) -> None:
        """Cierra la conexión SQLite (idempotente ante errores)."""
        with self._lock:
            try:
                self._con.close()
            except Exception as exc:  # noqa: BLE001 - cierre best-effort
                log.warning("No se pudo cerrar la base de corpus: %s", exc)
