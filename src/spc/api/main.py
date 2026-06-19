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
from spc.api.routers import almacen, catalog, compras, excel, jobs, ventas
from spc.config import Settings, batch_workers
from spc.service.artefactos import RegistroArtefactos
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
    models_dir: Path | None = None,
    cors_origins: list[str] | None = None,
) -> FastAPI:
    """Construye y configura la aplicación FastAPI.

    - ``registro``: artefactos ya cargados a inyectar (tests). Si es ``None``, se
      cargan en el lifespan desde ``models_dir`` (o ``<base>/models`` por defecto).
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
        try:
            yield
        finally:
            # Apaga el executor de lote esperando a los trabajos en curso.
            app.state.jobs.cerrar()

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

    # Gestor de trabajos por lote (in-process): se crea siempre, de modo que esté
    # disponible aunque el registro se inyecte directamente. Se cierra en el lifespan.
    app.state.jobs = GestorTrabajos(max_workers=batch_workers())

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins if cors_origins is not None else _origenes_cors(),
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    registrar_manejadores(app)
    app.include_router(ventas.router)
    app.include_router(compras.router)
    app.include_router(almacen.router)
    app.include_router(catalog.router)
    app.include_router(excel.router)
    app.include_router(jobs.router)

    @app.get("/health", tags=["status"], summary="Salud del servicio")
    def salud() -> dict[str, str]:
        """Comprueba que el servicio está arriba (no valida la carga del motor)."""
        return {"status": "ok"}

    return app


# Instancia para servidores ASGI (uvicorn spc.api.main:app).
app = crear_app()
