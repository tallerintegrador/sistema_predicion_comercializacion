# ADR-0026 — Retiro del motor congelado (#1), migración del frontend a `/v2` y etiquetas de clustering honestas

- **Estado:** Aceptado
- **Fecha:** 2026-07-01
- **Rama:** `feature/mejoras-modelos-camila`
- **Relacionado:** [ADR-0024](0024-rediseno-3x3-sklearn-sintetico.md) (rediseño 3×3),
  [ADR-0025](0025-mejoras-modelos-variedad-objetivos-clustering.md) (mejoras de calidad),
  [ADR-0023](0023-prediccion-agnostica-auto-entrenada.md) (motor agnóstico que se conserva).
  **Retira** lo decidido en [ADR-0011](0011-persistencia-corpus-incremental.md) (corpus) y
  [ADR-0013](0013-entrenamiento-por-cliente-bajo-demanda.md) (ajuste por cliente), atados al motor congelado.

## Contexto

El repositorio arrastraba **tres** motores de predicción conviviendo, lo que confundía y
dejaba código muerto:

| # | Motor | Endpoints | Frontend lo usaba | Entrenamiento |
|---|---|---|---|---|
| 1 | **Congelado** (Favorita, XGBoost/LightGBM) | `/sales /purchases /inventory` | **No** (muerto) | Artefactos offline |
| 2 | **Agnóstico** (ADR-0023) | `/auto/*` | Sí (todas las páginas) | En el momento |
| 3 | **3×3** (ADR-0024/0025) | `/v2/*` | No (aún) | En el momento |

El motor congelado #1 ya no lo consumía nadie: las páginas de dominio del frontend
apuntaban al motor agnóstico `/auto`, y el rediseño 3×3 (`/v2`) —lo que pidió el docente—
nunca llegó al frontend. Además, cinco canales auxiliares (catálogo, Excel legacy, lote,
training-por-cliente y persistencia de corpus) **solo existían para servir al motor #1**.

## Decisión

1. **Eliminar el motor congelado #1** y todo lo que solo lo servía. Quedan dos motores,
   ambos **entrenados en el momento** (sin artefactos): agnóstico (`/auto`) y 3×3 (`/v2`),
   más el control de acceso por roles.
2. **Migrar las páginas de dominio del frontend** (Ventas/Compras/Almacén) al contrato
   `/v2` (esquema fijo, tres bloques + indicadores de inventario). «Predicción a tu medida»
   (LibrePage) se mantiene sobre `/auto` (esquema flexible).
3. **Etiquetas de clustering honestas por dominio** (mejora de ADR-0025 c): la etiqueta ya
   no miente el eje que separa a los grupos.

### Alcance del borrado (backend)

- **Routers:** `/sales`, `/purchases`, `/inventory` (frozen) y sus canales: `catalog`,
  `excel` (legacy), `jobs` (lote), `entrenamiento` (ADR-0013).
- **Servicios:** `ventas/compras/almacen_service`, `adaptador`, `modelo_cliente`, `corpus`,
  `repositorio` (predicciones), `artefactos`, `ruteo`; `api/{catalog,jobs,jobs_entrenamiento}`;
  `ingest/{lector,plantilla,esquema_excel}` (Excel del contrato frozen); `training/cliente`.
- **Schemas** del contrato frozen y sus tests. La app ya **no carga artefactos** en el
  arranque; el lifespan solo abre el control de acceso.

### Conservado (por uso en `/auto` o auth)

`seleccion_modelo`, `politica`, `service/seguridad` (cripto de auth), `training/almacen`
(`slug_cliente`), `repositorio_auth`, `cache_agnostico`. `ArchivoDemasiadoGrande` se movió a
`ingest/errores_excel` (la usa `/auto`); `ErrorExcel` (solo frozen) se eliminó. Los permisos
de módulo (`module:sales/purchases/inventory`) ya no derivan del catálogo borrado: se listan
de los tres dominios 3×3, con las mismas claves que consume el enforcement de `/v2`.

### Frontend

- Nuevo componente `components/v2/AnalisisV2`: corre la demo (`GET /v2/{dominio}/demo`) o
  sube datos en el formato fijo (`POST /v2/{dominio}`) y muestra los tres bloques
  —regresión, clasificación, clustering— más `indicadores_inventario` en almacén.
- `api/endpoints.ts`: `postV2` + `getV2Demo`; se retiran las funciones muertas del motor #1
  y de sus canales. `api/types.ts`: tipos del contrato `/v2`; se eliminan tipos muertos.
- `PrediccionGuiada` (usado por LibrePage/`/auto`) deja de depender de `GET /catalog`: las
  opciones de consulta (granularidad, horizonte) pasan a ser **estáticas** en el frontend,
  de modo que el backend queda solo-predicción.
- Se retiran `CatalogPage`, `useDomainCatalog`, `DataSourcePanel`, `JobBanner`,
  `usePrediction` y la sección de catálogo del menú; `AboutPage` se reescribe sin la
  narrativa del modelo congelado.

### Etiquetas de clustering honestas (ADR-0025 c, afinado)

`zoo_liviano._etiquetas_narrativas` rotula según el dominio (`estilo_etiqueta` en
`ConfigDominio`):
- **Ventas:** `volumen bajo/medio/alto`.
- **Almacén:** `clase A/B/C` (A = mayor demanda) — el marco ABC clásico.
- **Compras:** `servicio rápido/medio/lento`, ordenado por **lead time** (lo que de verdad
  separa a los proveedores), no por costo, que antes ocultaba el eje real.

Además se corrigió el docstring de `/v2/almacen` (predecía `dias_de_cobertura` → `demanda_dia`).

## Consecuencias

- **Se retiran features documentadas:** persistencia incremental del corpus (ADR-0011) y
  ajuste por cliente bajo demanda (ADR-0013). Ambas solo ajustaban/alimentaban el modelo
  congelado; sin él no aplican. Quedan como historia en sus ADRs; reintroducirlas sobre los
  motores en-el-momento sería trabajo futuro con otro diseño.
- **Las páginas de dominio pierden el mapeo flexible de columnas** (queda solo en
  «Predicción a tu medida» vía `/auto`): a cambio muestran los **nueve modelos** del
  rediseño 3×3 que pidió el docente.
- **Suite backend:** 288 → **164 tests en verde** (se retiran las suites del motor frozen;
  `test_auth`, `test_cors`, `test_errores_api` se repuntan a `/v2`). **Frontend:** build y
  55 tests (vitest) en verde.
- El selector de umbral compartido (`clasificacion.seleccionar_umbral`, precision-first) se
  **conserva sin cambios**: `/auto` (demanda alta, señal fuerte) no sufre el colapso de
  recall que sí tenían los datos realistas de compras en el camino 3×3 (ya arreglado en
  `zoo_liviano._umbral_operativo`, ADR-0025 c).

## Fuera de alcance

- Reintroducir corpus/ajuste-por-cliente sobre los motores en-el-momento.
- Punto (d) de ADR-0025 (encadenar compras con la demanda pronosticada de ventas).
