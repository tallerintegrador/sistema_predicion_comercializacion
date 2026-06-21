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
| 12 | **Filtrar por valores concretos** de una dimensión (Ventas) | 🟡 Parcial | solo con JSON/manual (valores del histórico en el cliente) | **`AGREGAR EN BACKEND:`** ver §3 |
| 13 | **Rango estimado (80%)** (`interval_80`) | 🟥 Falta (visible, «Próximamente») | el modelo no lo produce; la respuesta lo omite | **`AGREGAR EN BACKEND:`** ver §4 |
| 14 | **Filtros por dimensión en Compras/Almacén** | 🟥 Falta | no hay `query_options` para esos dominios | **`AGREGAR EN BACKEND:`** ver §3 |
| 15 | **Verificación automática de «datos suficientes»** antes de entrenar | 🟥 Falta (visible, «Próximamente») | hoy solo veredicto `insufficient_data` *durante* el entrenamiento | **`AGREGAR EN BACKEND:`** ver §6 |
| 16 | **Reentrenamiento para Compras/Almacén** | 🟥 Falta (no expuesto) | solo Ventas tiene ajuste por cliente | **`AGREGAR EN BACKEND:`** ver §5 |
| 17 | **Reentrenamiento del modelo base** desde la UI | 🟥 Falta (no expuesto) | proceso offline (scripts), sin endpoint | **`AGREGAR EN BACKEND:`** ver §5 |

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

**`AGREGAR EN BACKEND:` valores disponibles por dimensión.**
La UI puede filtrar por valores concretos (p. ej. ciertas tiendas) cuando el histórico está en
el cliente (JSON/manual). En el flujo **Excel** el histórico se procesa en el servidor y el
cliente no conoce los valores. Opciones:
- (a) un endpoint `GET /{dominio}/dimensions/{name}/values` que, dado un conjunto de datos cargado/sesión, liste los valores distintos; o
- (b) que la respuesta de predicción incluya los valores presentes.
Recomendación: (b) es más barato (no añade estado) y suficiente para poblar el filtro tras el primer pronóstico. Marcar la versión Excel del filtro como «Próximamente» hasta entonces (ya hecho en la UI).

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
