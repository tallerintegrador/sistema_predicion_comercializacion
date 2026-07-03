# ADR-0030 — Baselines de contexto, tendencia enriquecida y coherencia de presentación

- **Estado:** Aceptado
- **Fecha:** 2026-07-03
- **Rama:** `feature/entrega-final`
- **Relacionado:** [ADR-0028](0028-catalogo-consultas-predefinidas.md) (catálogo v3),
  [ADR-0029](0029-presentacion-honesta-resultados.md) (presentación honesta)

## Contexto

Una segunda ronda de evaluación con la clienta pidió: (A1) que el Paso 1 explique los análisis
y en el mismo orden que los resultados; (A2) resolver la incoherencia "clasificación = sí/no"
frente a la consulta multiclase de canal; (A3) enriquecer la sección Tendencia; (B1) mejorar dos
regresiones débiles por anti-fuga; (B2) contextualizar las métricas con un baseline, ampliar
modelos y evitar clusters de 1 elemento; (B3) justificar todas las visualizaciones; (B4) corregir
el género de los nombres de segmento; (B5/B6) dos sectores y coherencia temporal. La autoevaluación
además detectó que **ALM-C1 y ALM-C2 usaban la misma condición** (etiquetas duplicadas).

## Decisión

Todo lo de ML se resuelve en el **motor**/**catálogo**; la API lo expone; el frontend solo muestra.

- **Baseline de contexto (B2):** el motor añade **siempre** un baseline (`DummyRegressor(median)` /
  `DummyClassifier(prior)`) que compite en VALID y aparece en la tabla de comparación. Si el
  baseline gana, es una señal honesta de que el modelo no aporta.
- **Más modelos (B2):** candidatos desde el catálogo — `extra_trees` (regresión) y
  `hist_gradient_boosting` (clasificación) se suman a los existentes.
- **Objetivo en log (B1/B2):** `transform_objetivo: log` por consulta (COM-R3 costo, VEN-R2
  ingreso). El motor entrena en `log1p(y)` e invierte con `expm1`; la métrica se calcula en la
  escala real. Estabiliza objetivos sesgados/heterocedásticos.
- **Clustering (B2):** compiten `kmeans` y `agglomerative`; se **descartan** particiones con algún
  grupo de menos de `umbrales_calidad.min_miembros_cluster` (evita "Clase A: 1 elemento"). Fallback
  sin la restricción solo si ninguna partición válida existe (pocas entidades).
- **Nombres de segmento (B4):** formato neutro de género `"{Variable}: alto/medio/bajo"`.
- **Tendencia enriquecida (A3):** el motor devuelve `horizonte` (del catálogo,
  `tendencia.horizonte_dias`), `resumen` (proyección, variación %, dirección) y `desgloses` por
  categoría (para filtrar). La API añade `horizon`, `summary`, `breakdowns` a `TrendAnalysis`; el
  frontend muestra el horizonte, una franja sombreada para el pronóstico, tarjetas de resumen, un
  filtro por categoría y una frase "cómo leer".
- **ALM-C1 ≠ ALM-C2:** C1 = quiebre inminente durante el lead time
  (`stock_actual < demanda_diaria_promedio × tiempo_reposicion_dias`); C2 = por debajo del
  **stock mínimo de seguridad** (`stock_actual < stock_minimo`, con `stock_minimo` = 1.5× demanda
  del lead time en los datos). Ya no son la misma etiqueta.
- **Coherencia de Paso 1 (A1) y vocabulario multiclase (A2):** una **fuente única** en el frontend
  (`data/tiposReporte.ts`) ordena el listado del Paso 1 y las secciones de resultados
  (Predicción → Alerta → Segmento) y describe cada tipo. La leyenda pasa a "clasificación (sí/no o
  categoría)" y la tarjeta multiclase aclara que "elige una categoría".
- **Justificación de gráficos (B3):** frase "cómo leer esto" en dona, barras y mapa PCA.
- **Datos (B1/B6):** el generador refuerza el ticket por canal (VEN-R2) y el tamaño de pedido por
  proveedor/categoría (COM-R3), da `stock_minimo` de seguridad, y muestrea Almacén en toda la
  ventana (misma densidad de fechas que Ventas/Compras). Dos sectores (minimarket, ferretería).

## Consecuencias

- **A favor:** métricas contextualizadas contra baseline (honestidad), clustering sin grupos
  triviales, tendencia con valor de negocio, Paso 1 coherente con los resultados desde una sola
  fuente, y dos alertas de almacén realmente distintas. Mejoras medidas: VEN-C2 F1 0.38→0.83,
  VEN-R2 ~0.58→0.37, COM-R3 ~0.35→0.32 (con log), sin clusters de 1 elemento.
- **Contrato (aditivo):** `TrendAnalysis.horizon/summary/breakdowns`.
- **Costo:** más candidatos → el análisis tarda algo más (aceptable).
- **En contra / honestidad:** VEN-R2 y COM-R3 siguen limitados (>30% WAPE) por el anti-fuga; se
  reportan con nota honesta (no se fingen buenos). ALM-C1/C2/C3 dan ~1.0 por regla determinística
  (documentado); ahora sí entrenables y distintos.

## Alternativas descartadas

- **Reemplazar VEN-C2 por una binaria** (Opción B): se descartó para conservar la única consulta
  multiclase del profesor; se ajustó el vocabulario en su lugar.
- **Cambiar los objetivos de VEN-R2/COM-R3** a algo trivialmente predecible: se prefirió reforzar
  los datos + log y mantener el objetivo del catálogo, con nota honesta si sigue limitado.
