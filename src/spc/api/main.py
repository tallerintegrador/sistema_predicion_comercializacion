"""App factory de FastAPI para el SPC (Fase 3).

Arma la aplicación: CORS, carga de artefactos en el arranque (lifespan), registro
de routers (un POST por campo del contrato), manejadores de error y documentación
Swagger/OpenAPI. Levantar en desarrollo:

    uvicorn spc.api.main:app --reload

`crear_app` permite inyectar un `RegistroArtefactos` ya cargado (lo usan los tests
con artefactos diminutos) o apuntar a otro directorio de modelos, sin tocar código.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from spc.api.errors import registrar_manejadores
from spc.api.jobs import GestorTrabajos
from spc.api.jobs_entrenamiento import GestorEntrenamientos
from spc.api.routers import (
    agnostico,
    almacen,
    auth,
    catalog,
    compras,
    dominios_3x3,
    entrenamiento,
    excel,
    jobs,
    ventas,
)
from spc.config import (
    Settings,
    auth_enabled,
    auth_secret_es_default,
    batch_workers,
    client_adjustment_enabled,
    db_enabled,
    db_path,
    training_workers,
)
from spc.config import client_models_dir as cfg_client_models_dir
from spc.service.artefactos import RegistroArtefactos
from spc.service.cache_agnostico import CacheModelosAgnosticos
from spc.service.modelo_cliente import ResolutorModeloCliente
from spc.service.repositorio import RepositorioPredicciones
from spc.service.repositorio_auth import RepositorioAuth
from spc.utils.logging import get_logger

log = get_logger("api.main")

DESCRIPCION = """
**Sistema Predictivo de Comercialización** — servicio de pronóstico para PYMEs,
agnóstico al sector. El cliente mapea su vocabulario a los **nombres genéricos del
contrato** (`store_id`, `product_id`, `units_sold`, ...) y recibe analítica por tres
campos:

- **SALES** (`/sales`) — pronóstico de demanda (regresión).
- **PURCHASES** (`/purchases`) — reposición sugerida (derivada del pronóstico + parámetros logísticos).
- **INVENTORY** (`/inventory`) — riesgo de quiebre y stock recomendado (clasificación + perfilado).

El **catálogo de predicciones** (`GET /catalog`) describe, por dominio, qué entra,
qué sale y qué limitaciones tiene cada servicio, derivado de los esquemas reales.

La entrada se valida contra el contrato; las entradas mal formadas devuelven un
error controlado y uniforme.
"""

TAGS_METADATA = [
    {"name": "SALES", "description": "Pronóstico de demanda por período, punto de venta y producto."},
    {"name": "PURCHASES", "description": "Cantidad a reponer y punto de reorden, derivados del pronóstico."},
    {"name": "INVENTORY", "description": "Clase de demanda, riesgo de quiebre, stock recomendado y segmento de tienda."},
    {"name": "AUTO", "description": "Predicción agnóstica auto-entrenada: el cliente declara su esquema y columnas (ADR-0023)."},
    {"name": "3X3", "description": "Rediseño 3×3: un formato por dominio (ventas/compras/almacén) que alimenta los tres modelos (regresión, clasificación, clustering) entrenados en el momento."},
    {"name": "catalog", "description": "Catálogo de predicciones por dominio (qué entra, qué sale, qué limita)."},
    {"name": "excel", "description": "Canal Excel: descarga de plantilla y carga de datos por dominio (mismo contrato)."},
    {"name": "batch", "description": "Modo por lote (asíncrono): estado y resultado de los envíos grandes (job_id)."},
    {"name": "status", "description": "Salud del servicio."},
]


def _origenes_cors() -> list[str]:
    """Orígenes CORS permitidos (coma-separados en ``SPC_CORS_ORIGINS``; ``*`` por defecto)."""
    valor = os.getenv("SPC_CORS_ORIGINS", "").strip()
    if not valor:
        return ["*"]
    return [o.strip() for o in valor.split(",") if o.strip()]


def crear_app(
    *,
    registro: RegistroArtefactos | None = None,
    repositorio: RepositorioPredicciones | None = None,
    auth_repo: RepositorioAuth | None = None,
    models_dir: Path | None = None,
    client_models_dir: Path | None = None,
    cors_origins: list[str] | None = None,
) -> FastAPI:
    """Construye y configura la aplicación FastAPI.

    - ``registro``: artefactos ya cargados a inyectar (tests). Si es ``None``, se
      cargan en el lifespan desde ``models_dir`` (o ``<base>/models`` por defecto).
    - ``repositorio``: almacén de corpus a inyectar (tests). Si es ``None`` y la
      persistencia está activa (``SPC_PERSIST_ENABLED``), se abre en el lifespan desde
      ``db_path()``. Ver ADR-0011 (Fase A MEJORADO).
    - ``client_models_dir``: carpeta de artefactos por cliente (ADR-0013). Si es ``None``
      se usa ``SPC_CLIENT_MODELS_DIR`` (o ``<base>/models/clientes``). Los tests inyectan
      una carpeta temporal para no tocar el repo.
    - ``cors_origins``: orígenes permitidos (por defecto, los de ``SPC_CORS_ORIGINS``).
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Carga perezosa en el arranque: solo si no se inyectó un registro.
        if getattr(app.state, "registro", None) is None:
            md = models_dir or (Settings().base_dir / "models")
            log.info("Cargando artefactos del motor desde %s ...", md)
            app.state.registro = RegistroArtefactos.cargar(md)
            log.info(
                "Motor listo: %s, %s, %s",
                app.state.registro.regresion.ruta.name,
                app.state.registro.clasificacion.ruta.name,
                app.state.registro.clustering_tiendas.ruta.name,
            )
        # Persistencia del corpus: solo si no se inyectó y está activa por entorno.
        if getattr(app.state, "repositorio", None) is None and db_enabled():
            ruta = db_path()
            log.info("Abriendo corpus incremental en %s ...", ruta)
            app.state.repositorio = RepositorioPredicciones.crear(ruta)
        # Control de acceso por roles (ADR-0014): abre la base de auth y siembra los admins.
        # Es independiente de SPC_PERSIST_ENABLED (la auth no es opcional como el corpus).
        if getattr(app.state, "auth", None) is None and auth_enabled():
            ruta = db_path()
            log.info("Abriendo control de acceso en %s ...", ruta)
            app.state.auth = RepositorioAuth.crear(ruta)
            if auth_secret_es_default():
                log.warning(
                    "SPC_AUTH_SECRET no está configurado: se usa el secreto de DESARROLLO "
                    "(los tokens son falsificables). Fíjelo en producción."
                )
        try:
            yield
        finally:
            # Apaga el executor de lote esperando a los trabajos en curso.
            app.state.jobs.cerrar()
            # Apaga el executor de entrenamiento por cliente (si está activo).
            if getattr(app.state, "entrenamientos", None) is not None:
                app.state.entrenamientos.cerrar()
            # Cierra la base del corpus (si se abrió).
            if getattr(app.state, "repositorio", None) is not None:
                app.state.repositorio.cerrar()
            # Cierra la base de auth (si se abrió).
            if getattr(app.state, "auth", None) is not None:
                app.state.auth.cerrar()

    app = FastAPI(
        title="SPC — Sistema Predictivo de Comercialización",
        description=DESCRIPCION,
        version="0.1.0",
        openapi_tags=TAGS_METADATA,
        lifespan=lifespan,
    )

    # Inyección directa (tests): disponible aunque no se ejecute el lifespan.
    if registro is not None:
        app.state.registro = registro
    if repositorio is not None:
        app.state.repositorio = repositorio
    if auth_repo is not None:
        app.state.auth = auth_repo

    # Gestor de trabajos por lote (in-process): se crea siempre, de modo que esté
    # disponible aunque el registro se inyecte directamente. Se cierra en el lifespan.
    app.state.jobs = GestorTrabajos(max_workers=batch_workers())

    # Ajuste por cliente bajo demanda (ADR-0013): resolutor de serving + executor de
    # entrenamiento (separado del de lote). Solo si está habilitado por entorno; si no, el
    # serving usa siempre el congelado y los endpoints de training responden 503.
    cmd = client_models_dir or cfg_client_models_dir()
    app.state.client_models_dir = cmd
    # Caché de modelos agnósticos auto-entrenados (ADR-0023): siempre disponible; reusa la
    # carpeta de artefactos por cliente (conviven sin pisarse con los del ADR-0013).
    app.state.cache_agnostico = CacheModelosAgnosticos(cmd)
    if client_adjustment_enabled():
        app.state.resolutor_cliente = ResolutorModeloCliente(cmd)
        app.state.entrenamientos = GestorEntrenamientos(max_workers=training_workers())
    else:
        app.state.resolutor_cliente = None
        app.state.entrenamientos = None

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins if cors_origins is not None else _origenes_cors(),
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    registrar_manejadores(app)
    app.include_router(auth.router)
    app.include_router(ventas.router)
    app.include_router(compras.router)
    app.include_router(almacen.router)
    app.include_router(agnostico.router)
    app.include_router(dominios_3x3.router)
    app.include_router(catalog.router)
    app.include_router(excel.router)
    app.include_router(jobs.router)
    app.include_router(entrenamiento.router)

    @app.get("/health", tags=["status"], summary="Salud del servicio")
    def salud() -> dict[str, str]:
        """Comprueba que el servicio está arriba (no valida la carga del motor)."""
        return {"status": "ok"}

    return app


# Instancia para servidores ASGI (uvicorn spc.api.main:app).
app = crear_app()
