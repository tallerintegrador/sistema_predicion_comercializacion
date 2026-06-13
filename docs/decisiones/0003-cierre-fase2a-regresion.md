# ADR 0003 — Cierre de la Fase 2a (Regresión / VENTAS)

- **Estado:** Aceptado (2026-06-13)
- **Fase:** 2a — Regresión (VENTAS) — cierre
- **Sustituye/actualiza:** ADR `0002-modelo-regresion-ventas.md` (selección de modelo
  y artefacto de producción)
- **Contexto previo:** `docs/reporte_eda.md`, `docs/plan_maestro_spc.md`,
  `docs/contrato_datos.md`, `docs/reporte_regresion_2a.md`

## Contexto

La Fase 2a ya cumplía el gate (el mejor modelo superaba al baseline en MAE/RMSE
sobre el holdout temporal). Antes de cerrarla e ir a 2b se aplicó una ronda de
correcciones de rigor y honestidad sobre el entregable. Este ADR registra las
decisiones de cierre; el ADR 0002 queda como antecedente histórico.

## Decisiones

### 1. Modelo lineal (Ridge) corregido y luego retirado

El Ridge reportaba R² = −143 / MAE = 2408: no era que "el lineal no sirva", sino
que estaba **mal montado** (categóricos de alta cardinalidad pasados como enteros
ordinales crudos a un modelo lineal). Se rehízo dentro de un **pipeline propio**,
aislado de los modelos de árbol:

- `OneHotEncoder(handle_unknown="ignore")` para `store_nbr`, `family`, `type`,
  `city`, `state`, `cluster`;
- `SimpleImputer(median)` + `StandardScaler` para las numéricas;
- recorte de la predicción tras `expm1` (clip a 0 y techo = `log1p` del máximo
  histórico) para evitar la explosión exponencial.

Tras la corrección mejoró de forma sustancial (MAE 2408 → ~1123), pero **sigue
muy por encima del peor baseline** (≈100). Decisión: **retirarlo de las tablas**
del reporte con una nota explicativa y conservarlo como referencia interpretable,
no como candidato a producción. Los modelos de árbol no usan este pipeline (toleran
escala y codificación ordinal/categórica nativa).

### 2. Modelo de producción: HistGradientBoosting (`regresion_v2`)

La selección **ya no se hace por el MAE de test "a secas"**, sino priorizando la
**estabilidad**. Regla explícita y reproducible:

1. Se consideran "empatados" los modelos cuyo **MAE medio en la validación cruzada
   temporal** cae dentro de una banda de ruido (`TOL_MAE_REL = 3 %`).
2. Entre los empatados gana el de **menor desviación estándar del RMSE** en CV
   (más estable y, en la práctica, más rápido).

Con la CV sobre el train real, los tres boosters quedan empatados en MAE de CV
(banda ≤ 58.15) y el más estable es **HistGradientBoosting** (RMSE_std ≈ 11.79
frente a 14.25 de LightGBM y 14.81 de XGBoost). Ventaja adicional: es **solo
scikit-learn**, sin dependencia extra de boosting para el artefacto de producción.

> Nota: la decisión inicial apuntaba a LightGBM con los números del submuestreo de
> 300 k (`RMSE_std 16.6 vs 40.7`). Al recomputar la CV sobre todo el train, el
> orden de estabilidad cambió y HistGradientBoosting pasó a ser el más estable.
> Se decidió seguir la regla objetiva con la evidencia real.

### 3. Artefacto entrenado con el volumen final

El submuestreo (250 k filas) se usa **solo para comparar** modelos de forma rápida
y reproducible. El **artefacto de producción se reajusta sobre todo el histórico
etiquetado** (≈2.98 M filas). Ambos volúmenes quedan registrados en los metadatos
(`n_filas_comparacion`, `n_filas_artefacto_final`).

### 4. Jerarquía de métricas y nota sobre el MAPE

El reporte encabeza con **WAPE, MAE, RMSE y RMSLE**. El **MAPE (~32 %) está
inflado** por el 31 % de ceros (zero-inflation): excluye los días de venta cero y
sobre-pondera las series de bajo volumen, por lo que **no se usa como métrica
principal** (queda solo como referencia, igual que R²).

### 5. Importancia de features

Se añade al reporte la **importancia por permutation importance held-out** (top-N)
del modelo de producción, calculada sobre el TEST. Es agnóstica al modelo
(necesaria porque HistGradientBoosting no expone `feature_importances_`) y más
honesta que la importancia interna de los árboles. Dominan los **rezagos/medias
móviles del objetivo**, la **promoción** y el **calendario**, como anticipaba el
EDA. Persistida en `data/processed/importancias_regresion_2a.csv`.

## Criterio de "hecho" verificado

- **No-fuga de futuro:** `tests/test_features_regresion.py` comprueba que los lags
  son el valor desplazado, que las ventanas sólo usan el pasado, que las
  transacciones entran sólo como rezago, y (nuevo) que **inflar la venta más
  futura de cada serie no altera ninguna feature de rezago/ventana**.
- **Artefacto recargable sin reentrenar:** `tests/test_regresion.py` carga el
  artefacto serializado y verifica que predice idéntico, incluido el
  preprocesamiento, también sobre un subconjunto de una sola serie.
- **Metadatos completos:** versión, fecha, modelo, criterio de selección, features,
  transformación (`log1p`), semilla, cortes temporales, métricas y volúmenes de
  entrenamiento (test dedicado `test_metadatos_artefacto_completos`).
- **Métricas persistentes y trazables:** `data/processed/metricas_regresion_2a.{csv,json}`
  por modelo y por corte (valid/test/cv).

## Métricas finales (TEST, escala de unidades)

| modelo | WAPE | MAE | RMSE | RMSLE |
|---|---|---|---|---|
| **HistGradientBoosting (producción)** | 14.23 | 66.47 | 227.45 | 0.388 |
| XGBoost | 13.57 | 63.40 | 221.64 | 0.386 |
| LightGBM | 14.05 | 65.61 | 229.20 | 0.386 |
| RandomForest | 15.36 | 71.77 | 249.00 | 0.407 |
| baseline media_móvil_7 | 19.45 | 90.84 | 297.31 | 0.449 |
| baseline naïve(t-7) | 21.46 | 100.23 | 350.06 | 0.569 |
| Ridge | — | (retirado: no apto) | — | — |

El modelo de producción supera al mejor baseline: **MAE −26.8 %, RMSE −23.5 %**.
XGBoost tiene el mejor MAE/WAPE de test pero es el menos estable en CV; se prefiere
HistGradientBoosting por estabilidad (y por ser sólo sklearn). Detalle completo en
`docs/reporte_regresion_2a.md`; métricas crudas en
`data/processed/metricas_regresion_2a.{csv,json}`.

## Estrategia de validación temporal

Cortes por fecha sin fuga: Train ≤ 2017-07-14 · Valid 2017-07-15..07-30 · Test
2017-07-31..08-15 (16 días = espejo del horizonte real del test de Corporación
Favorita) + validación cruzada temporal expanding (3 folds de 14 días dentro de
TRAIN+VALID, nunca toca TEST).

## Mejoras diferidas (documentadas, no implementadas en este cierre)

- **Intervalos de predicción:** cuantiles de boosting (`quantile`/`pinball`) o
  residuos empíricos del holdout.
- **Enfoque zero-inflated / two-part:** clasificar cero vs. positivo y regredir
  sólo los positivos, dado el 31 % de ceros; evaluar si reduce el sesgo en series
  intermitentes.
- **Pronóstico recursivo multi-horizonte:** responsabilidad de la capa de servicio
  (Fase 3).

## Consecuencias

- Nuevo artefacto **`models/regresion_v2.joblib`** (gitignored) + `regresion_v2.meta.json`
  con metadatos enriquecidos (incluye `criterio_seleccion` y los dos volúmenes de
  entrenamiento). El `regresion_v1` (XGBoost) queda como histórico.
- El nombre lógico del modelo en el contrato sigue siendo agnóstico a la versión;
  la capa de servicio/API (Fase 3) carga el artefacto vía
  `PredictorRegresion.predecir`.
- Dependencias sin cambios respecto al ADR 0002 (`lightgbm`, `xgboost`, `joblib`,
  `scikit-learn`).

## Reproducibilidad

`spc-train-regresion` (o `python -m spc.models.regresion`). Semilla fija 42; cortes
temporales, configuración de features y criterio de selección versionados en los
metadatos del artefacto. Mismos datos + mismo código + mismo entorno → mismas
métricas.
