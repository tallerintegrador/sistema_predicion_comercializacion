"""Vocabulario controlado de permisos del control de acceso por roles (ADR-0014).

Un permiso se identifica con una **clave en inglés** (contrato): ``module:<dominio>``
para el acceso a un módulo y ``action:<verbo>`` para una acción transversal. Esta es la
**única fuente** del vocabulario: la siembra de roles, el enforcement por endpoint y el
catálogo de permisos (``GET /permissions``) la consumen, de modo que no hay listas
paralelas que se desincronicen.

**Sin hardcodeo de módulos:** los permisos de módulo se DERIVAN de los dominios reales
del catálogo (``spc.api.catalog``), no de una lista fija aquí. Si mañana el catálogo
expone un dominio nuevo, su permiso de módulo aparece solo. Las acciones, en cambio, son
vocabulario operacional del backend (no salen de un artefacto) y sí se declaran aquí.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Permiso:
    """Una entrada del catálogo de permisos: clave en inglés + etiqueta en español."""

    key: str
    label: str
    group: str  # "module" | "action"


# Acciones transversales (no dependen de un dominio del catálogo). La etiqueta es para la
# UI (español); la clave, para el contrato/enforcement (inglés).
_ACCIONES: tuple[tuple[str, str], ...] = (
    ("action:catalog", "Ver catálogo"),
    ("action:forecast", "Predecir"),
    ("action:template_download", "Descargar plantilla"),
    ("action:template_upload", "Cargar plantilla"),
    ("action:training", "Reentrenar (opt-in)"),
    ("action:users_manage", "Administrar usuarios"),
)

# Etiquetas en español por dominio del catálogo (solo presentación; la clave es el id en
# inglés del catálogo). Si falta una etiqueta, se usa el propio id capitalizado.
_ETIQUETA_MODULO = {"sales": "Ventas", "purchases": "Compras", "inventory": "Almacén"}


def _dominios_catalogo() -> list[str]:
    """Ids de dominio del catálogo (import perezoso para evitar ciclos en el arranque)."""
    from spc.api.catalog import construir_catalogo

    return [d.domain for d in construir_catalogo().domains]


def permisos_modulo() -> list[Permiso]:
    """Permisos de acceso a módulo, derivados de los dominios del catálogo."""
    return [
        Permiso(key=f"module:{dom}", label=_ETIQUETA_MODULO.get(dom, dom.capitalize()), group="module")
        for dom in _dominios_catalogo()
    ]


def permisos_accion() -> list[Permiso]:
    """Permisos de acción transversal (vocabulario operacional del backend)."""
    return [Permiso(key=clave, label=etiqueta, group="action") for clave, etiqueta in _ACCIONES]


def catalogo_permisos() -> list[Permiso]:
    """Catálogo completo de permisos (módulos + acciones) para el editor de roles."""
    return [*permisos_modulo(), *permisos_accion()]


def claves_validas() -> set[str]:
    """Conjunto de claves de permiso válidas (para validar lo que envía el admin)."""
    return {p.key for p in catalogo_permisos()}


def permisos_administrador() -> list[str]:
    """Todas las claves: el rol administrador sembrado tiene acceso total (ADR-0014)."""
    return [p.key for p in catalogo_permisos()]
