# Contrato de Datos — SPC: Sistema Predictivo de Comercialización

> Documento vivo. Versión 0.1. Vive en `docs/contrato_datos.md`.
> Es la **frontera pública estable** del producto: define qué envía y qué recibe el cliente por API, con nombres genéricos y agnósticos al sector. Lo que cambie por dentro (modelos, features) **no debe romper este contrato**. Consolidado a partir de la sección 3 del Plan Maestro; cualquier cambio aquí se registra en un ADR.

---

## 1. Principios del contrato

- **Agnóstico al sector.** El cliente mapea su vocabulario (SKU, local, sucursal…) a estos campos genéricos. SPC no conoce el negocio del cliente; conoce este contrato.
- **El contrato manda sobre la implementación**, no al revés. Los modelos y features se ajustan al contrato, no el contrato a lo que los modelos esperen.
- **Granularidad por defecto: diaria.** Configurable a semanal/mensual por agregación.
- **Granularidad de producto: categoría/familia por defecto**, producto individual como opción. La data de prueba (*Store Sales — Corporación Favorita*) trabaja a nivel `family`.
- **Bloque `historico` compartido.** VENTAS, COMPRAS y ALMACÉN reutilizan el mismo bloque `historico`, de modo que el cliente integra una vez y puede pedir los tres campos.

---

## 2. Convención común de campos

| Campo genérico | Tipo | Significado | Equivalente en la data de prueba |
|---|---|---|---|
| `fecha` | date (ISO `YYYY-MM-DD`) | Fecha de la observación | `date` |
| `punto_venta_id` | str/int | Local, tienda o sucursal | `store_nbr` |
| `producto_id` o `categoria` | str | Producto o familia | `family` |
| `unidades_vendidas` | float ≥ 0 | Demanda observada | `sales` |
| `en_promocion` | int ≥ 0 | Ítems en promoción (0 si no aplica) | `onpromotion` |
| `transacciones` | float ≥ 0 *(opcional)* | Flujo de clientes/tickets | `transactions` |
| `evento_activo` | bool *(opcional)* | Feriado/evento relevante | `holiday_any` |

> **Tabla de equivalencias:** la columna "Equivalente en la data de prueba" existe para validar el motor con datos reales sin atar el contrato a un sector. Un cliente de otro rubro mapea sus propios campos a la columna "Campo genérico".

---

## 3. VENTAS — pronóstico de demanda (regresión)

**Datos mínimos que envía el cliente:** un histórico de la serie por `(fecha, punto_venta_id, producto_id)` con `unidades_vendidas`.
**Recomendado (mejora la señal, según el EDA):** `en_promocion` (corr ≈ 0.43) y `transacciones` (corr ≈ 0.23).
**Parámetros de la petición:** `horizonte` y `granularidad`.

**Qué devuelve:** por cada `(punto_venta_id, producto_id, periodo futuro)`, la demanda pronosticada en unidades, con intervalo opcional.

**Ejemplo de entrada**
```json
{
  "granularidad": "dia",
  "horizonte": 7,
  "historico": [
    {"fecha": "2017-08-01", "punto_venta_id": "1", "producto_id": "BEVERAGES",
     "unidades_vendidas": 1820, "en_promocion": 5, "transacciones": 1543},
    {"fecha": "2017-08-02", "punto_venta_id": "1", "producto_id": "BEVERAGES",
     "unidades_vendidas": 1675, "en_promocion": 0, "transacciones": 1490}
  ]
}
```

**Ejemplo de salida**
```json
{
  "campo": "ventas",
  "modelo": "regresion_v1",
  "pronostico": [
    {"fecha": "2017-08-16", "punto_venta_id": "1", "producto_id": "BEVERAGES",
     "demanda_pronosticada": 1742.5, "intervalo_80": [1450.0, 2080.0]},
    {"fecha": "2017-08-17", "punto_venta_id": "1", "producto_id": "BEVERAGES",
     "demanda_pronosticada": 1690.2, "intervalo_80": [1402.0, 2015.0]}
  ],
  "metadatos": {"escala": "unidades", "transformacion_interna": "log1p"}
}
```

> Nota: el modelo entrena en escala `log1p` (el EDA muestra que reduce la asimetría 7.36 → 0.41) pero **devuelve siempre unidades** (revierte con `expm1`). El campo `intervalo_80` es opcional.

---

## 4. COMPRAS — reposición (derivado del pronóstico)

**Datos mínimos que envía el cliente:** lo necesario para convertir demanda en una orden de reposición — `stock_actual` por producto, `lead_time_dias` (tiempo de entrega del proveedor) y una `politica` (días de cobertura objetivo o nivel de servicio). El pronóstico de demanda se calcula internamente a partir del mismo histórico de VENTAS.

**Qué devuelve:** por producto/periodo, la cantidad sugerida a reponer y el punto de reorden.

**Ejemplo de entrada**
```json
{
  "historico": [ "... igual que en VENTAS ..." ],
  "parametros_reposicion": [
    {"punto_venta_id": "1", "producto_id": "BEVERAGES",
     "stock_actual": 900, "lead_time_dias": 3, "dias_cobertura_objetivo": 7}
  ]
}
```

**Ejemplo de salida**
```json
{
  "campo": "compras",
  "recomendacion": [
    {"punto_venta_id": "1", "producto_id": "BEVERAGES",
     "demanda_esperada_horizonte": 12200,
     "punto_de_reorden": 5400,
     "cantidad_a_reponer": 11300,
     "justificacion": "demanda_pronosticada + stock_seguridad - stock_actual"}
  ],
  "metadatos": {"supuesto": "demanda y lead time aproximados; revisar política del cliente"}
}
```

> COMPRAS **no tiene modelo propio**: es lógica de negocio (capa servicio) que deriva del pronóstico de VENTAS + lead time + cobertura. Los parámetros logísticos son del cliente; SPC no los inventa.

---

## 5. ALMACÉN — riesgo de quiebre y stock recomendado (clasificación + perfilado)

**Datos mínimos que envía el cliente:** histórico de demanda por producto (para clasificar `demanda_alta`) y `stock_actual`. Opcionalmente `lead_time_dias` para afinar el riesgo.

**Qué devuelve:** clase de demanda (alta/baja) con probabilidad, bandera de riesgo de quiebre y stock recomendado (incluye stock de seguridad).

**Ejemplo de entrada**
```json
{
  "historico": [ "... igual que en VENTAS ..." ],
  "estado_inventario": [
    {"punto_venta_id": "1", "producto_id": "BEVERAGES",
     "stock_actual": 300, "lead_time_dias": 3}
  ]
}
```

**Ejemplo de salida**
```json
{
  "campo": "almacen",
  "alertas": [
    {"punto_venta_id": "1", "producto_id": "BEVERAGES",
     "clase_demanda": "alta", "probabilidad_demanda_alta": 0.87,
     "riesgo_quiebre": true,
     "stock_recomendado": 1600,
     "stock_seguridad": 420,
     "segmento_tienda": 1}
  ],
  "metadatos": {"umbral": "demanda_alta = ventas > P75 de su familia"}
}
```

> El umbral `demanda_alta` se define como `ventas > P75` de su familia. El `segmento_tienda` proviene de la capa de **clustering/perfilado**, que enriquece la respuesta y afina políticas de stock.

---

## 6. Validación de esquema

La capa de datos/API valida estrictamente la entrada contra este contrato: tipos correctos, campos obligatorios presentes, rangos válidos (p. ej. `unidades_vendidas ≥ 0`). Las entradas mal formadas devuelven un error controlado y claro; los campos opcionales ausentes degradan con elegancia (el modelo usa lo que tenga).
