# Alineación Frontend ↔ Backend (SPC)

> **Para:** Valentín (motor/artefactos y capa de servicio).
> **De:** rediseño del frontend orientado al cliente (ADR-0019 lenguaje, ADR-0020 identidad/pantallas).
> **Estado:** GROUND-TRUTH respecto al código real a la fecha de este documento. Cada brecha marcada con **`AGREGAR EN BACKEND:`** es una petición concreta y accionable.

Este documento concilia lo que la **interfaz muestra** con lo que el **backend soporta hoy**.
La UI nunca fabrica datos: cuando una capacidad no existe, el control se muestra **deshabilitado**
con la etiqueta **«Próximamente»** y queda registrado aquí.

Principio inviolable respetado por todo el frontend: **no se toca el motor de ML**
(`src/spc/models/`, features de ML). Las extensiones propuestas viven en la **capa
servicio/API** (`src/spc/api/`, `src/spc/service/`), derivadas del contrato, con pruebas
anti-desync.

---

## 1. Tabla de funcionalidades de la UI vs. estado real

| # | Funcionalidad en la UI | Estado | Soporte backend hoy | Brecha / acción |
|---|------------------------|--------|---------------------|-----------------|
| 1 | Catálogo amigable («¿Qué hace el sistema?») | ✅ Implementada | `GET /catalog` | — |
| 2 | Pronóstico de Ventas (total por período / por dimensión) | ✅ Implementada | `POST /sales` + `query_options` (R1/R2) | — |
| 3 | Granularidad (Día/Semana/Mes) y horizonte | ✅ Implementada | derivados del contrato en `query_options` | — |
| 4 | Carga por **Excel** (Ventas/Compras/Almacén) | ✅ Implementada | `POST /{dominio}/excel` + `GET /{dominio}/template` | — |
| 5 | Carga por **JSON** (subir archivo en la UI) | ✅ Implementada | `POST /{dominio}` (mismo cuerpo del contrato) | Se parsea en el cliente; reusa el endpoint JSON. |
| 6 | **Carga manual** por tabla editable (Compras/Almacén) | ✅ Implementada | columnas derivadas de `catalog.input_tables` | — |
| 7 | Compras: reposición (cuánto/cuándo) | ✅ Implementada | `POST /purchases` | — |
| 8 | Almacén: riesgo de quiebre + stock sugerido (semáforo) | ✅ Implementada | `POST /inventory` | — |
| 9 | Resúmenes en lenguaje natural | ✅ Implementada | calculado en el cliente sobre datos reales | — |
| 10 | Reentrenamiento por cliente (Ventas) | ✅ Implementada | `POST /training/sales/excel`, `GET /training/jobs/{id}`, `GET /training/sales/status`, `POST /training/sales/serving` | — |
| 11 | Administración de usuarios/roles con etiquetas legibles | ✅ Implementada | `GET /permissions`, `GET/POST /roles`, `GET/POST/PATCH /users` | etiquetas vienen de `permisos.py` |
| 12 | **Filtrar por valores concretos** de una dimensión (Ventas) | ✅ Implementada | **filtro sobre el resultado**: los valores salen de `forecast[]` (cualquier canal, también Excel) | resuelto en ADR-0022 (ver §3 y §10) |
| 13 | **Rango estimado (80%)** (`interval_80`) | 🟥 Falta (visible, «Próximamente») | el modelo no lo produce; la respuesta lo omite | **`AGREGAR EN BACKEND:`** ver §4 |
| 14 | **Filtros de resultado en Compras/Almacén** (tienda, producto, segmento, «solo reposición/riesgo», orden) | 🟡 Parcial | derivados de los **campos reales** de la respuesta (ADR-0021) | resto «Próximamente»: ver §9 |
| 15 | **Verificación automática de «datos suficientes»** antes de entrenar | 🟥 Falta (visible, «Próximamente») | hoy solo veredicto `insufficient_data` *durante* el entrenamiento | **`AGREGAR EN BACKEND:`** ver §6 |
| 16 | **Reentrenamiento para Compras/Almacén** | 🟥 Falta (Almacén visible, «Próximamente») | solo Ventas tiene ajuste por cliente | **`AGREGAR EN BACKEND:`** ver §5 y §9 |
| 17 | **Reentrenamiento del modelo base** desde la UI | 🟥 Falta (no expuesto) | proceso offline (scripts), sin endpoint | **`AGREGAR EN BACKEND:`** ver §5 |
| 18 | **«Configuración detectada en tu archivo» (Excel)** mostrada/ajustable en pantalla | ✅ Sin objeto | el Excel de Ventas es **solo datos**: la config viaja en la petición en pantalla (ADR-0022) | resuelto por diseño (ver §4b, §9.5 y §10) |
| 19 | **Defaults editables** de tiempo de entrega y días de cobertura en la carga manual | ✅ Implementada | `CatalogColumn.default` ← política (`spc.config`, ADR-0010) | añade `SPC_PURCHASES_TARGET_COVERAGE_DAYS`; ver §9 |
| 20 | **Historial de ventas solo por archivo** (Compras/Almacén) y resumen sin filas vacías | ✅ Implementada | usa los endpoints existentes | regla unificada (ADR-0021) |
| 21 | **Reutilización del historial guardado** entre módulos | 🟥 Falta (visible, «Próximamente») | el corpus se persiste por cliente (ADR-0011) pero no se expone al frontend | **`AGREGAR EN BACKEND:`** ver §9 |

Leyenda: ✅ implementada · 🟡 parcial · 🟥 falta.

---

## 2. Extensión de `/catalog` ya realizada en este trabajo (servicio/API, no motor)

Para eliminar el hardcodeo de columnas/etiquetas en la carga manual, se añadió a cada dominio
del catálogo el bloque **`input_tables`**: por cada tabla de entrada (`history`,
`replenishment_params`, `inventory_status`), sus **columnas con etiqueta y ayuda en español**,
derivadas de los esquemas Pydantic del contrato.

- Esquema: `CatalogColumn { name, label, type, required, help }` e `InputTable { name, label, description, columns }` en `src/spc/api/schemas/catalog.py`.
- Derivación honesta: `src/spc/api/catalog.py` (`_tablas_entrada` / `_columnas`). El nombre, tipo y obligatoriedad salen del esquema; solo la traducción (`label`/`help`) es texto centralizado (`_FIELD_LABELS`/`_TABLE_LABELS`).
- Pruebas anti-desync: `tests/api/test_catalog.py` (`test_catalog_input_tables_*`) verifican que cada columna existe en el esquema, que no se omite ningún obligatorio y que toda columna trae etiqueta en español.
- **Sin cambio de contrato de datos** (es metadata de presentación; ver §7).

---

## 3. Extensiones de `/catalog` pendientes (dimensiones y valores)

**`AGREGAR EN BACKEND:` `query_options` para Compras y Almacén.**
Hoy solo Ventas expone `query_options` (tipologías/dimensiones). Si se quiere ofrecer
desglose/filtrado por dimensión en Compras/Almacén, exponer `query_options` también en esos
dominios (mismas dimensiones identificadoras del `history`). Mientras tanto, la UI no muestra
ese filtro en Compras/Almacén.

**✅ Resuelto (ADR-0022): valores por dimensión como filtro sobre el resultado.**
Se adoptó la opción (b): la respuesta de Ventas **ya es granular** (`forecast[]` por
`date × store_id × product_id`), así que el filtro «valores concretos» se construye **en el
cliente a partir de las filas del resultado**, no del histórico previo. Por eso funciona para
**cualquier canal, también Excel** (deja de ser «Próximamente»). Categoría/familia como eje
distinto de `product_id` sigue «Próximamente» (la respuesta no lo trae). Para Compras/Almacén la
misma idea aplica vía sus filtros de resultado (§9.2).

---

## 4. Campo «Rango estimado (80%)» (`interval_80`)

- **Hoy:** `PronosticoItem.interval_80` existe en el esquema como **opcional** y el servicio lo
  **omite** (`response_model_exclude_none=True`) porque el modelo **no produce** intervalos
  (diferido desde Fase 2). La UI muestra el control deshabilitado con «Próximamente».
- **`AGREGAR EN BACKEND:`** para mostrarlo se necesita que el motor entregue, por cada punto
  pronosticado, un intervalo `[inferior, superior]` al 80% (p. ej. por cuantiles del modelo o
  un método de incertidumbre). Cuando el artefacto lo produzca, el servicio solo debe poblar
  `interval_80`; la respuesta y el catálogo ya lo contemplan. La UI lo activará automáticamente.

---

## 4b. Configuración del Excel — **resuelto por diseño** (ADR-0022): el archivo es solo datos

La brecha original asumía que el Excel de Ventas **llevaba** su configuración (hoja `parameters`) y
había que **mostrarla/ajustarla**. La decisión de ADR-0022 la elimina de raíz:

- **Antes:** `POST /sales/excel` **leía y aplicaba** la configuración de la hoja `parameters` del
  archivo, ignorando la pantalla (doble fuente). 
- **Ahora:** la plantilla de Ventas es **solo datos** (`instructions` + `history`). La configuración
  (`granularity`, `horizon`) viaja **en la petición en pantalla** como campos de formulario de
  `POST /sales/excel` y es la **única fuente**. No hay configuración embebida que detectar ni
  devolver: ya no existe. (Una plantilla antigua con hoja `parameters` se sigue subiendo: esa hoja se
  ignora y manda la pantalla.)
- **Sin cambio de contrato de datos:** `VentasRequest`/`VentasResponse` y `CONTRACT_VERSION` quedan
  igual; cambia la **firma del canal Excel** (cómo se aportan los escalares).

---

## 5. Reentrenamiento

### 5.1. Modelo base (datos de ejemplo)

- **Hoy:** el modelo base (congelado) se entrena **offline** con scripts (`scripts/train_regresion.py`, etc.) y se versiona como artefacto en `models/` (`regresion_v*.joblib` + `*.meta.json`). No hay endpoint de re-entrenamiento del base; la API solo lo **sirve** (lee `model`/metadata del artefacto).
- **`AGREGAR EN BACKEND:`** si se desea actualizar el modelo base desde una operación controlada (no desde la UI de cliente), definir un proceso/versionado explícito (p. ej. publicar `regresion_vN` y un puntero de «modelo base vigente») y documentar la promoción. **No corresponde a la UI de cliente** (es tarea de operación/modelado).

### 5.2. Reentrenamiento por cliente (Ventas) — **ya soportado**

- **Endpoints (existen):** `POST /training/sales/excel?source=` (dispara, devuelve job),
  `GET /training/jobs/{id}` y `GET /training/jobs/{id}/result` (estado/fase + resultado),
  `GET /training/sales/status` (adopción/serving), `POST /training/sales/serving` (switch).
- **Experimento de validación temporal:** compara modelo del cliente vs. base vs. una referencia
  simple en validación temporal honesta (WAPE recursivo). Resultado en `TrainingResult`.
- **Regla de adopción:** solo se adopta el modelo del cliente **si supera al base**; «no mejora»
  se reporta y se sigue con el base. Persistencia por cliente (se sirve solo a ese cliente).
- **`AGREGAR EN BACKEND:`** extender el ajuste por cliente a **Compras/Almacén** (hoy solo Ventas).
  Compras no tiene modelo propio (deriva de Ventas), así que basta con Ventas; Almacén
  (clasificación/clustering) requeriría su propio experimento y regla de adopción.

### 5.3. Umbral mínimo de volumen de datos (recomendado)

La UI recomienda al usuario, en lenguaje claro, **«al menos ~1 año de ventas y varios registros por
producto»**. Es una guía, no una verificación.

- **`AGREGAR EN BACKEND:` umbral mínimo de volumen — valor propuesto (a confirmar por backend):**
  ≥ **365 días** de histórico y ≥ **~30 observaciones por serie** `(store_id, product_id)` con
  ≥ **2** series. *Estos números son una propuesta inicial; el backend debe confirmarlos según el
  comportamiento real del experimento (cuándo el ajuste por cliente deja de ser ruido).*

---

## 6. Verificación automática de «datos suficientes»

- **Hoy:** la suficiencia se evalúa **dentro** del entrenamiento (devuelve `outcome="insufficient_data"`
  con `missing[]`). No hay un **pre-chequeo** independiente antes de gastar el trabajo de entrenar.
- **`AGREGAR EN BACKEND:`** endpoint sugerido `POST /training/sales/check` (o `GET` con la misma
  carga) que reciba el Excel/dataset y devuelva, **sin entrenar**, si cumple el umbral (§5.3):
  `{ sufficient: bool, reasons: string[], stats: { days, series, rows_per_series } }`.
  La UI lo usaría para habilitar el botón «Entrenar con mis datos» y dar feedback inmediato.
  Hoy ese control está marcado «Próximamente».

---

## 7. Cambios de contrato y versión

- El bloque `input_tables` de `/catalog` (§2) es **metadata de presentación derivada** del
  contrato existente; **no** cambia los esquemas de petición/respuesta ni la versión del contrato
  de datos (`CONTRACT_VERSION = "1.0.1"`).
- Ninguna de las brechas pendientes (§3–§6) está implementada aún, así que **no** alteran el
  contrato a la fecha. Cuando se implementen:
  - `interval_80` (§4): no cambia el contrato (campo ya declarado opcional); sí cambia la salida real.
  - `query_options`/valores por dimensión (§3): metadata de presentación; no cambia el contrato de datos.
  - `POST /training/sales/check` (§6): endpoint nuevo; documentar en el contrato de la capa de entrenamiento.
  - Cualquier cambio que altere cuerpos de petición/respuesta del contrato de datos debe **subir la versión** (`CONTRACT_VERSION`) y actualizar `docs/contrato_datos.md` (la prueba `test_catalog_version_alineada_con_encabezado_del_doc` lo verifica).

---

## 8. Onboarding del negocio (login / primer ingreso)

- **Hoy:** `GET /profile/options` entrega los conjuntos de `sector/size/region/currency` como
  **códigos en inglés** (`micro`, `small`, `medium`, `retail`, `south_america`, `PEN`…). `PUT /profile`
  **valida** contra esos códigos (`SECTORES/TAMANOS/REGIONES/MONEDAS` en `src/spc/api/schemas/auth.py`).
- **En la UI:** se muestran con **etiquetas en español** mapeando cada código
  (`frontend/src/data/onboardingLabels.ts`); el valor enviado/almacenado **no cambia** (sigue siendo
  el código), así las pruebas del backend siguen verdes. El mapeo vive en el frontend por ahora.
- **`AGREGAR EN BACKEND:` etiquetas en el catálogo de opciones.** Que `GET /profile/options` devuelva
  pares `{ value, label }` con `label` en español, para que la UI no duplique el mapeo y la traducción
  sea una sola fuente. (Cambia la **forma** del endpoint de onboarding, no el contrato de datos v1.0.1.)
- **`AGREGAR EN BACKEND:` ampliar los conjuntos de opciones** (la UI pidió un alcance mayor del que el
  backend acepta hoy; mientras tanto solo se ofrecen los códigos válidos):
  - `size`: falta el código **`large`** («Gran empresa»).
  - `sector`: faltan rubros frecuentes si se quieren ofrecer (p. ej. moda/ropa y calzado,
    tecnología/electrónica, belleza/cuidado personal).
  - `region`: hoy son **continentes**. Para ubicación local (p. ej. **departamentos del Perú**) o una
    opción libre **«Otra»**, agregar esos códigos (o soportar texto libre validado). La UI **no** envía
    valores fuera del catálogo para no romper la validación.
- **`AGREGAR EN BACKEND:` persistencia del perfil por cliente** — ya existe: `PUT /profile` liga el
  perfil al `client_id` y marca `onboarding_done`. Sin acción pendiente; se documenta para trazabilidad.

---

## 9. Ajustes de experiencia (ADR-0021): entrada de datos, filtros de resultado y reentrenamiento

Esta sección consolida lo hecho en el rediseño de experiencia (ADR-0021) y las brechas que
quedaron marcadas «Próximamente», para que el backend las recoja. Nada de esto toca el motor de ML.

### 9.1. Ya implementado (sin cambios pendientes de backend)

- **`CatalogColumn.default` editable desde la política.** `/catalog` declara, por columna, un
  `default` editable para prellenar la carga manual. **Sale de la configuración de política**
  (no es un literal de presentación): `lead_time_days` ← `inventory_lead_time_default()`
  (`SPC_INVENTORY_LEAD_TIME_DEFAULT`, 7) y `target_coverage_days` ← `purchases_target_coverage_days()`.
  - **Nota (variable nueva):** no existía una variable de política para los días de cobertura; se
    añadió **`SPC_PURCHASES_TARGET_COVERAGE_DAYS`** (default **14**) en `src/spc/config/__init__.py`.
    Es solo el valor sugerido editable de la UI; **no cambia** el cálculo de reposición (que usa el
    valor que finalmente envíe el cliente). Prueba anti-desync en `tests/api/test_catalog.py`.
  - **Sin cambio de contrato de datos:** `default` es metadata de presentación derivada (como
    `input_tables`); no altera `CONTRACT_VERSION`.
- **Historial de ventas solo por archivo** (Compras/Almacén) y **resumen sin filas vacías**: usan los
  endpoints existentes; no requieren backend.
- **Filtros de resultado derivados de campos reales** (ver §9.2): se implementan en el cliente sobre
  la respuesta; no requieren backend.

### 9.2. Filtros de resultado — implementados hoy vs. «Próximamente»

Implementados **en el cliente** porque el campo **viene en la respuesta** (los valores salen de las
filas reales, no se inventan):

- **Compras** (`recommendation[]`): por `store_id`, por `product_id`, «solo los que requieren
  reposición ahora» (`replenishment_quantity > 0`) y orden por cantidad a reponer.
- **Almacén** (`alerts[]`): por `store_id`, por `product_id`, por `store_segment`, «solo en riesgo de
  agotarse» (`stockout_risk`) y orden por riesgo (`stockout_risk` + `high_demand_probability`).

Marcados **«Próximamente»** (el campo/medida no existe hoy en la respuesta):

- **`AGREGAR EN BACKEND:` categoría/familia** (Compras y Almacén). No hay un eje de categoría/familia
  distinto de `product_id`. Exponerlo en `recommendation[]`/`alerts[]` (o vía `query_options` de esos
  dominios) para poder filtrar por categoría sin inventarla en el cliente.
- **`AGREGAR EN BACKEND:` medida de urgencia** (Compras), para «ordenar por urgencia». Hoy solo se
  ordena por cantidad a reponer. Una medida honesta sería p. ej. días hasta el quiebre o la brecha
  frente al punto de reorden; exponerla en `recommendation[]`.
- **`AGREGAR EN BACKEND:` nivel de riesgo en buckets alto/medio/bajo** (Almacén). Hoy solo hay
  `stockout_risk` (booleano) y `high_demand_probability` (0–1). Agrupar en niveles requiere **definir
  umbrales de política** (no inventarlos en el cliente): exponerlos en `alerts[]` o como constante de
  política configurable (mismo patrón que ADR-0010). Relacionado: dar un **nombre legible** al
  `store_segment` (hoy es solo un entero; la UI muestra «Segmento N»).

### 9.3. Reentrenamiento (alcance)

- El insumo de entrenamiento es **una sola plantilla**: el historial de ventas. El inventario **no**
  es dato de entrenamiento. **Compras** no se entrena por separado (mejora cuando mejora Ventas).
- **`AGREGAR EN BACKEND:` reentrenamiento de Almacén** (selector «Almacén» visible, «Próximamente»).
  Almacén (clasificación/clustering) necesitaría su propio experimento y regla de adopción (ver §5.2).
- **`AGREGAR EN BACKEND:` verificación automática de «datos suficientes»** antes de entrenar (ver §6):
  el control sigue marcado «Próximamente».

### 9.4. Reutilización del historial entre módulos

- **`AGREGAR EN BACKEND:` exponer el historial guardado del cliente al frontend.** El corpus ya se
  persiste por cliente (ADR-0011), pero el frontend no puede leerlo. Cuando se exponga (p. ej.
  `GET /history` por `client_id`, o reutilizarlo en `POST /{purchases,inventory}` sin reenviarlo),
  Compras/Almacén podrán pedir **solo el estado actual del inventario**. Hoy la opción se muestra
  deshabilitada con «Próximamente».

### 9.5. Fuente de la configuración del pronóstico (Ventas) — **✅ resuelto (ADR-0022)**

- La configuración del pronóstico (cada cuánto, hasta cuándo) es **la solicitud en pantalla**, única
  fuente de verdad, **también por Excel**.
- **Implementado:** `POST /sales/excel` ya **acepta** `granularity`/`horizon` como campos de
  formulario (la pantalla) y la plantilla dejó de llevar esa configuración. Ver §4b y §10.

---

## 10. Refinamiento de Ventas (ADR-0022): plantilla solo-datos, filtros sobre el resultado y procesamiento honesto

Consolida lo implementado en [ADR-0022](decisiones/0022-ventas-plantilla-datos-filtros-resultado-async.md).
Nada de esto toca el motor de ML; vive en la capa **servicio/API** (canal Excel) y en el frontend.

### 10.1. Implementado (sin brechas de backend pendientes)

- **Plantilla de Ventas solo-datos.** `instructions` + `history`; se eliminó la hoja `parameters`
  (`src/spc/api/ingest/esquema_excel.py`). Compras/Almacén sin cambios.
- **Configuración por la petición en pantalla.** `POST /sales/excel` recibe `granularity`/`horizon`
  como campos de formulario (`src/spc/api/routers/excel.py`); el lector los funde antes de validar con
  el mismo modelo strict (`leer_peticion(..., extra=)`). **Sin cambio de contrato de datos** ni de
  `CONTRACT_VERSION`.
- **Filtros sobre el resultado de Ventas.** «Ver total / por dimensión», «Agrupar / filtrar por» y
  «valores concretos» pasan a explorar el resultado **sin recalcular**; sus valores salen de
  `forecast[]` (cualquier canal). Lógica pura en `frontend/src/utils/ventasResult.ts`.
- **Procesamiento honesto de archivos grandes.** La UI muestra «Estamos procesando tu pronóstico…»
  sin exponer «en línea»/«por lote»/«job». El sondeo de `/jobs/{id}/result` y su tope **ya existían**
  (no requieren backend nuevo).
- **Textos en español en la app** (no en plantillas): leyenda del gráfico (unidades vendidas / demanda
  estimada), clase de demanda (alta/baja), «Por qué» de Compras como frase clara y «existencias» en
  vez de «stock». El backend sigue enviando `justification` y los encabezados de plantilla **en inglés**
  (contrato).

### 10.2. Sigue «Próximamente» (registrado arriba)

- **`interval_80`** (rango estimado al 80%): el modelo no lo produce (§4).
- **Categoría / familia** como eje distinto de `product_id` en Ventas/Compras/Almacén (§3, §9.2).
