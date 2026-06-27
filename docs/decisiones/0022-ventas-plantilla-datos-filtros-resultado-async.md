# ADR 0022 — Ventas: plantilla solo-datos, configuración en pantalla, filtros sobre el resultado y procesamiento honesto

- **Estado:** Aceptado (2026-06-21).
- **Fase:** 4.5 — experiencia de usuario. **Extiende** (no reemplaza) el rediseño de
  [ADR-0020](0020-rediseno-cliente-identidad-pantallas.md) y los ajustes de
  [ADR-0021](0021-ajustes-experiencia-entrada-filtros-reentrenamiento.md); reutiliza el catálogo
  de [ADR-0018](0018-catalogo-tipologias-dimensiones.md) y el glosario de
  [ADR-0019](0019-lenguaje-de-producto-glosario.md).
- **Alcance:** capa de presentación (frontend) y capa **servicio/API** (canal Excel y lector).
  **El motor de ML no se toca** (`src/spc/models/`, features de ML).

## Contexto

Tras el flujo en 3 pasos (Datos → Configuración → Resultado), quedaron cuatro fricciones en
**Ventas** que ADR-0021 ya había empezado a señalar:

1. **Doble fuente de configuración.** La plantilla de Ventas traía una hoja `parameters`
   (`granularity`, `horizon`), de modo que el pronóstico se configuraba **a la vez** en el archivo
   y en la pantalla. El canal Excel (`POST /sales/excel`) **derivaba** la configuración del archivo
   e **ignoraba** la pantalla; la UI ya declaraba la pantalla como única fuente, pero el backend no
   la respetaba para Excel.
2. **Controles de cálculo mezclados con vistas.** Antes de pronosticar, Ventas pedía la tipología
   («total / por dimensión»), la dimensión y los valores concretos. Pero esos controles **no cambian
   el cálculo**: son formas de **mirar el mismo resultado**. Estar antes del botón sugería —en falso—
   que recalculaban, y «valores concretos» filtraba el histórico previo (solo posible con JSON).
3. **Tecnicismos en el estado de archivos grandes.** El banner de procesamiento en segundo plano
   exponía «modo lote (asíncrono)», «job» y «consulta #N».
4. **Inglés filtrándose a la app.** La leyenda del gráfico mostraba `units_sold`/`forecast_demand`;
   Almacén mostraba «demanda high»; Compras mostraba la **fórmula cruda** en «Por qué»; y se usaba
   «stock» en vez de «existencias».

Las plantillas de **Compras y Almacén** no presentan el problema 1: su segunda hoja
(`replenishment_params` / `inventory_status`) es **estado actual del inventario = datos**, no
configuración.

## Decisión

### 1. Plantilla de Ventas: **solo datos**

La plantilla de Ventas pasa a tener únicamente la hoja de **instrucciones** (español) + la hoja
**`history`** (datos). Se **elimina la hoja `parameters`**. Compras/Almacén no cambian.

- Implementación: se quita la `HojaExcel` `parameters` de la plantilla `sales` en
  `src/spc/api/ingest/esquema_excel.py` (capa servicio/API, **no** el motor). El mecanismo de hoja
  escalar (`es_lista=False`) se conserva en el código por si un dominio futuro lo necesita, pero hoy
  ningún dominio lo usa.

### 2. La configuración del pronóstico viaja en la **petición en pantalla**

`granularity` y `horizon` se envían como **campos de formulario** en `POST /sales/excel`, junto al
archivo. Son la **única fuente** de la configuración del pronóstico, también cuando se sube Excel.

- `src/spc/api/routers/excel.py`: `cargar_sales` recibe `horizon: int = Form(...)` (obligatorio) y
  `granularity: str = Form("day")`.
- `src/spc/api/ingest/lector.py`: `leer_peticion(contenido, dominio, extra=...)` funde esos escalares
  en la raíz de la petición **antes** de validar con el **mismo modelo strict** (`VentasRequest`).
  Sus errores se mapean al **nombre del campo** (`horizon`), no a una hoja/fila, porque no provienen
  del archivo.
- **No cambia el contrato de datos.** `VentasRequest`/`VentasResponse` y `CONTRACT_VERSION` quedan
  igual: cambia la **firma del canal Excel** (cómo se aportan los escalares), no el contrato JSON.
- El endpoint de **entrenamiento por cliente** (`POST /training/sales/excel`) usa el mismo lector y
  solo necesita `history`; aporta un `horizon` de relleno (irrelevante: no pronostica un horizonte).

### 3. Ventas: **configuración previa** vs **filtros sobre el resultado**

- **Antes de pronosticar (Paso 2):** solo lo que el modelo necesita para calcular —«¿Cada cuánto?»
  (granularidad) y «¿Hasta cuándo?» (horizonte, contado en períodos de la granularidad). «Rango
  estimado (80%)» sigue **«Próximamente»** (`interval_80` no lo produce el modelo).
- **Después de pronosticar (Resultado):** «Ver total / por dimensión», «Agrupar / filtrar por»
  (tienda, producto) y **«Valores concretos»** pasan a ser **filtros sobre el resultado**, con el
  mismo principio que Compras/Almacén: **cambian la vista, no el cálculo**; el usuario pronostica una
  vez y explora el mismo resultado de varias formas **sin recalcular**.
- Los valores de los filtros **salen de las filas reales de la respuesta** (`forecast[]`), nunca se
  inventan. Como la respuesta es granular (`date × store_id × product_id`), «valores concretos»
  **funciona para cualquier canal, también Excel** (deja de estar «Próximamente»; antes lo estaba
  porque filtraba el histórico previo, conocido solo con JSON).
- **Categoría / familia** como eje distinto de producto sigue **«Próximamente»**: la respuesta no
  trae un eje de categoría separado de `product_id` (mismo criterio que Compras/Almacén).
- La lógica de agregación/filtrado vive en funciones puras y testeables
  (`frontend/src/utils/ventasResult.ts`).

### 4. Archivos grandes: estado de procesamiento **honesto**

Cuando un envío grande se procesa en segundo plano (202 + sondeo de `/jobs/{id}/result`, ya
existente), la UI muestra **«Estamos procesando tu pronóstico, esto puede tomar un momento…»** y el
resultado aparece solo al terminar. **No** se exponen los términos internos «en línea» ni «por lote»
ni el identificador del trabajo. El sondeo y su tope no cambian (`usePrediction`).

### 5. Textos en español en la app (no en las plantillas)

- Leyenda del gráfico de Ventas: **«Histórico (unidades vendidas)»** y **«Pronóstico (demanda
  estimada)»**.
- Almacén: la **clase de demanda** se muestra **«demanda alta» / «demanda baja»** (no «high»/«low»).
- Compras: «Por qué» muestra una **frase clara** —«Demanda estimada durante el tiempo de entrega más
  la cobertura, y unas existencias de seguridad.»— en vez de la fórmula cruda. La traducción ocurre
  **en la app**; el backend sigue enviando `justification` en inglés (contrato).
- Se usa **«existencias»** en vez de «stock» en la interfaz. Los **encabezados de las plantillas**
  (`current_stock`, etc.) **no se tocan**: son el contrato en inglés.

## Consecuencias

- **Positivas.** Una sola fuente de configuración (la pantalla), sin ambigüedad en Excel; los
  controles de vista dejan de insinuar que recalculan; «valores concretos» queda disponible también
  por Excel; el estado de procesamiento es honesto y sin jerga; la app habla español de forma
  consistente. Sin cambios en el motor ni en el contrato de datos.
- **A favor de la honestidad.** Lo que el backend aún no entrega (intervalo 80%, eje de
  categoría/familia) permanece **visible y «Próximamente»**, registrado en
  `docs/alineacion_frontend_backend.md`.
- **Compatibilidad.** Una plantilla antigua con hoja `parameters` se sigue subiendo sin error: el
  lector solo lee la hoja `history`; la hoja sobrante se ignora y la configuración la gobierna la
  pantalla.

## Pruebas

- Backend: `tests/api/test_excel.py` (plantilla de Ventas solo-datos; config por formulario manda;
  equivalencia JSON↔Excel; errores citando `history`/`horizon`), `tests/api/test_batch.py`,
  `tests/api/test_persistencia.py` y `tests/api/test_entrenamiento_cliente.py` actualizados al canal
  solo-datos.
- Frontend: `src/utils/ventasResult.test.ts` (vistas/filtros del resultado, funciones puras) y
  `src/test/textosEspanol.test.tsx` (leyenda sin nombres del contrato, clase de demanda y
  «existencias» en Almacén, «Por qué» de Compras sin fórmula, banner sin «lote/asíncrono/job»).
