# ADR 0016 — Perfil de cliente / onboarding

- **Estado:** Aceptado (2026-06-20).
- **Fase:** 4.5 — experiencia de usuario. Captura el contexto de negocio del cliente y lo
  liga a su identidad.
- **Contexto previo:** [ADR-0011](0011-persistencia-corpus-incremental.md) (corpus por
  `client_id`), [ADR-0013](0013-entrenamiento-por-cliente-bajo-demanda.md) (artefactos por
  cliente, slug saneado), [ADR-0014](0014-control-acceso-por-roles.md) (usuarios y `client_id`
  del usuario).
- **No toca** el motor de ML: el perfil es metadato de negocio, no entra al modelo.

## Contexto

El `client_id` daba namespace al corpus y a los artefactos, pero no había ningún **perfil de
negocio** asociado. Para encuadrar honestamente los resultados (el modelo está calibrado
sobre Favorita) y para una operación multi-cliente, hace falta conocer rubro, tamaño,
región y moneda del cliente, capturados la primera vez que un usuario no administrador entra.

## Decisión

### 1. Onboarding en el primer ingreso de un usuario no administrador

Si el usuario autenticado no es administrador y su `onboarding_done` es `false`, la app lo
lleva a un **formulario de onboarding** antes de cualquier otra sección. Pide: **nombre del
negocio**, **rubro/sector**, **tamaño**, **región** y **moneda**. Al guardar
(`PUT /profile`), se persiste el perfil y se marca `onboarding_done = true`.

### 2. Ligado al `client_id` del usuario

El perfil se guarda en `client_profiles` con clave `client_id` = el del usuario autenticado
(ADR-0014). Así el perfil, el corpus (ADR-0011) y los artefactos por cliente (ADR-0013)
comparten la misma identidad.

### 3. Opciones servidas por el backend (sin hardcode en la UI)

Los conjuntos de sector/tamaño/región/moneda los expone `GET /profile/options` y los valida
`PUT /profile` (campos y enums en inglés). La UI puebla los desplegables desde ahí; no clava
listas en el código.

### 4. Encuadre honesto

El formulario muestra una nota fija: el modelo está calibrado sobre el cliente de referencia
(**Favorita**); para otros rubros los resultados son **referenciales**, no una garantía de
exactitud. La UI no sobrevende el pronóstico.

## Consecuencias

- **A favor:** contexto de negocio capturado y ligado a la identidad; opciones consistentes
  servidas por el backend; encuadre honesto explícito; motor de ML intacto.
- **Deuda asumida:** (a) el perfil no alimenta el modelo (es solo contexto/encuadre); usarlo
  para segmentar o ajustar el pronóstico queda fuera de alcance; (b) un único perfil por
  `client_id`: no se modelan múltiples sucursales con perfiles distintos (diferido).

## Referencias

- [ADR-0011 — Persistencia incremental del corpus](0011-persistencia-corpus-incremental.md)
- [ADR-0013 — Entrenamiento por cliente bajo demanda](0013-entrenamiento-por-cliente-bajo-demanda.md)
- [ADR-0014 — Control de acceso por roles](0014-control-acceso-por-roles.md)
