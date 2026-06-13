# Reporte de Regresion (Fase 2a) - VENTAS

> Generado por `spc.models.regresion`. Metricas en **unidades** (objetivo entrenado en `log1p`, invertido con `expm1`). Validacion temporal sin fuga de futuro.

## Jerarquia de metricas

Se prioriza, en este orden: **WAPE**, **MAE**, **RMSE** y **RMSLE**. El **MAPE (~32%) esta inflado** por el 31% de ceros en `sales` (zero-inflation): al excluir los ceros del denominador, sobre-pondera las series de bajo volumen, asi que **no debe usarse como metrica principal** (se incluye solo como referencia). `R2` se reporta como contexto, no como criterio de seleccion.

## Cortes temporales

- **Train:** <= 2017-07-14
- **Valid:** 2017-07-15 .. 2017-07-30
- **Test:** 2017-07-31 .. 2017-08-15
- Filas para **comparar** modelos (submuestreo de train): 250 000
- Filas del **artefacto final** (`regresion_v2`, reajuste sobre todo el historico etiquetado): 2 975 940

## Resultados en TEST (ordenado por MAE, menor es mejor)

| modelo | WAPE | MAE | RMSE | RMSLE | MAPE | R2 |
| --- | --- | --- | --- | --- | --- | --- |
| XGBoost | 13.571 | 63.398 | 221.643 | 0.386 | 32.764 | 0.968 |
| LightGBM | 14.045 | 65.611 | 229.195 | 0.386 | 33.014 | 0.966 |
| HistGradientBoosting | 14.229 | 66.472 | 227.452 | 0.388 | 33.213 | 0.967 |
| RandomForest | 15.363 | 71.767 | 249.004 | 0.407 | 34.149 | 0.96 |
| BASELINE media_movil_7 | 19.446 | 90.84 | 297.306 | 0.449 | 44.039 | 0.943 |
| BASELINE naive_estacional(t-7) | 21.456 | 100.23 | 350.061 | 0.569 | 49.499 | 0.921 |

> **Nota — Ridge retirado de las tablas.** Tras montarlo correctamente (pipeline propio: one-hot de categoricos + estandarizacion de numericas y recorte de `expm1`), el lineal alcanza MAE(test) = 1123.48, todavia por encima del peor baseline (100.23). Se documenta y se excluye de la comparacion para no dejar un modelo no apto en el entregable; queda como referencia interpretable, no como candidato a produccion.

**Modelo elegido: `HistGradientBoosting`** (artefacto `regresion_v2`).

- MAE elegido = 66.472 vs mejor baseline = 90.840 -> mejora 26.8%.
- RMSE elegido = 227.452 vs mejor baseline = 297.306 -> mejora 23.5%.

### Criterio de seleccion (estabilidad, no solo MAE de test)

Regla aplicada: entre los modelos dentro de la banda de ruido del MAE de CV (<= 58.154; tolerancia 3%), el de menor RMSE_std (mas estable). Candidatos dentro de la banda de ruido del MAE de CV: `HistGradientBoosting` (MAE_cv 57.613, RMSE_std 11.794); `LightGBM` (MAE_cv 56.468, RMSE_std 14.248); `XGBoost` (MAE_cv 56.46, RMSE_std 14.807). Gana el de **menor RMSE_std** (mas estable y, en la practica, mas rapido) frente a desempatar por una decima de MAE de test.

## Resultados en VALID (ordenado por MAE)

| modelo | WAPE | MAE | RMSE | RMSLE | MAPE | R2 |
| --- | --- | --- | --- | --- | --- | --- |
| XGBoost | 11.557 | 55.678 | 212.623 | 0.379 | 30.813 | 0.974 |
| LightGBM | 11.753 | 56.619 | 215.506 | 0.378 | 30.643 | 0.974 |
| RandomForest | 11.778 | 56.741 | 210.856 | 0.387 | 31.741 | 0.975 |
| HistGradientBoosting | 12.007 | 57.846 | 223.87 | 0.38 | 30.873 | 0.972 |
| BASELINE naive_estacional(t-7) | 14.147 | 68.155 | 266.225 | 0.51 | 44.246 | 0.96 |
| BASELINE media_movil_7 | 21.534 | 103.744 | 373.731 | 0.449 | 42.745 | 0.921 |

## Validacion cruzada temporal (expanding, MAE/RMSE en unidades)

| modelo | MAE_mean | MAE_std | RMSE_mean | RMSE_std |
| --- | --- | --- | --- | --- |
| HistGradientBoosting | 57.613 | 2.151 | 229.237 | 11.794 |
| LightGBM | 56.468 | 1.886 | 221.768 | 14.248 |
| RandomForest | 60.868 | 8.449 | 244.051 | 50.449 |
| XGBoost | 56.46 | 3.256 | 220.932 | 14.807 |

## Importancia de features (top 15, modelo `HistGradientBoosting`)

Calculada por **permutation importance held-out** (cuanto empeora el MAE al barajar cada feature sobre el TEST); agnostica al modelo y mas robusta que la importancia interna de los arboles.

| feature | importancia | importancia_pct |
| --- | --- | --- |
| sales_rmean_7 | 0.942 | 43.51 |
| sales_lag_1 | 0.536 | 24.75 |
| onpromotion | 0.268 | 12.38 |
| sales_rmed_7 | 0.211 | 9.76 |
| sales_lag_7 | 0.07 | 3.23 |
| sales_lag_14 | 0.03 | 1.38 |
| family | 0.022 | 1.0 |
| promo_lag_7 | 0.02 | 0.92 |
| sales_rmean_28 | 0.016 | 0.75 |
| day | 0.015 | 0.68 |
| dayofweek | 0.014 | 0.63 |
| store_nbr | 0.009 | 0.42 |
| promo_lag_1 | 0.005 | 0.22 |
| trans_lag_1 | 0.003 | 0.14 |
| is_month_end | 0.002 | 0.07 |

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
