# Frontend SPC

Interfaz web (React + Vite + TypeScript + Tailwind + recharts) para la plataforma
SPC. Consume la API del backend con el modelo congelado (Camino B / Fase 4.5).
No toca el motor de ML ni la capa interna: habla solo el **contrato v1.0.1**.

## Qué muestra

- **Catálogo** — `GET /catalog`: versión del contrato, canales/modos (disponible vs.
  planificado, incl. `client_adjustment` diferido) y, por dominio, entradas/salidas.
- **Ventas** (`/sales`) — pronóstico con gráfico histórico + forecast y tabla.
- **Compras** (`/purchases`) — reposición sugerida con barras y tabla.
- **Inventario** (`/inventory`) — riesgo de quiebre, probabilidad y stock recomendado.

Cada dominio: **Cargar ejemplo** (datos de `examples/api/`) o **Excel** (descargar
plantilla / subir `.xlsx`) → **Predecir** → resultado. Si el envío supera el umbral
de filas, la API responde en **modo lote (202)** y la UI hace *polling* del job.

## Requisitos previos

- Node ≥ 20 (probado con Node 24), npm.
- La **API SPC** corriendo y aceptando este origen por CORS.

## Levantar la API (desde la raíz del repo)

```powershell
$env:SPC_CORS_ORIGINS = "http://localhost:5173"
venv\Scripts\python -m uvicorn spc.api.main:app --port 8010 --workers 1
```

`GET http://localhost:8010/health` debe responder `{"status":"ok"}`.

## Levantar el frontend

```powershell
cd frontend
npm install
copy .env.example .env   # ajustar VITE_API_BASE_URL si la API no está en :8010
npm run dev              # http://localhost:5173
```

## Configuración

| Variable             | Default                 | Uso                                                |
| -------------------- | ----------------------- | -------------------------------------------------- |
| `VITE_API_BASE_URL`  | `http://localhost:8010` | Base de la API SPC                                 |
| `VITE_CLIENT_ID`     | `frontend-demo`         | Header `X-Client-Id` (corpus incremental, Fase A)  |

## Scripts

- `npm run dev` — servidor de desarrollo.
- `npm run build` — typecheck (`tsc -b`) + build de producción a `dist/`.
- `npm run preview` — sirve el build de producción.
