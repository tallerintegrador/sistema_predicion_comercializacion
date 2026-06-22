# ADR 0021 — Ajustes de experiencia: regla de entrada de datos, filtros de resultado y alcance de reentrenamiento

- **Estado:** Aceptado (2026-06-21).
- **Fase:** 4.5 — experiencia de usuario. **Extiende** (no reemplaza) el rediseño de
  [ADR-0020](0020-rediseno-cliente-identidad-pantallas.md) y la derivación del catálogo de
  [ADR-0018](0018-catalogo-tipologias-dimensiones.md); reutiliza la política configurable de
  [ADR-0010](0010-politica-inventario-stock.md).
- **Alcance:** solo capa de presentación (frontend) y la capa servicio/API (catálogo). **El motor
  de ML no se toca.**

## Contexto

Tras el rediseño en 3 pasos (Datos → Configuración → Resultado), el uso real dejó ver fricciones:
la carga manual permitía teclear el **historial de ventas** (una lista larga, propensa a error),
una fila en blanco se contaba como dato, Ventas insinuaba que el sistema se adaptaba a la
configuración embebida del Excel, los resultados de Compras/Almacén no se podían filtrar, y
«Mejorar las predicciones» no dejaba claro qué se entrena (ni que el inventario no es insumo de
entrenamiento). Había además dos campos logísticos (tiempo de entrega y días de cobertura) que el
usuario debía llenar fila por fila.

## Decisión

### 1. Regla unificada de entrada de datos

La entrada manual («Agregar fila») es **solo** para listas cortas del **estado actual**; el
**historial de ventas se carga siempre por archivo** (Excel/JSON):

- **Ventas:** únicamente carga por archivo (ya era así; no hay tabla manual).
- **Compras / Almacén:** la sub-tabla «Historial de ventas» deja de ser editable (se quita su
  «Agregar fila») y se muestra como resumen de solo lectura cuando se carga. La carga manual queda
  solo para «Productos a reponer» / «Estado del inventario».
- El **resumen** deja de contar filas vacías: «Filas» refleja solo filas con datos reales.

### 2. Valores por defecto editables desde la política (`CatalogColumn.default`)

`/catalog` expone, por columna, un `default` **editable** para prellenar la carga manual sin
clavar literales en el frontend. La **fuente** del valor es la configuración de política
(ADR-0010), no la capa de presentación:

- `lead_time_days` → `inventory_lead_time_default()` (`SPC_INVENTORY_LEAD_TIME_DEFAULT`, 7).
- `target_coverage_days` → `purchases_target_coverage_days()`
  (`SPC_PURCHASES_TARGET_COVERAGE_DAYS`, **14**), **variable nueva** añadida en `spc.config` para
  este fin (no existía una equivalente). No altera el cálculo: es solo el valor sugerido editable.

Una prueba anti-desync verifica que el `default` del catálogo == el accesor de `spc.config` y que
cada clave es una columna real del contrato.

### 3. Filtros de resultado derivados de campos reales (vs. «Próximamente»)

Compras y Almacén ganan una **barra de filtros** sobre la tabla de resultado. Solo se ofrece lo que
la respuesta **ya entrega** (los valores salen de las filas reales, nunca se inventan ni se
hardcodean):

- **Compras:** por tienda (`store_id`), por producto (`product_id`), «solo los que requieren
  reposición ahora» (`replenishment_quantity > 0`) y orden por cantidad a reponer.
- **Almacén:** por tienda, por producto, por segmento de tienda (`store_segment`), «solo en riesgo
  de agotarse» (`stockout_risk`) y orden por riesgo (`stockout_risk` + `high_demand_probability`).

Lo que el backend no entrega hoy se muestra **deshabilitado** y rotulado **«Próximamente»**:
categoría/familia (ambos), orden por **urgencia** (Compras) y nivel de riesgo **alto/medio/bajo**
(Almacén). Registrado en [alineacion_frontend_backend.md](../alineacion_frontend_backend.md) §9.

### 4. Alcance del reentrenamiento

- Insumo único = **historial de ventas** (la misma plantilla de Ventas). El inventario **no** es
  dato de entrenamiento, por eso no se pide aquí.
- Selector **«¿Qué quieres mejorar?»**: **Ventas** (disponible) y **Almacén** («Próximamente»).
  **Compras** no se entrena por separado: mejora cuando mejora Ventas.

### 5. Limpieza

- El indicador técnico «Servidor: …» ya estaba restringido a administradores (ADR-0020); se
  conserva así (sin cambios).

## Consecuencias

- **A favor:** menos errores de carga (el historial no se teclea), resúmenes honestos (sin filas
  vacías), resultados navegables, expectativas claras de qué se entrena; cero hardcodeo (defaults y
  valores de filtro salen del catálogo / de los datos reales); honestidad preservada
  («Próximamente» para lo no soportado).
- **Deuda asumida:** quedan funciones marcadas «Próximamente» a la espera de backend
  (categoría/familia, urgencia, niveles de riesgo, reentrenamiento de Almacén, verificación de
  datos suficientes y reutilización del historial guardado) — todas en la alineación §9.

## Referencias

- [ADR-0010 — Política de inventario / stock](0010-politica-inventario-stock.md)
- [ADR-0018 — Catálogo: tipologías y dimensiones](0018-catalogo-tipologias-dimensiones.md)
- [ADR-0020 — Rediseño orientado al cliente](0020-rediseno-cliente-identidad-pantallas.md)
- [docs/alineacion_frontend_backend.md](../alineacion_frontend_backend.md)
