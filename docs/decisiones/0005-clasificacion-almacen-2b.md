# ADR 0005 — Clasificación de ALMACÉN (Fase 2b): `demanda_alta`, efecto de SMOTE y umbral de negocio

- **Estado:** Aceptado (2026-06-14)
- **Fase:** 2b — Clasificación (ALMACÉN) — riesgo de quiebre (`demanda_alta`)
- **Contexto previo:** `docs/plan_maestro_spc.md`, `docs/reporte_eda.md`,
  `docs/contrato_datos.md`, cierre 2a (`docs/README_fase2a.md`, ADR `0004`)
- **Reporte detallado:** `docs/reporte_clasificacion_2b.md`
- **No avanza** a 2c (clustering) ni toca la capa API/servicio.

> **Actualización (2026-06-14) — corrección del punto de operación (post-hoc).** El
> umbral por defecto cambió de **0.0175** (`max recall s.t. precisión ≥ 0.50`, que
> degeneraba en marcar **~71 %** de las filas con precisión **~0.48**) a **0.3185**
> (`max recall s.t. precisión ≥ 0.80`, piso REAL, con margen +0.02 VALID→TEST). El
> operativo pasa a marcar **37.4 %** con **precisión 0.81 / recall 0.87 en TEST**. La
> corrección es **post-hoc**: el booster de producción **no se reentrenó** y la
> **conclusión de SMOTE no cambia** (descansa en la PR-AUC, independiente del umbral).
> Detalle en §4–§5 y en la tabla de puntos de operación.

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
- **Umbral por defecto = 0.3185** (elegido en VALID; no el 0.5 por defecto). **Criterio
  de negocio:** `demanda_alta` señala riesgo de quiebre; fallar un positivo cuesta más
  que una falsa alarma, así que se prioriza recall **pero con un piso REAL de
  precisión**: **máximo recall sujeto a precisión ≥ 0.80**, con **margen +0.02 en VALID**
  (piso efectivo 0.82) para que el piso aguante en TEST. En VALID: precisión 0.820,
  recall 0.866. En TEST: precisión 0.809, recall 0.874.

  > **Por qué se cambió el criterio (de 0.50 a 0.80).** El umbral viejo (0.0175, `max
  > recall s.t. precisión ≥ 0.50`) operaba **al borde del precipicio** de la curva PR:
  > marcaba **~71 %** de las filas como riesgo (TEST FP 9868, TP 9243) con precisión
  > **0.484**, apenas por encima de la prevalencia base 0.346 (lift ~1.4×). Síntoma de
  > que era el **umbral** y no el modelo: la regresión logística (PR-AUC 0.870, peor)
  > superaba al LightGBM (PR-AUC 0.934) en F1 (0.749 vs 0.651) porque el booster se
  > operaba donde la precisión colapsa. Como la PR-AUC es 0.934, la curva se mantiene
  > alta hasta ~recall 0.90 y recién ahí se desploma: **retroceder el recall mejora
  > muchísimo la precisión**. El piso 0.50 era demasiado débil para priorizar un
  > almacén; el piso real 0.80 da un operativo accionable. Corrección **post-hoc** (solo
  > umbral/metadatos); el booster y las probabilidades no cambian.

- **Puntos de operación reportados** (umbral elegido **en VALID**; TEST informativo). La
  Fase 3 elige según su tolerancia; la **curva PR completa** (umbral, precisión, recall)
  de VALID se persiste en `data/processed/curva_pr_clasificacion_2b.csv`.

  | punto | umbral | P/R (VALID) | P/R (TEST) | % marcado (TEST) |
  |---|---|---|---|---|
  | **precisión ≥ 0.80** *(DEFAULT)* | 0.3185 | 0.820 / 0.866 | **0.809 / 0.874** | **37.4 %** |
  | máx F1 | 0.4022 | 0.856 / 0.835 | 0.848 / 0.839 | 34.3 % |
  | recall-prioritario (p≥0.50) *(referencia, default viejo)* | 0.0174 | 0.500 / 0.993 | 0.482 / 0.996 | 71.6 % |

### 5. Métricas finales en TEST (default elegido en VALID, una sola vez)

| métrica (minoritaria) | TEST | contexto |
|---|---|---|
| **PR-AUC** | **0.9343** | sin-skill (prevalencia TEST) 0.347 → **×2.70** sobre el azar (independiente del umbral) |
| **Precisión** | **0.809** | respeta el piso 0.80 gracias al margen +0.02 en VALID |
| **Recall** | **0.874** | captura ~87 % de la demanda alta |
| **F1** | 0.840 | |
| ROC-AUC | 0.9582 | contexto |

**Matriz de confusión (TEST, umbral 0.3185):** TN 15587 · FP 1916 · FN 1168 · TP 8113.
El operativo es **accionable**: marca **10 029 filas (37.4 %)** como riesgo (antes ~71 %)
con **precisión ~0.81** (antes ~0.48), capturando el ~87 % de la demanda alta. Las falsas
alarmas caen de 9 868 a 1 916. Supera con holgura al baseline trivial (`DummyClassifier`
PR-AUC ≈ 0.346 = sin-skill).

> **Robustez VALID→TEST.** Con el umbral viejo la precisión se deslizó de 0.50 (valid) a
> 0.484 (test). Con el piso real 0.80 ese deslizamiento importa más, así que el default se
> elige apuntando a precisión ≥ 0.82 en VALID (margen +0.02); en TEST la precisión aterriza
> en 0.809, **por encima del piso 0.80**. La PR-AUC de TEST (0.9343) coincide con la del
> registro original (0.9342) dentro del ruido numérico: el modelo es el mismo.

### 6. Artefacto, registro y portabilidad (correcciones de la 2a aplicadas desde el inicio)

- **`models/clasificacion_v1.joblib`** (+ `.meta.json`) serializado **vía import**
  (`scripts/train_clasificacion.py` o `spc-train-clasificacion`); `PredictorClasificacion`
  se picklea bajo `spc.models.clasificacion` (no `__main__`). **Test de portabilidad** en
  subproceso limpio incluido desde ya.
- **Metadatos:** versión, fecha, features, **estrategia (sin SMOTE), umbral por defecto y
  su criterio**, **tabla de puntos de operación** y **referencia a la curva PR**, semilla
  42, **métricas VALID y TEST** (PR-AUC/recall/F1/precisión) al default, matrices de
  confusión, prevalencias por split, línea sin-skill, familias degeneradas excluidas, nota
  GPU/CPU, **nota de recalibración** (`umbral_anterior`, fecha).
- **Registro persistente** `data/processed/metricas_clasificacion_2b.{csv,json}`: una
  fila por **estrategia × split** (valid/test/cv) — el efecto de SMOTE queda en disco —
  más **una fila por punto de operación × split** (columna `punto`).
- **Curva PR** `data/processed/curva_pr_clasificacion_2b.{csv,json}` (umbral, precisión,
  recall en VALID): la Fase 3 elige su punto de operación sin quedar amarrada al default.
- El artefacto **carga y predice sin reentrenar**: devuelve **clase y probabilidad** de
  `demanda_alta` (lo consumirá la Fase 3).

## Métricas vs baseline (resumen)

- **Modelo (LightGBM, sin SMOTE):** PR-AUC TEST **0.934** (independiente del umbral). Al
  **default (precisión ≥ 0.80)**: precisión **0.809**, recall **0.874**, F1 **0.840**.
- **Baseline trivial (`Dummy`):** PR-AUC ≈ 0.346 (= sin-skill), recall 0.0 (mayoritario).
- **Referencia logística (bien montada):** PR-AUC 0.870.
- **Efecto SMOTE:** nulo (PR-AUC VALID 0.9327 vs 0.9330 sin remuestreo).

> **Reproducibilidad (nota de GPU):** el booster entrena en GPU (LightGBM/OpenCL), que
> introduce un **jitter numérico mínimo** entre corridas (~±0.0006 de PR-AUC). La
> **decisión de SMOTE es estable** a ese ruido: en todas las corridas las tres estrategias
> quedan dentro de la tolerancia y se elige `sin_remuestreo`. La **recalibración del umbral**
> reproduce las probabilidades del modelo elegido en **CPU determinista** (sin jitter); su
> PR-AUC de TEST (0.9343) coincide con la del registro GPU original (0.9342). El umbral por
> defecto (0.3185) y el operativo (precisión 0.81 / recall 0.87 en TEST) son estables.

## Criterio de "hecho" verificado

- [x] F1, recall y **PR-AUC de la minoritaria** reportados, con matriz de confusión al
      umbral por defecto.
- [x] **Efecto de SMOTE** mostrado (tabla con/sin, decisión justificada: no aporta).
- [x] Selección de estrategia y umbral **en VALID**; TEST evaluado **una sola vez**.
- [x] **Umbral por defecto con piso REAL de precisión (0.80) + margen**; **puntos de
      operación** y **curva PR** persistidos para la Fase 3; operativo accionable (no
      degenerado: 37.4 % marcado, precisión 0.81 en TEST).
- [x] Artefacto **portable**, serializado y **versionado con su métrica**; registro de
      métricas persistido.
- [x] Tests en verde: no-fuga futuro/etiqueta, SMOTE-solo-en-fold, selección-en-VALID,
      portabilidad, metadatos, supera al baseline en PR-AUC, **piso real de umbral +
      puntos de operación + recalibración no cambia el booster**.

## Mejoras diferidas (documentadas, no implementadas)

- **Calibración de probabilidades** (Platt/isotónica) si la probabilidad va a usarse para
  decisiones de stock por nivel de servicio (el default fija un punto de operación; una
  probabilidad calibrada permitiría políticas de stock por nivel de servicio sin recablear
  el umbral).
- **Etiqueta no estacionaria (decisión de diseño diferida):** `demanda_alta` usa el **P75
  histórico fijo de TRAIN**; como las ventas crecen, la prevalencia sube de 0.224 (train) a
  ~0.347 (valid/test). Un **percentil móvil** (P75 por ventana reciente) definiría "demanda
  alta" relativa al **régimen actual**, no a un umbral histórico congelado. Cambia el
  **objetivo** (no solo el punto de operación), así que se documenta y **no** se aplica en
  esta corrección de umbral.
- **Métodos específicos de demanda intermitente** para las familias de bajo volumen (las
  degeneradas excluidas y las de P75 entero bajo).

## Reproducibilidad

**Entrenamiento:** `python scripts/train_clasificacion.py` (o `spc-train-clasificacion`).
GPU por defecto (`--cpu` para forzar CPU). Semilla 42; cortes, features, estrategia y
umbral versionados en el meta.

**Recalibración del umbral (post-hoc):** `python scripts/recalibrar_umbral_clasificacion.py`
(CPU determinista por defecto; `--gpu` para reproducir en GPU). **No reentrena** el booster
de producción: reproduce las probabilidades held-out de la estrategia elegida, re-elige el
umbral por defecto en VALID (piso real 0.80, margen +0.02), evalúa TEST una sola vez y
actualiza artefacto+meta, curva PR, registro y reporte. Semilla 42.

Mismos datos + mismo código + mismo entorno → mismas métricas (salvo ruido numérico mínimo
de GPU). Dependencia añadida: `imbalanced-learn==0.14.2`.
