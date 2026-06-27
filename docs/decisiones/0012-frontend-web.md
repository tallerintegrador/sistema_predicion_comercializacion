# ADR 0012 — Frontend web (interfaz de demostración, acoplada solo al contrato)

- **Estado:** Aceptado (2026-06-20).
- **Fase:** 4.5 (anticipada) — interfaz web para usar y demostrar la plataforma. **Corre
  en local; el despliegue (Fase 4.0–4.4) sigue pendiente.**
- **Contexto previo:** [ADR-0007](0007-capa-api-fase3.md) (capa API), [ADR-0008](0008-modos-ejecucion.md)
  (modos en línea/lote), [ADR-0011](0011-persistencia-corpus-incremental.md) (corpus),
  `docs/contrato_datos.md` v1.0.1 (frontera pública).
- **No toca** el motor de ML, la capa interna en español ni el contrato. Es un **cliente
  más** de la API, sujeto a las mismas reglas que cualquier integrador externo.

## Contexto

La plataforma se usaba por JSON/Swagger o Excel. Para la demo y un piloto hacía falta una
**interfaz** que ejercite los tres dominios, ambos canales (JSON/Excel) y ambos modos
(en línea/lote), y que muestre el **catálogo honesto**. El riesgo a evitar: que el
frontend se convierta en un segundo lugar donde "vive" la lógica o el vocabulario del
producto, rompiendo el contrato como única frontera.

## Decisión

Un **frontend desacoplado** (carpeta `frontend/`, build independiente) que **habla solo el
contrato v1.0.1** y no comparte código con el backend.

### 1. Stack

**React + Vite + TypeScript + Tailwind + recharts.** TypeScript permite **tipar el
contrato** (`frontend/src/api/types.ts` es el espejo de los esquemas Pydantic, en inglés);
Vite da arranque/HMR simple; recharts cubre los gráficos. Sin framework de servidor: es una
SPA estática que se puede servir desde cualquier host.

### 2. Acoplamiento solo por contrato (nombres en inglés)

Los tipos del frontend **reflejan el contrato** y **no se traducen**: los datos viajan con
los nombres canónicos (`store_id`, `units_sold`, `forecast_demand`…). La UI muestra
etiquetas en español, pero el **payload es el del contrato**. Lo **diferido se etiqueta**
en la interfaz (`interval_80` → "diferido"; `client_adjustment` → "planned" en el catálogo;
footer "modelo congelado · ajuste por cliente diferido"): la UI **no sobrevende** el
pronóstico como garantía.

### 3. Manejo de los dos modos (en línea y lote)

Una predicción puede volver **200** (resultado en línea) o **202** (`JobAccepted`, lote).
El cliente HTTP distingue por código; en lote, un hook hace **polling** de
`GET /jobs/{id}/result` hasta `done`/`error`. El polling tiene **tope** (máximo de intentos
≈ varios minutos): si se excede, la UI muestra un estado **"sigue en proceso"** en vez de
sondear indefinidamente. El error estructurado del contrato (`{error:{type,message,details}}`)
se traduce a una excepción tipada y se muestra con su `field/problem`.

### 4. Configuración (sin tocar código)

- **URL del backend configurable:** `VITE_API_BASE_URL` (default `http://localhost:8010`).
- **`VITE_CLIENT_ID`** → header `X-Client-Id` (alimenta el corpus; ver ADR-0011). Header de
  transporte, **no** parte del cuerpo del contrato.
- `.env.example` se versiona; **`.env` no** (config local del entorno).

### 5. CORS

El navegador exige que la API permita el **origen** del frontend. En dev se levanta la API
con `SPC_CORS_ORIGINS=http://localhost:5173`. En producción (Fase 4) debe fijarse al
**origen real** del frontend desplegado (hoy el default `*` es solo para dev).

## Consecuencias

- **A favor:** desacoplado y desplegable por separado; el contrato sigue siendo la única
  frontera; tipado end-to-end reduce el *drift*; honesto (no inventa capacidades).
- **Deuda asumida y explícita:** (a) **no desplegado** — Fase 4.0–4.4 pendientes; (b) el
  `X-Client-Id` que envía no está autenticado (ver ADR-0011); (c) `interval_80` y el ajuste
  por cliente se muestran como diferidos porque **no existen** en el backend.

## Referencias

- [ADR-0008 — Modos de ejecución](0008-modos-ejecucion.md)
- [ADR-0011 — Persistencia incremental del corpus](0011-persistencia-corpus-incremental.md)
- [contrato_datos.md](../contrato_datos.md) · [frontend/README.md](../../frontend/README.md)
