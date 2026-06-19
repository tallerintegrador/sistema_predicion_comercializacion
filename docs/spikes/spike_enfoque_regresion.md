# Spike — Definir enfoque del modelo de regresión inicial (VENTAS)

> Documento vivo. Spike de **decisión** (cerrado). Vive en `docs/spikes/spike_enfoque_regresion.md`.
> **Formaliza, a posteriori, una decisión ya tomada y ejecutada** en la Fase 2a: el enfoque del
> modelo de regresión inicial de SPC (artefacto `regresion_v3`). No entrena ni re-ejecuta nada
> sobre datos crudos (`data/raw/` está en `.gitignore` y no está disponible en este entorno);
> razona sobre los hallazgos persistidos en `docs/reporte_eda.md`, `docs/reporte_regresion_2a.md`,
> los ADR `0002`–`0004`, el meta `models/regresion_v3.meta.json` y las métricas de
> `data/processed/`. Todo número proviene de esos documentos; lo que no esté soportado se marca
> como `[PENDIENTE / verificar en máquina con GPU y dataset]`.

---

## 1. Encabezado / metadatos

| Campo | Valor |
|---|---|
| **ID del spike** | `SPK-REG-001` |
| **Título** | Definir enfoque del modelo de regresión inicial |
| **Autor/a** | Camila L. Moreno Quevedo (equipo SPC) |
| **Fecha (redacción del spike)** | 2026-06-16 |
| **Time-box (investigación de la 2a)** | ≈ 2–3 días-persona (2026-06-13 → 2026-06-14, ventana de los ADR `0002`→`0004`) `[estimado; verificar bitácora de Fase 2a]` |
| **Estado** | **Cerrado** (decisión tomada, ejecutada y auditada; artefacto `regresion_v3` en producción de Fase 3) |
| **Fase relacionada** | **Fase 2a — Regresión (VENTAS)**; insumo directo de la Fase 3 (API) |
| **Tipo de spike** | Spike de **decisión de arquitectura de modelo** (*technical/decision spike*) |
| **Decisión abierta que cierra** | Plan Maestro §"Anexo — Decisiones abiertas", punto 1: *"Modelo de regresión inicial: ¿baseline + LightGBM/XGBoost, o también un lineal explícito para contraste?"* |
| **ADR de respaldo** | `0002` (selección inicial), `0003` (cierre), **`0004` (cierre definitivo tras auditoría)** |
| **Fuentes base** | `docs/plan_maestro_spc.md`, `docs/reporte_eda.md`, `docs/contrato_datos.md`, `docs/reporte_regresion_2a.md`, `docs/auditoria_fase2a.md`, ADR `0002`–`0004` |
| **Artefactos de respaldo** | `models/regresion_v3.{joblib,meta.json}`, `data/processed/metricas_regresion_2a.{csv,json}`, `data/processed/importancias_regresion_2a.csv` |

---

## 2. Contexto y motivación

SPC (Sistema Predictivo de Comercialización) es un **motor de previsión ofrecido como servicio
(API)** para PYMEs, **agnóstico al sector** y estructurado en tres campos con separación estricta
de capas (`api → service → motor`): **VENTAS** (regresión), **COMPRAS** (derivado del pronóstico)
y **ALMACÉN** (clasificación + clustering). El campo VENTAS es la pieza central: COMPRAS deriva su
recomendación de reposición del pronóstico de ventas y ALMACÉN usa un proxy de demanda para el
stock, de modo que **la calidad del modelo de regresión condiciona a los otros dos campos**.

La necesidad de negocio que resuelve es concreta: pronosticar las **`unidades_vendidas`** del
contrato de VENTAS por `(fecha, punto_venta_id, producto_id)` a un horizonte configurable, para
que una PYME sin capacidad predictiva pueda anticipar su demanda (ver `docs/contrato_datos.md` §3).

El Plan Maestro dejó esta decisión **explícitamente abierta** para validación
(`docs/plan_maestro_spc.md`, "Anexo — Decisiones abiertas", punto 1):

> *"Modelo de regresión inicial: ¿partimos de un baseline + LightGBM/XGBoost, o exiges también un
> lineal explícito para contraste? (Sugiero ambos: lineal como referencia, boosting como modelo de
> producción.)"*

La decisión estaba abierta porque tres restricciones del proyecto tiran en direcciones distintas y
había que reconciliarlas antes de comprometer la arquitectura del motor:

1. **Naturaleza de la data** (del EDA): objetivo muy asimétrico (asimetría 7.36), **inflado de
   ceros (31.30 %)** y con **estructura temporal** (tendencia + estacionalidad). No es una
   regresión tabular cualquiera: es un pronóstico de serie de tiempo intermitente.
2. **Producto sector-agnóstico y multi-serie:** el motor debe servir a cualquier rubro sobre el
   contrato genérico, y el dataset de validación tiene **54 tiendas × 33 familias ≈ 1 782 series**.
   El enfoque debe escalar a "muchas series" sin un modelo artesanal por cada una.
3. **Disciplina metodológica exigida:** validación temporal sin fuga de futuro, comparación honesta
   contra baseline y artefacto portable/reproducible que la API solo cargue y prediga.

Este spike **formaliza** la investigación que resolvió esa tensión: qué se preguntó, qué
alternativas se sopesaron y por qué se eligió el enfoque adoptado (`regresion_v3`), dejando rastro
trazable a su ADR. El trabajo de modelado **ya está hecho**; este documento es el cierre
metodológico de la decisión, apto a nivel académico.

---

## 3. Pregunta del spike

**Pregunta principal**

> Dado el EDA (zero-inflation, asimetría, serie temporal) y el contrato de datos (pronóstico de
> `unidades_vendidas`, sector-agnóstico, multi-serie), **¿qué familia de modelo, qué tratamiento
> del objetivo y qué estrategia de validación adoptar como enfoque inicial de la regresión de
> VENTAS**, de modo que supere a un baseline honesto y deje un artefacto portable y reproducible?

**Sub-preguntas acotadas**

1. **Familia de modelo.** ¿Baseline, lineal/regularizado, series clásicas (ARIMA/SARIMA, Prophet)
   o *gradient boosting*? ¿Y, en boosting, **un modelo global** o **un modelo por serie**?
2. **Tratamiento del objetivo.** ¿`log1p` por la asimetría? ¿Hace falta un enfoque
   *two-stage / hurdle / zero-inflated* por el 31 % de ceros?
3. **Estrategia multi-horizonte.** ¿Pronóstico **recursivo** (autorregresivo) o **directo** (un
   modelo por paso)?
4. **Validación.** ¿Cómo particionar sin fuga de futuro y qué métrica reportar para que sea
   **honesta** y comparable contra baseline?

Un spike sin pregunta acotada no es un spike: la pregunta principal es el **gate de enfoque** de la
Fase 2a; las sub-preguntas son los ejes de decisión que debían cerrarse para tener un artefacto de
producción.

---

## 4. Alcance

**Dentro de alcance**

- **Familia de modelo** para la regresión de VENTAS y su criterio de elección.
- **Tratamiento del objetivo** (`log1p`, objetivos Tweedie/Poisson, no-negatividad).
- **Estrategia de validación temporal** (partición sin fuga, selección en VALID, TEST una vez) y
  **definición de la métrica** (WAPE recursivo honesto).
- **Baseline** de comparación como piso obligatorio.
- **Estrategia multi-horizonte** (recursiva vs directa) como parte del enfoque.

**Fuera de alcance (explícito)**

- **Tuning exhaustivo de hiperparámetros.** Aquí se decide el *enfoque*; la búsqueda fina de
  hiperparámetros no es objeto de este spike.
- **Despliegue / capa API.** La carga y el servicio del artefacto son Fase 3 (ADR `0007`).
- **Intervalos de predicción.** Es una **decisión abierta separada** (Plan Maestro, anexo, punto 3;
  diferida desde la Fase 2 en los ADR `0003`/`0004`). Aquí solo se menciona como **próximo paso**,
  no se resuelve.
- **Re-entrenamiento sobre datos crudos.** `data/raw/` está gitignored; este documento sintetiza lo
  ya calculado y **no re-ejecuta** entrenamiento (que depende de GPU y del crudo).

---

## 5. Supuestos

1. **Validación técnica, no de usuario.** Se asume que *Store Sales — Corporación Favorita* es
   representativa suficiente para validar el motor (Plan Maestro §6); el origen real/sintético de
   los datos no altera el funcionamiento del enfoque.
2. **Granularidad diaria** a nivel `(fecha, store_nbr, family)`; semanal/mensual se obtienen por
   agregación. La granularidad de producto es **familia**, no SKU individual.
3. **Entrenamiento offline y periódico.** El motor entrena fuera de línea (con GPU disponible) y
   produce un artefacto serializado; **en producción la API solo carga y predice**, sin reentrenar
   en caliente (Plan Maestro §2).
4. **Reproducibilidad de extremo a extremo:** mismos datos + mismo código + mismo entorno → mismos
   artefactos y métricas (salvo ruido numérico mínimo de GPU; ADR `0004` §7).
5. **El contrato manda sobre la implementación:** el enfoque se ajusta al contrato genérico (devolver
   **unidades**), no al revés. La escala interna (`log1p`) no se filtra al cliente más allá del
   metadato `transformacion_interna`.
6. **Los hallazgos del EDA son válidos** (asimetría, ceros, señal, estructura temporal) y se toman
   como insumo cerrado de la Fase 1 (ver `docs/spikes/spike_eda.md`).

---

## 6. Criterios de decisión

Propiedades exigidas al enfoque, derivadas del EDA y del producto. Son los criterios contra los que
se midió cada opción (§7) y que el enfoque elegido debe satisfacer (§9):

| # | Criterio | Origen | Por qué importa |
|---|---|---|---|
| **C1** | **Manejo de la inflación de ceros** (31.30 % de `sales` = 0) | EDA §3 | Un modelo que ignore los ceros sesga el pronóstico y rompe métricas relativas (MAPE). |
| **C2** | **Manejo de la asimetría del objetivo** (asimetría 7.36; cola larga, máx 124 717) | EDA §3 | Sin tratar la escala, la pérdida la dominan unas pocas series enormes. |
| **C3** | **Compatibilidad sector-agnóstica y multi-serie** (≈ 1 782 series; cualquier rubro) | Contrato + EDA §4 | El enfoque debe escalar a "muchas series" y a clientes nuevos sin un modelo artesanal por serie. |
| **C4** | **Ausencia de fuga temporal** (tendencia + estacionalidad; separación `train/test` limpia) | EDA §5 | Una fuga de futuro infla la métrica y produce un modelo inútil en producción. |
| **C5** | **Portabilidad / reproducibilidad del artefacto** | Plan Maestro §2; ADR `0004` | La API solo carga y predice: el `.joblib` debe cargar desde un proceso limpio, sin GPU, de forma determinista. |
| **C6** | **Métrica de error honesta y comparable contra baseline** | Plan Maestro §4; ADR `0004` | El gate del proyecto es "supera al baseline" con una métrica que no se infle a sí misma. |

---

## 7. Opciones consideradas

Núcleo del spike de decisión. Para cada opción: descripción, pros, contras y veredicto (aceptada /
descartada / adoptada como componente). Las opciones que **se probaron empíricamente** lo indican
con sus números; las que se **descartaron por razonamiento de diseño** (no se ejecutaron) se marcan
como tales, por honestidad metodológica.

### 7.1 Baseline — naïve / naïve estacional / media móvil *(piso de comparación)*

- **Descripción.** Modelos triviales sin aprendizaje: `naïve` estacional (predice `t-7`, capturando
  el ciclo semanal) y media móvil de 7 días. No son candidatos a producción; son el **piso
  obligatorio** que cualquier modelo debe batir (Plan Maestro §"Fase 2 → 2a").
- **Pros.** Cero costo, interpretables, robustos; definen el listón objetivo; capturan algo de la
  estacionalidad semanal del EDA.
- **Contras.** No usan promoción, calendario, transacciones ni relaciones entre series; techo de
  precisión bajo.
- **Veredicto: ACEPTADO como baseline (no como producción).** Se mantienen como referencia
  permanente. Evaluados con el **mismo** protocolo recursivo honesto que el modelo final: mejor
  baseline = `naïve(t-7)` recursivo con **WAPE 20.67 % · MAE 96.54 · RMSE 348.38**
  (`metricas_test_recursivo_baseline`, meta `regresion_v3`).

### 7.2 Modelos lineales / regularizados (Regresión lineal, Ridge/Lasso)

- **Descripción.** Modelo lineal sobre las features (con regularización L2/L1). El Plan Maestro pedía
  un lineal "explícito para contraste" como referencia interpretable.
- **Pros.** Interpretable (coeficientes), rápido, sirve como contraste y *sanity check*.
- **Contras.** No modela bien interacciones ni no-linealidades; sufre con categóricas de **alta
  cardinalidad** (`family` 33, `store_nbr` 54) si se codifican mal; al invertir `log1p` con `expm1`
  amplifica errores en la cola (predicciones extremas).
- **Veredicto: PROBADO y DESCARTADO de producción; conservado como referencia.** El primer montaje
  (categóricas pasadas como enteros ordinales) dio resultados absurdos (MAE 2408, R² negativo;
  ADR `0002`). Rehecho dentro de un **pipeline propio** (`OneHotEncoder` + `StandardScaler` +
  imputación + recorte de `expm1`) mejoró sustancialmente, **pero siguió muy por encima del peor
  baseline (~100)** y se **retiró de las tablas** del reporte (ADR `0003` §1; `docs/reporte_regresion_2a.md`).
  Cumple "lineal como referencia" del Plan Maestro, no "lineal como producción".

  > **⚠ Inconsistencia documental detectada (declarada, no silenciada).** El número del Ridge
  > corregido difiere entre fuentes: el ADR `0003` reporta `MAE ≈ 1123` y el
  > `docs/reporte_regresion_2a.md` reporta `MAE(test) = 743.72`. Ambos coinciden en la **conclusión**
  > (el lineal queda muy por encima del baseline ~100 y se retira), pero el valor exacto debe
  > **unificarse** en una pasada de mantenimiento. `[PENDIENTE / verificar en máquina con dataset]`

### 7.3 Modelos clásicos de series de tiempo (ARIMA/SARIMA, Prophet)

- **Descripción.** Modelos univariados por serie: ARIMA/SARIMA (autorregresivos + estacionalidad) y
  Prophet (descomposición tendencia + estacionalidad + feriados).
- **Pros.** Diseñados para series temporales; modelan estacionalidad y tendencia de forma explícita;
  Prophet incorpora feriados y es robusto a huecos.
- **Contras (decisivos para este producto).**
  - **No encajan con el escenario multi-serie:** exigirían **un modelo por cada una de las ≈ 1 782
    series** `(tienda × familia)` —y reentrenar uno nuevo por cada serie de cada cliente—, lo que
    rompe la portabilidad de "un artefacto que la API carga y predice" (C3, C5).
  - **No aprovechan señal cruzada ni exógena de forma natural:** la **promoción** (señal más fuerte
    del EDA, corr 0.43) y las transacciones entran con dificultad; no comparten aprendizaje entre
    series similares (clave para el *cold-start* de clientes nuevos).
  - **Mal ajuste a la zero-inflation:** las ≈ 1/3 de observaciones en cero y la intermitencia de
    muchas familias degradan a ARIMA gaussiano.
- **Veredicto: DESCARTADO por diseño (no probado empíricamente).** Se descartó por razonamiento
  frente a los criterios C3/C5, **no** por una corrida comparativa. Es una decisión de arquitectura,
  no un resultado de benchmark. `[PENDIENTE / verificar en máquina con dataset: un contraste
  cuantitativo ARIMA/Prophet vs boosting queda como validación opcional, no bloqueante.]`

### 7.4 Gradient boosting sobre features (LightGBM / XGBoost) — global vs por serie

- **Descripción.** Ensembles de árboles por *boosting* sobre una matriz de features (rezagos,
  ventanas móviles, promoción, calendario, categóricas). Dos variantes de arquitectura:
  **(a) un modelo global** entrenado sobre todas las series a la vez, con `store_nbr`/`family` como
  categóricas; **(b) un modelo por serie**.
- **Pros.** Capturan no-linealidades e interacciones; **toleran de forma nativa la alta cardinalidad**
  de `family`/`store_nbr`; ingieren todas las features exógenas (promo, transacciones rezagadas,
  calendario, petróleo); admiten **objetivos Tweedie/Poisson** que modelan masa en cero y
  no-negatividad (C1) y predicen en unidades; entrenan en GPU y **predicen en CPU** (C5).
- **Contras.** Requieren *feature engineering* cuidadoso para no filtrar el futuro (C4); no extrapolan
  fuera del rango visto; un modelo por serie multiplicaría artefactos y mataría la portabilidad.
- **Veredicto: ACEPTADO como familia de producción, en variante GLOBAL.** El **modelo global** gana
  a "uno por serie" en C3/C5 (un único artefacto sirve a todas las series y generaliza a series/
  clientes nuevos compartiendo patrones) y es lo que refleja el feature set de
  `regresion_v3.meta.json` (`store_nbr`, `family`, `type`, `city`, `state`, `cluster` como
  categóricas). La comparación empírica (250 k filas de submuestreo) dejó a los boosters muy por
  encima de baseline y lineal; los objetivos **Tweedie/Poisson** lideran el TEST teacher-forced
  (LightGBM_Tweedie WAPE 12.41 %; ver `docs/reporte_regresion_2a.md`).

  > **Evolución del artefacto (trazabilidad de la decisión, no improvisación):** la elección se
  > refinó a lo largo de tres ADR — `regresion_v1` = XGBoost (ADR `0002`) → `regresion_v2` =
  > HistGradientBoosting, elegido por estabilidad en CV (ADR `0003`) → **`regresion_v3` = ensemble de
  > boosters**, tras mover la selección a VALID en la auditoría (ADR `0004`). Cada cambio quedó
  > registrado con su criterio.

### 7.5 Ensemble de boosters vs individual *(refinamiento dentro de 7.4)*

- **Descripción.** Combinación **convexa en unidades** de cuatro boosters
  `XGBoost + XGBoost_Tweedie + LightGBM + LightGBM_Poisson` (pesos `[0.256, 0.254, 0.250, 0.240]`)
  frente al mejor modelo **individual** (ganador por estabilidad en CV temporal: `LightGBM_Tweedie`).
- **Pros (ensemble).** Promedia sesgos de objetivos distintos (espacio log + Tweedie + Poisson);
  más robusto; **menor WAPE honesto en VALID**.
- **Contras (ensemble).** Más complejo de servir (cuatro submodelos); mayor latencia y tamaño de
  artefacto que un individual.
- **Veredicto: ADOPTADO el ensemble, por gate en VALID.** Decidido sobre **VALID** (no TEST):
  ensemble **WAPE 12.18 %** vs individual **14.25 %** (`criterio_seleccion`, meta `regresion_v3`).
  Regla explícita: si el individual hubiera ganado en VALID se habría preferido por simplicidad;
  aquí el margen del ensemble es claro y consistente (ADR `0004` §2).

### 7.6 Estrategia multi-horizonte: recursiva vs directa

- **Descripción.** Para pronosticar H pasos: **recursiva** (un modelo de un paso que reinyecta sus
  predicciones como rezagos, día a día) o **directa** (un modelo distinto entrenado por cada horizonte
  `h = 1..H`).
- **Pros recursiva.** Un solo modelo; reutiliza toda la estructura de rezagos; coherente con cómo
  predice la API en producción.
- **Contras recursiva.** **Acumula error** al reinyectar predicciones (sesgo creciente con el
  horizonte).
- **Pros directa.** Evita la acumulación de error por horizonte.
- **Contras directa.** Requiere **H modelos**; no puede usar los rezagos más recientes para horizontes
  lejanos; multiplica artefactos (choca con C5).
- **Veredicto: ADOPTADA la recursiva**, y —lección de la auditoría— **evaluada como tal** (no con
  *teacher forcing*). La acumulación de error se asume y se mide: por eso el WAPE honesto recursivo
  (14.59 %) es mayor que el teacher-forced (12.40 %); el primero es el *headline* (ADR `0004` §4).

### 7.7 Tratamiento del objetivo: `log1p` y la alternativa zero-inflated / hurdle

- **Descripción.** Transformar el objetivo con **`log1p`** (asimetría) y, ortogonalmente, tratar la
  **inflación de ceros** con un enfoque **two-stage / hurdle / zero-inflated** (un clasificador
  cero-vs-positivo + un regresor sobre los positivos).
- **Pros `log1p`.** Reduce la asimetría de **7.36 → 0.41** (EDA §3); estabiliza la varianza; el `+1`
  admite ceros; se invierte con `expm1` y se recorta a 0 (las ventas no son negativas).
- **Pros two-stage/hurdle.** Modela explícitamente la masa en cero (C1); puede reducir el sesgo en
  series intermitentes.
- **Contras two-stage/hurdle.** Más complejo (dos modelos, dos umbrales); riesgo de
  sobre-ingeniería; **los objetivos Tweedie/Poisson ya absorben buena parte de la zero-inflation**
  dentro de un solo modelo.
- **Veredicto: ADOPTADO `log1p` (para los submodelos del espacio log) + objetivos Tweedie/Poisson;
  two-stage/hurdle DIFERIDO y documentado.** El predictor de producción declara
  `transformacion_objetivo = "identidad"` (combina/predice en **unidades**); los submodelos del
  espacio log entrenan en `log1p(sales)` e invierten con `expm1` antes de combinarse
  (`nota_transformacion`, meta `regresion_v3`). El enfoque *zero-inflated / two-part* queda como
  mejora diferida (ADR `0003`/`0004`; Lambert, 1992).

---

## 8. Metodología de evaluación

El protocolo es el núcleo de la honestidad del entregable y está fijado en los ADR `0002`–`0004`:

- **Partición temporal sin fuga (C4).** Cortes por fecha, espejo del horizonte real de la
  competencia (16 días):
  - **Train:** ≤ 2017-07-14 · **Valid:** 2017-07-15 .. 07-30 · **Test:** 2017-07-31 .. 08-15.
  - Más **validación cruzada temporal *expanding*** (3 folds de 14 días dentro de TRAIN+VALID, que
    **nunca toca TEST**) para medir estabilidad.
  - *Feature engineering* **leak-safe** (`spc.features.temporales`): rezagos del objetivo
    (`t-1..t-28`) y ventanas móviles **desplazadas** con `shift` antes de cualquier agregación;
    **transacciones solo como rezagos** (nunca el periodo a predecir); promoción del día (planificada,
    conocida) + rezagos; calendario/feriados; petróleo rezagado como contexto.
- **Selección en VALID; TEST una sola vez (C6).** La elección ganador-individual (por estabilidad en
  CV) y el **gate ensemble-vs-individual** se deciden sobre **VALID** con pronóstico recursivo
  honesto. **TEST se evalúa una única vez** sobre el modelo ya elegido, para el reporte final
  (`criterio_seleccion.decision_en = "valid"`). Esto corrige el bloqueante de la auditoría: antes se
  seleccionaba sobre el mismo TEST que se reportaba, lo que inflaba la métrica (ADR `0004` §1).
- **Métrica guía = WAPE recursivo (honesto), no one-step-ahead (C6).** Se reporta el **pronóstico
  recursivo multi-paso** (autorregresivo, como en producción: el modelo reinyecta sus propias
  predicciones), no el *teacher forcing* (que alimenta los rezagos con las ventas **reales** del
  horizonte y por eso **sobreestima** la precisión). El número teacher-forced se conserva solo como
  "referencia optimista" / cota superior.
- **Por qué WAPE y no MAPE.** El **MAPE (~34 %) está inflado** por el 31 % de ceros: excluye los días
  de venta cero del denominador y sobre-pondera las series de bajo volumen. El **WAPE** (error
  absoluto agregado ponderado por volumen), junto con MAE/RMSE en unidades, es la métrica fiable para
  una serie *zero-inflated* (Hyndman & Koehler, 2006). `R²` y `RMSLE` se reportan como contexto, no
  como criterio de selección.

---

## 9. Recomendación / decisión

**Enfoque adoptado (`regresion_v3`):** **modelo global de *gradient boosting*** en forma de
**ensemble convexo de boosters** `Ensemble(XGBoost + XGBoost_Tweedie + LightGBM + LightGBM_Poisson)`
(pesos `[0.256, 0.254, 0.250, 0.240]`), **predicción en unidades** con submodelos del espacio log en
`log1p` (invertidos con `expm1`), **pronóstico recursivo multi-paso**, **validación temporal sin
fuga** con selección en VALID y TEST evaluado una sola vez, sobre un **baseline** honesto.
Decisión registrada en el **ADR `0004`** (cierre definitivo tras auditoría), que actualiza los ADR
`0002` y `0003`.

**Resultado (TEST, escala de unidades, métrica guía = pronóstico recursivo honesto):**

| fuente (recursivo honesto) | WAPE | MAE | RMSE | RMSLE | R² |
|---|---|---|---|---|---|
| **Ensemble — `regresion_v3` (producción)** | **14.59 %** | **68.15** | **235.73** | 0.423 | 0.964 |
| baseline `naïve(t-7)` | 20.67 % | 96.54 | 348.38 | 0.617 | 0.922 |
| baseline `media_móvil_7` | 23.26 % | 108.66 | 359.82 | 0.531 | 0.917 |

El modelo de producción **supera al mejor baseline honesto: MAE −29.4 %, RMSE −32.3 %, WAPE −6.08
puntos.** *(Referencia teacher-forced, optimista, no es el headline: WAPE 12.40 % · MAE 57.91 ·
RMSE 202.39.)* Gate de selección en VALID: ensemble **12.18 %** vs individual `LightGBM_Tweedie`
**14.25 %** (meta `regresion_v3`).

**Tabla criterio → cómo lo cumple el enfoque elegido:**

| Criterio (§6) | Cómo lo cumple `regresion_v3` |
|---|---|
| **C1 — Inflación de ceros** | Objetivos **Tweedie/Poisson** (masa en cero + no-negatividad) dentro del ensemble; recorte de la predicción a 0 tras `expm1`; **WAPE/MAE** en vez de MAPE; *two-part* diferido y documentado. |
| **C2 — Asimetría del objetivo** | Submodelos del espacio log entrenan en **`log1p`** (asimetría 7.36 → 0.41); techo de predicción = `log1p`/unidades del máximo histórico (124 717) para acotar `expm1`. |
| **C3 — Sector-agnóstico + multi-serie** | **Un único modelo global** sobre las ≈ 1 782 series con `store_nbr`/`family`/`type`/`city`/`state`/`cluster` como **categóricas**; aprende patrones compartidos y generaliza a series/clientes nuevos (sin un modelo por serie). |
| **C4 — Sin fuga temporal** | Cortes por fecha + CV *expanding*; rezagos/ventanas con `shift`; transacciones **solo rezagadas**; **selección en VALID, TEST una vez**; tests de no-fuga (`tests/test_features_regresion.py`). |
| **C5 — Portabilidad / reproducibilidad** | Serializado **vía import** (no `__main__`); **GPU-train / CPU-predict**; semilla 42; test de carga en **proceso limpio** (`tests/test_portabilidad.py`); metadatos completos. |
| **C6 — Métrica honesta comparable** | **WAPE recursivo multi-paso** (no teacher forcing); baselines evaluados con el mismo protocolo; persistido como fila `split="test_recursivo"` en `data/processed/metricas_regresion_2a.{csv,json}`. |

---

## 10. Riesgos y limitaciones

| Riesgo / limitación | Detalle | Mitigación / estado |
|---|---|---|
| **Zero-inflation no modelada explícitamente** | El ensemble la absorbe con Tweedie/Poisson, no con un *hurdle* dedicado | Enfoque *two-part / zero-inflated* **diferido y documentado** (ADR `0003`/`0004`; Lambert, 1992) |
| **Familias intermitentes de bajo volumen** | `BOOKS`, `BABY CARE`, `HOME APPLIANCES`, `HARDWARE`: **WAPE altísimo** en el desglose (p. ej. BOOKS 1997 %) pero **MAE trivial** (fracciones de unidad) | No afecta el WAPE agregado (ponderado por volumen) ni al negocio; se trataría con *two-part* o métodos de demanda intermitente (Croston, 1972) |
| **Acumulación de error recursivo** | El pronóstico autorregresivo arrastra error a horizontes largos | Asumida y **medida** (WAPE honesto 14.59 % vs teacher-forced 12.40 %); estrategia directa diferida |
| **No extrapola fuera del rango** | Los árboles no predicen valores nunca vistos | Aceptable en demanda acotada; techo de predicción documentado |
| **Cold-start de clientes nuevos** | Poco histórico ⇒ rezagos pobres | El modelo **global** comparte patrones entre series; *fallback* a baseline/segmento (Plan Maestro §6); contrato exige histórico mínimo |
| **Dependencia de GPU para entrenar** | El entrenamiento usa XGBoost `cuda` / LightGBM `gpu` | El **artefacto predice en CPU** (portable); solo el (re)entrenamiento offline necesita GPU |
| **Composición del ensemble sensible al submuestreo** | El `top-k` por MAE en VALID cambió entre corridas (250 k vs `--full`) | Esperado; **confirmar composición exacta con corrida `--full`** queda como próximo paso |
| **Inconsistencia documental (Ridge)** | `MAE ≈ 1123` (ADR `0003`) vs `743.72` (reporte 2a) | Declarada en §7.2; unificar en mantenimiento `[PENDIENTE]` |
| **Deriva del ejemplo de contrato** | `docs/contrato_datos.md` y Plan Maestro §3.1 muestran `"modelo": "regresion_v1"` en el JSON de ejemplo (hoy `regresion_v3`) | Deriva menor de documentación; actualizar el ejemplo `[PENDIENTE / cosmético]` |
| **Spike no re-ejecutado aquí** | `data/raw/` gitignored; sin GPU en este entorno | Síntesis sobre cifras persistidas; reproducible vía `scripts/train_regresion.py` |
| **Time-box estimado** | Duración exacta de la 2a no registrada | `[estimado; verificar bitácora de Fase 2a]` |

---

## 11. Preguntas abiertas / próximos pasos

1. **Confirmar la composición exacta del ensemble** con una corrida `--full` (todo el histórico, no
   submuestreo de 250 k) y **verificar la reproducibilidad en máquina con GPU y dataset**: pesos y
   miembros pueden variar ligeramente con el volumen. `[PENDIENTE / verificar en máquina con GPU y
   dataset]`
2. **Intervalos de predicción** (`intervalo_80` del contrato): cuantiles de boosting
   (`quantile`/`pinball`) o residuos empíricos del holdout. **Decisión abierta separada**, diferida
   desde la Fase 2 (Plan Maestro anexo punto 3; ADR `0003`/`0004`). `[PENDIENTE]`
3. **Enfoque zero-inflated / two-part:** clasificar cero-vs-positivo y regredir solo los positivos;
   evaluar si reduce el sesgo en series intermitentes (Lambert, 1992). Diferido.
4. **Métodos de demanda intermitente** (p. ej. Croston, 1972) para las familias de bajo volumen
   con WAPE inflado.
5. **Contraste cuantitativo ARIMA/Prophet vs boosting** como validación opcional (no bloqueante) de
   la decisión de §7.3. `[PENDIENTE / verificar en máquina con dataset]`
6. **Unificar el MAE del Ridge** entre ADR `0003` y el reporte 2a, y **actualizar el ejemplo de
   contrato** a `regresion_v3`. `[PENDIENTE / cosmético]`

---

## 12. Conclusión

El spike resolvió la decisión abierta del Plan Maestro: el **enfoque inicial de la regresión de
VENTAS** es un **modelo global de *gradient boosting*** (ensemble convexo de boosters), con el
objetivo tratado vía `log1p` y objetivos Tweedie/Poisson, **pronóstico recursivo multi-paso** y
**validación temporal sin fuga** (selección en VALID, TEST una sola vez) sobre un baseline honesto.
Las alternativas se sopesaron contra criterios derivados del EDA y del producto: el **baseline**
queda como piso, el **lineal** como referencia interpretable (retirado de producción), las **series
clásicas** (ARIMA/Prophet) se descartaron por no encajar en un escenario sector-agnóstico y
multi-serie, y el **boosting global** ganó por tolerar la alta cardinalidad, ingerir la señal
exógena, manejar la zero-inflation con objetivos Tweedie/Poisson y dejar un artefacto portable. La
métrica guía es **honesta** por diseño (WAPE recursivo, no teacher-forced): **WAPE 14.59 % en TEST**,
superando al mejor baseline en **MAE −29.4 % / RMSE −32.3 %**. La decisión está cerrada y trazable al
**ADR `0004`**; quedan como cabos sueltos reales la confirmación de la composición del ensemble con
corrida `--full` en GPU y la decisión —separada— de los intervalos de predicción.

---

## 13. Referencias (APA 7ª edición)

Bergmeir, C., & Benítez, J. M. (2012). On the use of cross-validation for time series predictor
evaluation. *Information Sciences, 191*, 192–213. https://doi.org/10.1016/j.ins.2011.12.028

Box, G. E. P., & Cox, D. R. (1964). An analysis of transformations. *Journal of the Royal
Statistical Society: Series B (Methodological), 26*(2), 211–252.
https://doi.org/10.1111/j.2517-6161.1964.tb00553.x

Box, G. E. P., Jenkins, G. M., Reinsel, G. C., & Ljung, G. M. (2015). *Time series analysis:
Forecasting and control* (5.ª ed.). Wiley.

Chen, T., & Guestrin, C. (2016). XGBoost: A scalable tree boosting system. En *Proceedings of the
22nd ACM SIGKDD International Conference on Knowledge Discovery and Data Mining* (pp. 785–794).
Association for Computing Machinery. https://doi.org/10.1145/2939672.2939785

Corporación Favorita, Cook, A., Holbrook, R., Inversion, & Howard, A. (2021). *Store Sales — Time
Series Forecasting* [Conjunto de datos y competencia]. Kaggle.
https://www.kaggle.com/competitions/store-sales-time-series-forecasting `[verificar lista exacta de
organizadores en la página de la competencia]`

Croston, J. D. (1972). Forecasting and stock control for intermittent demands. *Operational Research
Quarterly, 23*(3), 289–303. https://doi.org/10.2307/3007885

Friedman, J. H. (2001). Greedy function approximation: A gradient boosting machine. *The Annals of
Statistics, 29*(5), 1189–1232. https://doi.org/10.1214/aos/1013203451

Hyndman, R. J., & Athanasopoulos, G. (2021). *Forecasting: Principles and practice* (3.ª ed.).
OTexts. https://otexts.com/fpp3/

Hyndman, R. J., & Koehler, A. B. (2006). Another look at measures of forecast accuracy.
*International Journal of Forecasting, 22*(4), 679–688. https://doi.org/10.1016/j.ijforecast.2006.03.001

Ke, G., Meng, Q., Finley, T., Wang, T., Chen, W., Ma, W., Ye, Q., & Liu, T.-Y. (2017). LightGBM: A
highly efficient gradient boosting decision tree. En I. Guyon, U. von Luxburg, S. Bengio, H. Wallach,
R. Fergus, S. Vishwanathan, & R. Garnett (Eds.), *Advances in Neural Information Processing Systems
30* (pp. 3146–3154). Curran Associates.

Lambert, D. (1992). Zero-inflated Poisson regression, with an application to defects in
manufacturing. *Technometrics, 34*(1), 1–14. https://doi.org/10.2307/1269547

McKinney, W. (2010). Data structures for statistical computing in Python. En S. van der Walt & J.
Millman (Eds.), *Proceedings of the 9th Python in Science Conference* (pp. 56–61).
https://doi.org/10.25080/Majora-92bf1922-00a

Pedregosa, F., Varoquaux, G., Gramfort, A., Michel, V., Thirion, B., Grisel, O., Blondel, M.,
Prettenhofer, P., Weiss, R., Dubourg, V., Vanderplas, J., Passos, A., Cournapeau, D., Brucher, M.,
Perrot, M., & Duchesnay, É. (2011). Scikit-learn: Machine learning in Python. *Journal of Machine
Learning Research, 12*, 2825–2830.

Taylor, S. J., & Letham, B. (2018). Forecasting at scale. *The American Statistician, 72*(1), 37–45.
https://doi.org/10.1080/00031305.2017.1380080

---

## 14. Anexos

### Anexo A — Resultados en TEST por modelo (teacher-forced, escala de unidades)

> Tabla comparativa del *zoo* de modelos (referencia optimista; el *headline* honesto es recursivo,
> §9). Fuente: `docs/reporte_regresion_2a.md`.

| modelo | WAPE | MAE | RMSE | RMSLE | R² |
|---|---|---|---|---|---|
| LightGBM_Tweedie | 12.41 | 57.96 | 197.09 | 0.389 | 0.975 |
| XGBoost_Tweedie | 12.43 | 58.05 | 211.74 | 0.387 | 0.971 |
| XGBoost | 13.07 | 61.05 | 216.07 | 0.384 | 0.970 |
| LightGBM_Poisson | 13.22 | 61.77 | 214.66 | 0.401 | 0.970 |
| LightGBM | 14.18 | 66.24 | 234.33 | 0.386 | 0.965 |
| HistGradientBoosting | 14.45 | 67.50 | 236.53 | 0.387 | 0.964 |
| RandomForest | 16.35 | 76.38 | 305.82 | 0.411 | 0.940 |
| BASELINE media_móvil_7 | 19.45 | 90.84 | 297.31 | 0.449 | 0.943 |
| BASELINE naïve(t-7) | 21.46 | 100.23 | 350.06 | 0.569 | 0.921 |
| Ridge | (retirado: MAE 743.72 / ≈1123, no apto) | — | — | — | — |

### Anexo B — Importancia de features (top-10, permutation importance held-out sobre TEST)

> Fuente: `docs/reporte_regresion_2a.md`, `data/processed/importancias_regresion_2a.csv`.

| feature | importancia_pct |
|---|---|
| sales_rmean_7 | 29.38 % |
| sales_lag_1 | 25.50 % |
| sales_ewm_7 | 9.18 % |
| sales_rmed_7 | 4.82 % |
| onpromotion | 4.53 % |
| sales_lag_7 | 3.65 % |
| sales_rmed_28 | 3.60 % |
| sales_rmean_14 | 3.53 % |
| sales_rmean_28 | 2.95 % |
| family | 2.83 % |

Dominan los **rezagos y medias móviles del objetivo** (autocorrelación fuerte), seguidos de la
**promoción** y el **calendario**, como anticipaba el EDA.

### Anexo C — Figuras del EDA relevantes para la decisión (existentes en `figures/`)

| # | Figura | Relevancia para el enfoque |
|---|---|---|
| 01 | [`01_distribucion_sales.png`](../../figures/01_distribucion_sales.png) | Asimetría y ceros del objetivo (C1/C2) |
| 02 | [`02_distribucion_log_sales.png`](../../figures/02_distribucion_log_sales.png) | Efecto de `log1p` (C2) |
| 03 | [`03_tendencia_ventas_diarias.png`](../../figures/03_tendencia_ventas_diarias.png) | Tendencia ⇒ validación temporal (C4) |
| 04 | [`04_estacionalidad_mensual.png`](../../figures/04_estacionalidad_mensual.png) | Estacionalidad ⇒ rezagos/calendario |
| 07 | [`07_promocion_vs_sales.png`](../../figures/07_promocion_vs_sales.png) | Promoción como señal fuerte (feature clave) |

### Anexo D — Documentos relacionados

- `docs/plan_maestro_spc.md` — plan por fases y decisión abierta que este spike cierra.
- `docs/reporte_eda.md` — hallazgos que condicionan el enfoque (ceros, asimetría, serie temporal).
- `docs/reporte_regresion_2a.md` — reporte completo de la Fase 2a (cifras originales).
- `docs/auditoria_fase2a.md` — auditoría que movió la selección a VALID y exigió portabilidad.
- `docs/contrato_datos.md` — frontera pública (VENTAS, `unidades_vendidas`).
- `docs/decisiones/0002`, `0003`, `0004` — ADR de selección y cierre de la regresión.
- `docs/spikes/spike_eda.md` — spike de datos previo (insumo de esta decisión).
- `models/regresion_v3.meta.json` — metadatos del artefacto de producción.
