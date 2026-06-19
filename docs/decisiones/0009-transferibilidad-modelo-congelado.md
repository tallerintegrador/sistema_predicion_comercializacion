# ADR 0009 — Transferibilidad: modelo congelado y Favorita como cliente de ejemplo

- **Estado:** Aceptado (2026-06-19).
- **Fase:** 3.6 — Documentación de alcance y limitaciones. **Formaliza** la postura de
  transferibilidad que ya estaba implícita en la arquitectura (modelo congelado de Fase 2,
  servido sin reentrenar por la API de Fase 3).
- **Contexto previo:** `docs/contrato_datos.md` (frontera agnóstica al sector), ADR-0007
  (capa API: degradación con elegancia para IDs/metadatos desconocidos), ADR-0008 §5
  (lote contra el modelo congelado; ajuste por cliente diferido), ADR-0010 (parámetros del
  modelo vienen de la metadata). Recomendaciones del docente 2 y 3 (plataforma agnóstica;
  el cliente trae sus datos) y 7 (transparencia).
- **No toca** el motor de ML ni la API: es una decisión de **postura y comunicación**.
  Cierra la referencia a "ADR-0009" que ADR-0008 y ADR-0010 ya hacían.

## Contexto

SPC se presenta como **plataforma agnóstica al rubro**: el cliente mapea su vocabulario al
contrato de datos y pide predicciones. Pero el motor de ML se entrenó, validó y **congeló**
sobre un único cliente de ejemplo —*Store Sales — Corporación Favorita*, retail de
supermercado en Ecuador— y la API lo **sirve sin reentrenar**. Hay que decir con precisión
**qué significa eso para un cliente nuevo**, sin vender de más.

La arquitectura ya implica la postura; faltaba escribirla como decisión:

- El modelo de regresión, el clasificador y los clusterings son artefactos **fijos** de la
  Fase 2 (`regresion_v3`, `clasificacion_v1`, `clustering_{tiendas,familias}_v1`).
- El contrato es **agnóstico**: solo lleva campos genéricos (`date`, `store_id`,
  `product_id`, `units_sold`, `on_promotion?`, `transactions?`, `event_active?`). **No**
  lleva los metadatos específicos de Favorita con los que el modelo se entrenó (tipo de
  tienda, ciudad, estado, cluster comercial, precio del petróleo).
- Para un cliente nuevo, esos metadatos caen a **"desconocido"** y, bajo el
  `CategoricalDtype` fijo del artefacto, las categóricas desconocidas pasan a `NaN` (los
  árboles lo toleran). El pronóstico se sostiene entonces sobre lo **genérico**: rezagos
  del propio histórico del cliente + calendario derivado de la fecha.

## Decisión

**El modelo se entrega congelado, y Favorita es el cliente de ejemplo con el que se validó
la metodología — no "el modelo del producto".** La transferibilidad a otro rubro se
comunica como **señal limitada y sin garantía**, y el ajuste por cliente queda como
**dirección futura y medida**.

### 1. Favorita es el banco de pruebas, no el producto

Las métricas de Favorita (WAPE recursivo 14.59 %, PR-AUC 0.9343, siluetas 0.6742 / 0.659)
**demuestran que el método funciona sobre ese dato**. Se reportan siempre rotuladas como
**medidas sobre Favorita**. No se presentan como rendimiento esperable para un cliente
arbitrario.

### 2. Un cliente nuevo opera con señal genérica y limitada (honestidad)

Hay que ser explícito para no inducir a error:

- La expresión técnica **"degradación con elegancia"** (ADR-0007) significa que el sistema
  **no se cae** ante datos desconocidos: responde con lo que tiene. **No** significa que
  "funciona bien" en otro rubro. Léase como **"se degrada"**, no como reaseguro.
- Para un negocio que **no se parezca** al retail de supermercado de Favorita, la señal del
  modelo congelado (rezagos + calendario, sin los niveles categóricos aprendidos) es
  **limitada y sin garantía**. La frase correcta es *"sigue respondiendo con señal
  reducida"*, no *"se mantiene el rendimiento"*.
- **Cuánto** se degrada para un rubro distinto **no está medido**: la validación se hizo con
  un solo cliente de ejemplo. Por tanto **no se afirma** un número de transferibilidad. Es
  una limitación honesta, no un detalle.

### 3. Por qué congelado en esta entrega

- **Separación de capas y reproducibilidad:** la API carga y predice; no entrena en
  caliente. El mismo artefacto + el mismo código → la misma respuesta.
- **No teníamos un segundo cliente** con el que medir transferibilidad o ajuste, así que
  reentrenar por cliente habría sido una promesa no validada.
- El modo por lote (ADR-0008 §5) también corre contra el modelo congelado (opción A): solo
  cambia *cómo* se procesa, no *qué* modelo.

### 4. Ajuste por cliente: dirección futura y medida (no se implementa)

El **ajuste por cliente** —reentrenar o calibrar el modelo con los datos del propio
cliente (opción B/híbrida de ADR-0008)— queda como **experimento futuro**, que solo se
activaría **si los resultados lo justifican** sobre datos reales del cliente. El catálogo
ya lo refleja: `mode client_adjustment = planned`. Caminos posibles, no comprometidos:

- *Fine-tuning* / reentrenamiento por cliente cuando haya histórico suficiente.
- Calibración de probabilidades por cliente (Platt/isotónica) para el clasificador.
- Perfil de clustering *as-of-time* y recomputado sobre el histórico del cliente.

## Consecuencias

- **Cumple las recomendaciones 2, 3 y 7:** la plataforma es agnóstica (el cliente trae sus
  datos por contrato) y la comunicación es **transparente** sobre los límites del modelo
  congelado.
- **Comunicación honesta:** se evita el sobre-claim de transferibilidad; "agnóstico al
  sector" describe el **contrato**, no una garantía de rendimiento del **modelo** en
  cualquier rubro.
- **Deuda asumida y explícita:** sin medición de transferibilidad a otros rubros; ajuste
  por cliente diferido. Ambas registradas, ninguna implementada aquí.

## Referencias

- [ADR-0007 — Capa de servicio / API (degradación con elegancia)](0007-capa-api-fase3.md)
- [ADR-0008 — Modos de ejecución (modelo congelado; ajuste por cliente diferido)](0008-modos-ejecucion.md)
- [ADR-0010 — Política de inventario (parámetros del modelo desde la metadata)](0010-politica-inventario-stock.md)
- [Alcance, metodología de validación y limitaciones (§2.2, §5.1)](../fase-3/alcance_validacion_limitaciones.md)
- [contrato_datos.md](../contrato_datos.md)
