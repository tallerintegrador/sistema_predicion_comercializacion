"""Creación del engine SQLAlchemy y la fábrica de sesiones (ADR-0026).

Un único engine sirve a toda la app; se resuelve desde :func:`spc.config.database_url`
(Postgres/Supabase en producción, SQLite en dev/tests). Los repositorios (auth, corpus,
modelos) comparten ese engine para que "una base de datos para todo" sea literal.

- SQLite: se fuerza ``check_same_thread=False`` (la API es multi-hilo) y, para
  ``:memory:``, un ``StaticPool`` que mantiene la MISMA conexión (si no, cada hilo vería
  una base vacía distinta). Se crea la carpeta del archivo si hace falta.
- Postgres: ``pool_pre_ping=True`` para reciclar conexiones muertas del pooler de Supabase.
"""

from __future__ import annotations

import threading
from pathlib import Path

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from spc.config import database_url
from spc.db.orm import Base
from spc.utils.logging import get_logger

log = get_logger("db.engine")

_engine: Engine | None = None
_Session: sessionmaker[Session] | None = None
_lock = threading.Lock()


def crear_engine(url: str) -> Engine:
    """Construye un :class:`Engine` con las opciones correctas según el motor de la ``url``."""
    if url.startswith("sqlite"):
        # Ruta de archivo entre ``sqlite:///`` y el final (vacío para ``:memory:``).
        ruta = url.split("sqlite:///", 1)[-1] if ":///" in url else ""
        es_memoria = ruta in ("", ":memory:")
        connect_args = {"check_same_thread": False}
        if es_memoria:
            return create_engine(
                url, connect_args=connect_args, poolclass=StaticPool, future=True
            )
        Path(ruta).expanduser().parent.mkdir(parents=True, exist_ok=True)
        return create_engine(url, connect_args=connect_args, future=True)
    # Postgres u otros: pre-ping para sobrevivir a conexiones cerradas por el pooler.
    return create_engine(url, pool_pre_ping=True, future=True)


def obtener_engine() -> Engine:
    """Devuelve el engine global (perezoso, thread-safe) y asegura el esquema."""
    global _engine, _Session
    if _engine is None:
        with _lock:
            if _engine is None:
                url = database_url()
                log.info("Abriendo base de datos: %s", _url_segura(url))
                _engine = crear_engine(url)
                _Session = sessionmaker(bind=_engine, expire_on_commit=False, future=True)
                crear_todo(_engine)
    return _engine


def obtener_sesion() -> Session:
    """Abre una nueva sesión ligada al engine global (recuerda cerrarla)."""
    if _Session is None:
        obtener_engine()
    assert _Session is not None  # noqa: S101 - garantizado por obtener_engine
    return _Session()


def crear_todo(engine: Engine) -> None:
    """Crea todas las tablas del ORM si no existen (idempotente)."""
    Base.metadata.create_all(engine)


def reset_engine() -> None:
    """Descarta el engine global (para tests que cambian de base entre casos)."""
    global _engine, _Session
    with _lock:
        if _engine is not None:
            _engine.dispose()
        _engine = None
        _Session = None


def _url_segura(url: str) -> str:
    """Oculta la contraseña de una URL para loguearla sin filtrar credenciales."""
    if "@" not in url:
        return url
    esquema, resto = url.split("://", 1) if "://" in url else ("", url)
    credenciales, host = resto.split("@", 1)
    usuario = credenciales.split(":", 1)[0]
    return f"{esquema}://{usuario}:***@{host}"
