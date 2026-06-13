# Reporte de Regresion (Fase 2a) - VENTAS

> Generado por `spc.models.regresion`. Metricas en **unidades** (objetivo entrenado en `log1p`, invertido con `expm1`). Validacion temporal sin fuga de futuro.

## Cortes temporales

- **Train:** <= 2017-07-14
- **Valid:** 2017-07-15 .. 2017-07-30
- **Test:** 2017-07-31 .. 2017-08-15
- Filas usadas para ajustar (submuestreo de train): 300 000

## Resultados en TEST (ordenado por MAE, menor es mejor)

| modelo | MAE | RMSE | RMSLE | MAPE | WAPE | R2 |
| --- | --- | --- | --- | --- | --- | --- |
| XGBoost | 64.642 | 233.393 | 0.385 | 32.666 | 13.838 | 0.965 |
| LightGBM | 65.222 | 228.428 | 0.386 | 33.074 | 13.962 | 0.967 |
| HistGradientBoosting | 65.992 | 227.013 | 0.389 | 33.697 | 14.127 | 0.967 |
| RandomForest | 70.803 | 242.895 | 0.405 | 34.122 | 15.157 | 0.962 |
| BASELINE media_movil_7 | 90.84 | 297.306 | 0.449 | 44.039 | 19.446 | 0.943 |
| BASELINE naive_estacional(t-7) | 100.23 | 350.061 | 0.569 | 49.499 | 21.456 | 0.921 |
| Ridge | 2408.493 | 15006.713 | 1.825 | 233.069 | 515.579 | -143.506 |

**Modelo ganador: `XGBoost`** (artefacto `regresion_v1`).

- MAE ganador = 64.642 vs mejor baseline = 90.840 -> mejora 28.8%.
- RMSE ganador = 233.393 vs mejor baseline = 297.306 -> mejora 21.5%.

## Resultados en VALID (ordenado por MAE)

| modelo | MAE | RMSE | RMSLE | MAPE | WAPE | R2 |
| --- | --- | --- | --- | --- | --- | --- |
| XGBoost | 55.714 | 211.015 | 0.377 | 30.696 | 11.565 | 0.975 |
| LightGBM | 56.256 | 212.844 | 0.377 | 30.585 | 11.677 | 0.974 |
| RandomForest | 56.465 | 210.496 | 0.387 | 31.692 | 11.72 | 0.975 |
| HistGradientBoosting | 58.241 | 224.929 | 0.38 | 31.015 | 12.089 | 0.971 |
| BASELINE naive_estacional(t-7) | 68.155 | 266.225 | 0.51 | 44.246 | 14.147 | 0.96 |
| BASELINE media_movil_7 | 103.744 | 373.731 | 0.449 | 42.745 | 21.534 | 0.921 |
| Ridge | 2400.242 | 14762.648 | 1.844 | 236.204 | 498.221 | -122.763 |

## Validacion cruzada temporal (expanding, MAE/RMSE en unidades)

| modelo | MAE_mean | MAE_std | RMSE_mean | RMSE_std |
| --- | --- | --- | --- | --- |
| HistGradientBoosting | 57.538 | 2.333 | 228.758 | 13.91 |
| LightGBM | 55.59 | 2.194 | 216.858 | 16.629 |
| RandomForest | 59.874 | 6.642 | 240.32 | 40.138 |
| Ridge | 2476.07 | 86.762 | 15117.804 | 333.18 |
| XGBoost | 55.532 | 3.799 | 231.88 | 40.734 |

## Notas de diseno

- Transacciones usadas **solo como rezagos** (t-1, t-7) y medias del pasado: en pronostico real no se conocen las del periodo a predecir.
- Rezagos/ventanas del objetivo calculados por serie `(store_nbr, family)` con `shift` antes de la ventana (sin fuga).
- Zero-inflation (31.3% de ceros) presente; el recorte a 0 tras `expm1` respeta que las ventas no son negativas.
- **Intervalos de prediccion:** pendientes (mejora futura via cuantiles de boosting o residuos empiricos).
