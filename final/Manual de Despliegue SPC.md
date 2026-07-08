# Manual de Despliegue — Sistema Predictivo de Comercialización (SPC)

**Índice**

1. Introducción
2. Requisitos previos
   - 2.1. Creación de la cuenta de Render
   - 2.2. Creación del proyecto en Supabase (base de datos + almacenamiento)
   - 2.3. Obtención de la cadena de conexión (Session pooler)
   - 2.4. Creación de la cuenta de GitHub / repositorio
   - 2.5. Habilitación de GitHub Pages
3. Arquitectura general del despliegue
4. Variables de entorno
5. Despliegue del backend
   - 5.1. Estructura y layout del proyecto
   - 5.2. El Dockerfile del backend
   - 5.3. Construcción y prueba local del contenedor
   - 5.4. El Blueprint de Render (`render.yaml`)
   - 5.5. Despliegue en Render
   - 5.6. Endpoint de salud
6. Despliegue del frontend
   - 6.1. Instalación de dependencias
   - 6.2. Configuración del endpoint del backend (`VITE_API_BASE_URL`)
   - 6.3. Compilación del proyecto Vite
   - 6.4. GitHub Actions + GitHub Pages
   - 6.5. Fallback SPA (404.html)
7. Configuración de CORS
8. Verificación del despliegue
9. Mantenimiento y actualización
10. Posibles errores y soluciones
11. Seguridad del despliegue
12. Evidencias del despliegue
13. Conclusión

---

# 1. Introducción

El presente manual describe el procedimiento para desplegar el **Sistema Predictivo de
Comercialización (SPC)**, compuesto por un **backend** desarrollado en **Python + FastAPI**
bajo una arquitectura por capas (API → servicio → motor ML), y un **frontend** desarrollado
en **React + Vite + TypeScript** como Single-Page Application (SPA).

El backend se **containeriza con Docker** y se despliega en **Render** a partir de un
*Blueprint* (`render.yaml`) que construye la imagen desde el `Dockerfile` del repositorio. La
persistencia (corpus de datos y registro de modelos) vive en **PostgreSQL sobre Supabase**, y
los artefactos de los modelos entrenados (`.joblib`) se almacenan en **Supabase Storage**. El
frontend se compila con Vite y se publica en **GitHub Pages** mediante un flujo automático de
**GitHub Actions**.

A diferencia de un despliegue clásico Java/Angular, aquí **no se usa Docker Hub ni Firebase**:
Render construye la imagen directamente desde el repositorio (autodeploy) y el hosting del SPA
es GitHub Pages.

**URLs de producción actuales:**

| Componente | URL |
| --- | --- |
| **Frontend (GitHub Pages)** | `https://tallerintegrador.github.io/sistema_predicion_comercializacion/` |
| **Backend (Render)** | `https://sistema-comercializacion-v2-latest.onrender.com` |
| **Salud del backend** | `https://sistema-comercializacion-v2-latest.onrender.com/health` |
| **Documentación (Swagger)** | `https://sistema-comercializacion-v2-latest.onrender.com/docs` |

# 2. Requisitos previos

| Componente | Herramienta / Servicio | Versión o detalle |
| --- | --- | --- |
| Backend | Python | 3.11 (imagen `python:3.11-slim`) |
| Backend | FastAPI | 0.137.1 |
| Backend | Uvicorn | 0.49.0 (servidor ASGI, 1 worker) |
| Backend | Docker | Para construir la imagen del servicio |
| Backend | Render | Plataforma de despliegue del backend |
| Base de datos | PostgreSQL (Supabase) | Driver `psycopg` v3 (`postgresql+psycopg://`) |
| Almacenamiento | Supabase Storage | Bucket `spc-modelos` para artefactos `.joblib` |
| ORM / migraciones | SQLAlchemy 2.x + Alembic | Esquema y migraciones |
| Frontend | Node.js | 22 (usado por el workflow de GitHub Actions) |
| Frontend | Vite + React + TypeScript | SPA de producción |
| Frontend | GitHub Pages | Hosting estático del SPA |
| CI/CD frontend | GitHub Actions | `.github/workflows/deploy-frontend.yml` |
| Sistema operativo (dev) | Windows | win32 x64 |

**Además, se requiere contar con:**

- Cuenta activa en **Render**.
- Cuenta y proyecto activos en **Supabase** (Postgres + Storage).
- Cuenta en **GitHub** con acceso al repositorio y **GitHub Pages** habilitado.
- **Docker** instalado (para pruebas locales del contenedor).
- Acceso al código fuente: `https://github.com/tallerintegrador/sistema_predicion_comercializacion`
- Variables de entorno configuradas para producción.

A continuación se detallan los pasos para completar los requisitos adicionales.

## 2.1. Creación de la cuenta de Render

1. Ingresar a `https://render.com` y seleccionar **Get Started**.
2. Registrarse con correo electrónico o directamente con la cuenta de **GitHub** (recomendado,
   porque simplifica conectar el repositorio).
3. Confirmar la cuenta desde el correo de verificación (**Verify your email**).
4. Iniciar sesión. Con la cuenta creada se puede proseguir a crear el servicio.

**Figura 1.** Landing page y registro en Render.

## 2.2. Creación del proyecto en Supabase (base de datos + almacenamiento)

1. Ingresar a `https://supabase.com` y seleccionar **Start your project** / **Sign up**
   (se puede usar la cuenta de GitHub).
2. Crear una **organización** y luego un **New project**. Se solicita:
   - **Name** del proyecto (p. ej. `spc`).
   - **Database Password** (guardarla: es la contraseña de la base de datos).
   - **Region**: elegir la más cercana al backend (Render). En este proyecto se usa
     `us-east-2`.
3. Esperar a que Supabase aprovisione la base Postgres.
4. Crear el bucket de almacenamiento: **Storage → New bucket**, nombre **`spc-modelos`**.
   Aquí se guardan los artefactos `.joblib` de los modelos entrenados por cliente.

**Figura 2.** Dashboard del proyecto en Supabase con la base y el bucket `spc-modelos`.

> **Nota sobre el modo degradado:** el backend funciona **sin** Supabase. Si no se
> configuran las variables, cae automáticamente a **SQLite local** (`data/spc.db`) y guarda
> los artefactos en disco (`models/clientes/`). Con Supabase, todo se persiste en la nube
> (ADR-0027). Es decir, Supabase no es un requisito para *arrancar*, sino para *persistir en
> producción*.

## 2.3. Obtención de la cadena de conexión (Session pooler)

El backend se conecta a Postgres mediante **SQLAlchemy** con el driver **psycopg 3**. Por eso
la cadena debe tener el prefijo `postgresql+psycopg://` (no el `postgresql://` que copia
Supabase por defecto).

1. En Supabase: **Connect** (botón superior) → pestaña **Connection string**.
2. Elegir **Session pooler** (recomendado para servicios de un solo proceso como este; el
   *pooler* de transacción no soporta ciertas features de SQLAlchemy).
3. Copiar la cadena, que tiene esta forma:

   ```
   postgresql://postgres.<ref>:<PASSWORD>@aws-1-<region>.pooler.supabase.com:5432/postgres
   ```

4. **Reemplazar el prefijo** `postgresql://` por `postgresql+psycopg://`. El valor final que
   se coloca en la variable `SPC_DATABASE_URL` queda así:

   ```
   postgresql+psycopg://postgres.<ref>:<PASSWORD>@aws-1-<region>.pooler.supabase.com:5432/postgres
   ```

5. Para **Storage** se necesitan además:
   - **`SUPABASE_URL`**: `https://<ref>.supabase.co` (Project Settings → API).
   - **`SUPABASE_KEY`**: la **service role key** (Project Settings → API → *service_role*),
     porque el backend **sube y borra** artefactos. **No usar la `anon` key.**
   - **`SUPABASE_BUCKET`**: `spc-modelos`.

> **Nota:** Los valores reales (contraseña de la base, service role key) **no deben** figurar
> en el código ni en el repositorio. Se configuran únicamente en el panel de variables de
> entorno de Render (ver §4).

## 2.4. Creación de la cuenta de GitHub / repositorio

1. El código fuente vive en GitHub:
   `https://github.com/tallerintegrador/sistema_predicion_comercializacion`.
2. Render se conecta a este repositorio para construir el backend, y GitHub Actions publica el
   frontend. Basta con tener permisos de lectura/escritura sobre el repo.

## 2.5. Habilitación de GitHub Pages

1. En el repositorio: **Settings → Pages**.
2. En **Build and deployment → Source**, seleccionar **GitHub Actions** (no "Deploy from a
   branch"). El workflow `deploy-frontend.yml` se encarga de compilar y publicar.
3. Registrar el secreto de la API: **Settings → Secrets and variables → Actions → New
   repository secret**, con nombre **`VITE_API_BASE_URL`** y valor la URL del backend en
   Render (ver §6.2).

**Figura 3.** Configuración de GitHub Pages con fuente "GitHub Actions".

# 3. Arquitectura general del despliegue

El sistema se despliega separando frontend y backend en plataformas especializadas.

| Módulo | Tecnología | Plataforma de despliegue |
| --- | --- | --- |
| Frontend | React + Vite + TypeScript (SPA) | GitHub Pages |
| Backend | Python + FastAPI (Uvicorn) | Render |
| Contenedor backend | Docker (`Dockerfile` + `render.yaml`) | Render (build desde repo) |
| Base de datos | PostgreSQL | Supabase |
| Almacenamiento de artefactos | Supabase Storage (bucket `spc-modelos`) | Supabase |
| Seguridad | Control de acceso por roles con token de sesión (ADR-0014) | Backend |

La comunicación general del sistema es:

```
Usuario → GitHub Pages → SPA (React/Vite) → API REST (fetch) → Render → FastAPI → Supabase (Postgres + Storage)
```

El frontend se publica como **SPA**. Consume los servicios REST del backend desplegado en
Render mediante `fetch`, resolviendo la base de la API por la variable de build
`VITE_API_BASE_URL`.

El backend se ejecuta como aplicación **FastAPI dentro de un contenedor Docker**. Render
construye la imagen a partir del `Dockerfile` del repositorio (definido en `render.yaml`) y
la ejecuta inyectando el puerto por `$PORT`. El servicio **entrena en el momento y predice**;
el corpus y el registro de modelos se persisten en Supabase.

> **Diferencia clave frente al despliegue Java/Angular:** aquí **no hay Docker Hub** (Render
> construye la imagen desde el repo directamente) ni **Firebase** (el SPA vive en GitHub
> Pages, publicado por GitHub Actions).

# 4. Variables de entorno

El backend requiere variables para conectarse a servicios externos, gestionar autenticación y
proteger información sensible. **Se configuran en el panel de Render** (Environment).

| Variable | Descripción | ¿Obligatoria en prod? |
| --- | --- | --- |
| `SPC_DATABASE_URL` | Cadena SQLAlchemy a Postgres (prefijo `postgresql+psycopg://`, Session pooler). Sin ella → SQLite local | Sí (para persistir) |
| `SUPABASE_URL` | `https://<ref>.supabase.co` | Sí (para Storage) |
| `SUPABASE_KEY` | **service role key** de Supabase (sube/borra artefactos) | Sí (para Storage) |
| `SUPABASE_BUCKET` | Nombre del bucket, `spc-modelos` | Sí (para Storage) |
| `SPC_AUTH_SECRET` | Secreto para firmar los tokens de sesión. En prod **debe** fijarse (si se deja vacío, se usa un secreto de desarrollo y los tokens son falsificables) | Sí |
| `SPC_AUTH_ENABLED` | Control de acceso por roles: `1` activo, `0` abierto | Recomendado `1` |
| `SPC_CORS_ORIGINS` | Orígenes CORS permitidos (coma-separados). **Fijar al origen del frontend**, no `*` | Sí |

**Knobs de política de negocio (opcionales, con defaults que reproducen la salida histórica):**
`SPC_ONLINE_MAX_ROWS`, `SPC_EXCEL_MAX_BYTES`, `SPC_BATCH_WORKERS` (dejar en `1`),
`SPC_PURCHASES_SAFETY_FACTOR`, `SPC_INVENTORY_SAFETY_METHOD`, etc. (ver
`docs/fase-3/checklist_despliegue.md`). No hace falta tocarlas para desplegar.

Para el **frontend** (variables de *build*, inyectadas por GitHub Actions):

| Variable | Descripción |
| --- | --- |
| `VITE_API_BASE_URL` | Base de la API en Render (secreto del repo). Ej. `https://sistema-comercializacion-v2-latest.onrender.com` |
| `VITE_BASE` | Path raíz del *project site*: `/sistema_predicion_comercializacion/` |
| `VITE_CLIENT_ID` | (Opcional) identificador de cliente para el header `X-Client-Id`. Default `frontend-demo` |

> **Seguridad:** Ningún valor real (contraseñas, service role key, `SPC_AUTH_SECRET`) debe
> colocarse en el código ni en el repositorio. En Render se configuran en **Environment**; en
> GitHub, como **Actions Secrets**.

**Figura 4.** Variables de entorno configuradas en Render.

# 5. Despliegue del backend

El backend fue desarrollado con **FastAPI**, aplicando una arquitectura por capas para
separar la capa API (contrato de datos), la capa de servicio (persistencia, auth) y el motor
de ML. El despliegue se realiza mediante **Docker + Render**.

## 5.1. Estructura y layout del proyecto

El proyecto usa el layout `src/`:

```
sistema_prediccion_comercializacion/
├── Dockerfile                 # imagen del servicio (build en Render)
├── render.yaml                # Blueprint de Render
├── requirements-api.txt       # deps de runtime del servicio
├── src/spc/                   # código (import spc gracias a PYTHONPATH=/app/src)
│   └── api/main.py            # app factory de FastAPI (CORS, routers, /health)
├── models/                    # artefactos del motor horneados en la imagen
└── frontend/                  # SPA React + Vite
```

## 5.2. El Dockerfile del backend

El backend cuenta con un `Dockerfile` de **una sola etapa** (a diferencia del *multi-stage*
de Maven, aquí no hay compilación previa: Python se ejecuta directo). El archivo es:

```dockerfile
# syntax=docker/dockerfile:1
FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app/src

# libgomp1: runtime de OpenMP que requieren LightGBM y XGBoost.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependencias primero: capa cacheable.
COPY requirements-api.txt ./
RUN pip install -r requirements-api.txt

# Código + artefactos del motor (models/ se hornea en la imagen).
COPY src/ ./src/
COPY models/ ./models/

# Usuario sin privilegios (buena práctica de seguridad).
RUN useradd --create-home --uid 1000 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Shell form para expandir $PORT (Render inyecta el puerto). 1 worker.
CMD ["sh", "-c", "uvicorn spc.api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
```

Puntos clave:

- **`libgomp1`**: sin esta librería el `import` de LightGBM/XGBoost falla con
  `libgomp.so.1: cannot open shared object file`.
- **`PYTHONPATH=/app/src`**: permite `import spc` sin instalar el paquete.
- **`$PORT`**: Render inyecta el puerto real; el `CMD` usa *shell form* para expandirlo, con
  fallback `8000` en local.
- **1 worker**: el almacén de trabajos por lote es *in-process* (ADR-0008); con más workers un
  `job_id` de un proceso no sería visible para otro. Además, 1 worker entra holgado en el free
  tier de 512 MB.

**Figura 5.** Archivo `Dockerfile` del backend.

## 5.3. Construcción y prueba local del contenedor

Antes de desplegar conviene construir y probar la imagen localmente:

```bash
docker build -t spc-api .
docker run --rm -p 8000:8000 spc-api
```

Comprobar el arranque accediendo al endpoint de salud:

```
http://localhost:8000/health   ->   {"status":"ok"}
```

Para probar contra Supabase en local, se inyectan las variables de entorno:

```bash
docker run --rm -p 8000:8000 \
  -e SPC_DATABASE_URL="postgresql+psycopg://postgres.<ref>:<PASSWORD>@aws-1-<region>.pooler.supabase.com:5432/postgres" \
  -e SUPABASE_URL="https://<ref>.supabase.co" \
  -e SUPABASE_KEY="<service_role_key>" \
  -e SUPABASE_BUCKET="spc-modelos" \
  -e SPC_AUTH_SECRET="<secreto_largo_aleatorio>" \
  -e SPC_CORS_ORIGINS="http://localhost:5173" \
  spc-api
```

> Sin variables, el contenedor arranca igual usando SQLite local: útil para una prueba de humo
> rápida sin tocar la nube.

## 5.4. El Blueprint de Render (`render.yaml`)

En lugar de publicar una imagen en Docker Hub, este proyecto usa un **Blueprint** que le dice
a Render cómo construir y ejecutar el servicio directamente desde el repositorio:

```yaml
services:
  - type: web
    name: spc-api
    runtime: docker
    dockerfilePath: ./Dockerfile
    plan: free
    healthCheckPath: /health
    autoDeploy: true
    envVars:
      - key: SPC_CORS_ORIGINS
        value: "*"     # cambiar al origen real del frontend en producción
```

- **`runtime: docker` + `dockerfilePath`**: Render construye la imagen desde el `Dockerfile`
  del repo. No se necesita Docker Hub.
- **`healthCheckPath: /health`**: Render marca el servicio como sano solo si `/health`
  responde 200.
- **`autoDeploy: true`**: cada push a la rama conectada dispara un *redeploy* automático.
- El resto de variables (`SPC_DATABASE_URL`, `SUPABASE_*`, `SPC_AUTH_SECRET`) se cargan desde
  el panel de Render, **no** desde el YAML (para no versionar secretos).

## 5.5. Despliegue en Render

Proceso aplicado:

1. Ingresar a Render → **New → Blueprint**.
2. Conectar el repositorio `sistema_predicion_comercializacion`. Render detecta `render.yaml`.
3. Confirmar la creación del servicio web (tipo **Web Service**, runtime Docker, plan Free).
4. En **Environment**, configurar las variables sensibles:
   - `SPC_DATABASE_URL`
   - `SUPABASE_URL`, `SUPABASE_KEY`, `SUPABASE_BUCKET`
   - `SPC_AUTH_SECRET`, `SPC_AUTH_ENABLED=1`
   - `SPC_CORS_ORIGINS` = origen del frontend (ver §7)
5. Ejecutar el despliegue. Render construye la imagen y arranca Uvicorn.
6. Verificar que el servicio quede **Live** y que `/health` responda.

El backend desplegado está disponible en:

```
https://sistema-comercializacion-v2-latest.onrender.com
```

> **Free tier — arranque en frío:** en el plan Free, Render **suspende** el servicio tras
> inactividad. La primera petición tras el reposo puede tardar **~40–50 s** en responder
> mientras el contenedor se reinicia (verificado: `/health` respondió en ~42 s tras reposo,
> y <1 s ya "caliente"). Es esperable; no es un error.

**Figura 6.** Servicio backend activo (Live) en Render.

## 5.6. Endpoint de salud

El backend expone un endpoint de *liveness* implementado en `src/spc/api/main.py`:

```python
@app.get("/health", tags=["status"], summary="Salud del servicio")
def salud() -> dict[str, str]:
    """Comprueba que el servicio está arriba."""
    return {"status": "ok"}
```

Verificación del backend desplegado:

```
https://sistema-comercializacion-v2-latest.onrender.com/health   ->   {"status":"ok"}
https://sistema-comercializacion-v2-latest.onrender.com/docs      ->   Swagger UI
```

**Figura 7.** Endpoint `/health` respondiendo `{"status":"ok"}` y Swagger en `/docs`.

# 6. Despliegue del frontend

El frontend fue desarrollado con **React + Vite + TypeScript** y se despliega en **GitHub
Pages** mediante **GitHub Actions**. Es una SPA con enrutado del lado cliente
(`BrowserRouter`), por lo que necesita un *fallback* a `index.html`.

## 6.1. Instalación de dependencias

Desde `frontend/`:

```bash
npm ci      # instalación reproducible desde package-lock.json (usado por CI)
# o, en local:
npm install
```

Scripts disponibles (`package.json`):

| Script | Comando | Uso |
| --- | --- | --- |
| `dev` | `vite` | Servidor de desarrollo (`http://localhost:5173`) |
| `build` | `tsc -b && vite build` | Compilación de producción |
| `preview` | `vite preview` | Previsualizar el build |
| `lint` | `eslint .` | Análisis estático |
| `test` | `vitest run` | Pruebas |

## 6.2. Configuración del endpoint del backend (`VITE_API_BASE_URL`)

El cliente HTTP resuelve la base de la API en `frontend/src/api/client.ts`:

```ts
const BASE_URL: string = (
  import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8010'
).replace(/\/$/, '')
```

- En **desarrollo**, sin definir la variable, apunta al backend local `http://localhost:8010`.
- En **producción**, GitHub Actions inyecta `VITE_API_BASE_URL` (secreto del repo) con la URL
  de Render, y Vite la hornea en el bundle en tiempo de build.

Verificado: el bundle publicado en GitHub Pages contiene la base
`https://sistema-comercializacion-v2-latest.onrender.com`.

## 6.3. Compilación del proyecto Vite

El parámetro **`base`** de Vite controla el path raíz del bundle. En local es `/`; al publicar
en GitHub Pages (*project site*) hay que servir bajo `/<repo>/`, por eso el workflow inyecta
`VITE_BASE=/sistema_predicion_comercializacion/` (`vite.config.ts`):

```ts
export default defineConfig({
  base: process.env.VITE_BASE ?? '/',
  plugins: [react(), tailwindcss()],
  server: { port: 5173 },
})
```

La compilación genera la carpeta **`dist/`** con los archivos estáticos que publica GitHub
Pages.

## 6.4. GitHub Actions + GitHub Pages

El despliegue del frontend es **automático**: cada push a `main` que toque `frontend/**`
dispara el workflow `.github/workflows/deploy-frontend.yml`, que compila el SPA y lo publica en
Pages. Extracto:

```yaml
name: Deploy frontend (GitHub Pages)
on:
  push:
    branches: [main]
    paths: ['frontend/**', '.github/workflows/deploy-frontend.yml']
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write

jobs:
  build:
    runs-on: ubuntu-latest
    defaults: { run: { working-directory: frontend } }
    env:
      VITE_BASE: /sistema_predicion_comercializacion/
      VITE_API_BASE_URL: ${{ secrets.VITE_API_BASE_URL }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: 22, cache: npm, cache-dependency-path: frontend/package-lock.json }
      - run: npm ci
      - run: npm run build
      - run: cp dist/index.html dist/404.html      # fallback SPA
      - uses: actions/upload-pages-artifact@v3
        with: { path: frontend/dist }
  deploy:
    needs: build
    runs-on: ubuntu-latest
    environment: { name: github-pages, url: '${{ steps.deployment.outputs.page_url }}' }
    steps:
      - id: deployment
        uses: actions/deploy-pages@v4
```

Al finalizar, la aplicación queda publicada en:

```
https://tallerintegrador.github.io/sistema_predicion_comercializacion/
```

**Figura 8.** Ejecución exitosa del workflow en la pestaña **Actions**.

## 6.5. Fallback SPA (404.html)

GitHub Pages es hosting **estático**: al recargar una ruta profunda (p. ej. `/sales`) buscaría
un archivo que no existe y devolvería 404. La solución es copiar `index.html` como `404.html`
durante el build (`cp dist/index.html dist/404.html`): Pages sirve `404.html` en rutas no
encontradas, y `BrowserRouter` resuelve el enrutado del lado cliente. Es el equivalente al
*rewrite* de Firebase hacia `/index.html`.

**Rutas internas del SPA** (`frontend/src/theme/modules.ts`):

| Ruta | Descripción |
| --- | --- |
| `/` | Inicio / panel |
| `/sales` | Ventas (predicción de demanda) |
| `/purchases` | Compras (recomendación de reposición) |
| `/inventory` | Almacén (stock / clasificación) |
| `/users` | Gestión de usuarios y roles |
| `/about` | Acerca del sistema |

Gracias al fallback, recargar cualquiera de estas rutas no produce error 404.

# 7. Configuración de CORS

Frontend y backend viven en dominios distintos, por lo que el backend debe permitir el origen
del frontend vía **CORS**. La configuración se hace por variable de entorno, no en código:

- Frontend (GitHub Pages): `https://tallerintegrador.github.io`
- Backend (Render): `https://sistema-comercializacion-v2-latest.onrender.com`

En `src/spc/api/main.py`, el middleware lee la variable `SPC_CORS_ORIGINS`:

```python
def _origenes_cors() -> list[str]:
    """Orígenes CORS permitidos (coma-separados en SPC_CORS_ORIGINS; * por defecto)."""
    valor = os.getenv("SPC_CORS_ORIGINS", "").strip()
    if not valor:
        return ["*"]
    return [o.strip() for o in valor.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins if cors_origins is not None else _origenes_cors(),
    allow_credentials=False,
    ...
)
```

**En producción**, `SPC_CORS_ORIGINS` debe fijarse al origen del frontend (no `*`):

```
SPC_CORS_ORIGINS = https://tallerintegrador.github.io
```

Para desarrollo local se permite `http://localhost:5173` (el puerto de Vite). Se pueden listar
varios orígenes separados por coma:

```
SPC_CORS_ORIGINS = http://localhost:5173,https://tallerintegrador.github.io
```

> **Nota:** el sistema usa **token de sesión en el header `Authorization: Bearer`** (no cookies
> HttpOnly), por eso `allow_credentials=False`. El token se guarda en memoria + `localStorage`
> y se envía por header en cada petición (`frontend/src/api/client.ts`).

**Figura 9.** Variable `SPC_CORS_ORIGINS` configurada en Render.

# 8. Verificación del despliegue

Tras desplegar, ejecutar las siguientes verificaciones:

| N.º | Verificación | Resultado esperado |
| --- | --- | --- |
| 1 | Acceder a la URL del frontend en GitHub Pages | La aplicación carga correctamente |
| 2 | Recargar una ruta interna (p. ej. `/sales`) | No muestra error 404 (fallback SPA) |
| 3 | `GET /health` del backend | Responde `{"status":"ok"}` (puede tardar ~40 s en frío) |
| 4 | Abrir `/docs` (Swagger) | Renderiza y documenta los endpoints |
| 5 | Iniciar sesión desde el frontend (`POST /auth/login`) | El usuario accede al sistema |
| 6 | Consumir un dominio (p. ej. `POST /v2/ventas` o `/v2/ventas/demo`) | El frontend recibe predicciones desde Render |
| 7 | Revisar la consola del navegador | Sin errores de CORS |
| 8 | Revisar los logs en Render | Sin errores críticos; arranque de Uvicorn correcto |
| 9 | Verificar persistencia en Supabase | El corpus y los modelos se registran en Postgres/Storage |
| 10 | Probar los módulos principales | Ventas, Compras y Almacén funcionan |

Endpoints reales expuestos (de `/openapi.json`): `/health`, `/docs`, `/auth/login`, `/auth/me`,
`/users`, `/roles`, `/permissions`, `/profile`, y por dominio
`/v2/{ventas|compras|almacen}` con sus variantes `/demo`, `/entrenar`, `/esquema`, `/excel`,
`/plantilla`, `/predecir`, `/modelos` y `/modelos/{id}/servir`.

**Figura 10.** `/health` respondiendo OK y **Figura 11.** inicio de sesión exitoso desde el SPA.

# 9. Mantenimiento y actualización

**Actualización del backend:**

El despliegue es **automático** (`autoDeploy: true` en `render.yaml`). Basta con hacer push a
la rama conectada:

```bash
git add .
git commit -m "feat: cambios del backend"
git push
```

Render detecta el push, reconstruye la imagen desde el `Dockerfile` y hace el redeploy. Si se
requiere un redeploy manual (p. ej. tras cambiar variables de entorno), usar en Render
**Manual Deploy → Deploy latest commit** (o **Clear build cache & deploy** si se sospecha de
la caché).

Si cambian las **dependencias** (`requirements-api.txt`) o los **artefactos** (`models/`), el
redeploy los toma automáticamente al reconstruir la imagen.

**Actualización del frontend:**

También automática. Cualquier push a `main` que toque `frontend/**` dispara el workflow y
republica en GitHub Pages. Para forzarlo manualmente: pestaña **Actions → Deploy frontend →
Run workflow** (`workflow_dispatch`).

Si se cambia la URL del backend, actualizar el secreto **`VITE_API_BASE_URL`** del repositorio
y re-ejecutar el workflow (el valor se hornea en tiempo de build).

**Migraciones de base de datos (Alembic):**

Ante cambios de esquema, aplicar las migraciones contra Supabase antes/después del deploy:

```bash
alembic upgrade head
```

# 10. Posibles errores y soluciones

| Error | Posible causa | Solución |
| --- | --- | --- |
| Error de CORS en la consola | El backend no permite el origen del frontend | Fijar `SPC_CORS_ORIGINS` al dominio de GitHub Pages en Render |
| Error 404 al recargar rutas internas | Falta el fallback SPA | Verificar que el build copia `index.html` → `404.html` |
| El frontend consume `localhost` | `VITE_API_BASE_URL` no configurada en el build | Definir el secreto en GitHub Actions y re-ejecutar el workflow |
| Primera petición muy lenta (~40 s) | Arranque en frío del free tier de Render | Comportamiento esperado; considerar un plan de pago o un *ping* periódico |
| `libgomp.so.1: cannot open shared object file` | Falta `libgomp1` en la imagen | Ya incluido en el `Dockerfile`; verificar que no se removió |
| Backend no arranca en Render | Variables de entorno incompletas/incorrectas | Revisar `SPC_DATABASE_URL`, `SUPABASE_*`, `SPC_AUTH_SECRET` en el panel |
| Error de conexión a la base | Prefijo de la cadena o pooler incorrecto | Usar `postgresql+psycopg://` y la cadena del **Session pooler** |
| Modelos no se guardan en la nube | `SUPABASE_KEY` es la `anon` en vez de `service_role` | Usar la **service role key** (sube/borra artefactos) |
| Tokens de sesión inválidos/falsificables | `SPC_AUTH_SECRET` sin fijar (usa secreto de dev) | Fijar un secreto largo y aleatorio en Render |
| `job_id` no encontrado en lote | Más de 1 worker de Uvicorn | Mantener **1 worker** (almacén de lote in-process, ADR-0008) |
| Workflow de Pages falla en `deploy-pages` | GitHub Pages no configurado como "GitHub Actions" | Settings → Pages → Source = GitHub Actions |

# 11. Seguridad del despliegue

El sistema aplica medidas básicas de seguridad en el despliegue y la ejecución:

- **Autenticación por token de sesión** (control de acceso por roles, ADR-0014). El backend
  deriva el `client_id` del usuario autenticado; el header `X-Client-Id` es solo respaldo.
- **`SPC_AUTH_SECRET`** firma los tokens: en producción **debe** ser un valor largo y
  aleatorio, nunca el de desarrollo.
- **CORS restringido** al origen del frontend (no `*` en producción).
- **Contenedor sin privilegios**: el `Dockerfile` crea y usa el usuario `appuser` (uid 1000).
- **Secretos fuera del repositorio**: contraseña de la base, service role key y
  `SPC_AUTH_SECRET` viven en Render (Environment) y en GitHub (Actions Secrets), no en el
  código.
- **HTTPS de extremo a extremo**: GitHub Pages y Render sirven bajo TLS.
- **Service role key de Supabase** solo en el backend (jamás en el frontend, que es público).
- Revisar los **logs de Render** después de cada despliegue.
- Mantener actualizadas las dependencias (pines exactos en `requirements-api.txt` para no
  romper el *unpickle* de los artefactos joblib).

**Consideraciones principales:**

- No publicar contraseñas ni secretos en el repositorio.
- No exponer `SUPABASE_KEY`, `SPC_DATABASE_URL` ni `SPC_AUTH_SECRET`.
- Configurar CORS solo para dominios permitidos.
- Usar variables de entorno para todo dato sensible.

**Figura 12.** Configuración de seguridad (usuario no-root en el `Dockerfile`, variables en
Render).

# 12. Evidencias del despliegue

Se recomienda adjuntar como evidencia:

- **12.1.** Archivo `Dockerfile` del backend.
- **12.2.** Archivo `render.yaml` (Blueprint) en el repositorio.
- **12.3.** Servicio backend en estado **Live** en Render.
- **12.4.** Variables de entorno configuradas en Render.
- **12.5.** Logs del backend (arranque de Uvicorn correcto).
- **12.6.** Endpoint de salud: `/health → {"status":"ok"}`.
- **12.7.** Swagger UI en `/docs`.
- **12.8.** Ejecución exitosa del workflow en la pestaña **Actions**.
- **12.9.** Configuración de GitHub Pages (Source = GitHub Actions).
- **12.10.** Aplicación publicada en `https://tallerintegrador.github.io/sistema_predicion_comercializacion/`.
- **12.11.** Inicio de sesión exitoso desde el frontend.
- **12.12.** Proyecto Supabase con la base Postgres y el bucket `spc-modelos`.

# 13. Conclusión

El despliegue del SPC separa frontend y backend en plataformas especializadas. El backend
**FastAPI** se containeriza con **Docker** y se ejecuta en **Render**, construido directamente
desde el repositorio mediante un *Blueprint* (`render.yaml`) —sin Docker Hub—. La persistencia
vive en **PostgreSQL y Storage sobre Supabase**. El frontend **React + Vite** se publica en
**GitHub Pages** de forma automática con **GitHub Actions** —sin Firebase—.

Esta estrategia mantiene una arquitectura de despliegue ordenada: el frontend consume una API
REST pública y el backend concentra la lógica de negocio, la seguridad (token de sesión y
roles), la conexión con la base de datos y el almacenamiento de artefactos. El uso de variables
de entorno, control de acceso por roles, CORS restringido, contenedor sin privilegios y HTTPS
de extremo a extremo refuerza la seguridad del sistema en producción.
