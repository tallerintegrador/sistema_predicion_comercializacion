# Sistema Predictivo de Comercializacion (SPC) — EDA

Analisis exploratorio reproducible del dataset **Store Sales - Corporacion Favorita**
(Taller Integrador I). El pipeline lee los CSV crudos, calcula metricas de calidad y
exploracion, genera figuras y **redacta el reporte automaticamente**: no hay cifras
escritas a mano, todo proviene de los calculos ejecutados sobre los archivos locales.

Antes era un unico `eda.py` de ~1700 lineas. Ahora es el paquete modular `spc`,
testeado y con tooling de calidad.

## Estructura

```
src/spc/
  config.py            # Settings (rutas, semilla, estilo de figuras) inmutable
  logging_setup.py     # logging configurable
  io/                  # carga de CSV (schemas + loaders) y escritura de artefactos
  quality/             # perfilado y chequeos de calidad
  features/            # integracion de fuentes y dataset analitico
  analysis/            # objetivo, univariado, temporal, relacional, correlacion,
                       #   clasificacion, clustering
  viz/                 # estilo unificado + figuras
  reporting/           # formatters, reporte Markdown y notebook
  pipeline.py          # run_pipeline() orquesta todo + CLI
scripts/run_eda.py     # entry point de linea de comandos
tests/                 # pytest sobre data sintetica
eda.py                 # shim: python eda.py / import eda; eda.main()
```

Flujo (tareas A–J del enunciado): carga → perfilado → calidad → variable objetivo →
univariado → temporal → integracion → bivariado/correlaciones → aptitud
(regresion/clasificacion/clustering).

## Requisitos previos

Colocar los 7 CSV del dataset en `data/raw/`:
`train.csv`, `test.csv`, `stores.csv`, `transactions.csv`, `oil.csv`,
`holidays_events.csv`, `sample_submission.csv`.

## Instalacion

```powershell
python -m venv venv
venv\Scripts\python -m pip install -e .[dev]
```

(`pip install -e .` sin `[dev]` instala solo lo necesario para ejecutar el EDA.)

## Ejecutar el EDA

```powershell
venv\Scripts\python scripts\run_eda.py        # genera todo
venv\Scripts\python scripts\run_eda.py -v     # logging DEBUG
venv\Scripts\python scripts\run_eda.py --no-notebook
# tambien: venv\Scripts\python eda.py   (shim de compatibilidad)
```

Desde Python:

```python
import spc
resumen = spc.run_pipeline()
```

## Artefactos generados

- `data/processed/*.csv` y `*.json` — tablas intermedias y resumenes.
- `figures/01..19_*.png` — figuras con estilo unificado.
- `reporte_eda.md` — reporte redactado.
- `notebooks/eda.ipynb` — notebook reproducible que recorre el flujo.

## Figuras: que se corrigio

Las figuras se rehicieron para que cada una sustente correctamente su afirmacion:

- **Estacionalidad mensual (04):** ahora es un **indice estacional** (media del mes /
  media diaria de su anio, promediada entre anios). El promedio crudo anterior mezclaba
  tendencia con estacionalidad (Sep–Dic no tienen datos de 2017, el anio de mayor nivel).
- **Petroleo vs ventas (09):** coloreado por anio, porque la correlacion negativa global
  es en gran parte espuria por la tendencia temporal.
- **Correlaciones (10):** triangulo superior enmascarado (mitad redundante).
- **Promocion vs ventas (07):** promedio directo de `sales` por bin de `onpromotion`.
- **Transacciones vs ventas (08):** linea de tendencia para leer la relacion.
- **Resto:** tema, paleta, tamanos y dpi unificados; acentos correctos; etiquetas de
  valor donde aportan.

## API (Fase 3)

Servicio FastAPI que expone el **contrato de datos** (`docs/contrato_datos.md`) por tres
campos —**VENTAS**, **COMPRAS**, **ALMACÉN**— cargando los artefactos del motor (Fase 2)
sin reentrenar. La capa de servicio (`src/spc/service/`) traduce el contrato genérico al
esquema del motor; la capa API (`src/spc/api/`) valida, documenta y maneja errores. La
decisión de diseño está en `docs/decisiones/0007-capa-api-fase3.md`.

Levantar el servidor (requiere los artefactos en `models/`):

```powershell
venv\Scripts\uvicorn spc.api.main:app --reload --port 8010
# Swagger interactivo: http://127.0.0.1:8010/docs
# Endpoints: POST /sales, POST /purchases, POST /inventory ; salud: GET /health
```

CORS configurable con `SPC_CORS_ORIGINS` (orígenes separados por coma; `*` por defecto).

### Control de acceso por roles (Fase 4.5, ADR-0014)

La API exige **autenticación y autorización** en el backend (no basta ocultar elementos en
la UI). Login por id + contraseña (`POST /auth/login`) que emite un **token firmado**
(`Authorization: Bearer …`); cada endpoint protegido valida rol/permiso con
`spc.api.seguridad.requiere`. Usuarios, roles, permisos y perfiles viven en el **mismo
SQLite** (`spc.db`), con contraseñas **hasheadas** (`hashlib.scrypt`). Detalle en
[`docs/decisiones/0014-control-acceso-por-roles.md`](docs/decisiones/0014-control-acceso-por-roles.md).

**Cuentas administrador de DEMOSTRACIÓN** sembradas al arranque: **256317** y **256370**,
con **contraseña inicial igual al id** (almacenada hasheada). ⚠️ **No son credenciales de
producción**: en un despliegue real hay que cambiarlas y fijar `SPC_AUTH_SECRET`.

Variables de entorno:

| Variable | Default | Uso |
|---|---|---|
| `SPC_AUTH_ENABLED` | `true` | Habilita el control de acceso (en `0`, la API no exige credenciales). |
| `SPC_AUTH_SECRET` | *(secreto de DEV)* | Firma de los tokens; **obligatorio en producción**. |
| `SPC_AUTH_TOKEN_TTL` | `28800` | Vida útil del token, en segundos (8 h). |

```powershell
# Levantar fijando un secreto propio y orígenes CORS del frontend:
$env:SPC_AUTH_SECRET = "un-secreto-largo-y-aleatorio"
$env:SPC_CORS_ORIGINS = "http://localhost:5173"
venv\Scripts\python -m uvicorn spc.api.main:app --port 8010 --workers 1
```

Tests de la API (entrenan artefactos diminutos sobre datos sintéticos; **sin `data/raw`
ni GPU**):

```powershell
venv\Scripts\python -m pytest tests/api      # solo la API
```

### Despliegue (Docker)

La API se empaqueta en una imagen lista para Render / Railway. Los artefactos del
motor (`models/`) se **hornean en la imagen**: el contenedor arranca sin volúmenes
ni descargas y solo carga y predice (no reentrena).

Archivos:

- `Dockerfile` — imagen de servicio (`python:3.11-slim` + `libgomp1` para
  LightGBM/XGBoost). Usa `requirements-api.txt`, no las deps de entrenamiento/EDA.
- `requirements-api.txt` — subconjunto de runtime con **pines exactos** (deben
  coincidir con los de `pyproject.toml`: con otras versiones de numpy/pandas/
  scikit-learn el `.joblib` puede no cargar).
- `.dockerignore` — deja fuera `venv/`, `data/`, `figures/`, `tests/`, etc.
- `render.yaml` — blueprint de Render (runtime docker, health `/health`).

El servidor hace bind a `0.0.0.0:$PORT` (puerto inyectado por la plataforma; `8000`
por defecto en local).

Probar la imagen en local:

```powershell
docker build -t spc-api .
docker run --rm -p 8000:8000 spc-api
# Swagger: http://127.0.0.1:8000/docs   ;   salud: http://127.0.0.1:8000/health
```

**Render:** New → Blueprint (usa `render.yaml`), o New → Web Service con runtime
Docker. Health check `/health`.

**Railway:** New Project → Deploy from repo; detecta el `Dockerfile` solo. Inyecta
`$PORT` automáticamente (ya contemplado en el `CMD`).

Variable de entorno relevante en ambas: `SPC_CORS_ORIGINS` (orígenes del frontend,
coma-separados; `*` por defecto).

## Frontend (interfaz web local — aún NO desplegado)

Interfaz web (React + Vite + TypeScript + Tailwind + recharts) en `frontend/`. Consume
la API con el modelo congelado; habla solo el **contrato v1.0.1** (no toca el motor ni la
capa interna). Cubre los tres dominios por JSON con datos de ejemplo, canal Excel
(plantilla + subida), modo lote con *polling* de `/jobs/{id}`, página de catálogo y
gráficos. Lo diferido se etiqueta (`interval_80`, `client_adjustment`).

La interfaz tiene una **identidad visual** formalizada como tokens de diseño
(`@theme` en `index.css`: marca índigo, acento teal, neutros fríos, semánticos; monograma
"SPC") — ver [ADR-0017](docs/decisiones/0017-identidad-visual-sistema-diseno.md). La
pantalla de **Ventas** organiza el pronóstico en una tarjeta *Configuración del pronóstico*
con **tipo de pronóstico** (R1) y **dimensión / filtrar por** (R2) mediante componentes
reutilizables; todas las opciones (tipologías, dimensiones, granularidad **Día/Semana/Mes** y
rango de horizonte) provienen de `GET /catalog` (`query_options`), sin hardcodeo — ver
[ADR-0018](docs/decisiones/0018-catalogo-tipologias-dimensiones.md).

> **Estado:** el frontend corre **en local** (dev). **El despliegue (Fase 4.0–4.4) sigue
> pendiente**: no hay backend ni frontend desplegados. La conexión a una API desplegada
> con su CORS real es la Fase 4.5. Ver `docs/SPC_Entrega_Despliegue_Valentin.md` §8.

**Pasos clave** (dos terminales):

1. Levantar la API permitiendo el origen del frontend por CORS:

   ```powershell
   $env:SPC_CORS_ORIGINS = "http://localhost:5173"
   venv\Scripts\python -m uvicorn spc.api.main:app --port 8010 --workers 1
   # salud: http://localhost:8010/health  ->  {"status":"ok"}
   ```

2. Levantar el frontend:

   ```powershell
   cd frontend
   npm install
   copy .env.example .env     # ajustar VITE_API_BASE_URL si la API no está en :8010
   npm run dev                # http://localhost:5173
   ```

Build de producción: `npm run build` (typecheck `tsc -b` + `dist/`). Detalle y variables
(`VITE_API_BASE_URL`, `VITE_CLIENT_ID`) en `frontend/README.md`.

## Persistencia incremental del corpus (ADR-0011)

Cada predicción guarda el `history` del cliente (normalizado y **deduplicado**) en una
base SQLite local — el **corpus que crece** con cada uso. Es **best-effort** (un fallo de
BD nunca rompe la predicción) y **configurable** (`SPC_PERSIST_ENABLED`, `SPC_DB_PATH`).

> **Qué es y qué NO es (honestidad).** Esto es **solo acumulación de datos**: construye el
> corpus que *haría posible* mejorar el modelo más adelante. **NO es** entrenamiento ni
> "ajuste por cliente": **el modelo se sigue entregando congelado** (ADR-0009) y predice
> igual con o sin persistencia. El reentrenamiento es un **puente manual y offline**
> (`scripts/exportar_corpus.py` → deduplicar → `scripts/train_*` en GPU → reemplazar el
> artefacto en `models/`). En el catálogo, `client_adjustment` **sigue `planned`**: no se
> ha implementado ni medido ningún ajuste por cliente. El corpus **debe deduplicarse antes
> de entrenar** (el export ya lo hace).

## Calidad

```powershell
venv\Scripts\python -m pytest        # tests
venv\Scripts\ruff check src tests    # lint
venv\Scripts\black --check src tests # formato
venv\Scripts\mypy src                # tipos
```
