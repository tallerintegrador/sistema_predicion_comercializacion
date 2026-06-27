# ADR 0020 — Rediseño orientado al cliente: identidad visual enriquecida y mapa de pantallas

- **Estado:** Aceptado (2026-06-21).
- **Fase:** 4.5 — experiencia de usuario. **Extiende** (no reemplaza) la identidad visual de
  [ADR-0017](0017-identidad-visual-sistema-diseno.md) y las opciones derivadas del catálogo de
  [ADR-0018](0018-catalogo-tipologias-dimensiones.md), con el lenguaje de [ADR-0019](0019-lenguaje-de-producto-glosario.md).
- **Dependencias nuevas (frontend):** `lucide-react` (íconos), `@fontsource/inter` y
  `@fontsource/sora` (fuentes auto-hospedadas). No afectan al backend ni al motor de ML.

## Contexto

El objetivo es que el frontend sea la experiencia ideal de un dueño de PYME no técnico: atractivo,
amigable, en español claro. La identidad de ADR-0017 (tokens en `@theme`) era una buena base pero
sobria y sin acentos por módulo, sin tipografía de títulos con personalidad y sin íconos
consistentes; faltaban pantallas de orientación (Inicio, «Acerca del sistema») y el catálogo
mostraba esquemas crudos.

## Decisión

### 1. Identidad visual enriquecida (extiende ADR-0017)

- **Acento por módulo** (orienta al usuario), en tokens `@theme`: Ventas índigo (`#4f46e5`),
  Compras naranja (`#ea580c`), Almacén teal (`#0d9488`), Mejorar/Reentrenamiento violeta
  (`#7c3aed`). Marca primaria índigo (continuidad con ADR-0017). Semánticos emerald/amber/red/blue
  con contraste AA.
- **Tipografía:** **Inter** (cuerpo) + **Sora** (títulos), auto-hospedadas vía `@fontsource`
  (subconjunto latino, sin CDN → funciona offline y con un solo worker), con respaldo al stack de
  sistema.
- **Íconos:** `lucide-react`, consistentes y accesibles (`aria-hidden`). Supera la decisión de
  ADR-0017 de usar solo SVG inline.
- **Registro central de secciones** (`theme/modules.ts`): id, etiqueta, ícono, permisos, frase de
  «qué hace y para qué sirve» y clases de acento (literales, para que Tailwind las genere). Lo
  consumen sidebar, Inicio y los encabezados de módulo.
- **Estados y accesibilidad:** primitivas con estados completos (normal/hover/foco/deshabilitado/
  carga/error/vacío): `ModuleHeader`, `EmptyState`, `ComingSoon`, `ResultSummary`, `RiskBadge`,
  `TechnicalDetails`. Layout responsivo (sidebar con íconos en móvil, etiquetas en ≥ md).

### 2. Mapa de pantallas

- **Inicio:** bienvenida, accesos directos a los módulos del usuario y guía de 4 pasos.
- **¿Qué hace el sistema? (catálogo amigable):** reemplaza el volcado de esquemas por tarjetas en
  lenguaje natural (qué datos pide, qué entrega). Lo crudo va a «Detalles técnicos».
- **Ventas / Compras / Almacén:** encabezado explicativo + configuración (cuando aplica) + carga de
  datos + resultado con gráfico, tabla y **resumen en lenguaje natural**. Almacén con **semáforo**
  de riesgo.
- **Mejorar las predicciones:** explica modelo base vs. propio, condiciones y veredicto honesto.
- **Usuarios y permisos** (admin) y **Acerca del sistema** (honestidad + tecnicismos colapsados).

### 3. Cambios transversales

- **Eliminado «Cargar ejemplo»** en todos los módulos (y los datos de ejemplo del frontend). El
  usuario solo: sube Excel, sube JSON o descarga la plantilla; en Compras/Almacén, además, **carga
  manual por tabla editable** («Agregar fila»).
- **Indicador de API** («Servidor: …») visible **solo para administradores**.
- **Footer** sin jerga; la honestidad técnica se movió a «Acerca del sistema».

### 4. Carga sin hardcodeo: `input_tables` en `/catalog` (servicio/API, no motor)

Para que la tabla editable no clave columnas ni etiquetas, `/catalog` expone por dominio las
**tablas de entrada** con sus columnas (nombre/tipo/obligatoriedad **derivados** del esquema
Pydantic; `label`/`help` en español centralizados). Detalle y pruebas anti-desync en
[docs/alineacion_frontend_backend.md](../alineacion_frontend_backend.md) §2. **El motor de ML no
se toca.**

## Consecuencias

- **A favor:** experiencia clara y atractiva para el público objetivo; identidad coherente y
  orientada por módulo; cero hardcodeo de columnas (derivadas del catálogo); honestidad preservada.
- **Deuda asumida:** tres dependencias nuevas de frontend (íconos + fuentes); el bundle crece por
  las fuentes (subconjunto latino, ~25 kB c/u). No se define modo oscuro (fuera de alcance). Quedan
  funciones marcadas «Próximamente» a la espera de backend (alineación §3–§6).

## Referencias

- [ADR-0017 — Identidad visual / sistema de diseño](0017-identidad-visual-sistema-diseno.md)
- [ADR-0018 — Catálogo: tipologías y dimensiones](0018-catalogo-tipologias-dimensiones.md)
- [ADR-0019 — Lenguaje de producto / glosario](0019-lenguaje-de-producto-glosario.md)
- [docs/alineacion_frontend_backend.md](../alineacion_frontend_backend.md)
