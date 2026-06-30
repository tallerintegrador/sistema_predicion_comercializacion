"""Esquemas de datos por dominio — **fuente única de la verdad** del rediseño 3×3.

El docente pidió un **formato por dominio** (VENTAS, COMPRAS, ALMACÉN) con variables
de negocio que alimenten los **tres** tipos de modelo (regresión, clasificación,
clustering). Aquí se declara, una sola vez, qué columnas tiene cada dominio, su tipo y
su rol. Los generadores sintéticos (`spc.synthetic.{ventas,compras,almacen}`), los
tests y —más adelante— el contrato del API derivan de **esta** definición, de modo que
nunca se desincronizan.

Decisiones de diseño que corrigen lo señalado por el docente:

- ``ingreso`` / ``costo_total`` / ``cumplimiento`` / ``dias_de_cobertura`` son
  **columnas calculadas** (``rol="calculada"``): se derivan de otras, no son entradas
  sueltas (corrige el ejemplo malo de "ingreso").
- ``en_promocion`` y ``es_fin_de_semana`` son **banderas 0/1** (``rol="bandera"``), no
  cantidades ambiguas ni un 0/1/2/3.
- La inútil bandera ``feriado`` se reemplaza por ``dias_a_proximo_feriado`` (entero): la
  **cercanía** a un feriado sí tiene señal.

Las **etiquetas** de clasificación (``demanda_alta``, ``riesgo_quiebre``,
``entrega_con_retraso``) NO se almacenan como columnas: se **derivan en tiempo de
modelo** con umbrales fijados solo en TRAIN (regla anti-fuga del repo). Aquí solo se
documenta su derivación, para trazabilidad.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

# Roles posibles de una columna del esquema.
#   clave   : identifica la serie/entidad (tienda, sku, proveedor) — categórica.
#   fecha   : eje temporal.
#   bandera : 0/1 (corrige el "fin de semana 0/1/2/3" y el "en promoción" ambiguo).
#   numerica: medida continua observada.
#   categorica: atributo discreto no clave.
#   calculada : se deriva de otras columnas (ingreso, costo_total, ...).
ROLES = ("clave", "fecha", "bandera", "numerica", "categorica", "calculada")


@dataclass(frozen=True)
class Columna:
    """Una columna del esquema de un dominio: nombre, tipo pandas y rol de negocio."""

    nombre: str
    tipo: str  # "date" | "int" | "float" | "str"
    rol: str
    descripcion: str


@dataclass(frozen=True)
class EsquemaDominio:
    """Formato único de un dominio: su grano y sus columnas (en orden canónico).

    ``objetivos`` documenta qué predice cada uno de los tres modelos del dominio (la
    columna objetivo de regresión y la **derivación** de la etiqueta de clasificación);
    ``clave_entidad_clustering`` indica sobre qué entidad agrupa el clustering.
    """

    dominio: str  # "ventas" | "compras" | "almacen"
    grano: str  # descripción legible de la fila
    columnas: tuple[Columna, ...]
    objetivo_regresion: str
    etiqueta_clasificacion: str  # nombre lógico de la etiqueta derivada
    derivacion_etiqueta: str  # cómo se deriva (documentación; train-only en el modelo)
    clave_entidad_clustering: str

    @property
    def orden(self) -> list[str]:
        """Orden canónico de columnas (cabecera de los datos)."""
        return [c.nombre for c in self.columnas]

    def columnas_por_rol(self, rol: str) -> list[str]:
        return [c.nombre for c in self.columnas if c.rol == rol]

    def tipos(self) -> dict[str, str]:
        return {c.nombre: c.tipo for c in self.columnas}


# ===========================================================================
# VENTAS — una fila por (fecha, tienda, producto, día)
# ===========================================================================
VENTAS = EsquemaDominio(
    dominio="ventas",
    grano="una fila por (fecha, tienda, producto, día)",
    columnas=(
        Columna("fecha", "date", "fecha", "Día de la observación (ISO YYYY-MM-DD)."),
        Columna("id_tienda", "str", "clave", "Local/tienda/sucursal."),
        Columna("sku", "str", "clave", "Producto."),
        Columna("categoria", "str", "categorica", "Familia del producto."),
        Columna("unidades_vendidas", "float", "numerica", "Objetivo base: unidades vendidas ese día (≥0)."),
        Columna("precio_unitario", "float", "numerica", "Precio de venta unitario."),
        Columna("ingreso", "float", "calculada", "unidades_vendidas × precio_unitario (columna calculada)."),
        Columna("en_promocion", "int", "bandera", "1 si el producto estuvo en promoción ese día, 0 si no."),
        Columna("descuento_pct", "float", "numerica", "Porcentaje de descuento aplicado (0 si no hay promo)."),
        Columna("metodo_pago", "str", "categorica", "Medio de pago predominante (sugerido por el docente)."),
        Columna("canal_venta", "str", "categorica", "Canal de venta: tienda/online (sugerido por el docente)."),
        Columna("es_fin_de_semana", "int", "bandera", "1 si la fecha cae sábado/domingo, 0 si no."),
        Columna("dias_a_proximo_feriado", "int", "numerica", "Días hasta el próximo feriado (reemplaza la bandera feriado)."),
    ),
    objetivo_regresion="unidades_vendidas",
    etiqueta_clasificacion="demanda_alta",
    derivacion_etiqueta="1 si unidades_vendidas > P75 de su categoría (P75 fijado solo en TRAIN)",
    clave_entidad_clustering="sku",
)


# ===========================================================================
# COMPRAS — una fila por (fecha_orden, proveedor, producto)
# ===========================================================================
COMPRAS = EsquemaDominio(
    dominio="compras",
    grano="una fila por (fecha_orden, proveedor, producto)",
    columnas=(
        Columna("fecha_orden", "date", "fecha", "Fecha de emisión de la orden de compra."),
        Columna("id_proveedor", "str", "clave", "Proveedor."),
        Columna("sku", "str", "clave", "Producto comprado."),
        Columna("categoria", "str", "categorica", "Familia del producto."),
        Columna("cantidad_pedida", "float", "numerica", "Objetivo de regresión: unidades solicitadas."),
        Columna("precio_unitario_compra", "float", "numerica", "Costo de compra unitario."),
        Columna("costo_total", "float", "calculada", "cantidad_pedida × precio_unitario_compra (calculada)."),
        Columna("lead_time_dias", "int", "numerica", "Días entre la orden y la entrega."),
        Columna("cantidad_recibida", "float", "numerica", "Unidades efectivamente recibidas."),
        Columna("cumplimiento", "float", "calculada", "cantidad_recibida / cantidad_pedida (fill rate, calculada)."),
        Columna("metodo_pago", "str", "categorica", "Condición de pago al proveedor."),
        Columna("descuento_volumen", "float", "numerica", "Descuento por volumen (%) negociado."),
    ),
    objetivo_regresion="cantidad_pedida",
    etiqueta_clasificacion="entrega_con_retraso",
    derivacion_etiqueta="1 si lead_time_dias > P75 del lead time (umbral fijado solo en TRAIN)",
    clave_entidad_clustering="id_proveedor",
)


# ===========================================================================
# ALMACÉN — una fila por (fecha, tienda, producto, día) — foto de stock
# ===========================================================================
ALMACEN = EsquemaDominio(
    dominio="almacen",
    grano="una fila por (fecha, tienda, producto, día) — foto de stock",
    columnas=(
        Columna("fecha", "date", "fecha", "Día de la foto de inventario."),
        Columna("id_tienda", "str", "clave", "Local/tienda/sucursal."),
        Columna("sku", "str", "clave", "Producto."),
        Columna("categoria", "str", "categorica", "Familia del producto."),
        Columna("stock_actual", "float", "numerica", "Existencias disponibles ese día."),
        Columna("stock_minimo", "float", "numerica", "Nivel mínimo de política de inventario."),
        Columna("stock_maximo", "float", "numerica", "Nivel máximo de política de inventario."),
        Columna("demanda_diaria_promedio", "float", "numerica", "Consumo medio diario reciente."),
        Columna("dias_de_cobertura", "float", "calculada", "stock_actual / demanda_diaria_promedio (KPI, calculada)."),
        Columna("rotacion", "float", "numerica", "Índice de rotación de inventario (apoya el análisis ABC)."),
        Columna("tiempo_reposicion_dias", "int", "numerica", "Días que tarda reponer el producto."),
        Columna("zona_almacen", "str", "categorica", "Zona física del almacén."),
    ),
    objetivo_regresion="dias_de_cobertura",
    etiqueta_clasificacion="riesgo_quiebre",
    derivacion_etiqueta="1 si stock_actual < demanda_diaria_promedio × tiempo_reposicion_dias",
    clave_entidad_clustering="sku",
)


ESQUEMAS: dict[str, EsquemaDominio] = {
    "ventas": VENTAS,
    "compras": COMPRAS,
    "almacen": ALMACEN,
}


def esquema_de(dominio: str) -> EsquemaDominio:
    """Devuelve el esquema de un dominio (``ventas``|``compras``|``almacen``)."""
    try:
        return ESQUEMAS[dominio]
    except KeyError:
        raise KeyError(
            f"Dominio desconocido: {dominio!r}. Use uno de {tuple(ESQUEMAS)}."
        ) from None


def validar_conforme(df: pd.DataFrame, dominio: str) -> None:
    """Verifica que ``df`` tenga **exactamente** las columnas del esquema, en orden.

    Lanza ``ValueError`` con un mensaje claro si faltan, sobran o están desordenadas.
    Es la guarda que usan los tests y el script de generación para no derivar.
    """
    esquema = esquema_de(dominio)
    esperado = esquema.orden
    obtenido = list(df.columns)
    if obtenido != esperado:
        faltan = [c for c in esperado if c not in obtenido]
        sobran = [c for c in obtenido if c not in esperado]
        detalle = []
        if faltan:
            detalle.append(f"faltan: {faltan}")
        if sobran:
            detalle.append(f"sobran: {sobran}")
        if not detalle:
            detalle.append("orden distinto")
        raise ValueError(
            f"El DataFrame de '{dominio}' no es conforme al esquema ({'; '.join(detalle)})."
        )
