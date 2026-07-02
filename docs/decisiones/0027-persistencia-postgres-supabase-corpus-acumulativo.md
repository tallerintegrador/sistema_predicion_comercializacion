# ADR-0027 — Persistencia en base de datos real (Postgres/Supabase) con corpus acumulativo

- **Estado:** Aceptado (en construcción)
- **Fecha:** 2026-07-01
- **Rama:** `feature/mejoras-modelos-camila`
- **Relacionado:** [ADR-0011](0011-persistencia-incremental-corpus.md) (corpus incremental que
  esto sustituye), [ADR-0013](0013-entrenamiento-por-cliente.md) (entrenamiento por cliente),
  [ADR-0014](0014-control-acceso-por-roles.md) (auth que aquí se migra de almacén),
  [ADR-0024](0024-rediseno-3x3-sklearn-sintetico.md) / [ADR-0025](0025-mejoras-modelos-variedad-objetivos-clustering.md) (motor 3×3)

## Contexto

Toda la persistencia vivía en **un archivo SQLite local** (`data/spc.db`) con `sqlite3` de
la stdlib, y solo guardaba el control de acceso (usuarios/roles/perfiles). El motor de
**corpus acumulativo** de ADR-0011 (tablas `submissions`/`observations`) había sido
**eliminado** en el refactor que retiró el motor congelado. Consecuencia: los endpoints
`/v2/*` entrenaban en el momento y **no guardaban nada**, así que el requisito de negocio
—"cada vez que el cliente entrena, se reentrena con **históricos + datos nuevos**"— **no se
podía cumplir**. Además, un archivo local no es multi-máquina ni "profesional" para el
entregable.

## Decisión

Mover **toda** la persistencia a **una base de datos real** vía **SQLAlchemy 2.x**:

- **Motor:** Postgres gestionado en **Supabase** en producción (`SPC_DATABASE_URL`), con
  **SQLite de respaldo** para dev/tests. El ORM es el mismo en ambos; los tests siguen
  corriendo en SQLite (aislado por test).
- **Migraciones:** **Alembic** (`migrations/`), migración inicial que crea el esquema desde
  la metadata del ORM (fuente única de verdad).
- **Auth:** se **conserva** la implementación propia (JWT + roles + permisos + onboarding);
  solo cambia su almacén a SQLAlchemy manteniendo **idéntica la interfaz** de
  `RepositorioAuth` (no se tocan routers).
- **Corpus acumulativo:** vuelve como tablas `datasets` (auditoría de cada carga) y
  `observations` (histórico de entrenamiento), con **dedup idempotente** por
  `(tenant, dominio, serie, fecha)` (política *keep-first*, `ON CONFLICT DO NOTHING`). El
  `payload` de cada fila se guarda como **JSON/JSONB**, así sirve tanto a los dominios
  fijos 3×3 como a esquemas declarados por el cliente (`/auto/*`).
- **Registro de modelos:** tabla `models` (versión, algoritmo, métricas honestas, cuál se
  sirve, puntero al artefacto) + `training_runs` (trazado del reentrenamiento) +
  `predictions` (auditoría). El artefacto `.joblib` se sube a **Supabase Storage**; si no
  está configurado (`SUPABASE_*` ausentes), cae a **disco local** sin romperse.
- **Reentrenamiento (el requisito):** `POST /v2/{dominio}/entrenar` carga **todo** el
  corpus del cliente para el dominio, reentrena los tres modelos sobre el conjunto completo,
  **versiona** cada uno y lo marca como servido. `GET /v2/{dominio}/modelos` lista el
  historial. El enganche del corpus en los POST de análisis es **best-effort**: un fallo de
  BD nunca rompe la predicción (mismo criterio que ADR-0011).

### Entidades

| Tabla | Rol |
|---|---|
| `tenants` | perfil de negocio del cliente (antes `client_profiles`); unidad de aislamiento |
| `users`, `roles`, `role_permissions` | control de acceso (ADR-0014) |
| `datasets` | auditoría de cada carga (JSON/Excel), con `schema_spec` para `/auto/*` |
| `observations` | corpus acumulativo; `payload` JSON + dedup por serie/fecha |
| `models` | versiones entrenadas por `(tenant, dominio, tarea)` + puntero al artefacto |
| `training_runs` | trazado de cada reentrenamiento (filas usadas, resultado) |
| `predictions` | auditoría de predicciones servidas |

## Alternativas descartadas

- **Seguir en SQLite:** cero infra, pero no es multi-máquina ni "profesional"; no resuelve
  el entregable.
- **Adoptar Supabase Auth:** obligaría a reescribir `auth.py`, `seguridad.py`, el modelo de
  permisos y el `AuthContext` del frontend; mucho riesgo para poco beneficio, teniendo una
  auth propia ya probada.
- **SQL crudo con psycopg:** funciona, pero pierde migraciones versionadas y el ORM
  agnóstico que permite testear en SQLite y desplegar en Postgres sin cambiar código.

## Configuración

| Variable | Rol | Default |
|---|---|---|
| `SPC_DATABASE_URL` | URL SQLAlchemy de la base | SQLite `data/spc.db` |
| `SUPABASE_URL` / `SUPABASE_KEY` | Storage de artefactos (service role key) | — (cae a disco) |
| `SUPABASE_BUCKET` | bucket de artefactos | `spc-modelos` |

Ejemplo de `SPC_DATABASE_URL` con el pooler de Supabase:
`postgresql+psycopg://postgres.<ref>:<clave>@aws-0-<region>.pooler.supabase.com:5432/postgres`

## Consecuencias

- **A favor:** una sola base para todo; corpus que crece por cliente; reentrenamiento con
  histórico completo; artefactos versionados fuera de local; despliegue profesional; tests
  siguen rápidos en SQLite.
- **En contra / pendiente:** dependencia de red en producción; falta enganchar el corpus en
  `/auto/*` (agnóstico) —previsto—; migrar la predicción para que **sirva** el modelo
  registrado (hoy sigue entrenando en el momento; el registro ya guarda y versiona).

## Puesta en marcha

1. `pip install -e .` (trae `sqlalchemy`, `alembic`, `psycopg[binary]`, `supabase`).
2. Crear proyecto Supabase; fijar `SPC_DATABASE_URL` (+ `SUPABASE_*` si se quiere Storage).
3. `alembic upgrade head` para crear el esquema.
4. (Opcional) `python scripts/migrar_sqlite_a_postgres.py --sqlite data/spc.db` para copiar
   usuarios/roles/perfiles del SQLite anterior.
