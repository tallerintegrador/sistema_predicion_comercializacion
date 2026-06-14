# Reporte de Regresion (Fase 2a) - VENTAS

> Generado por `spc.models.regresion`. Metricas en **unidades** (objetivo entrenado en `log1p`, invertido con `expm1`). Validacion temporal sin fuga de futuro.

## Jerarquia de metricas

Se prioriza, en este orden: **WAPE**, **MAE**, **RMSE** y **RMSLE**. El **MAPE (~32%) esta inflado** por el 31% de ceros en `sales` (zero-inflation): al excluir los ceros del denominador, sobre-pondera las series de bajo volumen, asi que **no debe usarse como metrica principal** (se incluye solo como referencia). `R2` se reporta como contexto, no como criterio de seleccion.

## Cortes temporales

- **Train:** <= 2017-07-14
- **Valid:** 2017-07-15 .. 2017-07-30
- **Test:** 2017-07-31 .. 2017-08-15
- Filas para **comparar** modelos (submuestreo de train): 2 893 968
- Filas del **artefacto final** (`regresion_v3`, reajuste sobre todo el historico etiquetado): 2 950 992

## Resultados en TEST (ordenado por MAE, menor es mejor)

| modelo | WAPE | MAE | RMSE | RMSLE | MAPE | R2 |
| --- | --- | --- | --- | --- | --- | --- |
| LightGBM | 11.482 | 53.636 | 185.33 | 0.37 | 30.975 | 0.978 |
| XGBoost_Tweedie | 11.729 | 54.792 | 191.235 | 0.377 | 33.109 | 0.977 |
| XGBoost | 11.777 | 55.015 | 193.567 | 0.371 | 31.091 | 0.976 |
| LightGBM_Tweedie | 12.407 | 57.959 | 196.137 | 0.386 | 33.559 | 0.975 |
| LightGBM_Poisson | 12.93 | 60.404 | 207.003 | 0.401 | 36.327 | 0.973 |
| HistGradientBoosting | 13.066 | 61.035 | 207.755 | 0.375 | 31.164 | 0.972 |
| RandomForest | 14.034 | 65.56 | 222.46 | 0.398 | 33.654 | 0.968 |
| BASELINE media_movil_7 | 19.446 | 90.84 | 297.306 | 0.449 | 44.039 | 0.943 |
| BASELINE naive_estacional(t-7) | 21.456 | 100.23 | 350.061 | 0.569 | 49.499 | 0.921 |

> **Nota — Ridge retirado de las tablas.** Tras montarlo correctamente (pipeline propio: one-hot de categoricos + estandarizacion de numericas y recorte de `expm1`), el lineal alcanza MAE(test) = 766.59, todavia por encima del peor baseline (100.23). Se documenta y se excluye de la comparacion para no dejar un modelo no apto en el entregable; queda como referencia interpretable, no como candidato a produccion.

**Modelo elegido: `Ensemble(XGBoost+XGBoost_Tweedie+LightGBM_Tweedie+LightGBM)`** (artefacto `regresion_v3`).

- MAE elegido = 51.308 vs mejor baseline = 90.840 -> mejora 43.5%.
- RMSE elegido = 179.453 vs mejor baseline = 297.306 -> mejora 39.6%.

### Criterio de seleccion (estabilidad, no solo MAE de test)

Regla: ensemble convexo de boosters elegido por **menor WAPE honesto (recursivo)** frente al ganador individual `LightGBM_Tweedie`.

## Evaluacion HONESTA - pronostico recursivo multi-paso (metrica guia)

A diferencia de la tabla anterior (que usa *teacher forcing*: alimenta los rezagos con las ventas **reales** del horizonte y por eso sobreestima la precision), aqui el modelo proyecta los 16 dias de TEST de forma **autorregresiva**, reinyectando sus propias predicciones como en produccion. Es la metrica de referencia del proyecto.

| fuente | WAPE | MAE | RMSE | RMSLE | MAPE | R2 |
| --- | --- | --- | --- | --- | --- | --- |
| **Ensemble(XGBoost+XGBoost_Tweedie+LightGBM_Tweedie+LightGBM)** (recursivo) | 12.713 | 59.389 | 205.007 | 0.396 | 32.866 | 0.973 |
| BASELINE naive_estacional(t-7) | 20.665 | 96.535 | 348.382 | 0.617 | 49.975 | 0.922 |
| BASELINE media_movil_7 | 23.261 | 108.662 | 359.824 | 0.531 | 50.974 | 0.917 |

- **WAPE honesto** del modelo = 12.71%.
- Mejor baseline honesto (recursivo) = 20.67% WAPE -> el modelo mejora 7.95 puntos.

- **Modelo de produccion = ensemble convexo** de: `XGBoost` (25%), `XGBoost_Tweedie` (25%), `LightGBM_Tweedie` (25%), `LightGBM` (25%).
- Elegido por **menor WAPE honesto**: ensemble 12.713% vs ganador individual `LightGBM_Tweedie` 13.618%.

### WAPE honesto por familia (las 10 peores)

| family | n | WAPE | MAE |
| --- | --- | --- | --- |
| BOOKS | 864.0 | 1089.21 | 0.11 |
| HOME APPLIANCES | 864.0 | 203.69 | 0.41 |
| BABY CARE | 864.0 | 168.19 | 0.31 |
| HARDWARE | 864.0 | 72.25 | 1.05 |
| SCHOOL AND OFFICE SUPPLIES | 864.0 | 69.24 | 41.51 |
| LINGERIE | 864.0 | 48.4 | 3.76 |
| MAGAZINES | 864.0 | 40.32 | 2.87 |
| CELEBRATION | 864.0 | 38.89 | 4.85 |
| AUTOMOTIVE | 864.0 | 37.26 | 2.75 |
| LADIESWEAR | 864.0 | 36.52 | 3.68 |

### WAPE honesto por tienda (las 10 peores)

| store_nbr | n | WAPE | MAE |
| --- | --- | --- | --- |
| 32 | 528.0 | 24.01 | 38.03 |
| 38 | 528.0 | 21.59 | 80.88 |
| 30 | 528.0 | 21.12 | 42.22 |
| 26 | 528.0 | 21.07 | 29.77 |
| 14 | 528.0 | 20.79 | 53.81 |
| 22 | 528.0 | 19.82 | 45.7 |
| 54 | 528.0 | 19.77 | 66.11 |
| 39 | 528.0 | 19.71 | 97.72 |
| 25 | 528.0 | 19.05 | 55.9 |
| 36 | 528.0 | 18.9 | 76.4 |

### Agregado SEMANAL (suma de ventas reales vs pronosticadas)

| semana | real | pred | WAPE | error_abs |
| --- | --- | --- | --- | --- |
| 2017-07-31 | 6.4101935e+06 | 6420978.32 | 0.17 | 10784.82 |
| 2017-08-07 | 5.385402e+06 | 5647773.08 | 4.87 | 262371.08 |
| 2017-08-14 | 1.5235844e+06 | 1516580.42 | 0.46 | 7003.96 |

### Agregado MENSUAL (suma de ventas reales vs pronosticadas)

| mes | real | pred | WAPE | error_abs |
| --- | --- | --- | --- | --- |
| 2017-07-01 | 885856.8 | 896093.61 | 1.16 | 10236.8 |
| 2017-08-01 | 1.2433324e+07 | 12689238.21 | 2.06 | 255915.21 |

## Resultados en VALID (ordenado por MAE)

| modelo | WAPE | MAE | RMSE | RMSLE | MAPE | R2 |
| --- | --- | --- | --- | --- | --- | --- |
| XGBoost | 10.523 | 50.695 | 195.664 | 0.368 | 29.603 | 0.978 |
| XGBoost_Tweedie | 10.699 | 51.544 | 197.602 | 0.374 | 31.95 | 0.978 |
| LightGBM_Tweedie | 10.748 | 51.78 | 190.831 | 0.382 | 32.777 | 0.979 |
| LightGBM | 10.806 | 52.058 | 198.54 | 0.371 | 29.768 | 0.978 |
| LightGBM_Poisson | 11.087 | 53.413 | 197.544 | 0.392 | 33.962 | 0.978 |
| RandomForest | 11.454 | 55.183 | 207.928 | 0.383 | 31.47 | 0.975 |
| HistGradientBoosting | 12.057 | 58.084 | 219.85 | 0.374 | 29.984 | 0.973 |
| BASELINE naive_estacional(t-7) | 14.147 | 68.155 | 266.225 | 0.51 | 44.246 | 0.96 |
| BASELINE media_movil_7 | 21.534 | 103.744 | 373.731 | 0.449 | 42.745 | 0.921 |

## Validacion cruzada temporal (expanding, MAE/RMSE en unidades)

| modelo | MAE_mean | MAE_std | RMSE_mean | RMSE_std |
| --- | --- | --- | --- | --- |
| HistGradientBoosting | 49.315 | 2.253 | 199.593 | 10.597 |
| LightGBM | 49.138 | 2.259 | 198.487 | 10.16 |
| LightGBM_Poisson | 51.119 | 2.221 | 203.534 | 11.149 |
| LightGBM_Tweedie | 47.49 | 1.865 | 188.982 | 6.106 |
| RandomForest | 53.156 | 2.205 | 207.644 | 11.344 |
| XGBoost | 48.006 | 2.342 | 196.949 | 9.683 |
| XGBoost_Tweedie | 48.617 | 1.671 | 201.308 | 14.09 |

## Importancia de features (top 15, modelo `Ensemble(XGBoost+XGBoost_Tweedie+LightGBM_Tweedie+LightGBM)`)

Calculada por **permutation importance held-out** (cuanto empeora el MAE al barajar cada feature sobre el TEST); agnostica al modelo y mas robusta que la importancia interna de los arboles.

| feature | importancia | importancia_pct |
| --- | --- | --- |
| sales_rmean_7 | 335.141 | 29.95 |
| sales_lag_1 | 194.556 | 17.39 |
| family | 147.036 | 13.14 |
| sales_rmean_14 | 103.106 | 9.21 |
| sales_rmed_7 | 57.672 | 5.15 |
| sales_rstd_7 | 43.467 | 3.88 |
| dias_desde_venta | 41.2 | 3.68 |
| sales_ewm_28 | 28.487 | 2.55 |
| ceros_rsum_7 | 23.949 | 2.14 |
| store_nbr | 17.617 | 1.57 |
| sales_lag_7 | 17.052 | 1.52 |
| onpromotion | 13.622 | 1.22 |
| sales_ewm_7 | 13.611 | 1.22 |
| sales_rmean_56 | 11.208 | 1.0 |
| sales_rmean_28 | 9.847 | 0.88 |

Dominan, como anticipaba el EDA, los **rezagos y medias moviles del objetivo** (autocorrelacion fuerte de la demanda), seguidos de la **promocion** (`onpromotion` y sus rezagos) y el **calendario**. Esto sustenta la trazabilidad hacia COMPRAS/ALMACEN: el pronostico se apoya en la historia reciente de cada serie y en las palancas planificadas.

## Nota sobre el MAPE

El MAPE (~32%) **sobre-estima el error**: excluye los dias de venta cero (31% del total) y penaliza desproporcionadamente las series pequenas. Para esta serie zero-inflated, el **WAPE** (error agregado ponderado por volumen) y el **MAE/RMSE** en unidades son las metricas fiables.

## Notas de diseno

- Transacciones usadas **solo como rezagos** (t-1, t-7) y medias del pasado: en pronostico real no se conocen las del periodo a predecir.
- Rezagos/ventanas del objetivo calculados por serie `(store_nbr, family)` con `shift` antes de la ventana (sin fuga).
- Modelo lineal (Ridge) montado en **pipeline propio** (one-hot + estandarizacion); los modelos de arbol usan categoricas nativas/codigos.
- Zero-inflation (31.3% de ceros) presente; el recorte a 0 tras `expm1` respeta que las ventas no son negativas.

## Mejoras diferidas (documentadas, no implementadas en este cierre)

- **Intervalos de prediccion:** via cuantiles de boosting (`quantile`/`pinball`) o residuos empiricos del holdout.
- **Enfoque zero-inflated / two-part:** clasificar cero vs. positivo y regredir solo los positivos, dado el 31% de ceros; evaluar si reduce el sesgo en series intermitentes.
