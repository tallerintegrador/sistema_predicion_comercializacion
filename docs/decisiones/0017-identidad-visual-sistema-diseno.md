# ADR 0017 — Identidad visual / sistema de diseño

- **Estado:** Aceptado (2026-06-20).
- **Fase:** 4.5 — experiencia de usuario. Formaliza la identidad visual del producto como un
  sistema de **tokens** centralizados, aplicable a toda la app.
- **Contexto previo:** [ADR-0012](0012-frontend-web.md) (React + Vite + TypeScript + Tailwind +
  recharts), [ADR-0015](0015-rediseno-frontend-experiencia.md) (rediseño de experiencia).
- **No introduce un framework nuevo ni dependencias:** consolida lo existente (Tailwind v4).

## Contexto

El frontend ya usaba Tailwind v4 con un pequeño bloque `@layer components` (`.card`, `.btn`,
`.btn-primary`, `.input`, `.badge`…), pero **sin tokens centralizados**: los colores se usaban
como utilidades crudas de la paleta (indigo/slate/emerald/amber/red) repartidas inline, y no
había marca (monograma) ni escala documentada. Faltaba una identidad coherente y formalizada
—confiable, analítica, clara, sobria, honesta— que se pudiera aplicar de forma consistente.

## Decisión

### 1. Tokens en `@theme` (Tailwind v4), no inline

Los tokens de marca viven en `frontend/src/index.css` dentro de `@theme`, de modo que generan
utilidades (`bg-brand-600`, `text-brand-700`, `ring-brand-200`, …). Los componentes consumen
estos tokens a través de las clases utilitarias de `@layer components`; así la identidad se
cambia en un solo lugar.

- **Marca (primario):** índigo/violeta. `brand-600 = #4f46e5` **reaprovecha** el indigo-600 del
  botón "Predecir" actual (continuidad), con la escala `50/100/200/500/600/700/900`.
- **Acento de datos:** teal (`accent-500 = #14b8a6`, `accent-600 = #0d9488`) para realces
  analíticos y series secundarias.
- **Neutros:** grises fríos (la paleta `slate` de Tailwind: fondo `slate-50`, texto `slate-900`,
  bordes `slate-200`, texto atenuado `slate-500`).
- **Semánticos:** éxito `emerald`, advertencia `amber`, error `red`, información `blue`
  (consistentes con los estados que ya usaba la UI).
- **Tipografía:** stack de sistema (`--font-sans: system-ui, …`), sin dependencia nueva; escala
  modular 1.25 (xs 12 · sm 14 · base 16 · lg 18 · xl 20 · 2xl 24) y pesos 400/500/600/700.
- **Foco accesible:** anillo de marca (`--shadow-focus` y `focus-visible:ring-brand-200`) para
  que el foco de teclado sea visible y consistente. Contraste objetivo **AA**.

### 2. Marca: monograma + wordmark + tagline

El sidebar muestra un **monograma** "SPC" en un cuadrado redondeado con el color primario, junto
al wordmark "SPC" y la tagline "Pronóstico para PYMEs". Iconografía lineal mediante SVG inline
(sin librería de iconos nueva).

### 3. Estados completos y accesibilidad

Las clases base incorporan estados por defecto, hover, **foco visible**, deshabilitado y carga.
Se añade un control segmentado accesible (`.segmented`/`.segmented-option`, `role="radiogroup"`)
para la tipología de pronóstico (ver [ADR-0018](0018-catalogo-tipologias-dimensiones.md)).

## Consecuencias

- **A favor:** identidad coherente y centralizada; un único punto de cambio; continuidad con el
  morado existente; sin dependencias nuevas; foco/contraste accesibles.
- **Deuda asumida:** quedan usos directos de `indigo-*` equivalentes a `brand-*` en pantallas no
  tocadas (mismo valor de color, sin impacto visual); migrarlos a `brand-*` es cosmético y se
  hará de forma incremental. No se define modo oscuro (fuera de alcance).

## Referencias

- [ADR-0012 — Frontend web](0012-frontend-web.md)
- [ADR-0015 — Rediseño de frontend / experiencia](0015-rediseno-frontend-experiencia.md)
- [ADR-0018 — Catálogo: tipologías y dimensiones de pronóstico](0018-catalogo-tipologias-dimensiones.md)
