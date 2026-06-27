# ADR 0010 — Política de inventario y stock de seguridad

- **Estado:** Aceptado (2026-06-19).
- **Fase:** 3.5 — Auditoría de parámetros + capa de política de negocio. **Cierra** la
  decisión P2 sobre el método de stock de seguridad de INVENTORY, abierta desde la Fase 2
  y destapada por el catálogo (Fase 3.3).
- **Contexto previo:** `docs/contrato_datos.md` (§4 PURCHASES, §5 INVENTORY, §8(a)),
  ADR-0007 (capa API), `docs/fase-3/propuesta_replanteamiento_fase3.md` (D2). Recomendación
  del docente 7: **no fijar parámetros que dependan de los datos del cliente**.
- **No toca** el motor de ML: sus parámetros (umbral de clasificación, composición/pesos
  del ensemble, k del clustering, transformaciones) siguen leyéndose de la metadata del
  artefacto. Esta decisión vive en la **capa de política de negocio** (`spc.service`,
  `spc.config`).

## Contexto

La auditoría de la Fase 3.5 confirmó que **ningún parámetro del modelo** está clavado: todos
se leen de la metadata/objetos del artefacto. Sí encontró **constantes de política de negocio
clavadas** en la capa de servicio y una **inconsistencia de método** entre dominios:

- **PURCHASES** dimensionaba el stock de seguridad por **días de cobertura**:
  `safety = 30 % × demanda(lead_time)`.
- **INVENTORY** lo dimensionaba por **nivel de servicio**: `safety = z · σ · √lead_time`,
  con `σ` estimada de la **demanda real reciente** del cliente.

Constantes clavadas detectadas (todas de política, **ninguna** dependiente de datos del
cliente en el sentido de "valor del cliente congelado en código"): el factor 30 % de
PURCHASES; y en INVENTORY el lead time por defecto (7 días), la ventana de demanda (28
días), los niveles de servicio `z` (1.28 / 1.65) y el factor de respaldo (0.5).

Matiz de honestidad importante: el `σ` de INVENTORY **no es inventado** — se calcula de la
demanda real del cliente. La inconsistencia entre dominios es de **consistencia/preferencia**,
no de corrección ni de honestidad.

## Opciones consideradas

- **(i) Unificar INVENTORY a días de cobertura** (igual que PURCHASES) como método por
  defecto, dejando `z·σ·√lead` como secundario documentado. Pro: consistencia + preferencia
  del docente. Contra: **cambia el significado y los valores** que devuelve INVENTORY
  (`recommended_stock`, `safety_stock`, `stockout_risk`) y exige actualizar catálogo/contrato.
  Riesgo medio justo antes del cierre, para una ganancia de preferencia (no de corrección).
- **(ii) Mantener los métodos actuales, volver TODAS las constantes configurables y
  documentarlas, difiriendo la unificación.** Pro: resuelve de lleno el hallazgo de la
  auditoría (cero política clavada) **sin cambiar comportamiento** por defecto; riesgo bajo,
  cambio localizado. Contra: la inconsistencia de método queda diferida.

## Decisión

Se adopta la **opción (ii) con un puente hacia (i)**:

1. **Las seis constantes de política se vuelven configurables** por entorno, con el mismo
   patrón que `online_max_rows()` (`spc.config`), y con **defaults = los valores históricos**
   (la salida por defecto NO cambia):

   | Constante | Variable de entorno | Default | Dominio |
   |---|---|---|---|
   | Factor del colchón (días de cobertura) | `SPC_PURCHASES_SAFETY_FACTOR` | `0.30` | PURCHASES |
   | Lead time por defecto | `SPC_INVENTORY_LEAD_TIME_DEFAULT` | `7` | INVENTORY |
   | Ventana de demanda (μ/σ) | `SPC_INVENTORY_DEMAND_WINDOW` | `28` | INVENTORY |
   | z nivel de servicio base | `SPC_INVENTORY_Z_BASE` | `1.28` | INVENTORY |
   | z nivel de servicio alto volumen | `SPC_INVENTORY_Z_HIGH_VOLUME` | `1.65` | INVENTORY |
   | Factor de respaldo (σ no estimable) | `SPC_INVENTORY_SAFETY_FALLBACK_FACTOR` | `0.5` | INVENTORY |

2. **El método de stock de seguridad es un knob de configuración por dominio**
   (`coverage_days` | `service_level`), con default = el método histórico de cada uno:

   | Knob | Variable de entorno | Default |
   |---|---|---|
   | Método de PURCHASES | `SPC_PURCHASES_SAFETY_METHOD` | `coverage_days` |
   | Método de INVENTORY | `SPC_INVENTORY_SAFETY_METHOD` | `service_level` |

   La fórmula vive en un único módulo, `spc.service.politica`, que ambos dominios comparten.
   Un **factor de cobertura puente** (`SPC_INVENTORY_COVERAGE_FACTOR`, default `0.30`) se usa
   solo si INVENTORY se conmuta a `coverage_days`, de modo que **conmutar el método deja a
   INVENTORY exactamente igual que PURCHASES** con un único cambio de variable.

### Rationale del default de INVENTORY (`service_level`)

La razón original para preferir días de cobertura era **evitar un σ inventado**. Pero el σ de
INVENTORY se calcula de la **demanda real del cliente** (media/desviación recientes del propio
histórico), así que el método `service_level` es **legítimo** y aporta más información (modula
el colchón por la variabilidad real y por el segmento de alto volumen del clustering). Por eso
se **mantiene como default** y la unificación con PURCHASES queda a **un cambio de variable de
entorno**.

> **Cómo unificar más adelante (si se alinea estrictamente con D2):** poner
> `SPC_INVENTORY_SAFETY_METHOD=coverage_days` (y, si se desea otro colchón,
> `SPC_INVENTORY_COVERAGE_FACTOR`), y actualizar la prosa de catálogo/contrato para declarar
> `coverage_days` como método por defecto de INVENTORY. No hace falta tocar código.

## Parámetro model-adjacent: nivel del cuantil de "demanda alta" (P75)

La definición `demanda_alta = sales > P75 de su familia` usaba `0.75` clavado en el adaptador.
No es política de negocio sino una **definición del modelo** (la etiqueta contra la que se
entrenó el clasificador), por lo que debe provenir de la metadata del artefacto, igual que el
`umbral` de probabilidad.

- **Caso que aplicó:** la metadata del clasificador **NO expone** el nivel como número (solo lo
  menciona en prosa en su campo `objetivo`). Por tanto **no se inventa**: se cablea la lectura
  de `meta["objetivo_cuantil"]` (que hoy no existe) con **fallback documentado `0.75`** y se
  marca como `[PENDIENTE]`.
- **Item de coordinación (Valentín / equipo de modelado):** agregar `objetivo_cuantil` (p. ej.
  `0.75`) a la metadata del clasificador en su próxima reconstrucción. La API no puede
  regenerar artefactos; en cuanto el campo exista, se leerá automáticamente sin tocar código.

## Consecuencias

- **Cumple la recomendación del docente 7:** no quedan números mágicos de política clavados;
  todos son configurables y documentados, y los parámetros del modelo siguen viniendo de la
  metadata.
- **Sin cambio de comportamiento por defecto:** con la configuración por defecto, las salidas
  de PURCHASES e INVENTORY son idénticas a las de la Fase 3.4 (verificado con tests de
  regresión).
- **Sin cambio de forma del contrato:** no se añaden ni quitan campos; la versión del contrato
  permanece en `1.0.1`. Solo cambia prosa (catálogo/contrato) y el valor reportado del supuesto
  según la configuración efectiva.
- **Riesgo acotado al cierre:** el cambio es localizado en `spc.config`, `spc.service.politica`
  y los dos servicios; el motor de ML queda intacto.
