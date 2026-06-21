# Frontend SPC

Interfaz web (React + Vite + TypeScript + Tailwind + recharts) para la plataforma
SPC. Consume la API del backend con el modelo congelado (Camino B / Fase 4.5).
No toca el motor de ML ni la capa interna: habla solo el **contrato v1.0.1**.

**Identidad visual (ADR-0017):** sistema de diseño por tokens en `src/index.css`
(`@theme`): marca índigo (`brand-*`), acento teal (`accent-*`), neutros fríos (slate) y
semánticos; tipografía de sistema con escala modular; foco accesible y monograma "SPC".
Los componentes consumen los tokens vía las clases de `@layer components`.

## Acceso y roles (ADR-0014/0015/0016)

La app está detrás de **autenticación**. El flujo es: **Login** (id + contraseña) →
**Onboarding** del negocio en el primer ingreso de un usuario no administrador → panel
principal con **sidebar filtrado por permisos**.

- **Cuentas de demostración (no de producción):** `256317` y `256370`, con **contraseña
  igual al id**. Se siembran hasheadas en el SQLite del backend. Cámbielas en un despliegue
  real (ver README raíz).
- El **sidebar** muestra solo las secciones que el rol permite (Catálogo, Ventas, Compras,
  Almacén, Reentrenamiento, Administración de usuarios). La autorización real la aplica el
  **backend** en cada endpoint; la UI solo filtra la vista.
- Con el control de acceso activo, el backend **deriva el `client_id` del usuario
  autenticado**: el header `X-Client-Id` se sigue enviando como respaldo pero se ignora si
  hay sesión.

## Qué muestra

- **Catálogo** — `GET /catalog`: versión del contrato, canales/modos (disponible vs.
  planificado, incl. `client_adjustment` diferido) y, por dominio, entradas/salidas.
- **Ventas** (`/sales`) — tarjeta *Configuración del pronóstico* con **tipo de pronóstico**
  (R1: serie temporal / por dimensión) y **dimensión / filtrar por** (R2), más granularidad
  (Día/Semana/Mes) y horizonte. Todas las opciones vienen de `GET /catalog`
  (`query_options`), sin hardcodeo (ADR-0018). Resultado con gráfico histórico + forecast y
  tabla (totales por período o desglose por dimensión, según la tipología).
- **Compras** (`/purchases`) — reposición sugerida con barras y tabla.
- **Inventario** (`/inventory`) — riesgo de quiebre, probabilidad y stock recomendado.
- **Reentrenamiento** (`/training/*`) — opt-in/local/experimental (solo SALES).
- **Administración de usuarios** — roles, permisos y cuentas (solo administradores).

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
