# ADR 0018 — Catálogo: tipologías y dimensiones de pronóstico

- **Estado:** Aceptado (2026-06-20).
- **Fase:** 4.5 — experiencia de usuario. Extiende `GET /catalog` para exponer, de forma
  estructurada, las opciones de consulta que la pantalla de Ventas necesita (tipología de
  pronóstico, dimensión de desglose/filtro, granularidad y rango de horizonte).
- **Contexto previo:** [ADR-0007](0007-capa-api-fase3.md) (capa API), catálogo derivado de los
  esquemas reales, [ADR-0015 §5](0015-rediseno-frontend-experiencia.md) (principio de cero
  hardcodeo de opciones en la UI).
- **No toca el motor de ML:** las opciones se derivan del **contrato** y de las **capacidades de
  agregación del servicio** (`ventas_service`), nunca del motor.

## Contexto

El profesor pidió dos controles en la pantalla de Ventas: **(R1)** un selector de *tipo de
pronóstico* (tipología) y **(R2)** un selector de *dimensión / filtrar por* (columna). Además,
[ADR-0015 §5](0015-rediseno-frontend-experiencia.md) fijó el principio de que tipologías,
columnas, granularidad y horizonte se **leen de `/catalog`** y no se clavan en la UI.

Sin embargo, `GET /catalog` aún **no** exponía esas opciones de forma consumible: la granularidad
solo aparecía como el `type` del input (`"day | week | month"`), el tope del horizonte (365) vivía
en un texto de `notes`, y no existían tipologías ni dimensiones. La pantalla de Ventas las
**hardcodeaba**. Este ADR cierra esa brecha.

## Decisión

### 1. Bloque `query_options` por dominio, derivado del contrato

Se añade a `DomainCatalog` un campo opcional `query_options` (esquema `QueryOptions`) presente en
los dominios que lo exponen —hoy **SALES**— y omitido (`None`) en los demás. Contiene:

- **`granularities`** — derivadas del `Literal Granularidad` del contrato (`day/week/month`), con
  etiqueta en español (**Día/Semana/Mes**).
- **`horizon`** (`min`/`max`/`default`/`unit`) — derivado de las restricciones del campo
  `horizon` de `VentasRequest` (`gt=0 → min 1`, `le=365 → max 365`). `default` es solo una
  sugerencia inicial para la UI (el campo es obligatorio en el contrato).
- **`dimensions`** (R2) — columnas **identificadoras** del bloque `history` (`store_id`,
  `product_id`), con etiqueta en español (**Tienda**, **Producto / Categoría**).
- **`typologies`** (R1) — `time_series` ("Serie temporal (por período)") y `by_dimension` ("Por
  dimensión"), con `requires_dimension` para activar R2 mediante *progressive disclosure*.

### 2. Honestidad por construcción + anti-desync

Igual que `inputs`/`outputs`, cada opción se **deriva** del contrato; no se escribe a mano un
valor que el contrato no respalde. Una batería de pruebas anti-desync
(`tests/api/test_catalog.py`) falla si: las granularidades dejan de calzar con el `Literal`; el
`min`/`max` del horizonte deja de calzar con las restricciones del request; o una dimensión deja
de existir como columna de `HistoricoItem`.

### 3. Las tipologías/dimensiones son afordancias de PRESENTACIÓN

`time_series` y `by_dimension` **no son modelos distintos**: el motor sigue produciendo el
pronóstico por `(date, store_id, product_id)`. La tipología y la dimensión gobiernan cómo la UI
**agrega/presenta** ese resultado (total por período vs. desglose por columna) y la
multiselección **filtra** las series. Por eso **no cambia el contrato** (`VentasRequest`/
`VentasResponse` intactos; versión 1.0.1): no se añaden campos al request ni a la respuesta.

### 4. Los VALORES de la dimensión no salen del catálogo

El catálogo expone las **columnas** (R2), no sus valores. Los valores concretos (p. ej.
categorías) se obtienen del **histórico real** que carga el cliente y la multiselección se
deshabilita hasta que haya datos: no se fabrican valores.

## Consecuencias

- **A favor:** la UI no hardcodea ninguna opción (cumple ADR-0015 §5); honestidad anti-desync;
  motor y contrato intactos; los controles (tipología/dimensión) son reutilizables por Compras y
  Almacén cuando declaren su propio `query_options`.
- **Deuda asumida:** la agregación/filtrado por tipología es **del lado del cliente**; si en el
  futuro se quisiera agregar/filtrar en el servidor habría que añadir campos al request y subir la
  versión del contrato (diferido, fuera de alcance).

## Referencias

- [ADR-0007 — Capa API (Fase 3)](0007-capa-api-fase3.md)
- [ADR-0015 — Rediseño de frontend / experiencia](0015-rediseno-frontend-experiencia.md)
- [ADR-0017 — Identidad visual / sistema de diseño](0017-identidad-visual-sistema-diseno.md)
