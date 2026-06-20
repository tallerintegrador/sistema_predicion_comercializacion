"""Resolución del artefacto de regresión **por cliente** en serving (ADR-0013).

En cada predicción de SALES, decide qué artefacto sirve a un ``client_id``:

- si el cliente tiene un modelo por cliente **adoptado y activo** (``servir=true``) → ese;
- en cualquier otro caso → el **congelado** (el camino por defecto, intacto byte a byte).

Solo un experimento ganador crea esa entrada (``spc.training.cliente``), así que el
default queda sin cambios para quien no opta. Cachea el ``.joblib`` por cliente (clave:
slug + versión) para no recargarlo en cada petición; si el cliente reentrena y adopta una
versión nueva, la clave cambia y se recarga sola.
"""

from __future__ import annotations

import threading
from pathlib import Path

from spc.service.artefactos import ArtefactoCargado
from spc.training import almacen
from spc.utils.logging import get_logger

log = get_logger("service.modelo_cliente")


class ResolutorModeloCliente:
    """Resuelve (y cachea) el artefacto de regresión a servir por ``client_id``."""

    def __init__(self, root: Path) -> None:
        self._root = Path(root)
        self._cache: dict[str, tuple[int, ArtefactoCargado]] = {}
        self._lock = threading.Lock()

    def resolver_regresion(
        self, client_id: str, congelado: ArtefactoCargado
    ) -> ArtefactoCargado:
        """Artefacto de regresión para este cliente: el suyo si está adoptado, si no el congelado."""
        try:
            version = almacen.version_servida(self._root, client_id)
        except Exception as exc:  # noqa: BLE001 - frontera: nunca romper la predicción
            log.warning("No se pudo resolver el modelo por cliente (%s): %s", client_id, exc)
            return congelado
        if version is None:
            return congelado

        slug = almacen.slug_cliente(client_id)
        with self._lock:
            cacheado = self._cache.get(slug)
            if cacheado is not None and cacheado[0] == version:
                return cacheado[1]
        # Carga fuera del lock (joblib puede tardar); el cache se rellena tras cargar.
        cargado = almacen.cargar_modelo_adoptado(self._root, client_id)
        if cargado is None:
            return congelado
        objeto, meta = cargado
        art = ArtefactoCargado(
            objeto=objeto,
            meta=meta,
            ruta=almacen.ruta_version(self._root, client_id, version),
        )
        with self._lock:
            self._cache[slug] = (version, art)
        log.info("Sirviendo modelo por cliente %s (%s)", client_id, meta.get("version"))
        return art

    def invalidar(self, client_id: str) -> None:
        """Olvida el artefacto cacheado de un cliente (tras reentrenar/cambiar el switch)."""
        with self._lock:
            self._cache.pop(almacen.slug_cliente(client_id), None)
