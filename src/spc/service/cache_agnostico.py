"""Caché de modelos **agnósticos auto-entrenados** por (cliente, esquema, datos).

La predicción agnóstica entrena el modelo en la misma llamada (ADR-0023). Reentrenar
el zoo en **cada** petición sería caro, así que se cachea el predictor entrenado y se
**reusa** si vuelve a llegar la misma data con el mismo esquema; si la data cambia
(el cliente aporta historia nueva), la firma cambia y el modelo se **reentrena** solo
—ese es el "auto-aprendizaje" del sistema: aprende cuando hay datos nuevos.

Dos niveles: memoria (por proceso, acotada) y disco (sobrevive reinicios). El disco
guarda **un** artefacto por (cliente, dominio, esquema): la data nueva lo sobreescribe,
de modo que el almacén no crece sin control. Reutiliza el saneo de `slug_cliente`
(anti path-traversal) y la serialización joblib del motor.
"""

from __future__ import annotations

import hashlib
import json
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Any

from spc.training.almacen import slug_cliente
from spc.utils.logging import get_logger
from spc.utils.serializacion import cargar_artefacto, guardar_artefacto

log = get_logger("service.cache_agnostico")

SUBDIR = "agnostico"
_MEM_MAX = 32  # artefactos en memoria por proceso (LRU)


def firma_esquema(dominio: str, schema: dict[str, Any]) -> str:
    """Hash estable del esquema declarado (clave de caché por cliente/dominio)."""
    payload = json.dumps({"dominio": dominio, "schema": schema}, sort_keys=True, default=str)
    return hashlib.blake2b(payload.encode("utf-8"), digest_size=8).hexdigest()


def firma_datos(rows: list[dict[str, Any]]) -> str:
    """Hash del bloque de datos (filas). Cambia ⇒ el modelo se reentrena."""
    payload = json.dumps(rows, sort_keys=True, default=str)
    return hashlib.blake2b(payload.encode("utf-8"), digest_size=8).hexdigest()


class CacheModelosAgnosticos:
    """Resuelve (memoria→disco) o entrena-y-guarda el predictor agnóstico de un cliente."""

    def __init__(self, root: Path) -> None:
        self._root = Path(root)
        self._mem: OrderedDict[str, tuple[str, Any, dict[str, Any]]] = OrderedDict()
        self._lock = threading.Lock()

    # --- rutas ---
    def _dir(self, client_id: str) -> Path:
        return self._root / slug_cliente(client_id) / SUBDIR

    def _ruta(self, client_id: str, dominio: str, sig_esquema: str) -> Path:
        return self._dir(client_id) / f"{dominio}__{sig_esquema}.joblib"

    def _clave_mem(self, client_id: str, dominio: str, sig_esquema: str) -> str:
        return f"{slug_cliente(client_id)}|{dominio}|{sig_esquema}"

    # --- API ---
    def obtener(
        self, client_id: str, dominio: str, sig_esquema: str, sig_datos: str
    ) -> tuple[Any, dict[str, Any]] | None:
        """Devuelve ``(predictor, info)`` si hay uno entrenado con la **misma** data; si no, ``None``."""
        clave = self._clave_mem(client_id, dominio, sig_esquema)
        with self._lock:
            cacheado = self._mem.get(clave)
            if cacheado is not None and cacheado[0] == sig_datos:
                self._mem.move_to_end(clave)
                return cacheado[1], cacheado[2]
        ruta = self._ruta(client_id, dominio, sig_esquema)
        if not ruta.exists():
            return None
        try:
            objeto, meta = cargar_artefacto(ruta)
        except Exception as exc:  # noqa: BLE001 - caché best-effort: nunca romper la predicción
            log.warning("No se pudo cargar modelo agnóstico cacheado (%s): %s", ruta.name, exc)
            return None
        if meta.get("sig_datos") != sig_datos:
            return None  # la data cambió → el llamador reentrena
        info = meta.get("info", {})
        with self._lock:
            self._guardar_mem(clave, sig_datos, objeto, info)
        return objeto, info

    def guardar(
        self,
        client_id: str,
        dominio: str,
        sig_esquema: str,
        sig_datos: str,
        predictor: Any,
        info: dict[str, Any],
    ) -> None:
        """Persiste (memoria + disco) el predictor entrenado. Best-effort en disco."""
        clave = self._clave_mem(client_id, dominio, sig_esquema)
        with self._lock:
            self._guardar_mem(clave, sig_datos, predictor, info)
        ruta = self._ruta(client_id, dominio, sig_esquema)
        try:
            ruta.parent.mkdir(parents=True, exist_ok=True)
            guardar_artefacto(
                predictor, ruta,
                {"dominio": dominio, "sig_esquema": sig_esquema, "sig_datos": sig_datos,
                 "client_id": client_id, "info": info},
            )
        except Exception as exc:  # noqa: BLE001 - el disco es opcional; la predicción ya se resolvió
            log.warning("No se pudo persistir modelo agnóstico (%s): %s", ruta.name, exc)

    def _guardar_mem(self, clave: str, sig_datos: str, objeto: Any, info: dict[str, Any]) -> None:
        self._mem[clave] = (sig_datos, objeto, info)
        self._mem.move_to_end(clave)
        while len(self._mem) > _MEM_MAX:
            self._mem.popitem(last=False)
