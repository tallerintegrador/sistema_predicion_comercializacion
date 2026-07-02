"""Onboarding del contrato **3×3**: diccionario de variables y filas de ejemplo.

Capa de servicio (no conoce HTTP). Traduce el esquema técnico
(``spc.synthetic.esquemas``) a un **diccionario en lenguaje simple** para el usuario
—qué columna pide el sistema, qué significa y un ejemplo— y qué predice cada uno de los
tres modelos. También produce **filas de ejemplo** (sintéticas, reproducibles) para las
plantillas descargables y las cargas de prueba.

Objetivo: que una PYME entienda, sin tecnicismos, qué datos debe traer y qué recibe.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from spc.service import dominios
from spc.synthetic import generar_dominio
from spc.synthetic.esquemas import esquema_de

# Traducción de los tipos/roles técnicos a palabras que entiende cualquiera.
_TIPO_HUMANO = {"date": "fecha", "int": "número entero", "float": "número", "str": "texto"}
_ROL_HUMANO = {
    "clave": "identificador",
    "fecha": "fecha",
    "bandera": "bandera (0 o 1)",
    "numerica": "número",
    "categorica": "categoría (texto)",
    "calculada": "la calcula el sistema (opcional)",
}

# Qué hace, en lenguaje simple, cada uno de los tres modelos por dominio.
_QUE_PREDICE: dict[str, dict[str, str]] = {
    "ventas": {
        "regresion": "Cuántas unidades se venderán los próximos días (un número).",
        "clasificacion": "Si un producto tendrá demanda alta (una alerta de sí / no).",
        "clustering": "Agrupa tus productos por su nivel de ventas (grupos parecidos).",
    },
    "compras": {
        "regresion": "Cuántas unidades conviene pedir (un número).",
        "clasificacion": "Si una orden llegará con retraso (una alerta de sí / no).",
        "clustering": "Agrupa tus proveedores por rapidez y fiabilidad (grupos parecidos).",
    },
    "almacen": {
        "regresion": "Cuánta demanda diaria habrá (un número); de ahí salen la cobertura y la reposición.",
        "clasificacion": "Si un producto corre riesgo de quedarse sin stock (una alerta de sí / no).",
        "clustering": "Clasifica tus productos en A / B / C por importancia (análisis ABC).",
    },
}

# Tamaños de las filas de ejemplo. "Plantilla" = poquitas filas (para ver el formato);
# "rico" = un conjunto variado y realista, listo para subir y ver el sistema en acción.
_EJEMPLO_PLANTILLA = {
    "ventas": dict(n_tiendas=1, n_productos=3, n_dias=14),
    "almacen": dict(n_tiendas=1, n_productos=3, n_dias=14),
    "compras": dict(n_proveedores=2, n_productos=2, n_ordenes_por_serie=6),
}


def _jsonable(valor: Any) -> Any:
    """Convierte un valor de pandas/numpy a algo serializable (fechas → texto)."""
    if hasattr(valor, "item"):  # numpy scalar
        return valor.item()
    return valor


def _filas_jsonables(df: pd.DataFrame, dominio: str) -> list[dict[str, Any]]:
    """DataFrame → lista de filas JSON-safe (columnas fecha como 'YYYY-MM-DD')."""
    esq = esquema_de(dominio)
    df = df.copy()
    for col in esq.columnas:
        if col.tipo == "date":
            df[col.nombre] = df[col.nombre].astype(str)
    return [{k: _jsonable(v) for k, v in fila.items()} for fila in df.to_dict(orient="records")]


def diccionario_de(dominio: str) -> dict[str, Any]:
    """Diccionario de variables del dominio, en lenguaje simple + qué predice cada modelo."""
    esq = esquema_de(dominio)
    cfg = dominios.config_de(dominio)
    muestra = _filas_jsonables(generar_dominio(dominio, seed=42).head(1), dominio)[0]

    columnas = [
        {
            "nombre": c.nombre,
            "tipo": _TIPO_HUMANO.get(c.tipo, c.tipo),
            "rol": _ROL_HUMANO.get(c.rol, c.rol),
            "descripcion": c.descripcion,
            "uso": c.uso,  # para qué le sirve al sistema (objetivo/factor/identificador/calculada)
            "formula": c.formula,  # solo columnas calculadas: cómo se obtiene (para instrucciones)
            # Las columnas calculadas son OPCIONALES al subir: el sistema las rellena con su
            # fórmula si no vienen (ver spc.service.motor_3x3.construir_dataframe).
            "obligatoria": c.rol != "calculada",
            "se_calcula_sola": c.rol == "calculada",
            "ejemplo": muestra.get(c.nombre),
        }
        for c in esq.columnas
    ]
    qp = _QUE_PREDICE[dominio]
    return {
        "dominio": dominio,
        "formato": esq.grano,
        "columnas": columnas,
        "que_se_predice": {
            "regresion": {"objetivo": esq.objetivo_regresion, "explicacion": qp["regresion"]},
            "clasificacion": {
                "alerta": esq.etiqueta_clasificacion,
                "cuando": esq.derivacion_etiqueta,
                "explicacion": qp["clasificacion"],
            },
            "clustering": {
                "agrupa": cfg.clave_entidad,
                "grupos_fijos": cfg.k_fijo,  # None = el sistema decide cuántos
                "explicacion": qp["clustering"],
            },
        },
    }


def filas_ejemplo(dominio: str, *, ricas: bool = False) -> list[dict[str, Any]]:
    """Filas de ejemplo del dominio (JSON-safe). ``ricas``: conjunto variado listo para subir."""
    if ricas:
        df = generar_dominio(dominio, seed=42)  # tamaño demo: variado y ágil de entrenar
    else:
        df = generar_dominio(dominio, seed=42, **_EJEMPLO_PLANTILLA[dominio])
    return _filas_jsonables(df, dominio)
