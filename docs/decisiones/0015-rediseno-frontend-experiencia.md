# ADR 0015 — Rediseño de frontend / experiencia de usuario

- **Estado:** Aceptado (2026-06-20).
- **Fase:** 4.5 — experiencia de usuario. Rediseña el frontend para un usuario no técnico de
  una PyME y lo integra con el control de acceso.
- **Contexto previo:** [ADR-0012](0012-frontend-web.md) (frontend desacoplado, React + Vite +
  TypeScript + Tailwind + recharts), [ADR-0014](0014-control-acceso-por-roles.md) (auth/roles),
  [ADR-0016](0016-perfil-cliente-onboarding.md) (onboarding).
- **No introduce un framework nuevo:** reutiliza el stack existente.

## Contexto

El frontend de ADR-0012 era una demo con **pestañas superiores** (Catálogo/Ventas/Compras/
Inventario) y sin sesión. La fase de experiencia pide una navegación predecible filtrada por
rol, login/onboarding, y una sección de administración, **reutilizando** componentes y
estilos para no fragmentar el producto ni la lógica.

## Decisión

### 1. Sin router nuevo: navegación por estado + guards de sesión

Se mantiene la navegación por estado (`useState`) ya usada, sin añadir `react-router`. El
componente raíz (`App.tsx`) actúa como **guard**: `loading` → indicador; sin sesión →
`LoginPage`; usuario no admin sin onboarding → `OnboardingPage`; en regla → panel principal.

### 2. Sidebar filtrado por permisos

La barra de pestañas se reemplaza por un **sidebar** (`components/Layout.tsx`). Las secciones
(Catálogo, Ventas, Compras, Almacén, Reentrenamiento, Administración de usuarios) se muestran
solo si el rol tiene sus permisos. La lista de permisos del usuario sale de `GET /auth/me`
(backend); la UI **solo filtra la vista**, la autorización real es del servidor (ADR-0014).

### 3. Reentrenamiento como sección propia y honesta

El `TrainingPanel` (ADR-0013) sale de la página de Ventas y pasa a una sección
**Reentrenamiento** etiquetada opt-in/local/experimental, visible solo con
`action:training`. No se simulan métricas: el panel muestra el experimento medido real o un
estado honesto ("datos insuficientes", "no disponible").

### 4. Estado de sesión en el cliente HTTP

`api/client.ts` guarda el token (memoria + `localStorage`), lo envía como
`Authorization: Bearer` y, ante un **401 con sesión activa** (token expirado), dispara el
cierre de sesión. El `AuthProvider` (`auth/AuthContext.tsx`) centraliza login/logout,
restauración de sesión al recargar (`GET /auth/me`) y los helpers de permisos
(`hasPerm`, `canModule`).

### 5. Cero hardcodeo de opciones del producto

Las tipologías, columnas, granularidad y horizonte siguen leyéndose de `GET /catalog`
(ADR-0012). Las opciones del editor de roles vienen de `GET /permissions` y las del
onboarding de `GET /profile/options`: ninguna se clava en el código de la UI.

## Consecuencias

- **A favor:** experiencia clara filtrada por rol; reutiliza estilos/componentes existentes;
  sin dependencias nuevas; honesto (no inventa capacidades ni métricas).
- **Deuda asumida:** (a) sin rutas URL (no hay deep-linking ni back del navegador entre
  secciones) — aceptable para la demo, migrable a `react-router` si hace falta; (b) el token
  en `localStorage` es práctico para la demo pero expuesto a XSS — endurecer en producción
  (cookie `HttpOnly`) queda diferido y documentado.

## Referencias

- [ADR-0012 — Frontend web](0012-frontend-web.md)
- [ADR-0014 — Control de acceso por roles](0014-control-acceso-por-roles.md)
- [ADR-0016 — Perfil de cliente / onboarding](0016-perfil-cliente-onboarding.md)
