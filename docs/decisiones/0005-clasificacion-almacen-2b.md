# ADR 0005 — Clasificación de ALMACÉN (Fase 2b): `demanda_alta`, efecto de SMOTE y umbral de negocio

- **Estado:** Aceptado (2026-06-14)
- **Fase:** 2b — Clasificación (ALMACÉN) — riesgo de quiebre (`demanda_alta`)
- **Contexto previo:** `docs/plan_maestro_spc.md`, `docs/reporte_eda.md`,
  `docs/contrato_datos.md`, cierre 2a (`docs/README_fase2a.md`, ADR `0004`)
- **Reporte detallado:** `docs/reporte_clasificacion_2b.md`
- **No avanza** a 2c (clustering) ni toca la capa API/servicio.

## Contexto

ALMACÉN responde "¿hay riesgo de quiebre?" con un clasificador de **demanda alta**.
Objetivo derivado: `demanda_alta = 1` si `sales > P75` de su **familia**. El plan pide
**mostrar el efecto de SMOTE** (con/sin), reportar métricas de la **clase minoritaria**
y dejar un artefacto portable versionado. Se heredan las lecciones de la 2a: validación
temporal sin fuga, **selección en VALID** (TEST una sola vez), artefacto **portable**
desde el inicio y train-GPU / predict-CPU.

## Decisiones

### 1. Etiqueta honesta: P75 por familia fijado SOLO en TRAIN; familias degeneradas excluidas

- El umbral P75 que define la clase positiva **no puede mirar el futuro**: se calcula
  sobre `date <= 2017-07-14` (TRAIN) por familia y se aplica idéntico a valid/test.
  (La columna `demanda_alta` del dataset integrado usa el P75 sobre todo `train.csv`;
  para la 2b se recalcula train-only para no contaminar la definición de la clase.)
- **Fuga de etiqueta evitada:** la cantidad que define la etiqueta (`sales` del periodo
  actual), `family_sales_p75` y `demanda_alta` **no son features**. Se reutilizan las
  mismas features leak-safe de la 2a (`spc.features.temporales`): solo rezagos/ventanas
  **pasadas** de `sales`, transacciones rezagadas, promoción y calendario. Test dedicado
  (`test_features_clasificacion.py`) verifica que ninguna feature filtra `sales`/
  `demanda_alta` del periodo y que inflar la venta del periodo no altera feature alguna.
- **Familias degeneradas (P75 = 0): `BABY CARE` y `BOOKS`** (2 de 33). En ellas
  `demanda_alta` se reduce a "vendió algo" en vez de "demanda alta" (etiqueta
  degenerada/ruidosa, demanda intermitente). **Decisión: excluirlas del train/eval y
  documentarlo.** El resto de familias de P75 entero bajo (`HARDWARE`, `HOME
  APPLIANCES`, `SCHOOL AND OFFICE SUPPLIES`) se conservan (etiqueta aún significativa,
  prevalencia algo deprimida por empates en el umbral).

### 2. Validación temporal heredada de la 2a (selección en VALID, TEST una sola vez)

Mismos cortes por fecha: **Train ≤ 2017-07-14 · Valid 2017-07-15..07-30 · Test
2017-07-31..08-15** + CV temporal *expanding* (3 folds de 14 días dentro de
TRAIN+VALID, nunca toca TEST). **La estrategia y el umbral se eligen en VALID; TEST se
evalúa una sola vez** sobre la configuración ya elegida. No se repite el error de la 2a
de seleccionar sobre TEST.

> **Hallazgo honesto — la prevalencia sube de TRAIN a VALID/TEST:** con el umbral P75
> fijado en TRAIN y ventas que crecen en el tiempo, la prevalencia de positivos pasa de
> **0.224 (train)** a **0.349 (valid) / 0.347 (test)**. Por eso la **línea sin-skill de
> la PR-AUC es la prevalencia del split evaluado** (no la de train); los `DummyClassifier`
> lo confirman (PR-AUC test ≈ 0.346).

### 3. Experimento central — ¿SMOTE aporta? **No.** Estrategia elegida: sin remuestreo

Tres estrategias sobre la misma validación temporal, mismo booster base (LightGBM):

| estrategia | PR-AUC (VALID) | Recall (VALID) | F1 | Precisión |
|---|---|---|---|---|
| **sin_remuestreo** *(elegida)* | **0.9330** | 0.9935 | 0.6654 | 0.5002 |
| costo_sensible (`scale_pos_weight≈3.27`) | 0.9331 | 0.9930 | 0.6656 | 0.5006 |
| SMOTE (SMOTENC, solo en train del fold) | 0.9327 | 0.9914 | 0.6658 | 0.5012 |

- **SMOTE no supera** a la costo-sensible ni a la base (PR-AUC 0.9327 ≤ 0.9330 ≈ 0.9331;
  las tres difieren < 0.001, dentro de la tolerancia de 0.005). La costo-sensible **no
  mejora de forma material** a la base (la rebasa por 0.0001, dentro del ruido). **Regla
  de decisión:** la estrategia **más simple** dentro de la tolerancia → **sin
  remuestreo**. Mostrar que SMOTE no aporta es un resultado válido y es lo que pedía el
  plan.
- **Por qué SMOTE no ayuda aquí:** el desbalance es **moderado** (~1:3.5), el booster ya
  ordena bien la minoritaria (PR-AUC ≈ 0.93) y SMOTE interpola en el espacio de features
  **ignorando el tiempo** (discutible en datos panel/temporales). El coste extra (SMOTENC
  ~20 min vs ~30 s) no compra nada.
- **Regla de fuga (cumplida):** SMOTE se aplica **solo al train de cada fold** vía
  `imblearn.Pipeline` (SMOTENC, que respeta las categóricas), nunca a valid/test ni al
  dataset completo. Test dedicado verifica que el val de cada fold conserva su
  prevalencia original (no balanceada).

### 4. Modelo de producción y umbral de negocio

- **Modelo:** **LightGBM (binary)** sin remuestreo (`clasificacion_v1`). Booster de
  gradient boosting coherente con la 2a; **entrena en GPU, predice en CPU** (LightGBM
  nativo) → artefacto portable. El artefacto se reajusta sobre **todo el histórico
  etiquetado no degenerado** (2 772 144 filas).
- **Referencia interpretable:** **regresión logística** montada **correctamente** en su
  propio pipeline (estandarización de numéricas + one-hot de categóricas +
  `class_weight='balanced'`): PR-AUC TEST **0.870**, por debajo del booster pero muy por
  encima del azar — un lineal bien montado sí es evidencia (lección del Ridge en la 2a).
- **Umbral elegido en VALID = 0.0175** (no el 0.5 por defecto). **Criterio de negocio:**
  `demanda_alta` señala riesgo de quiebre; **fallar un positivo cuesta más que una falsa
  alarma**, así que se toma el **máximo recall sujeto a precisión ≥ 0.50**. En VALID:
  precisión 0.500, recall 0.994.

### 5. Métricas finales en TEST (configuración elegida, una sola vez)

| métrica (minoritaria) | TEST | contexto |
|---|---|---|
| **PR-AUC** | **0.9342** | sin-skill (prevalencia TEST) 0.347 → **×2.70** sobre el azar |
| **Recall** | **0.9959** | casi todos los positivos detectados |
| **F1** | 0.6511 | |
| **Precisión** | 0.4836 | apenas bajo el piso 0.50 (umbral fijado en VALID, no reajustado a TEST) |
| ROC-AUC | 0.9582 | contexto |

**Matriz de confusión (TEST, umbral 0.0175):** TN 7635 · FP 9868 · FN 38 · TP 9243. El
punto de operación es deliberadamente **recall-prioritario**: marca ~71 % de las filas
como riesgo para capturar el 99.6 % de la demanda alta, a cambio de muchas falsas
alarmas (precisión ~0.48), coherente con el coste asimétrico del quiebre. Supera con
holgura al baseline trivial (`DummyClassifier` PR-AUC ≈ 0.346 = sin-skill).

### 6. Artefacto, registro y portabilidad (correcciones de la 2a aplicadas desde el inicio)

- **`models/clasificacion_v1.joblib`** (+ `.meta.json`) serializado **vía import**
  (`scripts/train_clasificacion.py` o `spc-train-clasificacion`); `PredictorClasificacion`
  se picklea bajo `spc.models.clasificacion` (no `__main__`). **Test de portabilidad** en
  subproceso limpio incluido desde ya.
- **Metadatos:** versión, fecha, features, **estrategia (sin SMOTE), umbral y su
  criterio**, semilla 42, **métricas VALID y TEST** (PR-AUC/recall/F1/precisión),
  matrices de confusión, prevalencias por split, línea sin-skill, familias degeneradas
  excluidas, nota GPU/CPU.
- **Registro persistente** `data/processed/metricas_clasificacion_2b.{csv,json}`: una
  fila por **estrategia × split** (valid/test/cv) — el efecto de SMOTE queda en disco.
- El artefacto **carga y predice sin reentrenar**: devuelve **clase y probabilidad** de
  `demanda_alta` (lo consumirá la Fase 3).

## Métricas vs baseline (resumen)

- **Modelo (LightGBM, sin SMOTE):** PR-AUC TEST **0.934**, recall **0.996**.
- **Baseline trivial (`Dummy`):** PR-AUC ≈ 0.346 (= sin-skill), recall 0.0 (mayoritario).
- **Referencia logística (bien montada):** PR-AUC 0.870.
- **Efecto SMOTE:** nulo (PR-AUC VALID 0.9327 vs 0.9330 sin remuestreo).

> **Reproducibilidad (nota de GPU):** el booster entrena en GPU (LightGBM/OpenCL), que
> introduce un **jitter numérico mínimo** entre corridas (~±0.0006 de PR-AUC). Las cifras
> aquí son las del artefacto de registro `clasificacion_v1`. La **decisión es estable** a
> ese ruido: en todas las corridas las tres estrategias quedan dentro de la tolerancia y
> se elige `sin_remuestreo`; el umbral (~0.0175) y las métricas de TEST (PR-AUC ~0.934,
> recall ~0.996) no cambian de forma material.

## Criterio de "hecho" verificado

- [x] F1, recall y **PR-AUC de la minoritaria** reportados, con matriz de confusión al
      umbral elegido.
- [x] **Efecto de SMOTE** mostrado (tabla con/sin, decisión justificada: no aporta).
- [x] Selección y umbral **en VALID**; TEST evaluado **una sola vez**.
- [x] Artefacto **portable**, serializado y **versionado con su métrica**; registro de
      métricas persistido.
- [x] Tests en verde: no-fuga futuro/etiqueta, SMOTE-solo-en-fold, selección-en-VALID,
      portabilidad, metadatos, supera al baseline en PR-AUC.

## Mejoras diferidas (documentadas, no implementadas)

- **Calibración de probabilidades** (Platt/isotónica) si la probabilidad va a usarse para
  decisiones de stock (el umbral actual prioriza recall; una probabilidad calibrada
  permitiría políticas de stock por nivel de servicio).
- **Métodos específicos de demanda intermitente** para las familias de bajo volumen (las
  degeneradas excluidas y las de P75 entero bajo).

## Reproducibilidad

`python scripts/train_clasificacion.py` (o `spc-train-clasificacion`). GPU por defecto
(`--cpu` para forzar CPU). Semilla 42; cortes, features, estrategia y umbral versionados
en el meta. Mismos datos + mismo código + mismo entorno → mismas métricas (salvo ruido
numérico mínimo de GPU). Dependencia añadida: `imbalanced-learn==0.14.2`.
