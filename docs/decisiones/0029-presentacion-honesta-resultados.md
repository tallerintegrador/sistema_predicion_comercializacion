# ADR-0029 — Presentación honesta de resultados v3 (magnitudes, notas, segmentos, validación)

- **Estado:** Aceptado
- **Fecha:** 2026-07-03
- **Rama:** `feature/entrega-final`
- **Relacionado:** [ADR-0028](0028-catalogo-consultas-predefinidas.md) (catálogo v3 y contrato en inglés)

## Contexto

Una auditoría funcional/UX detectó que la vista de resultados presentaba números
engañosos o confusos, pese a que el motor era correcto:

- El recuadro resumen **sumaba siempre**, produciendo imposibles (cumplimiento 456.6%,
  días de entrega 6 987, rotación 12 522): sumar un porcentaje, una duración o un índice no
  tiene sentido.
- No se avisaba cuando una métrica era **fácil por baja varianza** (objetivo casi constante),
  ni cuando un clasificador era **degenerado** (predice una sola clase para todos).
- Los **segmentos** reutilizaban "Volumen alto/bajo" aunque el cluster no fuera de volumen, y
  listaban miembros como `fecha·PROV-01` (poco legible).
- La carga no daba **retroalimentación** (qué columnas se reconocieron, qué filas se
  descartaron).

## Decisión

Se resuelve todo en el **motor** (o el catálogo) y la API lo expone; el frontend solo muestra.

- **Magnitud por objetivo (A2):** el catálogo declara `magnitud_por_objetivo`
  (extensiva = flujo acumulable → SUMA; intensiva = tasa/nivel/ratio → PROMEDIO). El motor
  calcula el recuadro (`result… summary = {aggregation, value, label, unit, magnitude}`) y el
  frontend lo muestra. Ninguna intensiva se suma; "cumplimiento" ya no supera 100%.
- **Nota de métrica fácil (A4):** si el coeficiente de variación del objetivo de regresión es
  menor que `umbrales_calidad.cv_objetivo_facil`, se adjunta una `technical_note` honesta
  (mismo espíritu que la nota de etiqueta casi determinística de clasificación).
- **Clasificador degenerado (A5):** si en el conjunto de prueba se predice una sola clase para
  todos, se emite un `warning` ("alerta poco informativa: … no discrimina"), consistente con
  el caso de una sola clase en entrenamiento que ya existía.
- **Nombre de segmento por variable dominante (A6):** `estilo_etiqueta: auto` calcula la
  variable que **más separa** los grupos (mayor eta² entre-clusters/total) y nombra
  "{Variable} alta/media/baja". Se conservan las taxonomías de negocio `abc` (ABC de inventario)
  y `servicio` (proveedores). Los miembros usan id legible (nombre de producto/tienda/proveedor;
  las órdenes se muestran como "Proveedor (fecha)").
- **Retroalimentación de carga (A8):** la respuesta incluye `dataset_info`
  (`recognized_columns`, `missing_columns`, `rows_received`, `rows_discarded`).
- **Umbral de magnitud/varianza en el catálogo:** nada de esto se hard-codea en el frontend
  ni en el motor; los knobs viven en `consultas.yaml` (`magnitud_por_objetivo`,
  `umbrales_calidad.cv_objetivo_facil`).

## Datos de ejemplo con señal causal

En paralelo se reemplazaron los datasets de ejemplo por unos **con relaciones causales reales**
(`scripts/generar_datos_pymes_ricos.py`, reproducible): elasticidad precio→demanda negativa,
efecto de promoción/calendario, canal balanceado, cumplimiento con varianza, sobrestock/quiebre
existentes y ≥ 6 zonas. Metas verificadas por el propio script (corr negativa, WAPE de ventas
~15–25%, día pico ~25%, σ cumplimiento ≥ 0.10, sobrestock ~11%, quiebre ~16%).

## Consecuencias

- **A favor:** los números dejan de mentir; las notas y avisos son consistentes en los 3
  módulos y **testeables a nivel de API** (A12); el clustering nombra por criterio real; la
  carga da feedback. La honestidad sigue por encima de lo impresionante (señal débil se sigue
  reportando como tal).
- **Contrato (aditivo, no rompe):** `QueryReport.summary` y `ModuleResponse.dataset_info`
  nuevos y opcionales.

## Alternativas descartadas

- **Calcular la suma/promedio en el frontend** leyendo un flag: rompe "el frontend solo
  muestra"; se prefiere que la API entregue el recuadro ya resuelto.
- **Etiquetas de segmento fijas por estilo:** se mantienen solo para taxonomías de negocio
  (abc/servicio); el resto se deriva de la variable dominante.
