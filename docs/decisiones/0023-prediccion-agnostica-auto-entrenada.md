# ADR-0023 — Predicción agnóstica auto-entrenada (esquema declarado por el cliente)

- **Estado:** Aceptado
- **Fecha:** 2026-06-26
- **Relacionado:** [ADR-0007](0007-capa-api-fase3.md) (capa API), [ADR-0010](0010-politica-inventario-stock.md) (política de stock), [ADR-0011](0011-persistencia-corpus-incremental.md) (corpus), [ADR-0013](0013-entrenamiento-por-cliente-bajo-demanda.md) (entrenamiento por cliente)

## Contexto

El contrato retail (sección 3, `comunes.HistoricoItem`) es **fijo**: el cliente mapea su
vocabulario a `store_id`, `product_id`, `units_sold`, `on_promotion`, `transactions`. Todo
el feature engineering (`spc.features.temporales`) y el motor (`regresion`/`clasificacion`)
están clavados a ese esquema: rezagos de `sales`, calendario, categóricas
`store_nbr`/`family`/`type`/`city`/`state`/`cluster`, macro del petróleo. Un cliente de otro
rubro (con otras columnas relevantes: temperatura, reservas, turno, canal, etc.) **no puede
aportar esas señales**: el adaptador las descarta y el modelo congelado nunca las ve.

Se necesita que el sistema sea **agnóstico al rubro**: que el cliente declare *su* esquema
(qué columna es el objetivo, la fecha, las series y qué features extra trae) y que el sistema
**entrene el algoritmo ganador sobre esa data** y prediga/mejore, sin reentrenar el motor a
mano por cada sector.

## Decisión

Se añade un **contrato agnóstico paralelo** bajo `/auto/{sales,inventory,purchases}` que
**convive** con el retail sin tocarlo (degrada con elegancia; el camino congelado queda
intacto byte a byte).

1. **Esquema declarado** (`SchemaSpec`): el request lleva `schema` + `rows` (columnas
   arbitrarias). El esquema declara `target`, `date`, `series_keys[]` y `features[]`, cada
   feature con `type` (`numeric`/`categorical`) y `known_future` (si su valor del período a
   predecir se conoce — calendario/promoción planificada — o solo se conoce a posteriori —
   tráfico/reservas —, en cuyo caso solo se usan sus rezagos para evitar la fuga).

2. **Motor de features genérico** (`spc.features.generico`): generaliza `temporales` a
   nombres de columna arbitrarios. Misma **regla de oro contra la fuga**: todo rezago/ventana
   se agrupa por serie y se `shift`-ea antes de cualquier ventana; el objetivo del período
   actual **nunca** es feature.

3. **AutoML genérico** (`spc.models.automl`): **reutiliza el mismo zoo y la misma selección
   honesta** del motor retail (no se reimplementan algoritmos). Parte la historia en
   train/valid/test temporal (ventanas adaptativas a la historia disponible, como ADR-0013),
   **elige el ganador en VALID**, opcionalmente combina los mejores boosters en un ensemble,
   reporta la métrica honesta de TEST con **pronóstico recursivo** (WAPE) y reajusta el
   ganador sobre toda la historia. La métrica de TEST se calcula con un modelo entrenado
   **solo con datos previos a la ventana TEST** (no con el artefacto reajustado sobre toda la
   historia): de lo contrario un modelo de alta capacidad memoriza la ventana y reporta una
   métrica falsamente perfecta (ver «Corrección 2026» más abajo). Para clasificación reutiliza
   las estrategias de desbalance y la selección de umbral de `clasificacion`.

4. **Entrenar-y-predecir en una llamada**: el endpoint entrena al vuelo y responde con el
   pronóstico **y** el resumen honesto (`training`: algoritmo ganador, métricas de prueba,
   candidatos). Es la semántica "auto-aprende y predice".

5. **Caché por (cliente, esquema, datos)** (`spc.service.cache_agnostico`): reentrenar el zoo
   en cada petición es caro, así que el predictor se cachea (memoria + disco) y se **reusa**
   si vuelve la misma data con el mismo esquema. **Si la data cambia, la firma cambia y el
   modelo se reentrena solo** — ese es el "auto-aprendizaje": el sistema aprende cuando hay
   datos nuevos. El disco guarda un artefacto por (cliente, dominio, esquema), de modo que la
   data nueva lo sobreescribe y el almacén no crece sin control. Conviven con los artefactos
   por cliente del ADR-0013 sin pisarse (subcarpeta `agnostico/`).

6. **Dominios**: VENTAS (regresión recursiva multi-horizonte), ALMACÉN (deriva
   `demanda_alta = target > P{q}` de la **propia serie**, clasifica, y aplica la política de
   stock de ADR-0010; el segmento se calcula por volumen de la serie, sin el clustering
   retail), COMPRAS (reposición sobre el pronóstico genérico). La política y sus constantes se
   leen de `spc.config` (no se clavan).

## Consecuencias

**A favor**
- El sistema sirve a **cualquier rubro** sin reentrenar el motor a mano: el cliente declara
  su esquema y trae sus columnas.
- Se reutiliza todo el rigor ya construido (zoo ganador, validación temporal sin fuga,
  selección honesta, ensemble, política de stock); no hay un segundo motor que mantener.
- El contrato retail y el modelo congelado **no se tocan**: cero regresión (toda la suite
  previa pasa).

**En contra / límites honestos**
- El pronóstico recursivo y los rezagos **requieren `date` + `series_keys`**; sin fecha el
  modo es tabular (sin horizonte que proyectar).
- **Entrenar por petición es más pesado** que servir un congelado; la caché por firma de
  datos lo amortiza, pero la primera llamada con data nueva entrena el zoo.
- El *cold-start* de un cliente con poca historia degrada (ventanas cortas, menos señal),
  igual que en ADR-0013; la métrica honesta de TEST lo refleja sin maquillarlo.
- Las features `known_future` del horizonte que el cliente no provea se asumen neutras
  (numéricas a 0, categóricas arrastradas del último valor).

## Alternativas descartadas

- **Esquema fijo + columnas extra**: menos disruptivo pero seguiría imponiendo `date`/serie/
  target retail; no es realmente agnóstico.
- **Entrenar aparte y servir después** (como ADR-0013): más controlado, pero el pedido era
  explícito de "auto-aprende y predice en una llamada".
- **Reescribir `temporales`/`regresion` parametrizando el esquema**: alto riesgo de regresión
  sobre el congelado; se prefirió un camino paralelo que reutiliza las piezas estables.

## Corrección 2026 — fuga en la métrica de TEST de regresión

Al enriquecer los ejemplos (rubro retail con proveedor, 17 features) el ganador pasó de
`Ridge` a boosters (`LightGBM`/ensemble) y el WAPE de TEST reportado cayó a ~1-2 % con
R²≈0.999 — imposible siendo el ruido irreducible de los datos ~15-20 % (un baseline
naive(t-7) daba ~44 %). Causa: `entrenar_regresion` calculaba la métrica de TEST con el
**predictor reajustado sobre TODA la historia**, que ya había visto la ventana TEST; los
modelos de alta capacidad la memorizaban. (La ruta de clasificación no tenía el defecto:
ya evaluaba con un modelo entrenado solo en train.)

**Arreglo:** la métrica de TEST se calcula con un modelo de la **misma arquitectura ganadora**
entrenado **solo con datos anteriores a `test_ini`**; el artefacto servido se mantiene
reajustado sobre toda la historia (más datos = mejor predicción en producción). Tras el
arreglo, sobre los ejemplos: WAPE≈18 %, R²≈0.76 (creíble). Guarda de regresión:
`tests/test_automl_no_fuga.py`.

## Enriquecimiento 2026 — ejemplos multi-país (40 features)

Para demostrar el agnosticismo de verdad (la empresa puede operar en cualquier país), los tres
ejemplos `/auto/*` se regeneraron con un mundo **multi-país** (Perú, Bolivia, España, México):
8 almacenes × 5 SKUs = **40 series**, 150 días, y el esquema pasó de **17 a 40 features** en
cuatro familias —comerciales/calendario, macro/país, atributos de producto e inventario/almacén—
todas cableadas con correlación real a la demanda (estacionalidad por **hemisferio**, feriados y
día de pago locales, moneda + tipo de cambio, simulación de stock por serie). El generador se
versionó en [`examples/api/generar_auto_retail.py`](../../examples/api/generar_auto_retail.py)
(antes vivía fuera del repo; semilla 42, reproducible).

**Resultado honesto (no se maquilla).** Ampliar de 17 a 40 features **no mejora el WAPE de TEST**
(A/B sobre las mismas filas: 16.35 % con 17 vs 16.46 % con 40; diferencia dentro del ruido). El
piso de ruido del generador (σ=0.12 lognormal ≈ WAPE ~13 %) ya lo alcanzan los rezagos + precio +
promo + calendario, y muchas columnas nuevas son **colineales** con ellos (`pais`↔serie `almacen`,
`temporada`↔mes/temperatura, `dia_pago_local`↔`g_is_payday`). No es un defecto: ML correcto, las
features redundantes no suman. Lo que el cambio sí aporta y queda verificado: (1) cobertura
agnóstica real (4 países, 40 campos de almacén), (2) **leak-safe** y **sin degradar** la métrica
con 40 columnas (no hay fuga ni colapso), (3) las solo-pasado de inventario **se usan** —la media
móvil de `recepciones` queda entre las 10 features más importantes del modelo. Sobre datos reales
con menos ruido irreducible, el margen de mejora de estas columnas sería mayor.
