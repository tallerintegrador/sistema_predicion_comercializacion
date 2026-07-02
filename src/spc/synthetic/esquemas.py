"""Esquemas de datos por dominio — **fuente única de la verdad** del rediseño 3×3.

Formato **por dominio** (VENTAS, COMPRAS, ALMACÉN) con variables de negocio que alimentan
los **tres** tipos de modelo (regresión, clasificación, clustering). Aquí se declara, una
sola vez, qué columnas tiene cada dominio, su tipo, su rol, **qué es**, **para qué le sirve
al sistema** y —si se calcula sola— **su fórmula**. Los generadores sintéticos
(`spc.synthetic.{ventas,compras,almacen}`), los tests, la hoja de instrucciones de las
plantillas Excel y el contrato del API derivan de **esta** definición, de modo que nunca se
desincronizan.

Notas de diseño:

- ``ingreso`` / ``costo_total`` / ``cumplimiento`` / ``dias_de_cobertura`` son **columnas
  calculadas** (``rol="calculada"``): se derivan de otras. Son **opcionales al subir tus
  datos** —el sistema las calcula solo con su fórmula si no vienen— y **no entran al
  pronóstico** (evitan que el modelo "haga trampa" mirando el resultado).
- ``en_promocion`` y ``es_fin_de_semana`` son **banderas 0/1** (``rol="bandera"``).
- ``dias_a_proximo_feriado`` (entero) reemplaza una bandera de feriado: la **cercanía** a un
  feriado sí tiene señal.
- ``demanda_dia`` (ALMACÉN) es un **conteo de unidades** → tipo entero (los promedios y el
  pronóstico sí llevan decimales, pero el consumo del día es un número entero).

Las **etiquetas** de clasificación (``demanda_alta``, ``riesgo_quiebre``,
``entrega_con_retraso``) NO se almacenan como columnas: se **derivan en tiempo de modelo**
con umbrales fijados solo en TRAIN (regla anti-fuga del repo). Aquí solo se documenta su
derivación, para trazabilidad.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

# Roles posibles de una columna del esquema.
#   clave   : identifica la serie/entidad (tienda, sku, proveedor) — categórica.
#   fecha   : eje temporal.
#   bandera : 0/1.
#   numerica: medida continua observada.
#   categorica: atributo discreto no clave.
#   calculada : se deriva de otras columnas (ingreso, costo_total, ...); opcional al subir.
ROLES = ("clave", "fecha", "bandera", "numerica", "categorica", "calculada")


@dataclass(frozen=True)
class Columna:
    """Una columna del esquema: nombre, tipo pandas, rol, qué es, para qué sirve y fórmula.

    - ``descripcion`` — **qué es**, en lenguaje simple.
    - ``uso`` — **para qué le sirve al sistema** al entrenar (objetivo / factor /
      identificador / la calcula el sistema).
    - ``formula`` — solo para columnas ``calculada``: cómo se obtiene (se muestra en las
      instrucciones; el sistema la aplica si la columna no viene).
    """

    nombre: str
    tipo: str  # "date" | "int" | "float" | "str"
    rol: str
    descripcion: str
    uso: str = ""
    formula: str = ""


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

    def columnas_calculadas(self) -> list[str]:
        """Columnas que el sistema puede rellenar solo (opcionales al subir datos)."""
        return [c.nombre for c in self.columnas if c.rol == "calculada"]

    def columnas_obligatorias(self) -> list[str]:
        """Columnas que el usuario SÍ debe traer (todas menos las calculadas)."""
        return [c.nombre for c in self.columnas if c.rol != "calculada"]

    def tipos(self) -> dict[str, str]:
        return {c.nombre: c.tipo for c in self.columnas}


# ===========================================================================
# VENTAS — una fila por (fecha, tienda, producto, día)
# ===========================================================================
VENTAS = EsquemaDominio(
    dominio="ventas",
    grano="una fila por (fecha, tienda, producto, día)",
    columnas=(
        Columna(
            "fecha", "date", "fecha",
            "Día de la venta (formato AAAA-MM-DD).",
            "Ordena el histórico en el tiempo: de aquí el sistema aprende tendencias y estacionalidad (fines de semana, feriados).",
        ),
        Columna(
            "id_tienda", "str", "clave",
            "Local, tienda o sucursal donde se vendió.",
            "Identificador: separa el pronóstico por cada tienda. No se predice.",
        ),
        Columna(
            "sku", "str", "clave",
            "Código del producto.",
            "Identificador: separa el pronóstico por cada producto. No se predice.",
        ),
        Columna(
            "categoria", "str", "categorica",
            "Familia o rubro del producto (p. ej. Bebidas, Abarrotes).",
            "Factor: ayuda a comparar productos parecidos y a definir qué es «demanda alta» dentro de cada categoría.",
        ),
        Columna(
            "unidades_vendidas", "float", "numerica",
            "Cantidad de unidades vendidas ese día (≥ 0).",
            "Objetivo: es lo que el sistema aprende a predecir a futuro.",
        ),
        Columna(
            "precio_unitario", "float", "numerica",
            "Precio de venta por unidad ese día (en soles).",
            "Factor: el precio influye en cuánto se vende.",
        ),
        Columna(
            "ingreso", "float", "calculada",
            "Dinero vendido ese día.",
            "La calcula el sistema; sirve para tus reportes, no entra al pronóstico. Opcional al subir.",
            formula="ingreso = unidades_vendidas × precio_unitario",
        ),
        Columna(
            "en_promocion", "int", "bandera",
            "1 si el producto estuvo en promoción ese día; 0 si no.",
            "Factor: las promociones suelen subir las ventas.",
        ),
        Columna(
            "descuento_pct", "float", "numerica",
            "Descuento aplicado ese día, en porcentaje (0 si no hubo promoción).",
            "Factor: a mayor descuento, suele haber más ventas.",
        ),
        Columna(
            "metodo_pago", "str", "categorica",
            "Medio de pago más usado ese día (p. ej. efectivo, tarjeta, Yape).",
            "Factor: aporta contexto del comportamiento de compra.",
        ),
        Columna(
            "canal_venta", "str", "categorica",
            "Canal por el que se vendió (p. ej. tienda física, online).",
            "Factor: el canal puede cambiar el nivel de ventas.",
        ),
        Columna(
            "es_fin_de_semana", "int", "bandera",
            "1 si la fecha cae sábado o domingo; 0 si no.",
            "Factor: capta el efecto del fin de semana en la demanda.",
        ),
        Columna(
            "dias_a_proximo_feriado", "int", "numerica",
            "Cuántos días faltan para el próximo feriado.",
            "Factor: la cercanía a un feriado suele mover las ventas.",
        ),
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
        Columna(
            "fecha_orden", "date", "fecha",
            "Fecha en que se emitió la orden de compra (AAAA-MM-DD).",
            "Ordena las órdenes en el tiempo: de aquí el sistema aprende el ritmo de pedidos.",
        ),
        Columna(
            "id_proveedor", "str", "clave",
            "Código del proveedor.",
            "Identificador: separa el análisis por proveedor. No se predice.",
        ),
        Columna(
            "sku", "str", "clave",
            "Código del producto comprado.",
            "Identificador: separa el análisis por producto. No se predice.",
        ),
        Columna(
            "categoria", "str", "categorica",
            "Familia o rubro del producto.",
            "Factor: ayuda a comparar productos parecidos.",
        ),
        Columna(
            "cantidad_pedida", "float", "numerica",
            "Unidades solicitadas en la orden.",
            "Objetivo: es lo que el sistema aprende a predecir (cuánto conviene pedir).",
        ),
        Columna(
            "precio_unitario_compra", "float", "numerica",
            "Costo de compra por unidad (en soles).",
            "Factor: el costo influye en el tamaño de los pedidos.",
        ),
        Columna(
            "costo_total", "float", "calculada",
            "Costo total de la orden.",
            "La calcula el sistema; sirve para tus reportes, no entra al pronóstico. Opcional al subir.",
            formula="costo_total = cantidad_pedida × precio_unitario_compra",
        ),
        Columna(
            "lead_time_dias", "int", "numerica",
            "Días entre la orden y la entrega.",
            "Factor: define la alerta de «entrega con retraso» y ayuda al análisis.",
        ),
        Columna(
            "cantidad_recibida", "float", "numerica",
            "Unidades que finalmente llegaron.",
            "Factor: sirve para medir qué tan bien cumple el proveedor (ver «cumplimiento»).",
        ),
        Columna(
            "cumplimiento", "float", "calculada",
            "Qué parte del pedido llegó, de 0 a 1 (1 = llegó completo).",
            "La calcula el sistema; se usa para agrupar proveedores por fiabilidad. Opcional al subir.",
            formula="cumplimiento = cantidad_recibida ÷ cantidad_pedida",
        ),
        Columna(
            "metodo_pago", "str", "categorica",
            "Condición o medio de pago al proveedor (p. ej. contado, crédito 30 días).",
            "Factor: aporta contexto de la negociación.",
        ),
        Columna(
            "descuento_volumen", "float", "numerica",
            "Descuento por volumen negociado, en porcentaje.",
            "Factor: los descuentos por volumen influyen en cuánto se pide.",
        ),
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
        Columna(
            "fecha", "date", "fecha",
            "Día de la foto de inventario (AAAA-MM-DD).",
            "Ordena el histórico en el tiempo: de aquí el sistema aprende el consumo diario.",
        ),
        Columna(
            "id_tienda", "str", "clave",
            "Local, tienda o sucursal.",
            "Identificador: separa el análisis por tienda. No se predice.",
        ),
        Columna(
            "sku", "str", "clave",
            "Código del producto.",
            "Identificador: separa el análisis por producto. No se predice.",
        ),
        Columna(
            "categoria", "str", "categorica",
            "Familia o rubro del producto.",
            "Factor: ayuda a comparar productos parecidos.",
        ),
        Columna(
            "stock_actual", "float", "numerica",
            "Unidades disponibles ese día.",
            "Factor: define el riesgo de quiebre y los indicadores de reposición.",
        ),
        Columna(
            "stock_minimo", "float", "numerica",
            "Nivel mínimo que quieres mantener.",
            "Factor: parte de tu política de inventario.",
        ),
        Columna(
            "stock_maximo", "float", "numerica",
            "Nivel máximo que quieres mantener.",
            "Factor: parte de tu política de inventario.",
        ),
        Columna(
            "demanda_dia", "int", "numerica",
            "Unidades consumidas ESE día (número entero: es un conteo de unidades).",
            "Objetivo: es la demanda futura que el sistema aprende a predecir.",
        ),
        Columna(
            "demanda_diaria_promedio", "float", "numerica",
            "Promedio de consumo de los últimos días (lleva decimales por ser un promedio).",
            "Factor: indica el nivel de consumo reciente del producto.",
        ),
        Columna(
            "dias_de_cobertura", "float", "calculada",
            "Para cuántos días alcanza el stock actual (lleva decimales por ser una división).",
            "La calcula el sistema; se usa en el análisis ABC (importancia), no en el pronóstico. Opcional al subir.",
            formula="dias_de_cobertura = stock_actual ÷ demanda_diaria_promedio",
        ),
        Columna(
            "rotacion", "float", "numerica",
            "Índice de rotación del producto (qué tan rápido se mueve).",
            "Factor: apoya la alerta de quiebre y el análisis ABC.",
        ),
        Columna(
            "tiempo_reposicion_dias", "int", "numerica",
            "Días que tarda en llegar una reposición del producto.",
            "Factor: define el riesgo de quiebre y el punto de reposición.",
        ),
        Columna(
            "zona_almacen", "str", "categorica",
            "Zona física del almacén donde se guarda.",
            "Factor: aporta contexto de ubicación.",
        ),
    ),
    # ADR-0025 (e): el objetivo pasa de `dias_de_cobertura` (casi una fórmula stock/demanda,
    # sin valor de aprendizaje) a `demanda_dia` (demanda futura, sí aprendible). Los KPIs
    # `dias_de_cobertura`/punto de reposición/stock de seguridad se siguen MOSTRANDO como
    # indicadores derivados del pronóstico de demanda (ver spc.service.motor_3x3).
    objetivo_regresion="demanda_dia",
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
