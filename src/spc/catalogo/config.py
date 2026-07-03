"""Parsers de configuración del catálogo YAML → dataclasses.

Carga el archivo YAML de consultas predefinidas y expone las 30 consultas como objetos
tipados (ConfigConsulta) para que el motor acceda sin conocer YAML.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml

# Rutas
CATALOGO_ROOT = Path(__file__).parent
CATALOGO_YAML = CATALOGO_ROOT / "consultas.yaml"


# ==============================================================================
# Dataclasses de Configuración
# ==============================================================================

@dataclass(frozen=True)
class DerivacionEtiqueta:
    """Especifica cómo generar la etiqueta de clasificación sin fuga."""

    tipo: Literal["percentil", "moda", "umbral", "regla"]
    columna_objetivo: str | None = None
    percentil: int | None = None
    umbral_valor: float | None = None
    formula: str | None = None
    agrupar_por: str | None = None
    calcular_en: Literal["train_only", "all"] = "train_only"
    descripcion: str = ""

    def __post_init__(self) -> None:
        """Valida coherencia del tipo y sus parámetros."""
        if self.tipo == "percentil" and self.columna_objetivo is None:
            raise ValueError("DerivacionEtiqueta tipo=percentil requiere columna_objetivo")
        if self.tipo == "percentil" and self.percentil is None:
            raise ValueError("DerivacionEtiqueta tipo=percentil requiere percentil")
        if self.tipo == "umbral" and self.umbral_valor is None:
            raise ValueError("DerivacionEtiqueta tipo=umbral requiere umbral_valor")
        if self.tipo == "regla" and self.formula is None:
            raise ValueError("DerivacionEtiqueta tipo=regla requiere formula")


@dataclass(frozen=True)
class ConfigConsulta:
    """Configuración de una consulta del catálogo.

    Representa una línea del catálogo YAML como un objeto tipado, listo para
    que motor_catalogo lo procese.
    """

    # Identificación
    id: str
    modulo: str
    tipo: Literal["regresion", "clasificacion", "clustering"]

    # Narrativa
    pregunta: str
    descripcion: str

    # Datos
    objetivo: str
    columnas_entrada: list[str]
    columnas_conocidas_futuro: list[str] = field(default_factory=list)
    columnas_solo_pasado: list[str] = field(default_factory=list)

    # ML: candidatos, métrica, validación
    modelos_candidatos: list[str] = field(default_factory=list)
    metrica_seleccion: str = "wape"
    col_fecha: str | None = None
    cols_serie: list[str] = field(default_factory=list)

    # Clasificación
    derivacion_etiqueta: DerivacionEtiqueta | None = None

    # Clustering
    entidad_cluster: str | None = None
    agregacion: str | None = None
    k_fijo: int | None = None
    estilo_etiqueta: str = "volumen"
    columna_etiqueta: str | None = None

    # Regresión temporal (solo COMPRAS, con ventanas cortas)
    lags_objetivo: tuple[int, ...] = field(default_factory=tuple)
    ventanas_media: tuple[int, ...] = field(default_factory=tuple)

    # Auditoría
    anti_fuga: str = ""

    def validar(self) -> None:
        """Verifica coherencia interna de la configuración."""
        # Clasificación: binaria (con derivacion_etiqueta) o multiclase directa (con objetivo).
        if self.tipo == "clasificacion" and self.derivacion_etiqueta is None and not self.objetivo:
            raise ValueError(
                f"Consulta {self.id}: clasificación requiere derivacion_etiqueta (binaria) "
                f"u objetivo (multiclase)"
            )
        if self.tipo == "clustering" and self.entidad_cluster is None:
            raise ValueError(f"Consulta {self.id}: clustering requiere entidad_cluster")
        if self.tipo in ("regresion", "clasificacion") and self.col_fecha is None:
            raise ValueError(f"Consulta {self.id}: {self.tipo} requiere col_fecha")
        if len(self.columnas_entrada) == 0:
            raise ValueError(f"Consulta {self.id}: sin columnas_entrada")


@dataclass(frozen=True)
class ConfigModulo:
    """Configuración de un módulo (10 consultas)."""

    dominio: str
    columnas_todas: list[str]
    columnas_excluir_features: dict[str, str]
    consultas: dict[str, ConfigConsulta]

    def consultas_por_tipo(self) -> dict[str, list[ConfigConsulta]]:
        """Agrupa consultas por tipo (regresion, clasificacion, clustering)."""
        por_tipo: dict[str, list[ConfigConsulta]] = {"regresion": [], "clasificacion": [], "clustering": []}
        for c in self.consultas.values():
            por_tipo[c.tipo].append(c)
        return por_tipo


# ==============================================================================
# Carga del Catálogo
# ==============================================================================

def _cargar_yaml_raw() -> dict[str, Any]:
    """Carga el YAML crudo desde disco."""
    if not CATALOGO_YAML.exists():
        raise FileNotFoundError(f"Catálogo no encontrado: {CATALOGO_YAML}")
    with open(CATALOGO_YAML, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _parse_consultas_de_dict(dominio_dict: dict[str, Any]) -> dict[str, ConfigConsulta]:
    """Parsea el dict de consultas YAML hacia ConfigConsulta."""
    consultas_raw = dominio_dict.get("consultas", {})
    consultas: dict[str, ConfigConsulta] = {}

    for consulta_id, consulta_data in consultas_raw.items():
        derivacion = None
        if "derivacion_etiqueta" in consulta_data and consulta_data["derivacion_etiqueta"]:
            der_data = consulta_data["derivacion_etiqueta"]
            derivacion = DerivacionEtiqueta(
                tipo=der_data.get("tipo", "percentil"),
                columna_objetivo=der_data.get("columna_objetivo"),
                percentil=der_data.get("percentil"),
                umbral_valor=der_data.get("umbral"),
                formula=der_data.get("formula"),
                agrupar_por=der_data.get("agrupar_por"),
                calcular_en=der_data.get("calcular_en", "train_only"),
                descripcion=der_data.get("descripcion", ""),
            )

        config = ConfigConsulta(
            id=consulta_data.get("id", consulta_id),
            modulo=dominio_dict.get("dominio", "unknown"),
            tipo=consulta_data.get("tipo", "regresion"),
            pregunta=consulta_data.get("pregunta", ""),
            descripcion=consulta_data.get("descripcion", ""),
            objetivo=consulta_data.get("objetivo", ""),
            columnas_entrada=consulta_data.get("columnas_entrada", []),
            columnas_conocidas_futuro=consulta_data.get("columnas_conocidas_futuro", []),
            columnas_solo_pasado=consulta_data.get("columnas_solo_pasado", []),
            modelos_candidatos=consulta_data.get("modelos_candidatos", []),
            metrica_seleccion=consulta_data.get("metrica_seleccion", "wape"),
            col_fecha=consulta_data.get("col_fecha"),
            cols_serie=consulta_data.get("cols_serie", []),
            derivacion_etiqueta=derivacion,
            entidad_cluster=consulta_data.get("entidad_cluster"),
            agregacion=consulta_data.get("agregacion"),
            k_fijo=consulta_data.get("k_fijo"),
            estilo_etiqueta=consulta_data.get("estilo_etiqueta", "volumen"),
            columna_etiqueta=consulta_data.get("columna_etiqueta"),
            lags_objetivo=tuple(consulta_data.get("lags_objetivo", [])),
            ventanas_media=tuple(consulta_data.get("ventanas_media", [])),
            anti_fuga=consulta_data.get("anti_fuga", ""),
        )
        config.validar()
        consultas[consulta_id] = config

    return consultas


def cargar_catalogo() -> dict[str, ConfigModulo]:
    """Carga el catálogo YAML completo.

    Retorna dict: { "ventas": ConfigModulo, "compras": ConfigModulo, "almacen": ConfigModulo }
    """
    raw = _cargar_yaml_raw()

    catalogo: dict[str, ConfigModulo] = {}
    for modulo_key in ["modulo_ventas", "modulo_compras", "modulo_almacen"]:
        if modulo_key not in raw:
            raise ValueError(f"Catálogo: falta sección {modulo_key}")

        modulo_data = raw[modulo_key]
        dominio = modulo_data.get("dominio")
        consultas = _parse_consultas_de_dict(modulo_data)

        config_modulo = ConfigModulo(
            dominio=dominio,
            columnas_todas=modulo_data.get("columnas_todas", []),
            columnas_excluir_features=modulo_data.get("columnas_excluir_features", {}),
            consultas=consultas,
        )
        catalogo[dominio] = config_modulo

    return catalogo


# Singleton: catálogo cargado al importar
_CATALOGO_SINGLETON: dict[str, ConfigModulo] | None = None


def obtener_catalogo() -> dict[str, ConfigModulo]:
    """Retorna el catálogo singleton (lazy load)."""
    global _CATALOGO_SINGLETON
    if _CATALOGO_SINGLETON is None:
        _CATALOGO_SINGLETON = cargar_catalogo()
    return _CATALOGO_SINGLETON


def obtener_consulta(consulta_id: str) -> ConfigConsulta:
    """Busca una consulta por ID en todo el catálogo.

    Normaliza consulta_id: acepta tanto "ven-r1" como "ven_r1".
    """
    # Normalizar: convertir guiones a underscores para búsqueda en diccionario
    consulta_id_normalizada = consulta_id.replace("-", "_")

    cat = obtener_catalogo()
    for modulo in cat.values():
        if consulta_id_normalizada in modulo.consultas:
            return modulo.consultas[consulta_id_normalizada]
    raise ValueError(f"Consulta no encontrada: {consulta_id}")


def obtener_modulo(dominio: str) -> ConfigModulo:
    """Retorna el ConfigModulo para un dominio."""
    cat = obtener_catalogo()
    if dominio not in cat:
        raise ValueError(f"Módulo no encontrado: {dominio}")
    return cat[dominio]
