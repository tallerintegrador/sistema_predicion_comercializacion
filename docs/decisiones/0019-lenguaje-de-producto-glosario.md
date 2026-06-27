# ADR 0019 — Lenguaje de producto / glosario sin tecnicismos

- **Estado:** Aceptado (2026-06-21).
- **Fase:** 4.5 — experiencia de usuario. Define el **lenguaje** del producto orientado a un
  dueño de PYME no técnico, como contraparte de la identidad visual ([ADR-0020](0020-rediseno-cliente-identidad-pantallas.md)).
- **Contexto previo:** [ADR-0014](0014-control-acceso-por-roles.md) (permisos con etiqueta en
  español), [ADR-0018](0018-catalogo-tipologias-dimensiones.md) (opciones derivadas del catálogo).

## Contexto

La interfaz funcionaba pero estaba escrita para desarrolladores: mostraba términos en inglés y
tecnicismos (`SALES`, `stock`, `lead time`, `granularity`, `horizon`, `replenishment_params`,
`inventory_status`, `forecast_demand`, `interval_80`, `WAPE`, «modelo congelado», `opt-in`,
`baseline`, `job_id`, esquemas de API, referencias a ADRs…) que un dueño de negocio no entiende.

## Decisión

### 1. Glosario obligatorio (inglés/tecnicismo → español claro)

La UI muestra **solo** español formal y sin jerga. Reemplazos aplicados:

| Técnico | En la interfaz |
|---|---|
| SALES / PURCHASES / INVENTORY | Ventas / Compras / Almacén |
| stock / current_stock | Existencias (actuales) |
| lead_time_days | Tiempo de entrega (días) |
| granularity | ¿Cada cuánto? (Día/Semana/Mes) |
| horizon | ¿Hasta cuándo? |
| forecast_demand | Demanda estimada |
| reorder_point | Reponer al bajar a |
| replenishment_quantity | Cuánto reponer |
| stockout_risk | Riesgo de agotarse (semáforo) |
| recommended_stock | Existencias sugeridas |
| safety_stock | Colchón de seguridad |
| store_id / product_id | Tienda / Producto |
| interval_80 | Rango estimado (80%) |
| WAPE | margen de error |
| «modelo congelado» | modelo base del sistema |
| opt-in | opcional, tú decides |
| baseline | método de referencia simple |
| online / batch | (oculto: el sistema decide solo) |
| model / metadata / scale / job_id / ADR | (ocultos al usuario) |

Los permisos de rol se muestran con su **etiqueta legible** (p. ej. «Ver catálogo»,
«Pronosticar», «Reentrenar»), nunca con la clave técnica (`module:sales`, `action:forecast`).

### 2. «Detalles técnicos» como único lugar para tecnicismos

Cualquier término técnico **necesario** (versión de contrato, nombre del modelo, métricas
`WAPE/MAE/RMSE`, definición de umbral) vive en un bloque colapsable **«Detalles técnicos»**
(`components/ui/TechnicalDetails.tsx`), cerrado por defecto, o en la pantalla **«Acerca del
sistema»**. Nunca en el camino principal del usuario.

### 3. Honestidad en lenguaje simple

- Se conserva el mensaje de que el sistema se entrenó con un **comercio de ejemplo** y que para
  otros rubros los resultados son **referenciales**, dicho sin jerga (sin «modelo congelado /
  contrato v1.0.1» visibles).
- Funciones no soportadas por el backend se muestran **deshabilitadas** con la etiqueta
  **«Próximamente»** (`components/ui/ComingSoon.tsx`); **nunca** se simulan resultados.
- Los **resúmenes en lenguaje natural** (`utils/resumen.ts`) son funciones puras sobre datos
  reales de la API: no inventan cifras.

## Consecuencias

- **A favor:** la interfaz es comprensible para el público objetivo; la honestidad se mantiene
  sin exponer jerga; el glosario centralizado evita fugas de inglés.
- **Deuda asumida:** el glosario es texto de producto (no derivado del backend); cualquier
  término nuevo del contrato debe traducirse al añadirse a la UI. Las etiquetas de columnas de
  carga **sí** se derivan del catálogo ([ADR-0020](0020-rediseno-cliente-identidad-pantallas.md), §`input_tables`)
  para no duplicar.

## Referencias

- [ADR-0020 — Rediseño orientado al cliente: identidad visual y pantallas](0020-rediseno-cliente-identidad-pantallas.md)
- [docs/alineacion_frontend_backend.md](../alineacion_frontend_backend.md)
