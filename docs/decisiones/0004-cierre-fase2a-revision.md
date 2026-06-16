# ADR 0004 — Cierre con revisión de la Fase 2a (Regresión / VENTAS)

- **Estado:** Aceptado (2026-06-14)
- **Fase:** 2a — Regresión (VENTAS) — cierre definitivo tras auditoría
- **Sustituye/actualiza:** ADR `0003-cierre-fase2a-regresion.md` (cierre previo) y, por
  herencia, `0002-modelo-regresion-ventas.md`
- **Contexto previo:** `docs/auditoria_fase2a.md`, `docs/reporte_regresion_2a.md`,
  `docs/plan_maestro_spc.md`, `docs/contrato_datos.md`

## Contexto

La auditoría de cierre (`docs/auditoria_fase2a.md`) detectó dos **bloqueantes** y
varios puntos de trazabilidad en el entregable de la 2a, pese a que el modelo ya
superaba al baseline:

1. **Selección sobre TEST (fuga de evaluación).** El gate ensemble-vs-individual se
   decidía comparando el WAPE recursivo **sobre TEST**, el mismo conjunto que luego
   se reportaba. Eso vuelve la métrica reportada **optimista** (se selecciona y se
   reporta sobre el mismo holdout).
2. **Artefacto no portable.** El `.joblib` se serializó ejecutando `regresion.py`
   como `__main__`, así que `PredictorRegresion` / `ModeloEnsemble` quedaron
   pickleadas bajo `__main__` y la carga **falla desde un proceso limpio**
   (`AttributeError: module '__main__' has no attribute 'PredictorRegresion'`), lo
   que rompería la Fase 3 (la API solo carga y predice).
3. **Métrica honesta sin fila propia** en el registro canónico
   `data/processed/metricas_regresion_2a.csv` (solo vivía en el meta y en la prosa).
4. **Headline del reporte** encabezaba con el número *teacher-forced* (optimista).

Este ADR registra las correcciones y el cierre definitivo. No se avanza a 2b ni se
toca la capa API/servicio.

## Decisiones

### 1. La selección se mueve a VALID; TEST se evalúa una sola vez

La decisión ensemble-vs-individual se toma ahora por **WAPE honesto recursivo sobre
VALID**, no sobre TEST. El protocolo honesto quedó así:

- **Ganador individual:** por estabilidad en validación cruzada temporal
  (expanding) sobre TRAIN+VALID (regla del ADR 0003, sin cambios).
- **Pesos/miembros del ensemble:** elegidos en VALID (convexos, sin tocar TEST).
- **Gate ensemble-vs-individual:** ambos modelos se entrenan **solo con TRAIN** y se
  proyectan de forma recursiva (autorregresiva) sobre **VALID**; gana el de menor
  WAPE honesto en VALID.
- **TEST queda intacto:** solo se evalúa **una vez**, sobre el modelo ya elegido,
  para el reporte final. `criterio_seleccion.decision_en = "valid"`.

`evaluar_recursivo(..., ventana="valid"|"test")` parametriza la ventana proyectada.

> Como anticipaba la auditoría, al no seleccionar sobre TEST el WAPE honesto
> reportado **sube ligeramente** respecto al 12.71 % anterior (que estaba
> contaminado). Es el número correcto, no un retroceso.

### 2. Modelo de producción elegido

**`Ensemble(XGBoost + XGBoost_Tweedie + LightGBM + LightGBM_Poisson)`** — combinación
convexa en unidades, pesos `[0.256, 0.254, 0.250, 0.240]`.

- **Ganador individual** (por estabilidad en CV temporal): `LightGBM_Tweedie`.
- **Gate en VALID** (WAPE honesto recursivo): ensemble **12.18 %** vs individual
  **14.25 %**. El ensemble baja el WAPE de VALID en ~2.1 puntos, así que es el modelo
  de producción. Si el individual hubiera ganado en VALID se habría usado (más simple
  de servir); aquí el margen del ensemble es claro y consistente.
- La composición del ensemble difiere de la del artefacto previo (que mezclaba
  `LightGBM_Tweedie` en vez de `LightGBM_Poisson`): el `top-k` por MAE en VALID
  cambió al comparar con submuestreo de 250 k filas en lugar de `--full`. Es una
  diferencia esperada de la nueva corrida; no afecta el procedimiento.
- El predictor predice en **unidades** (`transformacion_objetivo="identidad"`); los
  submodelos `log` invierten con `expm1` internamente (ver decisión 6).

### 3. Artefacto portable (entrenamiento vía import)

- Se eliminó el bloque `if __name__ == "__main__": cli()` de
  `src/spc/models/regresion.py`. El módulo **ya no se ejecuta como script**.
- El entrenamiento offline se lanza por **import**: `scripts/train_regresion.py`
  (entrypoint delgado) o el console-script `spc-train-regresion` (pyproject), ambos
  hacen `from spc.models.regresion import cli`. Así las clases serializadas se
  resuelven a `spc.models.regresion` y el `.joblib` carga desde un proceso limpio.
- **Test de portabilidad** (`tests/test_portabilidad.py`): serializa un artefacto y
  lo carga/predice en un **subproceso limpio** (sin aliasar `__main__`). Falla con el
  artefacto viejo (`AttributeError __main__`) y pasa con el nuevo.

### 4. Evaluación: teacher-forcing → recursiva honesta (hallazgo)

La evaluación por split (teacher forcing) alimenta los rezagos con las ventas
**reales** del horizonte y por eso **sobreestima** la precisión. La métrica guía del
proyecto es el **pronóstico recursivo multi-paso** (autorregresivo, como en
producción): el modelo reinyecta sus propias predicciones día a día. El reporte
abre ahora con la métrica honesta; el número teacher-forced queda como "referencia
optimista".

### 5. Métrica honesta persistida en el registro canónico

`persistir_metricas` agrega al `metricas_regresion_2a.{csv,json}` filas con
`split="test_recursivo"` para el **modelo de producción** y los **baselines**
(WAPE/MAE/RMSE/RMSLE/MAPE/R²). La métrica guía existe ahora como fila propia, no
solo en la prosa.

### 6. Aclaración de la transformación

`transformacion_objetivo="identidad"` significa que el modelo de producción predice
en **unidades** directamente (objetivo Tweedie o ensemble en unidades). Los
submodelos del espacio `log` sí entrenan en `log1p(sales)` e invierten internamente
con `expm1` antes de combinarse; el `log1p` aplica a esos submodelos, no a la salida
final. Documentado en el meta (`nota_transformacion`) y en el reporte.

### 7. GPU para el entrenamiento (predicción en CPU)

Los **boosters** entrenan en GPU (XGBoost `device="cuda"`, LightGBM `device="gpu"`
vía OpenCL); HistGradientBoosting, RandomForest y Ridge son de scikit-learn y **no
tienen backend GPU** (siguen en CPU; es un límite de la librería). Tras el ajuste se
**conmuta la predicción de XGBoost a CPU** (`_post_fit_cpu`): el motor entrena en GPU
pero el **artefacto se sirve sin GPU** en producción (portable). El parámetro
`usar_gpu` es `True` por defecto en `entrenar`/`cli` (producción) y `False` en
`entrenar_y_comparar` (tests portables, sin dependencia de GPU). Semilla fija 42.

## Métricas finales (TEST, escala de unidades)

Métrica **guía = pronóstico recursivo multi-paso honesto** (autorregresivo), evaluado
sobre TEST **una sola vez** tras seleccionar en VALID:

| fuente (recursivo honesto) | WAPE | MAE | RMSE | RMSLE |
|---|---|---|---|---|
| **Ensemble (producción)** | **14.59 %** | **68.15** | **235.73** | 0.423 |
| baseline naïve(t-7) | 20.67 % | 96.54 | 348.38 | 0.617 |
| baseline media_móvil_7 | 23.26 % | 108.66 | 359.82 | 0.531 |

El modelo de producción supera al mejor baseline honesto: **MAE −29.4 %, RMSE −32.3 %,
WAPE −6.08 puntos**.

> **Subida esperada del WAPE honesto:** antes se reportaba 12.71 %, pero ese número
> estaba **contaminado** (se seleccionaba el ensemble sobre el mismo TEST que se
> reportaba). Con la selección movida a VALID, el WAPE honesto sobre TEST sube a
> **14.59 %**. Es el número correcto, no un retroceso.
>
> *Referencia teacher-forced (optimista, NO es la métrica guía):* el ensemble alcanza
> WAPE 12.40 % · MAE 57.91 · RMSE 202.39 en TEST cuando se le alimentan los rezagos
> reales del horizonte. Útil solo como cota superior optimista.

Detalle completo (desglose por familia/tienda, agregados semanal/mensual) en
`docs/reporte_regresion_2a.md`; métricas crudas (incluida la fila
`split="test_recursivo"`) en `data/processed/metricas_regresion_2a.{csv,json}`.

## Estrategia de validación temporal

Cortes por fecha sin fuga: **Train ≤ 2017-07-14 · Valid 2017-07-15..07-30 · Test
2017-07-31..08-15** (16 días = espejo del horizonte real del test de Corporación
Favorita) + validación cruzada temporal expanding (3 folds de 14 días dentro de
TRAIN+VALID, nunca toca TEST). El gate ensemble-vs-individual se decide en **VALID**;
TEST se evalúa **una sola vez** sobre el modelo elegido.

## Mejoras diferidas (documentadas, no implementadas)

- **Intervalos de predicción:** cuantiles de boosting (`quantile`/`pinball`) o
  residuos empíricos del holdout.
- **Enfoque zero-inflated / two-part:** clasificar cero vs. positivo y regredir solo
  los positivos, dado el 31 % de ceros; evaluar si reduce el sesgo en series
  intermitentes.
- **Familias intermitentes de bajo volumen:** algunas familias (p. ej. `BOOKS`,
  `BABY CARE`, `HOME APPLIANCES`) muestran **WAPE alto** en el desglose pero su
  **MAE es trivial** (fracciones de unidad): el WAPE se dispara al dividir errores
  minúsculos entre ventas casi nulas. No afecta el WAPE agregado (ponderado por
  volumen) ni al negocio; se trataría, si acaso, con el enfoque two-part de arriba.

## Criterio de "hecho" verificado

- **No-fuga de futuro:** `tests/test_features_regresion.py` (3 tests).
- **Artefacto recargable y portable:** `tests/test_regresion.py` (mismo proceso) +
  `tests/test_portabilidad.py` (**proceso limpio / subproceso**).
- **Selección en VALID:** `tests/test_regresion.py::test_gate_ensemble_se_decide_en_valid`.
- **Metadatos completos** y **métrica honesta persistida** como fila del registro.

## Consecuencias

- Artefacto **`models/regresion_v3.joblib`** regenerado de forma portable (gitignored)
  + `regresion_v3.meta.json` con métricas honestas finales y `nota_transformacion`.
- Nuevo entrypoint `scripts/train_regresion.py`; `regresion.py` ya no corre como
  `__main__`.
- Dependencias sin cambios (la GPU usa los mismos `xgboost`/`lightgbm`; XGBoost trae
  soporte CUDA en su wheel, LightGBM usa el backend OpenCL del wheel).

## Reproducibilidad

`python scripts/train_regresion.py` (o `spc-train-regresion`). GPU por defecto
(`--cpu` para forzar CPU). Semilla 42; cortes, features y criterio de selección
versionados en el meta. Mismos datos + mismo código + mismo entorno → mismas
métricas (salvo ruido numérico mínimo de GPU).
