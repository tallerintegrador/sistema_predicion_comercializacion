# ADR 0014 — Control de acceso por roles (autenticación, usuarios, permisos)

- **Estado:** Aceptado (2026-06-20).
- **Fase:** 4.5 — experiencia de usuario y control de acceso. Da identidad y autorización a
  la plataforma antes del despliegue (Fase 4.0–4.4 sigue pendiente).
- **Contexto previo:** [ADR-0011](0011-persistencia-corpus-incremental.md) (SQLite local del
  corpus), [ADR-0012](0012-frontend-web.md) (frontend; el `X-Client-Id` **no estaba
  autenticado**), [ADR-0013](0013-entrenamiento-por-cliente-bajo-demanda.md) (entrenamiento por
  cliente; namespaced por `client_id`).
- **No toca** el motor de ML (`src/spc/models/`, features). La autenticación vive en la capa
  API/servicio; el motor nunca importa FastAPI ni conoce usuarios.

## Contexto

Hasta aquí cualquiera podía llamar a la API y declarar su `X-Client-Id` por header
(metadato de transporte, sin verificar). Para un piloto y una demo creíbles hace falta
**identidad** (quién entra) y **autorización** (qué puede hacer), aplicadas en el
**backend** —no basta con ocultar botones en la UI—. La restricción de despliegue vigente
(un solo worker de uvicorn, almacenes in-process) obliga a una solución **sin almacén de
sesión externo**.

## Decisión

Un control de acceso por roles construido sobre el **mismo stack** (SQLite de la
biblioteca estándar + knobs `SPC_*`), bajo seis invariantes:

### 1. Autorización en el BACKEND, por endpoint

Cada endpoint protegido declara los permisos que exige con la dependencia
`spc.api.seguridad.requiere(*permisos)`. Sin sesión válida → **401**; con sesión pero sin
el permiso → **403**. La UI filtra el sidebar por permisos solo para mejorar la
experiencia; la decisión real la toma el servidor.

### 2. Sesión autocontenida y firmada (sin almacén externo)

El login emite un **token firmado con HMAC-SHA256** (`spc.service.seguridad`) que
transporta `sub` (id de usuario) y `exp`. Al ir firmado y caducar solo, **no requiere
almacén de sesión** — respeta el despliegue de un solo worker y migra a la nube sin estado
compartido. El **rol y los permisos no viajan en el token**: se leen frescos de la base en
cada petición, de modo que un cambio de rol surte efecto sin re-emitir tokens.

### 3. Contraseñas hasheadas (nunca en claro)

Se almacenan con `hashlib.scrypt` (KDF con sal por contraseña), formato
`scrypt$n$r$p$salt$hash`. La verificación es en tiempo constante. **Cero dependencias
nuevas** (mismo criterio que el SQLite stdlib del corpus).

### 4. Modelo: roles ↔ permisos ↔ usuarios ↔ perfil

En el **mismo `spc.db`** (`RepositorioAuth`): `roles` + `role_permissions`, `users` (id,
hash, rol, `client_id`, estado de onboarding) y `client_profiles` (onboarding). El
vocabulario de permisos (`spc.service.permisos`) tiene dos ejes: **módulos** —derivados de
los dominios reales de `GET /catalog`, sin lista fija— y **acciones** transversales
(`catalog`, `forecast`, `template_download`, `template_upload`, `training`,
`users_manage`). El catálogo de permisos se expone en `GET /permissions` para que el editor
de roles de la UI no clave nada.

### 5. Seed de administradores de DEMOSTRACIÓN

Al arranque se siembran de forma idempotente el rol `administrator` (todos los permisos) y
dos cuentas: **256317** y **256370**, con **contraseña inicial igual al id**, almacenada
**hasheada**. Se documentan como credenciales de **demo, no de producción** (deben rotarse;
ver README).

### 6. El `client_id` se deriva del usuario autenticado

Con el control activo, `obtener_client_id` toma el `client_id` de la **sesión** (saneado
con `slug_cliente`, anti path-traversal) en vez del header `X-Client-Id`. Así el corpus
(ADR-0011) y el entrenamiento por cliente (ADR-0013) quedan ligados a la cuenta real y no a
un header falsificable. Sin sesión (control desactivado o tests previos) cae al header.

## Compatibilidad y gating

`SPC_AUTH_ENABLED` habilita la capacidad a nivel de despliegue (**activo por defecto**).
Con la bandera en `0`, los endpoints no exigen credenciales (comportamiento previo): la
suite de predicción heredada corre sin tokens (la desactiva por defecto en su conftest,
igual que la persistencia del corpus). Los tests de control de acceso la activan y crean su
propia app con un repositorio de auth temporal.

## Configuración (entorno, con defaults documentados)

| Variable | Default | Para qué |
|---|---|---|
| `SPC_AUTH_ENABLED` | `true` | Habilita el control de acceso por roles. |
| `SPC_AUTH_SECRET` | *(secreto de DEV)* | Firma de los tokens. **Obligatorio fijarlo en producción.** |
| `SPC_AUTH_TOKEN_TTL` | `28800` (8 h) | Vida útil del token de sesión, en segundos. |

## Consecuencias

- **A favor:** autorización real en el backend; sin almacén de sesión externo (un solo
  worker); cero dependencias nuevas; permisos de módulo derivados del catálogo (sin
  hardcode); corpus/entrenamiento ligados a la cuenta; "modelo de ML intacto".
- **Deuda asumida y explícita:** (a) los tokens **no se revocan** antes de expirar (no hay
  lista de revocación; mitigado con TTL corto); (b) el seed usa contraseña = id por ser
  **demo** — en producción hay que forzar cambio de contraseña y rotación del secreto;
  (c) sin límite de intentos de login (rate limiting) — diferido; (d) un solo proceso: la
  base de auth comparte archivo con el corpus (SQLite con lock, como ADR-0011).
- **Privacidad/operación:** la base contiene hashes y perfiles de negocio; en producción
  aplica retención/respaldo/acceso (como el corpus de ADR-0011).

## Referencias

- [ADR-0011 — Persistencia incremental del corpus](0011-persistencia-corpus-incremental.md)
- [ADR-0012 — Frontend web](0012-frontend-web.md)
- [ADR-0013 — Entrenamiento por cliente bajo demanda](0013-entrenamiento-por-cliente-bajo-demanda.md)
- [ADR-0015 — Rediseño de frontend / experiencia de usuario](0015-rediseno-frontend-experiencia.md)
- [ADR-0016 — Perfil de cliente / onboarding](0016-perfil-cliente-onboarding.md)
