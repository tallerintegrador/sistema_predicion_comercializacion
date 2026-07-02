"""Registro de modelos entrenados por cliente (ADR-0026).

Sustituye el almacenamiento en disco suelto de :mod:`spc.training.almacen`
(``adopcion.json``, versionado por carpeta) por una tabla ``models`` en la base + el
artefacto ``.joblib`` en un **bucket de Supabase Storage**. Si Storage no está configurado
(``SUPABASE_*`` ausentes), cae a **disco local** bajo ``client_models_dir()``: la
funcionalidad no cambia, solo dónde viven los bytes.

Flujo del reentrenamiento (ADR-0026):

1. :meth:`registrar_version` guarda una nueva versión (métricas + puntero al artefacto).
2. Si ``adoptar=True`` marca esa versión como la que se sirve (``is_serving``) y desmarca
   la anterior del mismo ``(tenant, dominio, tarea)``.
3. :meth:`cargar_adoptado` devuelve el objeto entrenado que se sirve (o ``None`` → sin
   modelo propio; el llamador cae a su comportamiento por defecto).
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib
from sqlalchemy import Engine, func, select, update
from sqlalchemy.orm import Session, sessionmaker

from spc.config import (
    client_models_dir,
    storage_habilitado,
    supabase_bucket,
    supabase_key,
    supabase_url,
)
from spc.db.orm import ModeloEntrenado, Prediction, TrainingRun
from spc.training.almacen import slug_cliente
from spc.utils.logging import get_logger

log = get_logger("service.repositorio_modelos")


@dataclass(frozen=True)
class ModeloInfo:
    """Vista de solo lectura de una versión registrada (lo que va a la API/frontend)."""

    id: int
    tenant_id: str
    domain: str
    task: str
    version: int
    algorithm: str | None
    metrics: dict | None
    status: str
    is_serving: bool
    storage_uri: str | None
    trained_rows: int
    trained_at: str


def _ahora_iso() -> str:
    return datetime.now(UTC).isoformat()


def _a_bytes(objeto: Any) -> bytes:
    """Serializa un objeto entrenado a bytes joblib (en memoria)."""
    buf = io.BytesIO()
    joblib.dump(objeto, buf)
    return buf.getvalue()


def _desde_bytes(datos: bytes) -> Any:
    """Reconstruye el objeto entrenado desde bytes joblib."""
    return joblib.load(io.BytesIO(datos))


class RepositorioModelos:
    """Registro (tabla ``models``) + almacén de artefactos (Supabase Storage o disco)."""

    def __init__(self, engine: Engine, dir_artefactos: Path | None = None) -> None:
        self._engine = engine
        self._Session: sessionmaker[Session] = sessionmaker(
            bind=engine, expire_on_commit=False, future=True
        )
        # Carpeta del fallback a disco cuando Storage no está configurado. Inyectable para que
        # los tests escriban en un temporal y no ensucien ``models/clientes`` del repo.
        self._dir_artefactos = dir_artefactos or client_models_dir()
        self._cliente_supabase = None  # perezoso

    # -- Escritura ---------------------------------------------------------
    def registrar_version(
        self,
        *,
        tenant_id: str,
        domain: str,
        task: str,
        objeto: Any,
        algorithm: str | None,
        metrics: dict | None,
        status: str,
        trained_rows: int,
        adoptar: bool,
    ) -> ModeloInfo:
        """Guarda una nueva versión del modelo y (si ``adoptar``) la marca como servida."""
        with self._Session() as s, s.begin():
            version = self._siguiente_version(s, tenant_id, domain, task)
            uri = self._subir_artefacto(tenant_id, domain, task, version, _a_bytes(objeto))
            if adoptar:
                # Solo una versión servida por (tenant, dominio, tarea).
                s.execute(
                    update(ModeloEntrenado)
                    .where(
                        ModeloEntrenado.tenant_id == tenant_id,
                        ModeloEntrenado.domain == domain,
                        ModeloEntrenado.task == task,
                    )
                    .values(is_serving=False)
                )
            modelo = ModeloEntrenado(
                tenant_id=tenant_id,
                domain=domain,
                task=task,
                version=version,
                algorithm=algorithm,
                metrics=metrics,
                status=status,
                is_serving=adoptar,
                storage_uri=uri,
                trained_rows=trained_rows,
                trained_at=_ahora_iso(),
            )
            s.add(modelo)
            s.flush()
            info = self._info(modelo)
        log.info(
            "Modelo registrado %s/%s/%s v%d (status=%s, servido=%s)",
            tenant_id, domain, task, version, status, adoptar,
        )
        return info

    def marcar_adopcion(self, model_id: int, *, servir: bool = True) -> ModeloInfo | None:
        """Conmuta qué versión se sirve (reversible). Desmarca a las hermanas si ``servir``."""
        with self._Session() as s, s.begin():
            modelo = s.get(ModeloEntrenado, model_id)
            if modelo is None:
                return None
            if servir:
                s.execute(
                    update(ModeloEntrenado)
                    .where(
                        ModeloEntrenado.tenant_id == modelo.tenant_id,
                        ModeloEntrenado.domain == modelo.domain,
                        ModeloEntrenado.task == modelo.task,
                    )
                    .values(is_serving=False)
                )
            modelo.is_serving = servir
            return self._info(modelo)

    # -- Lectura -----------------------------------------------------------
    def cargar_adoptado(self, tenant_id: str, domain: str, task: str) -> tuple[Any, ModeloInfo] | None:
        """Devuelve ``(objeto, info)`` de la versión servida, o ``None`` si no hay."""
        with self._Session() as s:
            modelo = s.scalar(
                select(ModeloEntrenado).where(
                    ModeloEntrenado.tenant_id == tenant_id,
                    ModeloEntrenado.domain == domain,
                    ModeloEntrenado.task == task,
                    ModeloEntrenado.is_serving.is_(True),
                )
            )
            if modelo is None or not modelo.storage_uri:
                return None
            info = self._info(modelo)
        datos = self._bajar_artefacto(info.storage_uri)  # type: ignore[arg-type]
        return _desde_bytes(datos), info

    def registrar_reentrenamiento(
        self, *, tenant_id: str, domain: str, status: str, corpus_rows: int, result: dict | None
    ) -> int:
        """Guarda una fila de trazado del reentrenamiento (``training_runs``) y devuelve su id."""
        ahora = _ahora_iso()
        with self._Session() as s, s.begin():
            run = TrainingRun(
                tenant_id=tenant_id,
                domain=domain,
                status=status,
                corpus_rows=corpus_rows,
                started_at=ahora,
                finished_at=ahora,
                result=result,
            )
            s.add(run)
            s.flush()
            return int(run.id)

    def listar(self, tenant_id: str, domain: str | None = None) -> list[ModeloInfo]:
        """Lista las versiones registradas del cliente (opcionalmente de un dominio)."""
        with self._Session() as s:
            q = select(ModeloEntrenado).where(ModeloEntrenado.tenant_id == tenant_id)
            if domain is not None:
                q = q.where(ModeloEntrenado.domain == domain)
            q = q.order_by(
                ModeloEntrenado.domain, ModeloEntrenado.task, ModeloEntrenado.version.desc()
            )
            return [self._info(m) for m in s.scalars(q).all()]

    def obtener(self, model_id: int) -> ModeloInfo | None:
        """Devuelve la versión por id (para validar propiedad antes de conmutar), o ``None``."""
        with self._Session() as s:
            modelo = s.get(ModeloEntrenado, model_id)
            return self._info(modelo) if modelo is not None else None

    def registrar_prediccion(
        self,
        *,
        tenant_id: str,
        domain: str,
        model_id: int | None,
        horizon: int | None,
        request: dict | None,
        response: dict | None,
    ) -> int:
        """Guarda una fila de auditoría de una predicción servida (tabla ``predictions``).

        ``request``/``response`` deben ser **resúmenes** (no el payload completo) para no
        inflar la base. Devuelve el id de la fila creada.
        """
        with self._Session() as s, s.begin():
            fila = Prediction(
                tenant_id=tenant_id,
                domain=domain,
                model_id=model_id,
                horizon=horizon,
                request=request,
                response=response,
                created_at=_ahora_iso(),
            )
            s.add(fila)
            s.flush()
            return int(fila.id)

    # -- Internos ----------------------------------------------------------
    @staticmethod
    def _siguiente_version(s: Session, tenant_id: str, domain: str, task: str) -> int:
        maxv = s.scalar(
            select(func.max(ModeloEntrenado.version)).where(
                ModeloEntrenado.tenant_id == tenant_id,
                ModeloEntrenado.domain == domain,
                ModeloEntrenado.task == task,
            )
        )
        return int(maxv or 0) + 1

    @staticmethod
    def _info(m: ModeloEntrenado) -> ModeloInfo:
        return ModeloInfo(
            id=int(m.id),
            tenant_id=m.tenant_id,
            domain=m.domain,
            task=m.task,
            version=int(m.version),
            algorithm=m.algorithm,
            metrics=m.metrics,
            status=m.status,
            is_serving=bool(m.is_serving),
            storage_uri=m.storage_uri,
            trained_rows=int(m.trained_rows),
            trained_at=m.trained_at,
        )

    # -- Almacén de artefactos (Storage o disco) ---------------------------
    def _ruta_relativa(self, tenant_id: str, domain: str, task: str, version: int) -> str:
        return f"{slug_cliente(tenant_id)}/{domain}_{task}_v{version}.joblib"

    def _subir_artefacto(
        self, tenant_id: str, domain: str, task: str, version: int, datos: bytes
    ) -> str:
        rel = self._ruta_relativa(tenant_id, domain, task, version)
        if storage_habilitado():
            cliente = self._supabase()
            cliente.storage.from_(supabase_bucket()).upload(
                path=rel,
                file=datos,
                file_options={"content-type": "application/octet-stream", "upsert": "true"},
            )
            return f"supabase://{supabase_bucket()}/{rel}"
        # Fallback a disco local.
        ruta = self._dir_artefactos / rel
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_bytes(datos)
        return ruta.as_uri()

    def _bajar_artefacto(self, uri: str) -> bytes:
        if uri.startswith("supabase://"):
            _, resto = uri.split("supabase://", 1)
            bucket, rel = resto.split("/", 1)
            return self._supabase().storage.from_(bucket).download(rel)
        if uri.startswith("file://"):
            from urllib.parse import urlparse
            from urllib.request import url2pathname

            return Path(url2pathname(urlparse(uri).path)).read_bytes()
        return Path(uri).read_bytes()

    def _supabase(self):
        """Cliente Supabase perezoso (solo si Storage está configurado)."""
        if self._cliente_supabase is None:
            from supabase import create_client

            self._cliente_supabase = create_client(supabase_url(), supabase_key())
        return self._cliente_supabase
