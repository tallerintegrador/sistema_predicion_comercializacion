# ADR 0002 — Modelo de regresión para VENTAS (Fase 2a)

- **Estado:** Aceptado (2026-06-13)
- **Fase:** 2a — Regresión (VENTAS)
- **Contexto previo:** `docs/reporte_eda.md`, `docs/plan_maestro_spc.md`, `docs/contrato_datos.md`

> Nota de numeración: se reserva el ADR `0001` para la decisión de stack y
> arquitectura que el plan maestro (§5) menciona (`0001-stack-y-arquitectura.md`)
> y que aún está pendiente de redactar.

## Contexto

El campo VENTAS exige un pronóstico de demanda (`sales`) a nivel
`(fecha, punto_venta_id, producto_id/familia)`. El EDA mostró: objetivo muy
asimétrico (asimetría 7.36; con `log1p` baja a 0.41), 31.3 % de ceros
(zero-inflation), y señal lineal principal en `onpromotion` (≈0.43) y
`transactions` (≈0.23). El motor de ML entrena offline y debe dejar un artefacto
que la API solo cargue y prediga, sin reentrenar en caliente.

## Decisión

1. **Objetivo en `log1p(sales)`**; todas las métricas se reportan en **unidades**
   (inversión con `expm1`, recorte de negativas a 0).
2. **Validación temporal sin fuga** con cortes por fecha + validación cruzada
   expanding:
   - Train ≤ 2017-07-14 · Valid 2017-07-15..07-30 · Test 2017-07-31..08-15
     (16 días = espejo del horizonte real del test de Corporación Favorita).
3. **Feature engineering leak-safe** (`spc.features.temporales`): rezagos del
   objetivo (t-1, t-7, t-14) y medias/medianas móviles desplazadas; transacciones
   **solo como rezagos** (t-1, t-7) y media del pasado — nunca el periodo a
   predecir; promoción del día (planificada, conocida) más rezagos;
   calendario/feriados; categóricas de serie. Todo rezago/ventana se calcula por
   serie `(store_nbr, family)` aplicando `shift` antes de cualquier ventana.
4. **Comparación de 2 baselines + 5 modelos** (semilla 42): naïve estacional(t-7)
   y media móvil 7; Ridge, RandomForest, HistGradientBoosting, LightGBM, XGBoost.
5. **Modelo de producción: XGBoost** (`regresion_v1`), reajustado sobre todo el
   histórico etiquetado, serializado con joblib junto a sus metadatos.

## Métricas (TEST, escala de unidades)

| modelo | MAE | RMSE | R² |
|---|---|---|---|
| **XGBoost (ganador)** | 64.64 | 233.39 | 0.965 |
| LightGBM | 65.22 | 228.43 | 0.967 |
| HistGradientBoosting | 65.99 | 227.01 | 0.967 |
| RandomForest | 70.80 | 242.90 | 0.962 |
| baseline media_móvil_7 | 90.84 | 297.31 | 0.943 |
| baseline naïve(t-7) | 100.23 | 350.06 | 0.921 |
| Ridge | 2408 | 15007 | (no apto) |

El ganador supera al mejor baseline: **MAE −28.8 %, RMSE −21.5 %**. La validación
cruzada expanding confirma el orden (XGBoost y LightGBM líderes; Ridge inestable
en escala log). Detalle completo en `docs/reporte_regresion_2a.md` y métricas
crudas en `data/processed/metricas_regresion_2a.{csv,json}`.

## Alternativas consideradas

- **Solo sklearn (HistGradientBoosting):** muy competitivo (incluso mejor RMSE);
  descartado como producción por el margen en MAE, pero se conserva en el zoo.
- **Ridge lineal (referencia interpretable):** inestable al invertir `log1p`
  (predicciones extremas tras `expm1`); se documenta y descarta. Se añadió un
  techo de predicción (`log1p` del máximo histórico) para acotar `expm1` en todos
  los modelos.

## Consecuencias

- Nuevas dependencias: `lightgbm`, `xgboost`, `joblib`.
- Artefacto `models/regresion_v1.joblib` (gitignored) + `regresion_v1.meta.json`
  con versión, fecha, features, transformación, cortes, métricas y semilla.
  Reutilizable por la capa de servicio/API (Fase 3) vía
  `PredictorRegresion.predecir`.
- **Pendiente:** intervalos de predicción (cuantiles de boosting o residuos
  empíricos); pronóstico recursivo multi-horizonte (capa de servicio, Fase 3).

## Reproducibilidad

`spc-train-regresion` (o `python -c "from spc.models.regresion import cli; cli()"`).
Semilla fija 42; cortes temporales y configuración de features versionados en los
metadatos del artefacto. Mismos datos + mismo código + mismo entorno → mismas
métricas.
