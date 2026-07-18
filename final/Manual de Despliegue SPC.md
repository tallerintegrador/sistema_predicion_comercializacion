# Manual de Despliegue — Sistema Predictivo de Comercialización (SPC)

**Índice**

1. Introducción
2. Requisitos previos
   - 2.1. Creación de la cuenta de Docker Hub
   - 2.2. Creación de la cuenta de Render
   - 2.3. Creación del proyecto en Supabase (base de datos + almacenamiento)
   - 2.4. Obtención de la cadena de conexión (Session pooler)
   - 2.5. Creación de la cuenta de GitHub / repositorio
   - 2.6. Habilitación de GitHub Pages
3. Arquitectura general del despliegue
4. Variables de entorno
5. Despliegue del backend
   - 5.1. Estructura y layout del proyecto
   - 5.2. El Dockerfile del backend
   - 5.3. Construcción y prueba local del contenedor
   - 5.4. Publicación de la imagen en Docker Hub
   - 5.5. Despliegue en Render
   - 5.6. Endpoint de salud
6. Despliegue del frontend
   - 6.1. Instalación de dependencias
   - 6.2. Configuración del endpoint del backend (`VITE_API_BASE_URL`)
   - 6.3. Compilación del proyecto Vite
   - 6.4. GitHub Actions + GitHub Pages
   - 6.5. Fallback SPA (404.html)
7. Configuración de CORS
8. Endpoints de la API
   - 8.1. Salud y documentación (OpenAPI/Swagger)
   - 8.2. Autenticación y restablecimiento de contraseña
   - 8.3. Roles, usuarios y permisos
   - 8.4. Perfil del negocio (onboarding)
   - 8.5. Catálogo v3 (motor actual de la interfaz)
   - 8.6. Motor 3×3 v2 (heredado, funcional)
   - 8.7. Convenciones (autenticación, `client_id`, errores)
9. Verificación del despliegue
10. Mantenimiento y actualización
11. Posibles errores y soluciones
12. Seguridad del despliegue
13. Evidencias del despliegue
14. Conclusión

---

# 1. Introducción

El presente manual describe el procedimiento para desplegar el **Sistema Predictivo de
Comercialización (SPC)**, compuesto por un **backend** desarrollado en **Python + FastAPI**
bajo una arquitectura por capas (API → servicio → motor ML), y un **frontend** desarrollado
en **React + Vite + TypeScript** como Single-Page Application (SPA).

El backend se **containeriza con Docker**; la imagen se **publica en Docker Hub**
(`valxux/sistema_comercializacion_v2:latest`) y se **despliega en Render** a partir de esa
imagen (opción *Existing Image*). La persistencia (corpus de datos y registro de modelos) vive
en **PostgreSQL sobre Supabase**, y los artefactos de los modelos entrenados (`.joblib`) se
almacenan en **Supabase Storage**. El frontend se compila con Vite y se publica en
**GitHub Pages** mediante un flujo automático de **GitHub Actions**.

El flujo del backend es, por tanto, el patrón clásico **Docker → Docker Hub → Render**: se
construye la imagen localmente, se sube al registro y Render la ejecuta. El hosting del SPA,
en cambio, **no usa Firebase**: es **GitHub Pages**, publicado por GitHub Actions.

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
| Backend | Docker Hub | Registro de la imagen del backend (`valxux/sistema_comercializacion_v2`) |
| Backend | Render | Plataforma de despliegue del backend (Existing Image) |
| Base de datos | PostgreSQL (Supabase) | Driver `psycopg` v3 (`postgresql+psycopg://`) |
| Almacenamiento | Supabase Storage | Bucket `spc-modelos` para artefactos `.joblib` |
| ORM / migraciones | SQLAlchemy 2.x + Alembic | Esquema y migraciones |
| Frontend | Node.js | 22 (usado por el workflow de GitHub Actions) |
| Frontend | Vite + React + TypeScript | SPA de producción |
| Frontend | GitHub Pages | Hosting estático del SPA |
| CI/CD frontend | GitHub Actions | `.github/workflows/deploy-frontend.yml` |
| Sistema operativo (dev) | Windows | win32 x64 |

**Además, se requiere contar con:**

- Cuenta activa en **Docker Hub** (para publicar la imagen del backend).
- Cuenta activa en **Render**.
- Cuenta y proyecto activos en **Supabase** (Postgres + Storage).
- Cuenta en **GitHub** con acceso al repositorio y **GitHub Pages** habilitado.
- **Docker** instalado (para pruebas locales del contenedor).
- Acceso al código fuente: `https://github.com/tallerintegrador/sistema_predicion_comercializacion`
- Variables de entorno configuradas para producción.

A continuación se detallan los pasos para completar los requisitos adicionales.

## 2.1. Creación de la cuenta de Docker Hub

**Docker Hub** es el registro donde se publica la imagen del backend para que Render la
descargue y ejecute.

1. Ingresar a `https://hub.docker.com` y seleccionar **Sign up**.
2. Registrarse con correo electrónico (o con una cuenta de Google/GitHub) y confirmar la
   cuenta desde el correo de verificación.
3. Iniciar sesión. Anotar el **nombre de usuario** (en este proyecto, `valxux`): forma parte
   del nombre de la imagen, con la forma `<usuario>/<repositorio>:<tag>` — aquí
   `valxux/sistema_comercializacion_v2:latest`.
4. El repositorio de imagen `sistema_comercializacion_v2` se crea automáticamente en el primer
   `docker push`; también puede crearse a mano desde **Repositories → Create repository**.

**Figura 1.** Creación e inicio de sesión en Docker Hub.

## 2.2. Creación de la cuenta de Render

1. Ingresar a `https://render.com` y seleccionar **Get Started**.
2. Registrarse con correo electrónico o directamente con la cuenta de **GitHub** (recomendado,
   porque simplifica conectar el repositorio).
3. Confirmar la cuenta desde el correo de verificación (**Verify your email**).
4. Iniciar sesión. Con la cuenta creada se puede proseguir a crear el servicio.

**Figura 2.** Landing page y registro en Render.

## 2.3. Creación del proyecto en Supabase (base de datos + almacenamiento)

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

**Figura 3.** Dashboard del proyecto en Supabase con la base y el bucket `spc-modelos`.

> **Nota sobre el modo degradado:** el backend funciona **sin** Supabase. Si no se
> configuran las variables, cae automáticamente a **SQLite local** (`data/spc.db`) y guarda
> los artefactos en disco (`models/clientes/`). Con Supabase, todo se persiste en la nube
> (ADR-0027). Es decir, Supabase no es un requisito para *arrancar*, sino para *persistir en
> producción*.

## 2.4. Obtención de la cadena de conexión (Session pooler)

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

## 2.5. Creación de la cuenta de GitHub / repositorio

1. El código fuente vive en GitHub:
   `https://github.com/tallerintegrador/sistema_predicion_comercializacion`.
2. Render se conecta a este repositorio para construir el backend, y GitHub Actions publica el
   frontend. Basta con tener permisos de lectura/escritura sobre el repo.

## 2.6. Habilitación de GitHub Pages

1. En el repositorio: **Settings → Pages**.
2. En **Build and deployment → Source**, seleccionar **GitHub Actions** (no "Deploy from a
   branch"). El workflow `deploy-frontend.yml` se encarga de compilar y publicar.
3. Registrar el secreto de la API: **Settings → Secrets and variables → Actions → New
   repository secret**, con nombre **`VITE_API_BASE_URL`** y valor la URL del backend en
   Render (ver §6.2).

**Figura 4.** Configuración de GitHub Pages con fuente "GitHub Actions".

# 3. Arquitectura general del despliegue

El sistema se despliega separando frontend y backend en plataformas especializadas.

| Módulo | Tecnología | Plataforma de despliegue |
| --- | --- | --- |
| Frontend | React + Vite + TypeScript (SPA) | GitHub Pages |
| Backend | Python + FastAPI (Uvicorn) | Render |
| Contenedor backend | Docker | Docker Hub (`valxux/sistema_comercializacion_v2:latest`) |
| Despliegue backend | Imagen de Docker Hub (Existing Image) | Render |
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

El backend se ejecuta como aplicación **FastAPI dentro de un contenedor Docker**. La imagen se
**construye localmente**, se **publica en Docker Hub** (`valxux/sistema_comercializacion_v2:latest`)
y **Render la ejecuta** como *Existing Image*, inyectando el puerto por `$PORT`. El flujo de
publicación es:

```
Dockerfile → docker build → docker push → Docker Hub → Render (Existing Image) → servicio Live
```

El servicio **entrena en el momento y predice**; el corpus y el registro de modelos se
persisten en Supabase.

> **Diferencia frente al despliegue Java/Angular:** el patrón del backend es el mismo
> (**contenedor → Docker Hub → Render**). La única diferencia es el hosting del SPA: aquí
> **no se usa Firebase**, sino **GitHub Pages** publicado por GitHub Actions.

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

**Correo saliente (restablecimiento de contraseña, `POST /auth/forgot`).** El envío del
enlace de restablecimiento por correo (ver §8.2) usa SMTP. Es **opcional**: si
`SPC_SMTP_HOST` queda vacío, el envío está deshabilitado y el enlace solo se registra en los
logs (la respuesta al usuario es genérica en ambos casos, para no filtrar si el correo
existe).

| Variable | Descripción | Default |
| --- | --- | --- |
| `SPC_SMTP_HOST` | Host del servidor SMTP. Vacío → envío deshabilitado | *(vacío)* |
| `SPC_SMTP_PORT` | Puerto SMTP (STARTTLS) | `587` |
| `SPC_SMTP_USER` | Usuario de autenticación SMTP | *(vacío)* |
| `SPC_SMTP_PASSWORD` | Contraseña SMTP (secreto) | *(vacío)* |
| `SPC_SMTP_FROM` | Remitente del correo | `no-reply@spc.local` |
| `SPC_APP_BASE_URL` | Base del frontend para construir el enlace del correo. **Fijar al origen de GitHub Pages** en producción | `http://localhost:5173` |

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

**Figura 5.** Variables de entorno configuradas en Render.

# 5. Despliegue del backend

El backend fue desarrollado con **FastAPI**, aplicando una arquitectura por capas para
separar la capa API (contrato de datos), la capa de servicio (persistencia, auth) y el motor
de ML. El despliegue se realiza mediante **Docker + Render**.

## 5.1. Estructura y layout del proyecto

El proyecto usa el layout `src/`:

```
sistema_prediccion_comercializacion/
├── Dockerfile                 # imagen del servicio (build local → Docker Hub)
├── render.yaml                # Blueprint alternativo (no usado en prod; ver §5.4)
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

**Figura 6.** Archivo `Dockerfile` del backend.

## 5.3. Construcción y prueba local del contenedor

Antes de publicar conviene construir y probar la imagen localmente. Se etiqueta directamente
con el nombre del repositorio de Docker Hub (`<usuario>/<repositorio>:<tag>`) para poder
subirla después sin re-etiquetar:

```bash
docker build -t valxux/sistema_comercializacion_v2:latest .
docker run --rm -p 8000:8000 valxux/sistema_comercializacion_v2:latest
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
  valxux/sistema_comercializacion_v2:latest
```

> Sin variables, el contenedor arranca igual usando SQLite local: útil para una prueba de humo
> rápida sin tocar la nube.

## 5.4. Publicación de la imagen en Docker Hub

Con la imagen construida y etiquetada (§5.3), se sube a Docker Hub. Primero se inicia sesión
en el registro desde la terminal:

```bash
docker login
```

Luego se publica la imagen etiquetada:

```bash
docker push valxux/sistema_comercializacion_v2:latest
```

Una vez publicada, queda disponible en Docker Hub con la referencia:

```
valxux/sistema_comercializacion_v2:latest
```

Cada vez que se cambie el backend hay que **reconstruir y volver a publicar** la imagen
(`docker build` + `docker push`) y luego hacer **redeploy manual** en Render (§10).

> **Nota — `render.yaml`:** el repositorio incluye un `render.yaml` (Blueprint) que permitiría
> el flujo alternativo de "build desde el repo". **No es el que se usa en producción**: el
> servicio real corre la imagen publicada en Docker Hub (Existing Image, §5.5).

**Figura 7.** Imagen del backend publicada en Docker Hub.

## 5.5. Despliegue en Render (Existing Image)

El backend se despliega en Render usando la **imagen publicada en Docker Hub**. Proceso
aplicado:

1. Ingresar a Render → **New → Web Service**.
2. Elegir como fuente **Existing Image** (imagen de un registro), no un repositorio.
3. Indicar la imagen de Docker Hub `valxux/sistema_comercializacion_v2:latest` y conectar.
4. Elegir el **plan Free** y la región de despliegue.
5. Fijar el **Health Check Path** en `/health`.
6. En **Environment**, configurar las variables sensibles:
   - `SPC_DATABASE_URL`
   - `SUPABASE_URL`, `SUPABASE_KEY`, `SUPABASE_BUCKET`
   - `SPC_AUTH_SECRET`, `SPC_AUTH_ENABLED=1`
   - `SPC_CORS_ORIGINS` = origen del frontend (ver §7)
7. Ejecutar **Deploy Web Service**. Render descarga la imagen y arranca Uvicorn.
8. Verificar que el servicio quede **Live** y que `/health` responda.

El backend desplegado está disponible en:

```
https://sistema-comercializacion-v2-latest.onrender.com
```

> **Despliegue no automático:** al usar una imagen externa, Render **no** se reconstruye solo
> al hacer `git push`. Tras publicar una nueva versión de la imagen hay que hacer **redeploy
> manual** desde Render (**Manual Deploy → Deploy latest reference**) para que tome la imagen
> más reciente (§10).

**Figura 8.** Selección de la fuente *Existing Image* con la imagen de Docker Hub en Render.

> **Free tier — arranque en frío:** en el plan Free, Render **suspende** el servicio tras
> inactividad. La primera petición tras el reposo puede tardar **~40–50 s** en responder
> mientras el contenedor se reinicia (verificado: `/health` respondió en ~42 s tras reposo,
> y <1 s ya "caliente"). Es esperable; no es un error.

**Figura 9.** Servicio backend activo (Live) en Render.

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

**Figura 10.** Endpoint `/health` respondiendo `{"status":"ok"}` y Swagger en `/docs`.

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

**Figura 11.** Ejecución exitosa del workflow en la pestaña **Actions**.

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

**Figura 12.** Variable `SPC_CORS_ORIGINS` configurada en Render.

# 8. Endpoints de la API

Esta sección documenta la superficie REST del backend desplegado en Render. Todas las rutas
son **relativas a la URL base** del servicio:

```
https://sistema-comercializacion-v2-latest.onrender.com
```

La documentación interactiva **siempre está sincronizada con el código** (se genera desde el
propio FastAPI): consultar `**/docs**` (Swagger UI) o `**/openapi.json**` es la referencia
autoritativa. Las tablas siguientes resumen los endpoints por familia, con su método, ruta,
requisito de acceso y propósito.

Convenciones de la columna **Acceso**:

- **Público** — no requiere token.
- **Sesión** — requiere el header `Authorization: Bearer <token>` de un login válido.
- **Sesión + `action:users_manage`** — además, el rol debe tener ese permiso (administración).
- **Sesión + permiso de módulo** — el rol debe tener `module:{sales|purchases|inventory}` +
  `action:forecast` según el dominio (solo en el motor v2; ver §8.6 y §8.7).

## 8.1. Salud y documentación (OpenAPI/Swagger)

| Método | Ruta | Acceso | Descripción |
| --- | --- | --- | --- |
| GET | `/health` | Público | *Liveness*: responde `{"status":"ok"}`. Lo usa el `healthCheckPath` de Render. |
| GET | `/docs` | Público | Swagger UI (documentación interactiva). |
| GET | `/redoc` | Público | Documentación ReDoc (alternativa a Swagger). |
| GET | `/openapi.json` | Público | Contrato OpenAPI completo (fuente de verdad de todos los endpoints). |

## 8.2. Autenticación y restablecimiento de contraseña

Control de acceso por roles con **token de sesión firmado** (ADR-0014). El token viaja en el
header `Authorization: Bearer <token>` en cada petición autenticada.

| Método | Ruta | Acceso | Descripción |
| --- | --- | --- | --- |
| POST | `/auth/login` | Público | Verifica id + contraseña y devuelve `{token, expires_in, user}`. Mensaje genérico ante fallo (no revela si el id existe). |
| POST | `/auth/forgot` | Público | Inicia el restablecimiento: envía un enlace al correo de la cuenta (vía SMTP, §4). Respuesta **siempre genérica** (no enumera cuentas). |
| POST | `/auth/reset` | Público | Confirma el restablecimiento con el token del correo y fija la nueva contraseña. El token es de un solo uso y caduca pronto. |
| GET | `/auth/me` | Sesión | Devuelve la identidad efectiva (id, rol, permisos, `client_id`) del token vigente. |

## 8.3. Roles, usuarios y permisos

Administración del control de acceso. La autorización se valida **en el backend**; ocultar
elementos en la interfaz no basta.

| Método | Ruta | Acceso | Descripción |
| --- | --- | --- | --- |
| GET | `/permissions` | Sesión + `action:users_manage` | Catálogo de permisos (módulos + acciones) para construir/editar roles. |
| GET | `/roles` | Sesión + `action:users_manage` | Lista los roles con sus permisos. |
| POST | `/roles` | Sesión + `action:users_manage` | Crea un rol. `409` si el nombre ya existe. |
| PATCH | `/roles/{role_id}` | Sesión + `action:users_manage` | Edita descripción y/o permisos. No permite tocar los permisos del rol administrador. |
| DELETE | `/roles/{role_id}` | Sesión + `action:users_manage` | Elimina un rol. Rechaza el rol administrador o roles con usuarios asignados. |
| GET | `/users` | Sesión + `action:users_manage` | Lista las cuentas. |
| POST | `/users` | Sesión + `action:users_manage` | Crea una cuenta y le asigna un rol. `409` si el id ya existe. |
| PATCH | `/users/{user_id}` | Sesión + `action:users_manage` | Edita rol, contraseña, correo o estado (activo/inactivo). |

## 8.4. Perfil del negocio (onboarding)

Perfil ligado al `client_id` del usuario (sector, tamaño, región, moneda).

| Método | Ruta | Acceso | Descripción |
| --- | --- | --- | --- |
| GET | `/profile/options` | Sesión | Conjuntos de opciones (sector/tamaño/región/moneda) para poblar el formulario. |
| GET | `/profile` | Sesión | Perfil del negocio del cliente. `404` si el onboarding no se ha completado. |
| PUT | `/profile` | Sesión | Guarda el onboarding y marca la cuenta como `onboarding_done`. |

## 8.5. Catálogo v3 (motor actual de la interfaz)

**Es el motor que usa el frontend en producción (ADR-0028).** Cada módulo
(`ventas`, `compras`, `almacen`) ejecuta automáticamente **10 consultas predefinidas**
(4 regresión → 3 clasificación → 3 clustering) entrenadas en el momento, y devuelve 10
reportes + un bloque de tendencia. No exige permiso de módulo: deriva el `client_id` del
token si está presente (ver §8.7).

| Método | Ruta | Acceso | Descripción |
| --- | --- | --- | --- |
| GET | `/v3/catalogo` | Sesión | Lista informativa de las 30 consultas (10 por módulo) y las etiquetas de columnas. |
| POST | `/v3/{modulo}` | Sesión | Ejecuta las 10 consultas del módulo sobre las filas enviadas (`{rows: [...]}`). Devuelve 10 reportes + tendencia. |
| POST | `/v3/{modulo}/archivo` | Sesión | Igual que el anterior, pero subiendo un archivo `.xlsx`/`.xls`/`.json` (detecta la hoja de datos por sus encabezados). |
| GET | `/v3/{modulo}/plantilla` | Sesión | Descarga la plantilla del módulo (`formato=excel` por defecto, o `formato=json`). |
| GET | `/v3/{modulo}/demo` | Sesión | Corre el análisis con datos sintéticos del sistema (para verlo funcionar sin aportar datos). |
| GET | `/v3/{modulo}/historial` | Sesión | Historial de análisis del cliente para el módulo (`limite` configurable). `modulo=todos` devuelve todas las categorías. |
| GET | `/v3/historial/{prediction_id}` | Sesión | Detalle de un análisis pasado con sus valores predichos (para re-verlo sin re-ejecutar). |

`{modulo}` ∈ `{ventas, compras, almacen}` (para el historial también `todos`).

## 8.6. Motor 3×3 v2 (heredado, funcional)

Motor **anterior** (rediseño 3×3, ADR-0024/0025): un formato fijo por dominio que alimenta
**tres modelos** (regresión + clasificación + clustering) en una sola respuesta. Sigue
**operativo** y se usa para el reentrenamiento y la persistencia de modelos por cliente
(ADR-0027), pero está marcado como **`deprecated`** en OpenAPI: la interfaz activa migró al
catálogo v3 (§8.5). A diferencia de v3, **sí exige permiso de módulo**.

| Método | Ruta | Acceso | Descripción |
| --- | --- | --- | --- |
| POST | `/v2/{dominio}` | Sesión + permiso de módulo | Entrena al vuelo y devuelve los tres modelos sobre las filas enviadas (`{rows, horizon}`). |
| GET | `/v2/{dominio}/demo` | Sesión + permiso de módulo | Análisis 3×3 sobre datos sintéticos (`horizon` opcional). |
| GET | `/v2/{dominio}/esquema` | Sesión + permiso de módulo | Diccionario de variables del dominio: qué columnas pedir y qué predice cada modelo. |
| GET | `/v2/{dominio}/plantilla` | Sesión + permiso de módulo | Plantilla/ejemplo del dominio (`formato=excel|json`, `contenido=basica|rica`). |
| POST | `/v2/{dominio}/excel` | Sesión + permiso de módulo | Sube un `.xlsx` con los datos y corre el análisis 3×3. |
| POST | `/v2/{dominio}/entrenar` | Sesión + permiso de módulo | Reentrena con **todo** el corpus acumulado + lo nuevo, versiona los modelos en el registro y marca la versión servida. |
| POST | `/v2/{dominio}/predecir` | Sesión + permiso de módulo | Predice con el modelo **guardado** del cliente (sin reentrenar). `400` si aún no entrenó. |
| GET | `/v2/{dominio}/modelos` | Sesión + permiso de módulo | Lista las versiones de modelos entrenadas del cliente para el dominio (métricas, cuál se sirve). |
| POST | `/v2/{dominio}/modelos/{model_id}/servir` | Sesión + permiso de módulo | Elige qué versión se sirve para el dominio. |

`{dominio}` ∈ `{ventas, compras, almacen}`. Permiso requerido por dominio: `ventas` →
`module:sales`, `compras` → `module:purchases`, `almacen` → `module:inventory`, todos con
`action:forecast`.

## 8.7. Convenciones (autenticación, `client_id`, errores)

- **Autenticación.** Los endpoints marcados «Sesión» esperan `Authorization: Bearer <token>`.
  El token se obtiene de `POST /auth/login`, se guarda en el frontend (memoria + `localStorage`)
  y se envía en cada petición. No se usan cookies (por eso `allow_credentials=False`, §7).
- **Identidad del cliente (`client_id`).** Con el control de acceso activo, el backend
  **deriva el `client_id` del token** para separar corpus y modelos por cuenta. El header
  `X-Client-Id` es solo respaldo para desarrollo/pruebas sin sesión (cae a `default`).
- **Diferencia v2 vs v3.** El motor **v2** exige el permiso de módulo del dominio; el motor
  **v3** no exige permiso de módulo (solo aprovecha el `client_id` del token si está
  presente). La interfaz de producción consume **v3**.
- **Errores uniformes.** Las entradas mal formadas devuelven `422`; los datos inválidos o
  insuficientes para entrenar, `400`; sin permiso, `403`; sin token en un endpoint de sesión,
  `401`. El cuerpo de error sigue un formato uniforme (`ErrorResponse`).
- **Documentación viva.** Ante cualquier duda, `**/docs**` y `**/openapi.json**` reflejan el
  estado exacto del servicio desplegado (métodos, parámetros, esquemas de request/response).

# 9. Verificación del despliegue

Tras desplegar, ejecutar las siguientes verificaciones:

| N.º | Verificación | Resultado esperado |
| --- | --- | --- |
| 1 | Acceder a la URL del frontend en GitHub Pages | La aplicación carga correctamente |
| 2 | Recargar una ruta interna (p. ej. `/sales`) | No muestra error 404 (fallback SPA) |
| 3 | `GET /health` del backend | Responde `{"status":"ok"}` (puede tardar ~40 s en frío) |
| 4 | Abrir `/docs` (Swagger) | Renderiza y documenta los endpoints |
| 5 | Iniciar sesión desde el frontend (`POST /auth/login`) | El usuario accede al sistema |
| 6 | Consumir un dominio desde el frontend (motor v3: `POST /v3/ventas` o `GET /v3/ventas/demo`) | El frontend recibe los 10 reportes desde Render |
| 7 | Revisar la consola del navegador | Sin errores de CORS |
| 8 | Revisar los logs en Render | Sin errores críticos; arranque de Uvicorn correcto |
| 9 | Verificar persistencia en Supabase | El corpus y los modelos se registran en Postgres/Storage |
| 10 | Probar los módulos principales | Ventas, Compras y Almacén funcionan |

La referencia completa de endpoints (salud/docs, autenticación y restablecimiento, roles y
usuarios, perfil, catálogo **v3** y motor **v2**) está en la **§8**. En vivo, `**/openapi.json**`
y `**/docs**` reflejan el estado exacto del servicio desplegado.

**Figura 13.** `/health` respondiendo OK e inicio de sesión exitoso desde el SPA.

# 10. Mantenimiento y actualización

**Actualización del backend:**

Como Render sirve una **imagen externa de Docker Hub**, la actualización **no es automática**:
hay que reconstruir la imagen, volver a publicarla y hacer un redeploy manual. Desde la raíz
del proyecto:

```bash
docker build -t valxux/sistema_comercializacion_v2:latest .
docker push valxux/sistema_comercializacion_v2:latest
```

Después, en Render: **Manual Deploy → Deploy latest reference** para que el servicio tome la
imagen recién publicada. Los cambios de **dependencias** (`requirements-api.txt`) o
**artefactos** (`models/`) quedan incluidos al reconstruir la imagen.

> Como el tag es `:latest`, Render descarga esa referencia en cada redeploy manual. No hace
> falta cambiar el nombre de la imagen en Render entre versiones.

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

# 11. Posibles errores y soluciones

| Error | Posible causa | Solución |
| --- | --- | --- |
| Error de CORS en la consola | El backend no permite el origen del frontend | Fijar `SPC_CORS_ORIGINS` al dominio de GitHub Pages en Render |
| Error 404 al recargar rutas internas | Falta el fallback SPA | Verificar que el build copia `index.html` → `404.html` |
| El frontend consume `localhost` | `VITE_API_BASE_URL` no configurada en el build | Definir el secreto en GitHub Actions y re-ejecutar el workflow |
| Primera petición muy lenta (~40 s) | Arranque en frío del free tier de Render | Comportamiento esperado; considerar un plan de pago o un *ping* periódico |
| `libgomp.so.1: cannot open shared object file` | Falta `libgomp1` en la imagen | Ya incluido en el `Dockerfile`; verificar que no se removió |
| La imagen no se actualiza en Render | Despliegue no automático (Existing Image) | Tras `docker push`, hacer **Manual Deploy → Deploy latest reference** en Render |
| `docker push` rechazado (denied) | Sin `docker login` o nombre de imagen ajeno | `docker login` y usar tu usuario: `valxux/sistema_comercializacion_v2:latest` |
| Backend no arranca en Render | Variables de entorno incompletas/incorrectas | Revisar `SPC_DATABASE_URL`, `SUPABASE_*`, `SPC_AUTH_SECRET` en el panel |
| Error de conexión a la base | Prefijo de la cadena o pooler incorrecto | Usar `postgresql+psycopg://` y la cadena del **Session pooler** |
| Modelos no se guardan en la nube | `SUPABASE_KEY` es la `anon` en vez de `service_role` | Usar la **service role key** (sube/borra artefactos) |
| Tokens de sesión inválidos/falsificables | `SPC_AUTH_SECRET` sin fijar (usa secreto de dev) | Fijar un secreto largo y aleatorio en Render |
| `job_id` no encontrado en lote | Más de 1 worker de Uvicorn | Mantener **1 worker** (almacén de lote in-process, ADR-0008) |
| Workflow de Pages falla en `deploy-pages` | GitHub Pages no configurado como "GitHub Actions" | Settings → Pages → Source = GitHub Actions |

# 12. Seguridad del despliegue

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

**Figura 14.** Configuración de seguridad (usuario no-root en el `Dockerfile`, variables en
Render).

# 13. Evidencias del despliegue

Se recomienda adjuntar como evidencia:

- **13.1.** Archivo `Dockerfile` del backend.
- **13.2.** Imagen del backend publicada en Docker Hub (`valxux/sistema_comercializacion_v2:latest`).
- **13.3.** Servicio backend en Render con fuente **Existing Image** (imagen de Docker Hub).
- **13.4.** Servicio backend en estado **Live** en Render.
- **13.5.** Variables de entorno configuradas en Render.
- **13.6.** Logs del backend (arranque de Uvicorn correcto).
- **13.7.** Endpoint de salud: `/health → {"status":"ok"}`.
- **13.8.** Swagger UI en `/docs` (referencia viva de los endpoints, §8).
- **13.9.** Ejecución exitosa del workflow en la pestaña **Actions**.
- **13.10.** Configuración de GitHub Pages (Source = GitHub Actions).
- **13.11.** Aplicación publicada en `https://tallerintegrador.github.io/sistema_predicion_comercializacion/`.
- **13.12.** Inicio de sesión exitoso desde el frontend.
- **13.13.** Proyecto Supabase con la base Postgres y el bucket `spc-modelos`.

# 14. Conclusión

El despliegue del SPC separa frontend y backend en plataformas especializadas. El backend
**FastAPI** se containeriza con **Docker**, la imagen se **publica en Docker Hub**
(`valxux/sistema_comercializacion_v2:latest`) y se **ejecuta en Render** como *Existing Image*.
La persistencia vive en **PostgreSQL y Storage sobre Supabase**. El frontend **React + Vite**
se publica en **GitHub Pages** de forma automática con **GitHub Actions** —sin Firebase—.

Esta estrategia mantiene una arquitectura de despliegue ordenada: el frontend consume una API
REST pública y el backend concentra la lógica de negocio, la seguridad (token de sesión y
roles), la conexión con la base de datos y el almacenamiento de artefactos. El uso de variables
de entorno, control de acceso por roles, CORS restringido, contenedor sin privilegios y HTTPS
de extremo a extremo refuerza la seguridad del sistema en producción.
