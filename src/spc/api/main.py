"""App factory de FastAPI para el SPC.

Arma la aplicación: CORS, control de acceso (lifespan), registro de routers y
documentación Swagger/OpenAPI. Levantar en desarrollo:

    uvicorn spc.api.main:app --reload

El servicio expone dos motores de predicción **entrenados en el momento** (sin
artefactos congelados): el agnóstico auto-entrenado (``/auto/*``, ADR-0023) y el
3×3 por dominio (``/v2/*``, ADR-0024/0025). `crear_app` permite inyectar un
repositorio de auth ya abierto (lo usan los tests) sin tocar el disco real.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from spc.api.errors import registrar_manejadores
from spc.api.routers import (
    agnostico,
    auth,
    dominios_3x3,
)
from spc.config import (
    auth_enabled,
    auth_secret_es_default,
    db_path,
)
from spc.config import client_models_dir as cfg_client_models_dir
from spc.service.cache_agnostico import CacheModelosAgnosticos
from spc.service.repositorio_auth import RepositorioAuth
from spc.utils.logging import get_logger

log = get_logger("api.main")

DESCRIPCION = """
**Sistema Predictivo de Comercialización** — servicio de pronóstico para PYMEs,
agnóstico al sector. Dos motores, ambos **entrenados en el momento** con los datos
que envía el cliente (sin modelos congelados):

- **AUTO** (`/auto/*`) — predicción **agnóstica auto-entrenada** (ADR-0023): el
  cliente declara su propio esquema y trae las columnas que tenga; el backend entrena
  el mejor modelo con validación honesta y predice en una sola llamada.
- **3×3** (`/v2/{ventas,compras,almacen}`) — un **formato fijo por dominio** que
  alimenta los tres modelos (regresión, clasificación, clustering) con scikit-learn
  liviano (ADR-0024/0025). Cada dominio ofrece además un endpoint `/demo` con datos
  sintéticos del propio sistema.

La entrada se valida contra el esquema; las entradas mal formadas devuelven un
error controlado y uniforme.
"""

TAGS_METADATA = [
    {"name": "AUTO", "description": "Predicción agnóstica auto-entrenada: el cliente declara su esquema y columnas (ADR-0023)."},
    {"name": "3X3", "description": "Rediseño 3×3: un formato por dominio (ventas/compras/almacén) que alimenta los tres modelos (regresión, clasificación, clustering) entrenados en el momento."},
    {"name": "auth", "description": "Control de acceso por roles: login, identidad, administración de usuarios y perfil."},
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
    auth_repo: RepositorioAuth | None = None,
    client_models_dir: Path | None = None,
    cors_origins: list[str] | None = None,
) -> FastAPI:
    """Construye y configura la aplicación FastAPI.

    - ``auth_repo``: repositorio de auth ya abierto a inyectar (tests). Si es ``None`` y
      el control de acceso está activo (``SPC_AUTH_ENABLED``), se abre en el lifespan.
    - ``client_models_dir``: carpeta de la caché de modelos agnósticos auto-entrenados
      (ADR-0023). Si es ``None`` se usa ``SPC_CLIENT_MODELS_DIR``. Los tests inyectan una
      carpeta temporal para no tocar el repo.
    - ``cors_origins``: orígenes permitidos (por defecto, los de ``SPC_CORS_ORIGINS``).
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Control de acceso por roles (ADR-0014): abre la base de auth y siembra los admins.
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
    if auth_repo is not None:
        app.state.auth = auth_repo

    # Caché de modelos agnósticos auto-entrenados (ADR-0023): siempre disponible.
    cmd = client_models_dir or cfg_client_models_dir()
    app.state.client_models_dir = cmd
    app.state.cache_agnostico = CacheModelosAgnosticos(cmd)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins if cors_origins is not None else _origenes_cors(),
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    registrar_manejadores(app)
    app.include_router(auth.router)
    app.include_router(agnostico.router)
    app.include_router(dominios_3x3.router)

    @app.get("/health", tags=["status"], summary="Salud del servicio")
    def salud() -> dict[str, str]:
        """Comprueba que el servicio está arriba."""
        return {"status": "ok"}

    return app


# Instancia para servidores ASGI (uvicorn spc.api.main:app).
app = crear_app()
