"""Almacén de artefactos **por cliente** (ADR-0013): namespaced, versionado, adopción.

Cada cliente que opta por entrenar tiene su propia carpeta bajo
``<client_models_dir>/<slug>/`` con:

- ``regresion_v{N}.joblib`` + ``.meta.json`` — el artefacto por cliente (portable: las
  clases viven en ``spc.models.regresion``, no en ``__main__``, igual que el congelado).
- ``comparacion_v{N}.json`` — el experimento medido (WAPE candidato vs congelado vs
  baseline, y el veredicto de adopción).
- ``adopcion.json`` — puntero: qué versión está **adoptada** y si se **sirve** a ese
  cliente. Reentrenar **incrementa N** (se conserva el historial); adoptar mueve el
  puntero. Sin este puntero (o con ``servir=false``) el cliente recibe el **congelado**.

Estos artefactos **conviven** con los congelados de ``models/`` sin reemplazarlos: el
camino por defecto queda intacto para quien no opta.

**Seguridad:** ``client_id`` llega de un header y se usa para nombrar una carpeta, así que
se **sanea** a un slug seguro + un hash corto del id original (:func:`slug_cliente`). El
hash garantiza unicidad (dos ids distintos nunca colisionan) y, junto al saneo, **impide
path-traversal** (``..``, ``/``, etc. no sobreviven).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import unicodedata
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from spc.utils.logging import get_logger
from spc.utils.serializacion import cargar_artefacto, guardar_artefacto

log = get_logger("training.almacen")

_VERSION_RE = re.compile(r"^regresion_v(\d+)\.joblib$")
_ADOPCION = "adopcion.json"
_NO_SEGURO_RE = re.compile(r"[^a-z0-9]+")


def slug_cliente(client_id: str) -> str:
    """Slug de carpeta **seguro y único** para un ``client_id``.

    Normaliza a ASCII, deja solo ``[a-z0-9-]`` y añade un hash corto del id original. El
    hash hace el mapeo inyectivo (sin colisiones) y el saneo elimina cualquier intento de
    path-traversal. P. ej. ``"ACME S.A."`` → ``"acme-s-a-1a2b3c4d"``.
    """
    crudo = (client_id or "").strip()
    base = unicodedata.normalize("NFKD", crudo).encode("ascii", "ignore").decode("ascii")
    base = _NO_SEGURO_RE.sub("-", base.lower()).strip("-")[:40]
    h = hashlib.blake2b(crudo.encode("utf-8"), digest_size=4).hexdigest()
    return f"{base}-{h}" if base else f"cliente-{h}"


def dir_cliente(root: Path, client_id: str) -> Path:
    """Carpeta del cliente bajo ``root`` (no la crea)."""
    return Path(root) / slug_cliente(client_id)


def _versiones(carpeta: Path) -> list[int]:
    """Versiones ``N`` presentes (de ``regresion_v{N}.joblib``), ascendentes."""
    if not carpeta.exists():
        return []
    vs: list[int] = []
    for ruta in carpeta.glob("regresion_v*.joblib"):
        m = _VERSION_RE.match(ruta.name)
        if m:
            vs.append(int(m.group(1)))
    return sorted(vs)


def siguiente_version(root: Path, client_id: str) -> int:
    """Próxima versión a escribir para el cliente (1 si no tiene ninguna)."""
    vs = _versiones(dir_cliente(root, client_id))
    return (vs[-1] + 1) if vs else 1


def ruta_version(root: Path, client_id: str, version: int) -> Path:
    """Ruta del ``.joblib`` de una versión concreta del cliente."""
    return dir_cliente(root, client_id) / f"regresion_v{version}.joblib"


def etiqueta_version(client_id: str, version: int) -> str:
    """Etiqueta legible del modelo por cliente (va al ``meta.version`` y a la respuesta)."""
    return f"regresion_cliente_{slug_cliente(client_id)}_v{version}"


def _ahora() -> str:
    return datetime.now(UTC).isoformat()


def guardar_modelo(
    root: Path,
    client_id: str,
    *,
    predictor: Any,
    meta: dict[str, Any],
    comparacion: dict[str, Any],
) -> tuple[int, Path]:
    """Serializa una versión nueva del modelo del cliente + su comparación.

    Devuelve ``(version, ruta_joblib)``. No mueve el puntero de adopción (eso es decisión
    del orquestador, :func:`marcar_adopcion`). Estampa en el meta la etiqueta de versión
    y el ``client_id`` original para trazabilidad.
    """
    carpeta = dir_cliente(root, client_id)
    carpeta.mkdir(parents=True, exist_ok=True)
    version = siguiente_version(root, client_id)

    meta = dict(meta)
    meta["version"] = etiqueta_version(client_id, version)
    meta["client_id"] = client_id
    meta["slug"] = slug_cliente(client_id)
    meta["version_cliente"] = version

    ruta = carpeta / f"regresion_v{version}.joblib"
    guardar_artefacto(predictor, ruta, meta)
    (carpeta / f"comparacion_v{version}.json").write_text(
        json.dumps(comparacion, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    log.info("Modelo por cliente guardado: %s (v%d)", meta["version"], version)
    return version, ruta


def leer_comparacion(root: Path, client_id: str, version: int) -> dict[str, Any] | None:
    """Lee el experimento (``comparacion_v{N}.json``) de una versión, o ``None``."""
    ruta = dir_cliente(root, client_id) / f"comparacion_v{version}.json"
    if not ruta.exists():
        return None
    return json.loads(ruta.read_text(encoding="utf-8"))


def leer_adopcion(root: Path, client_id: str) -> dict[str, Any] | None:
    """Lee el puntero de adopción del cliente (``adopcion.json``), o ``None`` si no existe."""
    ruta = dir_cliente(root, client_id) / _ADOPCION
    if not ruta.exists():
        return None
    return json.loads(ruta.read_text(encoding="utf-8"))


def _escribir_adopcion(root: Path, client_id: str, datos: dict[str, Any]) -> dict[str, Any]:
    """Escribe ``adopcion.json`` de forma **atómica** (tmp + replace).

    El puntero lo escribe el hilo de entrenamiento y lo lee el de serving en cada
    predicción; el reemplazo atómico evita que el lector vea un JSON a medio escribir.
    """
    carpeta = dir_cliente(root, client_id)
    carpeta.mkdir(parents=True, exist_ok=True)
    datos = {**datos, "actualizado_utc": _ahora()}
    destino = carpeta / _ADOPCION
    tmp = destino.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(datos, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    os.replace(tmp, destino)
    return datos


def marcar_adopcion(
    root: Path, client_id: str, version: int, *, servir: bool = True
) -> dict[str, Any]:
    """Adopta la versión ``version`` del cliente y deja si se sirve (auto-servir por defecto).

    Esta es la decisión honesta tras el experimento: solo se llama cuando el candidato
    **superó** al congelado. ``servir=True`` hace que ese cliente empiece a recibir su
    modelo de inmediato (reversible con :func:`set_servir`).
    """
    return _escribir_adopcion(
        root,
        client_id,
        {"version_adoptada": version, "servir": bool(servir)},
    )


def set_servir(root: Path, client_id: str, servir: bool) -> dict[str, Any]:
    """Activa/desactiva servir con el modelo por cliente (switch reversible).

    Conserva la versión adoptada; solo cambia ``servir``. Si el cliente no tiene adopción
    previa, no hay nada que servir y se devuelve un puntero ``servir`` sin versión.
    """
    actual = leer_adopcion(root, client_id) or {"version_adoptada": None}
    return _escribir_adopcion(
        root,
        client_id,
        {"version_adoptada": actual.get("version_adoptada"), "servir": bool(servir)},
    )


def version_servida(root: Path, client_id: str) -> int | None:
    """Versión por cliente que debe servirse, o ``None`` (→ usar el congelado).

    ``None`` si no hay adopción, si ``servir=false`` o si el artefacto de esa versión no
    está en disco. Es la **única** condición que desvía el serving del modelo congelado.
    """
    ad = leer_adopcion(root, client_id)
    if not ad or not ad.get("servir"):
        return None
    version = ad.get("version_adoptada")
    if version is None:
        return None
    if not ruta_version(root, client_id, int(version)).exists():
        return None
    return int(version)


def cargar_modelo_adoptado(root: Path, client_id: str) -> tuple[Any, dict[str, Any]] | None:
    """Carga ``(objeto, meta)`` del modelo por cliente a servir, o ``None`` si toca el congelado."""
    version = version_servida(root, client_id)
    if version is None:
        return None
    return cargar_artefacto(ruta_version(root, client_id, version))


def estado(root: Path, client_id: str) -> dict[str, Any]:
    """Resumen para el endpoint de estado: ¿tiene modelo? ¿adoptado? ¿se sirve? última comparación."""
    carpeta = dir_cliente(root, client_id)
    vs = _versiones(carpeta)
    ad = leer_adopcion(root, client_id) or {}
    version_adoptada = ad.get("version_adoptada")
    comparacion = (
        leer_comparacion(root, client_id, int(version_adoptada))
        if version_adoptada is not None
        else (leer_comparacion(root, client_id, vs[-1]) if vs else None)
    )
    return {
        "client_id": client_id,
        "slug": slug_cliente(client_id),
        "versiones_entrenadas": vs,
        "version_adoptada": version_adoptada,
        "serving_cliente": version_servida(root, client_id) is not None,
        "model_version": (
            etiqueta_version(client_id, int(version_adoptada))
            if version_adoptada is not None
            else None
        ),
        "ultima_comparacion": comparacion,
    }
