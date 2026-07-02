"""Entidades SQLAlchemy del SPC (ADR-0026).

Un solo esquema para toda la plataforma. Tres bloques:

1. **Acceso** (``roles``, ``role_permissions``, ``users``, ``tenants``): antes vivían en el
   SQLite de ADR-0014; aquí son las mismas columnas, ahora agnósticas al motor.
2. **Corpus acumulativo** (``datasets``, ``observations``): el histórico de entrenamiento
   que crece por cliente y dominio. ``observations`` guarda cada fila del dominio como
   ``payload`` JSON, con dedup idempotente por ``(tenant, dominio, serie, fecha)``.
3. **Modelos y ejecución** (``models``, ``training_runs``, ``predictions``): registro de
   versiones entrenadas (con métricas y puntero al artefacto), trazado de reentrenamientos
   y auditoría de predicciones.

Notas de portabilidad (SQLite ⇆ Postgres):

- Los JSON usan :data:`JSONFlexible`, que se materializa como ``JSONB`` en Postgres y como
  ``JSON`` en SQLite.
- Las marcas de tiempo se guardan como texto ISO-8601 (``String``), igual que el esquema
  original de auth, para que las vistas de solo lectura no cambien.
- Los ``id`` autoincrementales son ``Integer`` (portátil); en Postgres se mapean a
  ``BIGSERIAL``/``SERIAL`` por SQLAlchemy.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# JSON portátil: JSONB en Postgres (indexable, binario), JSON genérico en SQLite.
JSONFlexible = JSON().with_variant(JSONB(), "postgresql")


class Base(DeclarativeBase):
    """Base declarativa compartida por todas las entidades (una sola ``metadata``)."""


# ---------------------------------------------------------------------------
# 1) Control de acceso (ADR-0014, ahora sobre SQLAlchemy)
# ---------------------------------------------------------------------------
class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)

    permissions: Mapped[list[RolePermission]] = relationship(
        back_populates="role", cascade="all, delete-orphan", passive_deletes=True
    )


class RolePermission(Base):
    __tablename__ = "role_permissions"

    role_id: Mapped[int] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )
    permission: Mapped[str] = mapped_column(String(120), primary_key=True)

    role: Mapped[Role] = relationship(back_populates="permissions")


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), nullable=False)
    client_id: Mapped[str] = mapped_column(String(120), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    onboarding_done: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)


class Tenant(Base):
    """Perfil de negocio del cliente (antes ``client_profiles``). Es la unidad de tenant."""

    __tablename__ = "tenants"

    client_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    business_name: Mapped[str] = mapped_column(String(255), nullable=False)
    sector: Mapped[str] = mapped_column(String(120), nullable=False)
    size: Mapped[str] = mapped_column(String(60), nullable=False)
    region: Mapped[str] = mapped_column(String(120), nullable=False)
    currency: Mapped[str] = mapped_column(String(20), nullable=False)
    owner_user_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)


# ---------------------------------------------------------------------------
# 2) Corpus acumulativo (núcleo del reentrenamiento con históricos + nuevos)
# ---------------------------------------------------------------------------
class Dataset(Base):
    """Auditoría de cada carga de datos (una fila por envío JSON/Excel)."""

    __tablename__ = "datasets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    domain: Mapped[str] = mapped_column(String(40), nullable=False)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)  # json | excel
    schema_spec: Mapped[dict | None] = mapped_column(JSONFlexible, nullable=True)
    n_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)


class Observation(Base):
    """Fila de entrenamiento acumulada. Dedup idempotente por serie+fecha (keep-first)."""

    __tablename__ = "observations"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "domain", "series_key", "event_date", name="uq_observacion_serie_fecha"
        ),
        Index("ix_obs_tenant_dominio", "tenant_id", "domain"),
        Index("ix_obs_serie", "tenant_id", "domain", "series_key", "event_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(120), nullable=False)
    domain: Mapped[str] = mapped_column(String(40), nullable=False)
    dataset_id: Mapped[int | None] = mapped_column(ForeignKey("datasets.id"), nullable=True)
    series_key: Mapped[str] = mapped_column(String(255), nullable=False)
    event_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    payload: Mapped[dict] = mapped_column(JSONFlexible, nullable=False)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)


# ---------------------------------------------------------------------------
# 3) Registro de modelos, reentrenamientos y predicciones
# ---------------------------------------------------------------------------
class ModeloEntrenado(Base):
    """Versión de modelo entrenada para un (tenant, dominio, tarea)."""

    __tablename__ = "models"
    __table_args__ = (
        UniqueConstraint("tenant_id", "domain", "task", "version", name="uq_modelo_version"),
        Index("ix_modelo_tenant_dominio", "tenant_id", "domain"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(120), nullable=False)
    domain: Mapped[str] = mapped_column(String(40), nullable=False)
    task: Mapped[str] = mapped_column(String(40), nullable=False)  # regresion|clasificacion|clustering
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    algorithm: Mapped[str | None] = mapped_column(String(120), nullable=True)
    metrics: Mapped[dict | None] = mapped_column(JSONFlexible, nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False)  # adopted|not_adopted|insufficient_data
    is_serving: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    storage_uri: Mapped[str | None] = mapped_column(String(500), nullable=True)
    trained_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    trained_at: Mapped[str] = mapped_column(String(40), nullable=False)


class TrainingRun(Base):
    """Trazado de un reentrenamiento (históricos + nuevos → entrenar → adoptar)."""

    __tablename__ = "training_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    domain: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # running|done|error
    corpus_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[str] = mapped_column(String(40), nullable=False)
    finished_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    result: Mapped[dict | None] = mapped_column(JSONFlexible, nullable=True)


class Prediction(Base):
    """Auditoría de una predicción servida (replay/trazabilidad)."""

    __tablename__ = "predictions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    domain: Mapped[str] = mapped_column(String(40), nullable=False)
    model_id: Mapped[int | None] = mapped_column(ForeignKey("models.id"), nullable=True)
    horizon: Mapped[int | None] = mapped_column(Integer, nullable=True)
    request: Mapped[dict | None] = mapped_column(JSONFlexible, nullable=True)
    response: Mapped[dict | None] = mapped_column(JSONFlexible, nullable=True)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)
