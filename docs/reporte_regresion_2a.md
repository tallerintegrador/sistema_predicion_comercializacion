# Reporte de Regresion (Fase 2a) - VENTAS

> Generado por `spc.models.regresion`. Metricas en **unidades**. Validacion temporal sin fuga de futuro. Nota sobre la transformacion: los submodelos del espacio `log` entrenan en `log1p(sales)` e invierten con `expm1`; los objetivos Tweedie/Poisson predicen **unidades** directas. Si el modelo de produccion es un ensemble (o un individual Tweedie), su `transformacion_objetivo` es `identidad` (combina/predice en unidades) aunque por dentro use submodelos `log1p`.

## Jerarquia de metricas

Se prioriza, en este orden: **WAPE**, **MAE**, **RMSE** y **RMSLE**. El **MAPE (~32%) esta inflado** por el 31% de ceros en `sales` (zero-inflation): al excluir los ceros del denominador, sobre-pondera las series de bajo volumen, asi que **no debe usarse como metrica principal** (se incluye solo como referencia). `R2` se reporta como contexto, no como criterio de seleccion.

## Cortes temporales

- **Train:** <= 2017-07-14
- **Valid:** 2017-07-15 .. 2017-07-30
- **Test:** 2017-07-31 .. 2017-08-15
- Filas para **comparar** modelos (submuestreo de train): 250 000
- Filas del **artefacto final** (`regresion_v3`, reajuste sobre todo el historico etiquetado): 2 950 992

## Resultados en TEST (ordenado por MAE, menor es mejor)

| modelo | WAPE | MAE | RMSE | RMSLE | MAPE | R2 |
| --- | --- | --- | --- | --- | --- | --- |
| LightGBM_Tweedie | 12.407 | 57.956 | 197.091 | 0.389 | 33.311 | 0.975 |
| XGBoost_Tweedie | 12.426 | 58.047 | 211.737 | 0.387 | 33.405 | 0.971 |
| XGBoost | 13.068 | 61.046 | 216.067 | 0.384 | 32.493 | 0.97 |
| LightGBM_Poisson | 13.223 | 61.769 | 214.655 | 0.401 | 35.923 | 0.97 |
| LightGBM | 14.179 | 66.235 | 234.328 | 0.386 | 32.974 | 0.965 |
| HistGradientBoosting | 14.45 | 67.501 | 236.533 | 0.387 | 33.319 | 0.964 |
| RandomForest | 16.35 | 76.38 | 305.819 | 0.411 | 34.499 | 0.94 |
| BASELINE media_movil_7 | 19.446 | 90.84 | 297.306 | 0.449 | 44.039 | 0.943 |
| BASELINE naive_estacional(t-7) | 21.456 | 100.23 | 350.061 | 0.569 | 49.499 | 0.921 |

> **Nota — Ridge retirado de las tablas.** Tras montarlo correctamente (pipeline propio: one-hot de categoricos + estandarizacion de numericas y recorte de `expm1`), el lineal alcanza MAE(test) = 743.72, todavia por encima del peor baseline (100.23). Se documenta y se excluye de la comparacion para no dejar un modelo no apto en el entregable; queda como referencia interpretable, no como candidato a produccion.

**Modelo elegido: `Ensemble(XGBoost+XGBoost_Tweedie+LightGBM+LightGBM_Poisson)`** (artefacto `regresion_v3`).

### Resultado headline -- metrica HONESTA (pronostico recursivo sobre TEST, evaluado una sola vez)

La metrica guia del proyecto es el **pronostico recursivo multi-paso** (autorregresivo, como en produccion), no el teacher forcing. Sobre TEST, evaluado una sola vez tras seleccionar en VALID:

- **MAE honesto = 68.151** vs mejor baseline honesto recursivo = 96.535 -> mejora **29.4%**.
- **WAPE honesto = 14.59%** vs mejor baseline honesto = 20.67% -> mejora **6.08 puntos**.
- **RMSE honesto = 235.731** vs mejor baseline honesto recursivo = 348.382 -> mejora **32.3%**.

> *Referencia teacher-forced (optimista, alimenta los rezagos con ventas reales del horizonte; NO es la metrica guia):* MAE 57.914 vs baseline 90.840 (36.2%), RMSE 202.386 vs baseline 297.306. Util solo como cota superior optimista.

### Criterio de seleccion (gate en VALID; estabilidad por CV temporal)

Regla: ensemble convexo de boosters elegido por **menor WAPE honesto (recursivo) sobre VALID** frente al ganador individual `LightGBM_Tweedie`; TEST no se uso para seleccionar. La decision ensemble-vs-individual se tomo sobre **VALID** (pronostico recursivo honesto), no sobre TEST. WAPE VALID individual = 14.249%. WAPE VALID ensemble = 12.177%.

## Evaluacion HONESTA - pronostico recursivo multi-paso (metrica guia)

A diferencia de la tabla anterior (que usa *teacher forcing*: alimenta los rezagos con las ventas **reales** del horizonte y por eso sobreestima la precision), aqui el modelo proyecta los 16 dias de TEST de forma **autorregresiva**, reinyectando sus propias predicciones como en produccion. Es la metrica de referencia del proyecto.

| fuente | WAPE | MAE | RMSE | RMSLE | MAPE | R2 |
| --- | --- | --- | --- | --- | --- | --- |
| **Ensemble(XGBoost+XGBoost_Tweedie+LightGBM+LightGBM_Poisson)** (recursivo) | 14.589 | 68.151 | 235.731 | 0.423 | 34.063 | 0.964 |
| BASELINE naive_estacional(t-7) | 20.665 | 96.535 | 348.382 | 0.617 | 49.975 | 0.922 |
| BASELINE media_movil_7 | 23.261 | 108.662 | 359.824 | 0.531 | 50.974 | 0.917 |

- **WAPE honesto** del modelo = 14.59%.
- Mejor baseline honesto (recursivo) = 20.67% WAPE -> el modelo mejora 6.08 puntos.

- **Modelo de produccion = ensemble convexo** de: `XGBoost` (26%), `XGBoost_Tweedie` (25%), `LightGBM` (25%), `LightGBM_Poisson` (24%).
- Elegido por **menor WAPE honesto sobre VALID** (gate, no TEST): ensemble 12.177% vs ganador individual `LightGBM_Tweedie` 14.249%.

### WAPE honesto por familia (las 10 peores)

| family | n | WAPE | MAE |
| --- | --- | --- | --- |
| BOOKS | 864.0 | 1997.66 | 0.21 |
| HOME APPLIANCES | 864.0 | 219.43 | 0.44 |
| BABY CARE | 864.0 | 190.74 | 0.35 |
| HARDWARE | 864.0 | 73.72 | 1.07 |
| SCHOOL AND OFFICE SUPPLIES | 864.0 | 73.48 | 44.05 |
| LINGERIE | 864.0 | 50.29 | 3.91 |
| MAGAZINES | 864.0 | 40.36 | 2.87 |
| CELEBRATION | 864.0 | 39.12 | 4.88 |
| AUTOMOTIVE | 864.0 | 38.5 | 2.84 |
| LADIESWEAR | 864.0 | 38.38 | 3.87 |

### WAPE honesto por tienda (las 10 peores)

| store_nbr | n | WAPE | MAE |
| --- | --- | --- | --- |
| 26 | 528.0 | 30.09 | 42.51 |
| 25 | 528.0 | 24.13 | 70.79 |
| 38 | 528.0 | 24.07 | 90.18 |
| 32 | 528.0 | 23.19 | 36.73 |
| 39 | 528.0 | 22.18 | 109.93 |
| 14 | 528.0 | 21.44 | 55.48 |
| 40 | 528.0 | 21.06 | 114.8 |
| 54 | 528.0 | 21.05 | 70.38 |
| 30 | 528.0 | 20.56 | 41.1 |
| 42 | 528.0 | 20.37 | 70.07 |

### Agregado SEMANAL (suma de ventas reales vs pronosticadas)

| semana | real | pred | WAPE | error_abs |
| --- | --- | --- | --- | --- |
| 2017-07-31 | 6.4101935e+06 | 6494776.53 | 1.32 | 84583.03 |
| 2017-08-07 | 5.385402e+06 | 5658375.33 | 5.07 | 272973.33 |
| 2017-08-14 | 1.5235844e+06 | 1508365.25 | 1.0 | 15219.13 |

### Agregado MENSUAL (suma de ventas reales vs pronosticadas)

| mes | real | pred | WAPE | error_abs |
| --- | --- | --- | --- | --- |
| 2017-07-01 | 885856.8 | 868458.28 | 1.96 | 17398.53 |
| 2017-08-01 | 1.2433324e+07 | 12793058.83 | 2.89 | 359735.83 |

## Resultados en VALID (ordenado por MAE)

| modelo | WAPE | MAE | RMSE | RMSLE | MAPE | R2 |
| --- | --- | --- | --- | --- | --- | --- |
| LightGBM_Tweedie | 11.35 | 54.681 | 198.001 | 0.386 | 32.353 | 0.978 |
| XGBoost | 11.417 | 55.002 | 207.79 | 0.376 | 30.784 | 0.975 |
| RandomForest | 11.519 | 55.495 | 209.651 | 0.384 | 31.432 | 0.975 |
| XGBoost_Tweedie | 11.534 | 55.568 | 208.699 | 0.383 | 32.68 | 0.975 |
| LightGBM_Poisson | 11.87 | 57.184 | 209.51 | 0.395 | 34.296 | 0.975 |
| LightGBM | 12.215 | 58.848 | 213.199 | 0.38 | 31.062 | 0.974 |
| HistGradientBoosting | 12.379 | 59.636 | 222.94 | 0.379 | 31.082 | 0.972 |
| BASELINE naive_estacional(t-7) | 14.147 | 68.155 | 266.225 | 0.51 | 44.246 | 0.96 |
| BASELINE media_movil_7 | 21.534 | 103.744 | 373.731 | 0.449 | 42.745 | 0.921 |

## Validacion cruzada temporal (expanding, MAE/RMSE en unidades)

| modelo | MAE_mean | MAE_std | RMSE_mean | RMSE_std |
| --- | --- | --- | --- | --- |
| HistGradientBoosting | 58.727 | 2.613 | 242.111 | 19.048 |
| LightGBM | 57.18 | 3.161 | 230.713 | 23.806 |
| LightGBM_Poisson | 55.292 | 3.352 | 223.093 | 4.567 |
| LightGBM_Tweedie | 53.263 | 3.401 | 205.603 | 8.165 |
| RandomForest | 61.613 | 12.878 | 260.725 | 84.845 |
| XGBoost | 55.103 | 3.476 | 235.269 | 45.488 |
| XGBoost_Tweedie | 63.142 | 10.059 | 256.617 | 45.671 |

## Importancia de features (top 15, modelo `Ensemble(XGBoost+XGBoost_Tweedie+LightGBM+LightGBM_Poisson)`)

Calculada por **permutation importance held-out** (cuanto empeora el MAE al barajar cada feature sobre el TEST); agnostica al modelo y mas robusta que la importancia interna de los arboles.

| feature | importancia | importancia_pct |
| --- | --- | --- |
| sales_rmean_7 | 286.989 | 29.38 |
| sales_lag_1 | 249.078 | 25.5 |
| sales_ewm_7 | 89.671 | 9.18 |
| sales_rmed_7 | 47.13 | 4.82 |
| onpromotion | 44.241 | 4.53 |
| sales_lag_7 | 35.677 | 3.65 |
| sales_rmed_28 | 35.182 | 3.6 |
| sales_rmean_14 | 34.475 | 3.53 |
| sales_rmean_28 | 28.808 | 2.95 |
| family | 27.687 | 2.83 |
| sales_ewm_28 | 17.421 | 1.78 |
| sales_rstd_7 | 16.577 | 1.7 |
| dias_desde_venta | 12.03 | 1.23 |
| sales_lag_14 | 7.492 | 0.77 |
| sales_rmean_56 | 7.394 | 0.76 |

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
- **Familias intermitentes de bajo volumen:** algunas familias (p. ej. `BOOKS`, `BABY CARE`, `HOME APPLIANCES`) muestran **WAPE alto** en el desglose, pero su **MAE es trivial** (fracciones de unidad): el WAPE se dispara al dividir errores minusculos entre ventas casi nulas. No afecta el WAPE agregado (ponderado por volumen) ni el negocio; se trataria, si acaso, con el enfoque two-part de arriba.
