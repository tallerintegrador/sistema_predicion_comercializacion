# Spike — Análisis Exploratorio de Datos (EDA) del dataset de validación de SPC

> Documento vivo. Spike de investigación (cerrado). Vive en `docs/spikes/spike_eda.md`.
> **Síntesis y formalización** del EDA ya ejecutado en la Fase 1. No re-ejecuta análisis
> sobre datos crudos (el crudo está en `.gitignore`); consolida y razona sobre los
> hallazgos persistidos en `docs/reporte_eda.md` y los artefactos de `data/processed/` y
> `figures/`. Todo número proviene de esos documentos; lo que no esté soportado se marca
> como `[PENDIENTE / verificar en máquina con dataset]`.

---

## 1. Encabezado / metadatos

| Campo | Valor |
|---|---|
| **ID del spike** | `SPK-EDA-001` |
| **Título** | EDA del dataset de validación (Store Sales — Corporación Favorita): aptitud para regresión, clasificación y clustering |
| **Autor/a** | Camila L. Moreno Quevedo (equipo SPC) |
| **Fecha (redacción del spike)** | 2026-06-16 |
| **Time-box (investigación EDA)** | ≈ 3–5 días-persona `[estimado; verificar bitácora de Fase 1]` |
| **Estado** | **Cerrado** (hallazgos consumidos por las Fases 2a/2b/2c y 3) |
| **Fase relacionada** | **Fase 1 — Datos** (insumo directo de la Fase 2 — Motor de ML) |
| **Tipo de spike** | Investigación de datos (*data spike*) previa al modelado |
| **Fuentes base** | `docs/reporte_eda.md`, `docs/contrato_datos.md`, `docs/plan_maestro_spc.md`, ADRs `0002`–`0006` |
| **Artefactos de respaldo** | `data/processed/*.csv` / `*.json`, `figures/01..19_*.png`, `notebooks/eda.ipynb` |

---

## 2. Contexto y motivación

SPC (Sistema Predictivo de Comercialización) es un **motor de previsión ofrecido como
servicio (API)** para PYMEs, agnóstico al sector y estructurado en tres campos —VENTAS
(regresión), COMPRAS (derivado) y ALMACÉN (clasificación + clustering)— con separación
estricta de capas (`api → service → motor`). La validación del motor es **técnica**: se
realiza sobre el dataset público *Store Sales — Corporación Favorita* (retail de Ecuador,
diario 2013–2017), que el contrato de datos mapea a campos genéricos.

Antes de comprometer arquitectura de modelos, transformaciones, esquema de validación y
métricas, existía una **incertidumbre de fondo**: ¿la data elegida es **rica y suficiente**
para sostener las tres familias de modelos sin que el diseño se construya sobre supuestos
falsos? Decisiones caras y difíciles de revertir dependen de la respuesta: si el objetivo
fuera casi simétrico, `log1p` sería innecesario; si no hubiera estructura temporal, el
*feature engineering* de rezagos sobraría; si las clases estuvieran balanceadas, todo el
aparato de desbalance (SMOTE, umbral de negocio) carecería de sentido; si las tiendas no
se separaran, el clustering no aportaría `segmento_tienda` al contrato de ALMACÉN.

Este spike formaliza esa investigación: documenta **qué se preguntó**, **qué se encontró**
y **cómo cada hallazgo aterrizó en una decisión de modelado** trazable a su ADR.

---

## 3. Pregunta(s) del spike

**Pregunta principal**

> ¿El dataset *Store Sales — Corporación Favorita* es **rico y suficiente**, en calidad y
> estructura, para sustentar los tres campos de SPC (regresión de ventas, clasificación de
> demanda alta y clustering de perfilado) con una validación técnica honesta?

**Sub-preguntas acotadas**

1. **Calidad e integración.** ¿Cuál es el estado de nulos, duplicados, tipos, rangos y
   fechas faltantes de los 7 archivos, y cómo deben integrarse sin introducir ruido ni fuga?
2. **Variable objetivo (regresión).** ¿Qué forma tiene `sales` (ceros, asimetría) y
   justifica eso una transformación antes de modelar?
3. **Estructura temporal.** ¿Existen tendencia, estacionalidad y efectos de calendario que
   obliguen a una validación temporal sin fuga de futuro y a ingeniería de rezagos?
4. **Señal predictiva (bivariado).** ¿Qué variables muestran relación con la demanda y
   cuáles correlaciones son espurias?
5. **Clasificación.** ¿Cómo definir `demanda_alta` de forma honesta y cuál es el desbalance
   real resultante?
6. **Clustering.** ¿Las tiendas y familias se separan en segmentos cuantificablemente
   diferenciables, y sobre qué eje?

Un spike sin pregunta clara no es un spike: la pregunta principal es el **gate de aptitud**
de la Fase 1; las sub-preguntas son las condiciones que debían cumplirse para abrir la Fase 2.

---

## 4. Alcance

**Dentro de alcance**

- Perfilado y control de calidad de los 7 CSV del dataset y del **dataset analítico
  integrado** (30 columnas, 27 predictoras).
- Análisis univariado, de la variable objetivo, temporal y bivariado/multivariado.
- Diagnóstico de **aptitud** para regresión, clasificación y clustering, con sus
  implicaciones de modelado.
- Mapeo de los campos reales al **contrato de datos** genérico (tabla de equivalencias).

**Fuera de alcance (explícito)**

- Entrenar o ajustar modelos (eso es Fase 2; aquí solo se diagnostica aptitud). Las
  siluetas de KMeans y los conteos de clase reportados son **mediciones exploratorias**,
  no modelos de producción.
- Re-ejecutar el EDA sobre datos crudos: `data/raw/` está en `.gitignore` y no está
  disponible en este entorno; este documento **sintetiza** lo ya calculado.
- Datos sintéticos / generación (solo se mencionan como insumo de experimentación de Fase 1/2).
- Diseño de la API y de la capa de servicio (Fase 3).

---

## 5. Supuestos

1. **Validación técnica, no de usuario.** Se asume que *Store Sales — Corporación Favorita*
   es **representativa suficiente** para validar el motor; los datos sintéticos complementan
   la experimentación (Plan Maestro §6).
2. **Granularidad diaria** a nivel `(fecha, store_nbr, family)`; semanal/mensual se obtienen
   por agregación. La granularidad de producto es **familia** (no SKU individual).
3. **Entrenamiento offline.** El EDA alimenta un pipeline reproducible; en producción la API
   solo carga artefactos y predice.
4. **Reproducibilidad de extremo a extremo:** mismos datos + mismo código + mismo entorno →
   mismas cifras. Las del EDA se consideran reproducibles vía `notebooks/eda.ipynb` y el
   pipeline de integración (criterio de validación de Fase 1).
5. **El contrato de datos manda sobre la implementación:** los hallazgos del EDA se traducen
   a decisiones de modelado sin romper la frontera pública genérica.

---

## 6. Metodología / enfoque

- **Insumos.** 7 archivos CSV del dataset (`train`, `test`, `stores`, `transactions`,
  `oil`, `holidays_events`, `sample_submission`) integrados en un **dataset analítico**
  reproducible. El reporte fuente declara que todas las cifras provienen de cálculos
  ejecutados, no escritas a mano (`docs/reporte_eda.md`).
- **Herramientas.** Ecosistema Python: **pandas** para perfilado/integración, **matplotlib**
  para las 19 figuras, **scikit-learn** para la validación de separabilidad (KMeans +
  coeficiente de silueta). Notebook reproducible `notebooks/eda.ipynb`; tablas intermedias
  en `data/processed/`.
- **Integración (decisiones aplicadas, §6 del reporte EDA).**
  - `train` ⋈ `stores` por `store_nbr` (muchos-a-uno validada).
  - `transactions` ⋈ por `date`+`store_nbr`; faltantes conservados con bandera
    `transactions_missing` y versión `transactions_filled = 0`.
  - `oil` reindexado al calendario diario; `dcoilwtico` imputado con *forward/backward fill*
    y bandera `dcoilwtico_original_missing`.
  - `holidays_events` agregado por **alcance** (nacional por fecha; regional por
    fecha-estado; local por fecha-ciudad); los `transferred = True` no cuentan como activos.
- **Partición temporal (heredada por la Fase 2).** Aunque la partición formal es de modelado,
  el EDA ya verificó la **separación temporal limpia** entre `train` (2013-01-01 .. 2017-08-15)
  y `test` (2017-08-16 .. 2017-08-31): solapamiento de fechas = 0. La Fase 2 fija los cortes
  honestos **Train ≤ 2017-07-14 · Valid 2017-07-15..07-30 · Test 2017-07-31..08-15** (16 días
  = espejo del horizonte real de la competencia), con CV temporal *expanding* (ADRs `0002`–`0006`).
- **Subconjunto de datos.** El perfilado se hizo sobre el **dataset completo** (3 000 888
  filas) para las cifras de calidad y objetivo; la **validación de separabilidad de
  clustering** se hizo sobre **perfiles agregados** (54 tiendas, 33 familias). El reporte
  no usó datos crudos fuera del repositorio para estas cifras.

---

## 7. Hallazgos / resultados

> Núcleo del spike. Todas las cifras provienen de `docs/reporte_eda.md` y de los CSV de
> `data/processed/`; las figuras citadas existen en `figures/`.

### 7.1 Descripción del dataset y mapeo al contrato

- **Fuente:** *Store Sales — Time Series Forecasting*, Corporación Favorita (retail de
  Ecuador), distribuido vía Kaggle.
- **Periodo cubierto:** `train` 2013-01-01 → 2017-08-15; `test` 2017-08-16 → 2017-08-31.
- **Granularidad:** diaria, por `(date, store_nbr, family)`.
- **Volumen:** `train.csv` = **3 000 888 filas × 6 columnas**; **54 tiendas**, **33 familias**.
- **Dataset analítico integrado:** **3 000 888 filas × 30 columnas**, de las cuales **27 son
  potenciales predictoras** (se excluyen `id`, `date` y el objetivo `sales`).

Tamaño por archivo (extracto de la tabla de calidad):

| archivo | filas | columnas | rango de fechas | observaciones |
|---|---|---|---|---|
| train | 3 000 888 | 6 | 2013-01-01 .. 2017-08-15 | 939 130 ventas en cero; 0 negativas; 4 días faltantes |
| test | 28 512 | 5 | 2017-08-16 .. 2017-08-31 | sin nulos/duplicados |
| stores | 54 | 5 | — | tabla maestra de tiendas |
| transactions | 83 488 | 3 | 2013-01-01 .. 2017-08-15 | 6 días faltantes |
| oil | 1 218 | 2 | 2013-01-01 .. 2017-08-31 | 43 nulos; 486 fechas faltantes (mercado cerrado) |
| holidays_events | 350 | 6 | 2012-03-02 .. 2017-12-26 | 12 eventos transferidos |
| sample_submission | 28 512 | 2 | — | formato de envío |

**Mapeo al contrato de datos** (frontera pública genérica, `docs/contrato_datos.md` §2):

| Campo genérico (contrato) | Equivalente en la data de prueba |
|---|---|
| `fecha` | `date` |
| `punto_venta_id` | `store_nbr` |
| `producto_id` / `categoria` | `family` |
| `unidades_vendidas` | `sales` |
| `en_promocion` | `onpromotion` |
| `transacciones` *(opcional)* | `transactions` |
| `evento_activo` *(opcional)* | `holiday_any` |

> La tabla de equivalencias existe para validar el motor con datos reales **sin atar el
> contrato a un sector**. El catálogo completo de las 30 columnas integradas está en
> `data/processed/catalogo_columnas.csv` y en §6 del reporte EDA.

### 7.2 Calidad de datos

- **Nulos / duplicados.** `train`, `test`, `stores`, `transactions`, `holidays_events` y
  `sample_submission`: **0 duplicados, 0 nulos**. El único campo con nulos es
  `oil.dcoilwtico` (**43 nulos**, 1.7652 % del archivo / 3.53 % de la serie cargada).
- **Tipos / rangos (chequeos específicos).** Ventas negativas: **0**. Ventas en cero:
  **939 130**. Promociones negativas: **0**. Transacciones negativas: **0**.
- **Integridad referencial.** Tiendas de `train`, `test` y `transactions` ausentes en
  `stores`: **0** en los tres casos.
- **Separación temporal.** Solapamiento de fechas `train`↔`test`: **0** (separación limpia,
  pre-requisito de una validación temporal honesta).
- **Fechas faltantes / cierres.** `train`: 4 días faltantes en rango; `transactions`: 6;
  `oil`: **486** (mercado cerrado fines de semana/feriados → patrón estructural, no error).
- **Resultado de integración.** Filas con transacciones faltantes: **245 784 (8.19 %)**
  (conservadas con bandera). Fechas con petróleo faltante: 525 antes del relleno → **0**
  después. Filas con algún feriado/evento activo: **254 760 (8.49 %)**.

Respaldo: `data/processed/resumen_calidad.json`, `data/processed/resumen_integracion.json`.

### 7.3 Análisis univariado

**Categóricas** (cardinalidad y moda):

| variable | cardinalidad | valor más frecuente |
|---|---|---|
| `family` | 33 | AUTOMOTIVE (90 936) |
| `store_nbr` | 54 | 1 |
| `city` | 22 | Quito |
| `state` | 16 | Pichincha |
| `type` | 5 | D |
| `cluster` (original de stores) | 17 | 3 |

**Numéricas** (extracto):

| variable | media | mediana | desv. estándar | asimetría | máx |
|---|---|---|---|---|---|
| `onpromotion` | 2.603 | 0.000 | 12.219 | 11.167 | 741 |
| `transactions` | 1 694.602 | 1 393.000 | 963.287 | 1.518 | 8 359 |
| `dcoilwtico` | 67.714 | 53.190 | 25.630 | 0.321 | 110.62 |

Observación clave: `onpromotion` tiene **mediana 0** → la mayoría de las filas no están en
promoción; la promoción es una señal **escasa pero fuerte** (ver §7.6). Figura:
[`figures/06_top_familias_ventas.png`](../../figures/06_top_familias_ventas.png).

### 7.4 Variable objetivo `sales` — ceros, asimetría y `log1p`

Estadísticos descriptivos (extracto): media **357.78**, desv. estándar **1 101.9977**,
mediana **11**, máximo **124 717**, coeficiente de variación **3.08**. Media sin ceros
**520.74** vs media global 357.78.

**Inflación de ceros y forma de la distribución:**

| métrica | valor |
|---|---|
| Proporción de ventas en cero | **31.30 %** (939 130 filas) |
| Asimetría (*skewness*) cruda | **7.3588** |
| Asimetría tras `log1p` | **0.4083** |
| Curtosis cruda | 154.5618 |
| Curtosis tras `log1p` | −1.1497 |
| Outliers por regla IQR | 447 105 filas (14.90 %) |

**Interpretación.** La asimetría positiva alta y la curtosis elevada confirman una variable
muy sesgada con cola larga. La transformación **`log1p` reduce la asimetría de 7.36 → 0.41**
(de "muy sesgada" a "casi simétrica"), lo que justifica transformar el objetivo antes de
modelar (Box & Cox, 1964). El contraste entre media con y sin ceros (357.78 vs 520.74) y el
31 % de ceros indican que la **demanda nula debe tratarse de forma explícita**.

Figuras: distribución cruda
[`figures/01_distribucion_sales.png`](../../figures/01_distribucion_sales.png) y en `log1p`
[`figures/02_distribucion_log_sales.png`](../../figures/02_distribucion_log_sales.png).

> **Nota de contrato.** El modelo entrena en escala `log1p` (para los submodelos del espacio
> log) pero **devuelve siempre unidades** (revierte con `expm1`); el contrato expone
> `metadatos.transformacion_interna = "log1p"` sin que el cliente vea la escala interna.

### 7.5 Análisis temporal (es serie de tiempo)

**Tendencia (year-over-year, venta media diaria):** crecimiento sostenido — 2014 **+49.18 %**,
2015 **+14.99 %**, 2016 **+19.50 %**, 2017 **+8.19 %** (año parcial, solo hasta agosto, no
comparable en total anual). La serie tiene **tendencia creciente** marcada.

**Estacionalidad intra-anual (índice estacional mensual; >1 = mes por encima del nivel típico
de su año):** pico claro en **diciembre = 1.349**, seguido de noviembre (1.111), septiembre
(1.074) y octubre (1.068); valle en febrero (0.862). Hay **estacionalidad anual repetida**.

**Efectos de calendario:**

- **Feriados/eventos activos:** días con evento venden más (media diaria **699 588** vs
  **627 096** sin evento). Por tipo, los días `Additional` (929 777) y `Transfer` (845 275)
  destacan; los `Holiday` puros quedan cerca de la base.
- **Quincena / fin de mes (`is_payday`):** efecto leve a favor (mediana diaria 660 088 vs
  630 812) — coherente con ciclos de pago.
- **Días pico (señal de eventos):** entre los días de mayor venta agregada aparecen fechas de
  abril de 2016, consistentes con el **terremoto de abril 2016** (shock visible en la serie).

Figuras: tendencia diaria
[`figures/03_tendencia_ventas_diarias.png`](../../figures/03_tendencia_ventas_diarias.png),
estacionalidad mensual
[`figures/04_estacionalidad_mensual.png`](../../figures/04_estacionalidad_mensual.png),
día de semana
[`figures/05_estacionalidad_dia_semana.png`](../../figures/05_estacionalidad_dia_semana.png),
heatmap año×mes [`figures/14_heatmap_anio_mes.png`](../../figures/14_heatmap_anio_mes.png),
efecto por tipo de feriado
[`figures/15_efecto_tipo_feriado.png`](../../figures/15_efecto_tipo_feriado.png).

> **Autocorrelación.** El reporte EDA no incluye un correlograma (ACF/PACF) formal; la
> estructura temporal se evidencia vía estacionalidad, tendencia y efectos de calendario,
> y se explota con rezagos `t-1, t-7, t-14, t-21, t-28` y medias/medianas móviles en la
> Fase 2a. Un ACF/PACF explícito queda como `[PENDIENTE / verificar en máquina con dataset]`.

### 7.6 Análisis bivariado / multivariado

**Promoción → ventas (señal comercial directa):**

| | filas | media `sales` | mediana `sales` |
|---|---|---|---|
| Sin promo | 2 389 559 | 158.25 | 3 |
| Con promo | 611 329 | **1 137.69** | **373** |

**Ranking de señal lineal contra `sales`:** `onpromotion` **0.4279**, `transactions_filled`
**0.2331**, `year` 0.0811, `dcoilwtico` **−0.0748**, `is_weekend` 0.0519, `cluster` 0.0385.

**Ventas por tipo de tienda:** A (media 705.88) > B (326.74) > E (269.12) > D (350.98 media,
mayor volumen total) > C (197.26) — heterogeneidad relevante entre tipos.

> **Correlación espuria del petróleo.** La correlación global `dcoilwtico ↔ sales` (−0.0748)
> es en gran parte **espuria**: responde a una tendencia temporal (las ventas suben mientras
> el petróleo baja en el periodo), no a causalidad. Se trata como **variable macro de
> contexto**, no causal (ver figura coloreada por año
> [`figures/09_petroleo_vs_sales.png`](../../figures/09_petroleo_vs_sales.png)).

Figuras: promo vs ventas
[`figures/07_promocion_vs_sales.png`](../../figures/07_promocion_vs_sales.png), transacciones
vs ventas [`figures/08_transacciones_vs_sales.png`](../../figures/08_transacciones_vs_sales.png),
matriz de correlaciones
[`figures/10_correlaciones_numericas.png`](../../figures/10_correlaciones_numericas.png),
penetración de promo en el tiempo
[`figures/16_penetracion_promo_mensual.png`](../../figures/16_penetracion_promo_mensual.png).
Respaldo: `data/processed/correlaciones_numericas.csv`, `data/processed/relacional_*.csv`.

### 7.7 Segmentación (para clustering)

Se construyeron **perfiles agregados** (un vector por entidad) de 54 tiendas y 33 familias.
La **validación de separabilidad** se hizo con KMeans + coeficiente de silueta (Rousseeuw,
1987):

| entidad | mejor k por silueta (EDA) | silueta |
|---|---|---|
| tiendas | **k = 2** | **0.6075** |
| familias | **k = 2** | **0.7052** |

Perfil de los dos segmentos de tienda (EDA):

| segmento | n | venta media | transacciones media | `pct_demanda_alta` |
|---|---|---|---|---|
| 0 (bajo volumen) | 44 | 262.69 | 1 194.86 | 0.14 |
| 1 (alto volumen) | 10 | 776.15 | 3 143.97 | 0.61 |

**Interpretación + transparencia.** Las siluetas positivas confirman que tiendas y familias
forman grupos diferenciables → la data **es apta para clustering**. Sin embargo, la
separación está **dominada por el volumen**: los segmentos se distinguen por nivel de ventas,
flujo de transacciones y proporción de demanda alta, que son colineales. Esta limitación se
documenta con transparencia y se profundiza en la Fase 2c (ver §8.3 y §9). Figuras:
segmentación [`figures/18_segmentacion_tiendas_kmeans.png`](../../figures/18_segmentacion_tiendas_kmeans.png),
curva de silueta [`figures/19_silueta_k_tiendas.png`](../../figures/19_silueta_k_tiendas.png).
Respaldo: `data/processed/features_clustering_{tiendas,familias}.csv`,
`data/processed/perfil_segmentos_{tiendas,familias}.csv`.

### 7.8 Balance de clases (para clasificación)

Objetivo derivado **`demanda_alta = 1` si `sales > P75` de su `family`** (umbral por familia,
para que las familias de gran escala no dominen el corte):

| `demanda_alta` | filas | % |
|---|---|---|
| No | 2 329 621 | **77.63 %** |
| Sí | 671 267 | **22.37 %** |

**Ratio de desbalance No:Sí ≈ 3.47 : 1.** Como contraste, un umbral P75 **global** (= 195.85)
da 25.00 % de positivos (3:1). Ambas definiciones generan clases desbalanceadas; la
**definición por familia es preferible** porque reparte el positivo entre todas las
categorías. Figura:
[`figures/11_balance_clases_demanda.png`](../../figures/11_balance_clases_demanda.png).
Respaldo: `data/processed/clasificacion_demanda_alta.csv`,
`data/processed/clasificacion_umbral_global.csv`.

> **⚠ Implicación revisada después (ver §9 y §10).** El reporte EDA (§8.2 y §9) concluye que
> este desbalance **"justifica técnicas de balanceo (SMOTE)"**. Esa era una recomendación
> *a priori*. En la Fase 2b se **probó empíricamente** y se encontró que **SMOTE no aporta**
> sobre un desbalance moderado (~1:3.5): se descartó. Ver ADR `0005`.

### 7.9 Síntesis: hallazgo → decisión de modelado → ADR

| # | Hallazgo (EDA) | Decisión de modelado | Dominio | ADR |
|---|---|---|---|---|
| H1 | `sales` muy sesgada (asimetría 7.36 → 0.41 con `log1p`) | Entrenar en `log1p`; reportar en unidades (`expm1`) | Regresión | `0002`/`0004` |
| H2 | 31.30 % de ceros (zero-inflation) | MAPE marcado como inflado; WAPE/MAE como métricas guía; enfoque *zero-inflated* **diferido** | Regresión | `0003`/`0004` |
| H3 | Tendencia + estacionalidad + separación temporal limpia | Validación **temporal sin fuga** (cortes por fecha + CV *expanding*); selección en VALID, TEST una vez | Regresión / Clasif. | `0002`–`0006` |
| H4 | Señal: `onpromotion` (0.43), `transactions` (0.23); efectos de calendario | *Feature engineering* leak-safe: rezagos del objetivo, promo, transacciones rezagadas, calendario | Regresión / Clasif. | `0002`/`0005` |
| H5 | Petróleo: correlación −0.07 espuria (tendencia) | Petróleo como variable macro de contexto, no causal | Regresión | `0002` |
| H6 | Faltantes operativos (transacciones 8.19 %, oil) | Banderas de faltantes + imputación documentada en la integración | Datos | (Fase 1) |
| H7 | Alta cardinalidad (`family` 33, `store_nbr` 54) | Modelos de árbol/boosting que la toleran; codificación con cuidado temporal | Regresión / Clasif. | `0002` |
| H8 | `demanda_alta` desbalanceada (22.37 %, 3.47:1) | Métricas de la **clase minoritaria** (PR-AUC, recall); etiqueta P75 **train-only**; umbral de negocio | Clasificación | `0005` |
| H9 | Desbalance moderado → recomendación EDA de SMOTE | **SMOTE evaluado y descartado** (no aporta); modelo sin remuestreo | Clasificación | `0005` |
| H10 | Tiendas/familias separables (silueta 0.61 / 0.71) pero **dominadas por volumen** | KMeans sobre perfiles; k por silueta + interpretabilidad; transparencia "dominado por volumen" | Clustering | `0006` |

---

## 8. Implicaciones para el modelado

### 8.1 Regresión (VENTAS)

- **Transformación del objetivo.** H1 justifica `log1p`: la Fase 2a entrena los submodelos
  del espacio log en `log1p(sales)` e invierte con `expm1`; el predictor de producción
  (`regresion_v3`) devuelve **unidades** (`transformacion_objetivo = "identidad"`).
- **Validación honesta.** H3 obliga a cortes por fecha sin fuga y a evaluar el **pronóstico
  recursivo multi-paso** (autorregresivo) como métrica guía, no el *teacher forcing*
  (optimista). Resultado: WAPE recursivo honesto en TEST **14.59 %**, MAE **68.15**, RMSE
  **235.73**, frente al mejor baseline honesto (WAPE 20.67 %): **MAE −29.4 %, RMSE −32.3 %**.
- **Features.** H4/H5/H7 aterrizan en el set de `regresion_v3.meta.json`: rezagos del objetivo
  (`t-1..t-28`), medias/medianas/EWM móviles desplazadas, promoción y sus rezagos,
  transacciones **solo rezagadas**, calendario cíclico, feriados por alcance y petróleo
  rezagado como contexto. Las categóricas de alta cardinalidad las absorben los boosters.
- **Zero-inflation (H2).** El MAPE (~34 %) se marca como **inflado** por el 31 % de ceros y no
  se usa como métrica principal; el enfoque *zero-inflated / two-part* queda **diferido y
  documentado**.

### 8.2 Clasificación (ALMACÉN — `demanda_alta`)

- **Etiqueta honesta (H8).** `demanda_alta = sales > P75 por familia`. El EDA fija el P75 sobre
  todo `train.csv`; la Fase 2b lo **recalcula solo en TRAIN** (`date <= 2017-07-14`) para no
  contaminar la definición de la clase. La cantidad que define la etiqueta (`sales` del
  periodo), `family_sales_p75` y `demanda_alta` **no son features**.
- **Desbalance (H8).** Métricas de la **minoritaria** (PR-AUC, recall), no accuracy. Resultado:
  PR-AUC TEST **0.934**; al umbral de negocio (precisión ≥ 0.80) precisión **0.809**, recall
  **0.874**.
- **SMOTE descartado (H9).** Tres estrategias (sin remuestreo / costo-sensible / SMOTE solo en
  train del fold) → diferencias < 0.001 en PR-AUC VALID. Se elige la **más simple, sin
  remuestreo** (`clasificacion_v1`). Mostrar que SMOTE no aporta era parte de lo pedido.
- **Familias degeneradas.** `BABY CARE` y `BOOKS` (P75 = 0 → etiqueta "vendió algo") se
  excluyen del train/eval y se documenta.

### 8.3 Clustering (perfilado)

- **Aptitud confirmada (H10).** La silueta positiva del EDA habilita el clustering. La Fase 2c
  reproduce la silueta del EDA **a 4 decimales** (0.6075 tiendas / 0.7052 familias) como
  *validación de plomería*.
- **Refinamiento.** El modelo desplegado usa un **subconjunto de features elegido por
  diagnóstico** (no "más por defecto"): tiendas k=2 (silueta **0.6742**), **familias k=3
  deliberado** (silueta **0.6590**) para **aislar las familias intermitentes** (`BABY CARE`,
  `BOOKS`, `HARDWARE`, `HOME APPLIANCES`) en su propio segmento.
- **Transparencia.** El diagnóstico (PCA: PC1 ≈ 69 % tiendas / 62 % familias) confirma la
  observación del EDA: la segmentación está **dominada por volumen**; promo, transacciones,
  demanda alta e intermitencia son **co-variables descriptivas**, no ejes independientes
  (`segmentacion_dominada_por_volumen = true`).
- **Vínculo con el contrato.** El artefacto de tiendas produce el `segmento_tienda` de la
  respuesta de ALMACÉN; el de familias apoya políticas de stock por tipo de demanda.

---

## 9. Recomendaciones / decisiones habilitadas

El EDA respondió afirmativamente al gate de aptitud y habilitó las siguientes decisiones,
todas ya tomadas y trazables:

1. **Regresión apta** → transformar `log1p`, validación temporal sin fuga, ensemble de
   boosters. **ADR `0002` (selección), `0003` (cierre), `0004` (cierre con auditoría).**
2. **Clasificación apta** con `demanda_alta` por familia → etiqueta train-only, métricas de la
   minoritaria, **SMOTE evaluado y descartado**, umbral de negocio. **ADR `0005`.**
3. **Clustering apto** → KMeans sobre perfiles, k por silueta **e** interpretabilidad,
   transparencia de dominancia por volumen. **ADR `0006`.**
4. **Integración de datos** con banderas de faltantes e imputación documentada → pipeline
   reproducible de Fase 1 (criterio: reproduce 3 000 888 filas, 30 columnas, 31.30 % ceros,
   22.37 % positivos).
5. **Contrato de datos** validado contra data real sin atarlo a un sector → `docs/contrato_datos.md`.

> **Revisión explícita de una implicación del EDA.** La recomendación de SMOTE (reporte EDA
> §8.2/§9) fue **revisada empíricamente** en la Fase 2b: con desbalance moderado (~1:3.5) y un
> booster que ya ordena bien la minoritaria (PR-AUC ≈ 0.93), SMOTE no mejora y se descarta.
> Es honestidad metodológica, no contradicción: el EDA recomendó *probarlo*; la 2b lo probó.
> **ADR `0005`.**

---

## 10. Riesgos y limitaciones del análisis

| Riesgo / limitación | Detalle | Mitigación / estado |
|---|---|---|
| **Ceros y asimetría en `sales`** | 31.3 % ceros, asimetría 7.36 | `log1p` (validado); *zero-inflated* diferido (ADR `0003`/`0004`) |
| **Fuga de futuro** | Métricas infladas si se mira el futuro | Cortes por fecha, rezagos solo del pasado, SMOTE jamás fuera de train |
| **Recomendación EDA no verificada *a priori*** | El EDA "justifica SMOTE" sin probarlo | Probado y **descartado** en 2b (ADR `0005`) |
| **Segmentación dominada por volumen** | PC1 ≈ 60–70 % de varianza; ejes colineales | Documentado con transparencia; etiquetas = niveles de volumen (ADR `0006`) |
| **Correlación espuria del petróleo** | −0.07 global por tendencia temporal | Tratado como macro-contexto, no causal |
| **Faltantes operativos** | Transacciones 8.19 %, oil 486 fechas | Banderas + imputación documentada |
| **Etiqueta no estacionaria** | Prevalencia sube 0.224 (train) → ~0.347 (valid/test) | Documentada; percentil móvil **diferido** (ADR `0005`) |
| **Sin ACF/PACF formal** | El reporte no incluye correlograma explícito | `[PENDIENTE / verificar en máquina con dataset]` |
| **EDA no re-ejecutado aquí** | `data/raw/` gitignored; síntesis sobre cifras persistidas | Reproducible vía `notebooks/eda.ipynb` + pipeline de Fase 1 |
| **Time-box estimado** | Duración exacta de la investigación no registrada | `[estimado; verificar bitácora de Fase 1]` |

---

## 11. Preguntas abiertas / próximos pasos

1. **Autocorrelación formal (ACF/PACF):** producir el correlograma para confirmar
   cuantitativamente los rezagos elegidos. `[PENDIENTE / verificar en máquina con dataset]`
2. **Enfoque zero-inflated / two-part:** clasificar cero-vs-positivo y regredir solo los
   positivos; evaluar si reduce el sesgo en series intermitentes (diferido, ADR `0003`/`0004`).
3. **Etiqueta `demanda_alta` no estacionaria:** evaluar un P75 por ventana móvil (régimen
   actual) frente al P75 histórico fijo (diferido, ADR `0005`).
4. **Intervalos de predicción** para VENTAS (cuantiles de boosting o residuos empíricos)
   (diferido, ADRs `0003`/`0004`).
5. **Métodos de demanda intermitente** (p. ej. Croston) para familias de bajo volumen
   (`BOOKS`, `BABY CARE`, `HOME APPLIANCES`).
6. **Perfil de clustering as-of-time** si el segmento llega a usarse como feature predictiva
   en `t` (diferido, ADR `0006`).
7. **Métodos de clustering alternativos** (jerárquico, DBSCAN) como contraste de KMeans.

---

## 12. Conclusión

El EDA respondió la pregunta del spike: el dataset *Store Sales — Corporación Favorita* es
**rico y suficiente** para los tres campos de SPC. La data combina historial de ventas,
tiendas, familias, promociones, transacciones, petróleo, calendario y feriados, con calidad
alta (sin duplicados, casi sin nulos, integridad referencial completa, separación temporal
limpia) y limitaciones **reales y documentadas** (31 % de ceros y fuerte asimetría en
`sales`; faltantes operativos en transacciones; huecos estructurales en petróleo). Cada
hallazgo aterrizó en una decisión de modelado trazable: `log1p` y validación temporal honesta
para regresión; etiqueta `demanda_alta` honesta y métricas de la minoritaria para
clasificación; KMeans sobre perfiles con transparencia de dominancia por volumen para
clustering. La única implicación que el EDA dejó como recomendación *a priori* —SMOTE— fue
**probada y revisada** en la Fase 2b, ejemplo de la honestidad metodológica que atraviesa el
proyecto. **El gate de aptitud de la Fase 1 quedó superado**, habilitando la Fase 2 (motor de
ML), hoy completa.

---

## 13. Referencias (APA 7ª edición)

Box, G. E. P., & Cox, D. R. (1964). An analysis of transformations. *Journal of the Royal
Statistical Society: Series B (Methodological), 26*(2), 211–252.
https://doi.org/10.1111/j.2517-6161.1964.tb00553.x

Chawla, N. V., Bowyer, K. W., Hall, L. O., & Kegelmeyer, W. P. (2002). SMOTE: Synthetic
minority over-sampling technique. *Journal of Artificial Intelligence Research, 16*, 321–357.
https://doi.org/10.1613/jair.953

Chen, T., & Guestrin, C. (2016). XGBoost: A scalable tree boosting system. En *Proceedings of
the 22nd ACM SIGKDD International Conference on Knowledge Discovery and Data Mining*
(pp. 785–794). Association for Computing Machinery. https://doi.org/10.1145/2939672.2939785

Corporación Favorita, Cook, A., Holbrook, R., Inversion, & Howard, A. (2021). *Store Sales —
Time Series Forecasting* [Conjunto de datos y competencia]. Kaggle.
https://www.kaggle.com/competitions/store-sales-time-series-forecasting `[verificar lista
exacta de organizadores en la página de la competencia]`

Hyndman, R. J., & Athanasopoulos, G. (2021). *Forecasting: Principles and practice* (3.ª ed.).
OTexts. https://otexts.com/fpp3/

Ke, G., Meng, Q., Finley, T., Wang, T., Chen, W., Ma, W., Ye, Q., & Liu, T.-Y. (2017).
LightGBM: A highly efficient gradient boosting decision tree. En I. Guyon, U. von Luxburg,
S. Bengio, H. Wallach, R. Fergus, S. Vishwanathan, & R. Garnett (Eds.), *Advances in Neural
Information Processing Systems 30* (pp. 3146–3154). Curran Associates.

Lemaître, G., Nogueira, F., & Aridas, C. K. (2017). Imbalanced-learn: A Python toolbox to
tackle the curse of imbalanced datasets in machine learning. *Journal of Machine Learning
Research, 18*(17), 1–5.

MacQueen, J. (1967). Some methods for classification and analysis of multivariate
observations. En *Proceedings of the Fifth Berkeley Symposium on Mathematical Statistics and
Probability* (Vol. 1, pp. 281–297). University of California Press.

McKinney, W. (2010). Data structures for statistical computing in Python. En S. van der Walt
& J. Millman (Eds.), *Proceedings of the 9th Python in Science Conference* (pp. 56–61).
https://doi.org/10.25080/Majora-92bf1922-00a

Pedregosa, F., Varoquaux, G., Gramfort, A., Michel, V., Thirion, B., Grisel, O., Blondel, M.,
Prettenhofer, P., Weiss, R., Dubourg, V., Vanderplas, J., Passos, A., Cournapeau, D.,
Brucher, M., Perrot, M., & Duchesnay, É. (2011). Scikit-learn: Machine learning in Python.
*Journal of Machine Learning Research, 12*, 2825–2830.

Rousseeuw, P. J. (1987). Silhouettes: A graphical aid to the interpretation and validation of
cluster analysis. *Journal of Computational and Applied Mathematics, 20*, 53–65.
https://doi.org/10.1016/0377-0427(87)90125-7

---

## 14. Anexos

### Anexo A — Figuras del EDA (existentes en `figures/`)

| # | Figura | Tema |
|---|---|---|
| 01 | [`01_distribucion_sales.png`](../../figures/01_distribucion_sales.png) | Distribución cruda de `sales` |
| 02 | [`02_distribucion_log_sales.png`](../../figures/02_distribucion_log_sales.png) | Distribución `log1p(sales)` |
| 03 | [`03_tendencia_ventas_diarias.png`](../../figures/03_tendencia_ventas_diarias.png) | Serie diaria / tendencia |
| 04 | [`04_estacionalidad_mensual.png`](../../figures/04_estacionalidad_mensual.png) | Índice estacional mensual |
| 05 | [`05_estacionalidad_dia_semana.png`](../../figures/05_estacionalidad_dia_semana.png) | Estacionalidad por día de semana |
| 06 | [`06_top_familias_ventas.png`](../../figures/06_top_familias_ventas.png) | Top familias por ventas |
| 07 | [`07_promocion_vs_sales.png`](../../figures/07_promocion_vs_sales.png) | Promoción vs ventas |
| 08 | [`08_transacciones_vs_sales.png`](../../figures/08_transacciones_vs_sales.png) | Transacciones vs ventas |
| 09 | [`09_petroleo_vs_sales.png`](../../figures/09_petroleo_vs_sales.png) | Petróleo vs ventas (por año) |
| 10 | [`10_correlaciones_numericas.png`](../../figures/10_correlaciones_numericas.png) | Matriz de correlaciones |
| 11 | [`11_balance_clases_demanda.png`](../../figures/11_balance_clases_demanda.png) | Balance de clases `demanda_alta` |
| 12 | [`12_sales_promedio_cluster.png`](../../figures/12_sales_promedio_cluster.png) | Ventas promedio por cluster |
| 13 | [`13_estacionalidad_anual.png`](../../figures/13_estacionalidad_anual.png) | Perfil mensual por año |
| 14 | [`14_heatmap_anio_mes.png`](../../figures/14_heatmap_anio_mes.png) | Heatmap año × mes |
| 15 | [`15_efecto_tipo_feriado.png`](../../figures/15_efecto_tipo_feriado.png) | Efecto por tipo de feriado |
| 16 | [`16_penetracion_promo_mensual.png`](../../figures/16_penetracion_promo_mensual.png) | Penetración de promo |
| 17 | [`17_dist_log_sales_por_tipo.png`](../../figures/17_dist_log_sales_por_tipo.png) | `log1p(sales)` por tipo de tienda |
| 18 | [`18_segmentacion_tiendas_kmeans.png`](../../figures/18_segmentacion_tiendas_kmeans.png) | Segmentación de tiendas |
| 19 | [`19_silueta_k_tiendas.png`](../../figures/19_silueta_k_tiendas.png) | Curva de silueta vs k |

### Anexo B — Tablas intermedias persistidas (`data/processed/`)

Calidad/integración: `resumen_calidad.json`, `resumen_integracion.json`,
`catalogo_columnas.csv`. Objetivo y univariado: `clasificacion_demanda_alta.csv`,
`clasificacion_umbral_global.csv`. Temporal: `estacionalidad_*.csv`, `indice_estacional_mes.csv`,
`efecto_eventos.csv`, `efecto_quincena.csv`, `efecto_tipo_feriado.csv`, `dias_pico_ventas.csv`.
Relacional: `correlaciones_numericas.csv`, `relacional_*.csv`, `penetracion_promo_mensual.csv`.
Clustering: `features_clustering_{tiendas,familias}.csv`,
`perfil_segmentos_{tiendas,familias}.csv`.

### Anexo C — Documentos relacionados

- `docs/reporte_eda.md` — reporte EDA fuente (cifras originales).
- `docs/contrato_datos.md` — contrato de datos (frontera pública).
- `docs/plan_maestro_spc.md` — plan maestro por fases.
- `docs/decisiones/0002`..`0006` — ADRs de regresión, clasificación y clustering.
</content>
</invoke>
