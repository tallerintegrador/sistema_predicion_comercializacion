# Contrato de Datos — SPC: Sistema Predictivo de Comercialización

> **Versión: `1.0.1`** · Documento vivo. Vive en `docs/contrato_datos.md`.
>
> Es la **única fuente de verdad** y la **frontera pública estable** del producto:
> define qué envía y qué recibe el cliente por API, con nombres genéricos y agnósticos
> al sector. Lo que cambie por dentro (modelos, features) **no debe romper este
> contrato**. La implementación se ajusta al contrato, no al revés.
>
> **Convención de idioma:** los **nombres de campos, parámetros, enums y errores van en
> inglés** (coinciden exacto con la API). La **explicación en prosa va en español**.

---

## 0. Versionado y changelog

El contrato se **versiona** (SemVer). Cualquier cambio que rompa la forma de entrada o
salida sube la versión **MAYOR**; un campo nuevo opcional sube la **MENOR**; una
aclaración sin cambio de forma sube el **PARCHE**.

| Versión | Cambios |
|---|---|
| **1.0.1** | **Solo documentación** (sin cambio de comportamiento): documenta dos campos de `metadata` que la API **ya entrega hoy** — `purchases.metadata.policy` (política de reposición, `coverage_days`) e `inventory.metadata.probability_threshold` (umbral numérico de probabilidad, leído del meta del artefacto). Ambos se declaran explícitamente en los esquemas de respuesta para que el catálogo (`GET /catalog`) los cubra. Añade el **catálogo de predicciones** como endpoint de solo lectura. |
| **1.0.0** | Primer contrato **canónico en inglés** como única fuente de verdad. Documenta el enum `granularity` (`day`/`week`/`month`), la cota `horizon ≤ 365` (en períodos de la granularidad), el **contrato de error estructurado** y el estado **diferido** de `interval_80`. Endurece la validación: **`strict=True`** prohíbe coerciones silenciosas de tipo. Incluye la tabla de mapeo desde los nombres en español de la v0.1. |
| 0.1 | Borrador inicial del contrato (nombres en español; consolidado desde la sección 3 del Plan Maestro). Sustituido por la 1.0.0. |

> El mapeo `nombre_es (v0.1)` → `nombre_en (v1.0.0)` está en la **sección 8**, para que
> nada se pierda en la transición.

---

## 1. Principios del contrato

- **Agnóstico al sector.** El cliente mapea su vocabulario (SKU, local, sucursal…) a
  estos campos genéricos. SPC no conoce el negocio del cliente; conoce este contrato.
- **El contrato manda sobre la implementación**, no al revés. Los modelos y features se
  ajustan al contrato, no el contrato a lo que los modelos esperen.
- **Único nombre de producto: `product_id`.** Ahí entra **producto individual o
  familia/categoría**, según la granularidad de producto del cliente. La data de prueba
  (*Store Sales — Corporación Favorita*) trabaja a nivel `family`.
- **Granularidad temporal por defecto: diaria.** Configurable a semanal/mensual por
  agregación (`granularity`).
- **Bloque `history` compartido.** SALES, PURCHASES e INVENTORY reutilizan el mismo
  bloque `history`, de modo que el cliente integra una vez y puede pedir los tres campos.
- **Validación estricta en la frontera.** La API valida; el motor confía. Una entrada
  mal formada se rechaza con un **error controlado** (HTTP 422), nunca llega al motor.
- **Honestidad.** El contrato describe solo lo real: no hay campos ni valores inventados.

---

## 2. Bloque común `history`

VENTAS, COMPRAS y ALMACÉN reutilizan este bloque. Cada elemento es una observación de la
serie `(date, store_id, product_id)`.

| Campo (canónico) | Tipo | Unidad | Obligatorio | Restricciones | Significado (ES) | Ejemplo |
|---|---|---|---|---|---|---|
| `date` | date (ISO `YYYY-MM-DD`) | — | **Sí** | Fecha válida; se parsea desde cadena ISO | Fecha de la observación | `"2017-08-01"` |
| `store_id` | str (acepta int→str) | — | **Sí** | No vacío (`min_length=1`) | Local, tienda o sucursal | `"1"` |
| `product_id` | str (acepta int→str) | — | **Sí** | No vacío | **Producto o familia/categoría** | `"BEVERAGES"` |
| `units_sold` | float | unidades | **Sí** | `≥ 0` | Demanda observada | `1820` |
| `on_promotion` | int | ítems | No (default `0`) | `≥ 0` | Ítems en promoción (0 si no aplica) | `5` |
| `transactions` | float \| null | tickets | No (default `null`) | `≥ 0` | Flujo de clientes/tickets | `1543` |
| `event_active` | bool \| null | — | No (default `null`) | — | Feriado/evento relevante | `true` |

> **Nota sobre identificadores.** `store_id` y `product_id` aceptan número o texto y se
> normalizan a texto (el cliente puede enviar `1` o `"1"` y se tratan igual). Esta es la
> **única** conversión de tipo permitida, y es **intencional y documentada** (no una
> coerción silenciosa).
>
> **Nota sobre opcionales.** Los campos opcionales ausentes **degradan con elegancia**:
> el motor usa lo que tenga. `on_promotion` (corr ≈ 0.43) y `transactions` (corr ≈ 0.23)
> mejoran la señal según el EDA.

---

## 3. SALES — pronóstico de demanda (regresión) · `POST /sales`

**Qué envía el cliente:** el bloque `history` más los parámetros `granularity` y
`horizon`.

**Parámetros de la petición**

| Campo | Tipo | Obligatorio | Restricciones | Significado (ES) |
|---|---|---|---|---|
| `granularity` | enum | No (default `"day"`) | `day` \| `week` \| `month` | Granularidad del pronóstico |
| `horizon` | int | **Sí** | `> 0` y `≤ 365` | Número de **períodos** futuros a pronosticar |
| `history` | list | **Sí** | `min_length = 1` | Histórico de la(s) serie(s) (sección 2) |

> **`horizon` se cuenta en períodos de la `granularity` elegida.** Con `day` son días,
> con `week` semanas y con `month` meses. La cota `≤ 365` aplica a **esos períodos** (no
> siempre a días): p. ej. `granularity="week"`, `horizon=8` pronostica 8 semanas.

**Qué devuelve:** por cada `(date, store_id, product_id)` futuro, la demanda pronosticada
en **unidades**, con intervalo opcional.

| Campo de salida | Tipo | Significado (ES) |
|---|---|---|
| `field` | str (`"sales"`) | Campo que respondió |
| `model` | str | Versión del artefacto que pronosticó (leída de la metadata, p. ej. `regresion_v3`) |
| `forecast[].date` | date | Período futuro |
| `forecast[].store_id` | str | Punto de venta |
| `forecast[].product_id` | str | Producto/familia |
| `forecast[].forecast_demand` | float `≥ 0` | Demanda esperada en unidades |
| `forecast[].interval_80` | list[float] \| ausente | Intervalo de predicción al 80% **(diferido, ver nota)** |
| `metadata.scale` | str | Escala de la salida (`units`) |
| `metadata.internal_transform` | str | Transformación interna informativa (`log1p`) |

**Ejemplo de entrada**
```json
{
  "granularity": "day",
  "horizon": 7,
  "history": [
    {"date": "2017-08-01", "store_id": "1", "product_id": "BEVERAGES",
     "units_sold": 1820, "on_promotion": 5, "transactions": 1543},
    {"date": "2017-08-02", "store_id": "1", "product_id": "BEVERAGES",
     "units_sold": 1675, "on_promotion": 0, "transactions": 1490}
  ]
}
```

**Ejemplo de salida**
```json
{
  "field": "sales",
  "model": "regresion_v3",
  "forecast": [
    {"date": "2017-08-03", "store_id": "1", "product_id": "BEVERAGES",
     "forecast_demand": 1742.5},
    {"date": "2017-08-04", "store_id": "1", "product_id": "BEVERAGES",
     "forecast_demand": 1690.2}
  ],
  "metadata": {"scale": "units", "internal_transform": "log1p"}
}
```

> **Escala.** El modelo entrena en escala `log1p` (el EDA muestra que reduce la asimetría
> 7.36 → 0.41) pero **devuelve siempre unidades** (revierte con `expm1`).
>
> **`interval_80` — diferido.** El campo existe en el contrato pero el modelo **aún no lo
> produce** (diferido a una fase posterior); por eso la respuesta lo **omite** hoy. Cuando
> se implemente, aparecerá como `[inferior, superior]` sin romper el contrato (campo
> opcional que pasa de ausente a presente).

---

## 4. PURCHASES — reposición (derivada del pronóstico) · `POST /purchases`

**Qué envía el cliente:** el mismo bloque `history` (de donde se deriva internamente el
pronóstico de demanda) y, por producto, los parámetros logísticos `replenishment_params`.
COMPRAS **no tiene modelo propio**: es lógica de negocio que deriva del pronóstico de
SALES + lead time + cobertura.

**Parámetros de `replenishment_params[]`** (son **del cliente**; SPC no los inventa)

| Campo | Tipo | Unidad | Obligatorio | Restricciones | Significado (ES) |
|---|---|---|---|---|---|
| `store_id` | str | — | **Sí** | No vacío | Punto de venta |
| `product_id` | str | — | **Sí** | No vacío | Producto/familia |
| `current_stock` | float | unidades | **Sí** | `≥ 0` | Stock disponible hoy |
| `lead_time_days` | int | días | **Sí** | `> 0` | Tiempo de entrega del proveedor |
| `target_coverage_days` | int | días | **Sí** | `> 0` | Días de demanda que se quiere cubrir |

**Qué devuelve:** por producto/período, la cantidad sugerida a reponer y el punto de
reorden.

| Campo de salida | Tipo | Significado (ES) |
|---|---|---|
| `field` | str (`"purchases"`) | Campo que respondió |
| `recommendation[].store_id` / `.product_id` | str | Serie recomendada |
| `recommendation[].expected_demand_horizon` | float `≥ 0` | Demanda pronosticada acumulada sobre la cobertura |
| `recommendation[].reorder_point` | float `≥ 0` | Nivel que dispara una nueva orden |
| `recommendation[].replenishment_quantity` | float `≥ 0` | Unidades sugeridas a pedir |
| `recommendation[].justification` | str | Fórmula/razonamiento |
| `metadata.assumption` | str | Supuestos de la derivación (incluye el colchón de seguridad aplicado) |
| `metadata.policy` | str | Política de reposición aplicada (`coverage_days`) |

**Ejemplo de entrada**
```json
{
  "history": [
    {"date": "2017-08-01", "store_id": "1", "product_id": "BEVERAGES",
     "units_sold": 1820, "on_promotion": 5, "transactions": 1543}
  ],
  "replenishment_params": [
    {"store_id": "1", "product_id": "BEVERAGES",
     "current_stock": 900, "lead_time_days": 3, "target_coverage_days": 7}
  ]
}
```

**Ejemplo de salida**
```json
{
  "field": "purchases",
  "recommendation": [
    {"store_id": "1", "product_id": "BEVERAGES",
     "expected_demand_horizon": 12200,
     "reorder_point": 5400,
     "replenishment_quantity": 11300,
     "justification": "forecast_demand(lead_time + coverage) + safety_stock - current_stock"}
  ],
  "metadata": {
    "assumption": "stock de seguridad = 30% de la demanda en lead time; demanda y lead time aproximados; revisar política del cliente",
    "policy": "coverage_days"
  }
}
```

> **Colchón de seguridad — constante de política configurable (ADR-0010).** Por defecto el
> stock de seguridad es el **30 %** de la demanda durante el *lead time* (método
> `coverage_days`), y se reporta en `metadata.assumption` / `metadata.policy`. Ya **no es
> fija**: el factor (`SPC_PURCHASES_SAFETY_FACTOR`) y el método
> (`SPC_PURCHASES_SAFETY_METHOD`: `coverage_days` | `service_level`) se configuran por
> entorno con defaults documentados. La forma de la respuesta no cambia; solo el valor
> reportado del supuesto refleja la configuración efectiva.

---

## 5. INVENTORY — riesgo de quiebre y stock recomendado · `POST /inventory`

**Qué envía el cliente:** el bloque `history` (para clasificar `high`/`low` demanda) y, por
producto, el `inventory_status` (clasificación + perfilado).

**Parámetros de `inventory_status[]`**

| Campo | Tipo | Unidad | Obligatorio | Restricciones | Significado (ES) |
|---|---|---|---|---|---|
| `store_id` | str | — | **Sí** | No vacío | Punto de venta |
| `product_id` | str | — | **Sí** | No vacío | Producto/familia |
| `current_stock` | float | unidades | **Sí** | `≥ 0` | Stock disponible hoy |
| `lead_time_days` | int \| null | días | No (default `null`) | `> 0` | Tiempo de entrega (opcional; afina el riesgo) |

**Qué devuelve:** clase de demanda (`high`/`low`) con probabilidad, bandera de riesgo de
quiebre y stock recomendado (incluye stock de seguridad).

| Campo de salida | Tipo | Significado (ES) |
|---|---|---|
| `field` | str (`"inventory"`) | Campo que respondió |
| `alerts[].store_id` / `.product_id` | str | Serie evaluada |
| `alerts[].demand_class` | enum (`high`\|`low`) | Clase de demanda predicha |
| `alerts[].high_demand_probability` | float `0–1` | Probabilidad de demanda alta |
| `alerts[].stockout_risk` | bool | True si el stock no cubre la demanda esperada |
| `alerts[].recommended_stock` | float `≥ 0` | Stock objetivo (demanda en lead time + seguridad) |
| `alerts[].safety_stock` | float `≥ 0` | Colchón ante variabilidad |
| `alerts[].store_segment` | int | Segmento del punto de venta (clustering/perfilado) |
| `metadata.threshold` | str | Definición del umbral de demanda alta |
| `metadata.probability_threshold` | float \| null | Umbral numérico de probabilidad (leído del meta; `null` si no se expone) |

**Ejemplo de entrada**
```json
{
  "history": [
    {"date": "2017-08-01", "store_id": "1", "product_id": "BEVERAGES",
     "units_sold": 1820, "on_promotion": 5, "transactions": 1543}
  ],
  "inventory_status": [
    {"store_id": "1", "product_id": "BEVERAGES", "current_stock": 300, "lead_time_days": 3}
  ]
}
```

**Ejemplo de salida**
```json
{
  "field": "inventory",
  "alerts": [
    {"store_id": "1", "product_id": "BEVERAGES",
     "demand_class": "high", "high_demand_probability": 0.87,
     "stockout_risk": true,
     "recommended_stock": 1600,
     "safety_stock": 420,
     "store_segment": 1}
  ],
  "metadata": {
    "threshold": "high_demand = sales > P75 of its family",
    "probability_threshold": 0.3185
  }
}
```

> El umbral `high_demand` se define como `sales > P75` de su familia. El `store_segment`
> proviene de la capa de **clustering/perfilado**, que enriquece la respuesta y afina las
> políticas de stock. Ambos valores son informativos: se leen de la metadata del
> artefacto, no se clavan aquí. El `probability_threshold` es el umbral numérico de
> probabilidad con que el clasificador separa alta/baja: también se **lee del meta** del
> artefacto (no se hard-codea) y es `null` si el artefacto no lo expone.
>
> **Constantes de política configurables (ADR-0010).** Si el cliente no envía
> `lead_time_days`, se asume **7 días** (`SPC_INVENTORY_LEAD_TIME_DEFAULT`). Por defecto
> el stock de seguridad usa **nivel de servicio** (`z·σ·√lead_time`, con σ calculada de la
> demanda **real** del cliente, no inventada): `z` base 1.28 / alto volumen 1.65
> (`SPC_INVENTORY_Z_BASE` / `SPC_INVENTORY_Z_HIGH_VOLUME`), ventana de demanda 28 días
> (`SPC_INVENTORY_DEMAND_WINDOW`) y respaldo 0.5 (`SPC_INVENTORY_SAFETY_FALLBACK_FACTOR`).
> El método es un knob (`SPC_INVENTORY_SAFETY_METHOD`: `service_level` por defecto |
> `coverage_days`): ponerlo en `coverage_days` **unifica INVENTORY con PURCHASES**. La
> forma de la respuesta no cambia.

---

## 6. Validación de esquema (frontera estricta)

La capa de API valida **estrictamente** toda entrada contra este contrato **antes** de
pasar nada al motor. Reglas que se aplican:

- **Campos desconocidos prohibidos** (`extra="forbid"`): cualquier campo no declarado en
  el contrato hace fallar la petición.
- **Campos obligatorios presentes** y **listas no vacías** (`min_length=1` en `history`,
  `replenishment_params`, `inventory_status`).
- **Rangos numéricos**: `units_sold ≥ 0`, `on_promotion ≥ 0`, `horizon` en `(0, 365]`,
  `lead_time_days > 0`, etc.
- **Formato de fecha**: `date` debe ser una fecha ISO válida (`YYYY-MM-DD`).
- **Identificadores no vacíos**: `store_id` y `product_id` con al menos un carácter.
- **Sin coerciones silenciosas de tipo (`strict=True`)**: enviar un número como texto
  (`units_sold: "123"`), un entero como decimal donde se espera entero
  (`on_promotion: 5.0`), o un booleano como texto (`event_active: "true"`) se **rechaza**
  con error, en vez de convertirse en silencio. La **única** conversión permitida es
  `store_id`/`product_id` de número a texto, que es intencional y está documentada
  (sección 2). El campo `date` acepta cadena ISO porque JSON no tiene tipo fecha nativo.

### 6.1. Contrato de error (forma uniforme)

Toda entrada mal formada o regla de negocio incumplida devuelve **el mismo cuerpo**,
nunca un 500 sin manejar ni un volcado de pila:

```json
{
  "error": {
    "type": "validation",
    "message": "La entrada no cumple el contrato de datos.",
    "details": [
      {"field": "history.0.units_sold", "problem": "Input should be greater than or equal to 0"}
    ]
  }
}
```

| Campo del error | Tipo | Significado (ES) |
|---|---|---|
| `error.type` | str | Categoría: `validation`, `invalid_request`, `service_unavailable`, `internal_error` |
| `error.message` | str | Mensaje claro y accionable para el cliente |
| `error.details[].field` | str | Ruta del campo que falló (p. ej. `history.0.units_sold`) |
| `error.details[].problem` | str | Descripción legible del problema |

| Situación | HTTP | `error.type` |
|---|---|---|
| Entrada mal formada (tipo, rango, campo faltante, campo extra, fecha inválida) | **422** | `validation` |
| Regla de negocio incumplida (p. ej. producto sin histórico) | **400** | `invalid_request` |
| Motor no cargado | **503** | `service_unavailable` |
| Error inesperado controlado | **500** | `internal_error` |

---

## 7. Un solo contrato para todos los canales y modos

> El **canal Excel** ya está **implementado** (Fase 3.3, en línea). El **modo por lote**
> sigue siendo **documentación de intención** (Fase 3.4).

- **Mismo contrato para JSON y para Excel (implementado).** El cliente puede enviar los
  mismos campos por un archivo Excel: descarga la plantilla en `GET /{domain}/template` y
  la sube en `POST /{domain}/excel`. La **fuente de verdad sigue siendo este contrato**:
  el lector de Excel produce exactamente los mismos campos (`date`, `store_id`,
  `product_id`, `units_sold`, …), **convierte los tipos explícitamente** (ver §8.b) y pasa
  por **la misma validación y la misma predicción** que el JSON, devolviendo la misma
  respuesta. No hay un "contrato de Excel" aparte ni un segundo camino de predicción. Los
  errores reutilizan el cuerpo de §6.1, añadiendo en `field` la **hoja/fila/columna**.
- **Mismo contrato en modo en línea y por lote (lote: planificado).** La entrada en línea
  (una petición) y la entrada por lote (un conjunto grande de series) comparten **idéntico
  esquema de campos y reglas**. Cambia el transporte y el tamaño, no el contrato.

---

## 8. Dependencias a futuro (no se implementan en esta fase)

Registradas para no perderlas; **ninguna** se implementa en la Fase 3.1:

- **(a) ALMACÉN por días de cobertura (ADR-0010, resuelto).** La decisión P2 quedó cerrada
  en el ADR-0010: INVENTORY mantiene **nivel de servicio** (`z·σ·√lead`) como método por
  defecto —legítimo porque σ sale de la demanda real— y la unificación a días de cobertura
  queda a **un cambio de variable de entorno** (`SPC_INVENTORY_SAFETY_METHOD=coverage_days`),
  sin tocar la forma del contrato. Si en el futuro se quisiera que el cliente fije la
  cobertura por petición, haría falta un campo nuevo `target_coverage_days` en INVENTORY
  (como ya existe en PURCHASES): sería un **campo nuevo** y subiría la versión del contrato
  (MENOR si es opcional). Eso **no** se implementa aquí.
- **(b) Lector de Excel (Fase 3.3) y `strict`.** Con `strict=True` ya **no hay coerción
  automática** de tipos. Por eso, el lector de Excel deberá **convertir los tipos de forma
  explícita** (texto de celda → número/fecha/booleano) **antes** de validar contra el
  contrato; si no, las celdas (que llegan como texto) serían rechazadas. La conversión
  explícita es responsabilidad del adaptador de Excel, no de la frontera de validación.

---

## 9. Mapeo de nombres `v0.1 (es)` → `v1.0.0 (en)`

Para que nada se pierda en la transición desde el borrador en español.

**Bloque común**

| v0.1 (es) | v1.0.0 (en) |
|---|---|
| `historico` | `history` |
| `fecha` | `date` |
| `punto_venta_id` | `store_id` |
| `producto_id` / `categoria` | `product_id` (único nombre) |
| `unidades_vendidas` | `units_sold` |
| `en_promocion` | `on_promotion` |
| `transacciones` | `transactions` |
| `evento_activo` | `event_active` |

**SALES**

| v0.1 (es) | v1.0.0 (en) |
|---|---|
| `granularidad` (valor `dia`) | `granularity` (valor `day`) |
| `horizonte` | `horizon` |
| `campo` | `field` |
| `modelo` | `model` |
| `pronostico` | `forecast` |
| `demanda_pronosticada` | `forecast_demand` |
| `intervalo_80` | `interval_80` |
| `metadatos` | `metadata` |

**PURCHASES**

| v0.1 (es) | v1.0.0 (en) |
|---|---|
| `parametros_reposicion` | `replenishment_params` |
| `stock_actual` | `current_stock` |
| `lead_time_dias` | `lead_time_days` |
| `dias_cobertura_objetivo` | `target_coverage_days` |
| `recomendacion` | `recommendation` |
| `demanda_esperada_horizonte` | `expected_demand_horizon` |
| `punto_de_reorden` | `reorder_point` |
| `cantidad_a_reponer` | `replenishment_quantity` |
| `justificacion` | `justification` |

**INVENTORY**

| v0.1 (es) | v1.0.0 (en) |
|---|---|
| `almacen` | `inventory` |
| `estado_inventario` | `inventory_status` |
| `alertas` | `alerts` |
| `clase_demanda` (valores `alta`/`baja`) | `demand_class` (valores `high`/`low`) |
| `probabilidad_demanda_alta` | `high_demand_probability` |
| `riesgo_quiebre` | `stockout_risk` |
| `stock_recomendado` | `recommended_stock` |
| `stock_seguridad` | `safety_stock` |
| `segmento_tienda` | `store_segment` |
