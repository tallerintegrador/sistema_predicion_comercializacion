# Fase 2b — Corrección del punto de operación (ALMACÉN, `demanda_alta`)

> **Estado: ✅ APLICADA** (2026-06-14). Recalibración **post-hoc** del umbral del
> clasificador de riesgo de quiebre. El **booster de producción no se reentrenó**: las
> probabilidades del modelo son las mismas; solo cambió el **punto de operación**
> (umbral) y los metadatos/reportes. La conclusión de SMOTE, las features, los cortes
> temporales y la disciplina de selección en VALID/TEST **siguen intactos**.
>
> Reporte detallado: [`reporte_clasificacion_2b.md`](reporte_clasificacion_2b.md).
> Decisiones: [ADR 0005](decisiones/0005-clasificacion-almacen-2b.md) (actualizado).
> No avanza a la 2c (clustering) ni toca la capa API/servicio.

---

## 1. Resultado en una línea

| | Antes (degenerado) | **Ahora (corregido)** |
|---|---|---|
| **Umbral por defecto** | 0.0175 | **0.3185** |
| **Criterio** | máx recall s.t. precisión ≥ **0.50** | máx recall s.t. precisión ≥ **0.80** (+margen 0.02 VALID→TEST) |
| **Precisión TEST** | 0.484 | **0.809** |
| **Recall TEST** | 0.996 | **0.874** |
| **F1 TEST** | 0.651 | **0.840** |
| **% filas marcadas (TEST)** | ~71 % | **37.4 %** |
| **Falsas alarmas (FP, TEST)** | 9 868 | **1 916** |
| **PR-AUC TEST** (independiente del umbral) | 0.9342 | 0.9343 |
| **Modelo** | `clasificacion_v1` (LightGBM, sin SMOTE) | **el mismo** (no se reentrenó) |
| **Tests** | — | **46 passed** |

**Operativo accionable:** marca la mitad de filas que antes, con precisión 0.81 (antes
0.48), cediendo ~12 pts de recall. Lift sobre la prevalencia base (0.346) sube de ~1.4×
a ~2.3×.

---

## 2. El problema (por qué era el umbral, no el modelo)

El umbral viejo (0.0175) usaba el criterio **máx recall sujeto a precisión ≥ 0.50**. Con
una prevalencia base de 0.346, exigir 0.50 es un **lift de apenas 1.44×**: un piso
demasiado débil. Resultado: operaba **al borde del precipicio** de la curva PR — marcaba
**~71 %** de todas las filas como riesgo (TEST `FP=9868`, `TP=9243`) y la precisión
(0.484) quedaba apenas por encima del azar. Inútil para priorizar un almacén.

**Síntoma de que era el umbral y no el modelo:** la regresión logística (PR-AUC 0.870, el
**peor** modelo) superaba al LightGBM (PR-AUC 0.934) en F1 (0.749 vs 0.651) y precisión
(0.628 vs 0.484), porque el LightGBM se operaba donde la precisión colapsa. Como la PR-AUC
es 0.934, la curva se mantiene alta hasta ~recall 0.90 y recién ahí se desploma:
**retroceder el recall mejora muchísimo la precisión**.

> No se cambió ni el modelo ni las probabilidades: esto es **selección de umbral
> post-hoc**. No se reentrenó ni se re-corrió la comparación de estrategias (SMOTE).

---

## 3. Qué se hizo

| # | Acción | Detalle |
|---|---|---|
| 1 | **Nuevo criterio de umbral** | `máx recall s.t. precisión ≥ 0.80` (piso REAL), con **margen +0.02 en VALID** (piso efectivo 0.82) para que el piso aguante en TEST. |
| 2 | **Puntos de operación** | Se reportan 3: default (p≥0.80), **máx F1**, y recall-prioritario (p≥0.50, el viejo) como referencia. |
| 3 | **Curva PR completa** | `(umbral, precisión, recall)` de VALID persistida en disco (26 784 puntos) para que la Fase 3 elija su tolerancia. |
| 4 | **Robustez VALID→TEST** | Margen +0.02: precisión VALID 0.820 → TEST 0.809, **se mantiene sobre el piso 0.80** (antes se deslizaba bajo el piso). |
| 5 | **TEST una sola vez** | Evaluado al default ya elegido en VALID; los puntos alternativos son informativos. |
| 6 | **Artefacto / meta** | Mismo booster, nuevo umbral + criterio + tabla de puntos + ref. a curva PR + métricas al nuevo umbral. |
| 7 | **Registro, reporte, ADR** | Filas de puntos de operación añadidas; reporte y ADR 0005 actualizados (headline = nuevo default). |

---

## 4. Protocolo de validación (heredado de la 2a, sin cambios)

| Split | Rango | Uso |
|---|---|---|
| **Train** | `<= 2017-07-14` | Ajuste / P75 de la etiqueta (train-only) |
| **Valid** | `2017-07-15 .. 2017-07-30` | **Selección de estrategia y umbral** |
| **Test** | `2017-07-31 .. 2017-08-15` | **Evaluado una sola vez** |

- **Etiqueta honesta:** `demanda_alta = sales > P75(familia)`, con **P75 fijado solo en
  TRAIN** (no mira el futuro). `sales` actual, `family_sales_p75` y `demanda_alta` **no**
  son features.
- **Prevalencia no estacionaria:** sube de 0.224 (train) a 0.349 (valid) / 0.347 (test) —
  el P75 se congela en TRAIN y las ventas crecen. Por eso la **línea sin-skill de la
  PR-AUC = prevalencia del split evaluado** (los `Dummy` lo confirman).
- **Selección del default = en VALID.** TEST nunca se usa para elegir.

---

## 5. Métricas

### 5.1 Nuevo punto de operación por defecto (umbral 0.3185)

| split | Precisión | Recall | F1 | PR-AUC | ROC-AUC |
|---|---|---|---|---|---|
| VALID | 0.8201 | 0.8658 | 0.8423 | 0.9332 | 0.9557 |
| **TEST** | **0.8090** | **0.8742** | **0.8403** | **0.9343** | 0.9582 |

**Matriz de confusión (TEST, umbral 0.3185):**

|  | pred 0 | pred 1 |
|---|---|---|
| **real 0** | 15 587 (TN) | 1 916 (FP) |
| **real 1** | 1 168 (FN) | 8 113 (TP) |

Marca **10 029 / 26 784 filas (37.4 %)** como riesgo (antes ~71 %). Las falsas alarmas
caen de **9 868 a 1 916**.

### 5.2 Puntos de operación (umbral elegido en VALID; TEST informativo)

| punto | umbral | P/R (VALID) | P/R (TEST) | F1 (TEST) | % marcado (TEST) |
|---|---|---|---|---|---|
| **precisión ≥ 0.80** *(DEFAULT)* | 0.3185 | 0.820 / 0.866 | **0.809 / 0.874** | 0.840 | **37.4 %** |
| máx F1 | 0.4022 | 0.856 / 0.835 | 0.848 / 0.839 | 0.844 | 34.3 % |
| recall-prioritario (p≥0.50) *(referencia, viejo)* | 0.0174 | 0.500 / 0.993 | 0.482 / 0.996 | 0.649 | 71.6 % |

> **Curva PR completa** (umbral, precisión, recall, VALID) en
> `data/processed/curva_pr_clasificacion_2b.{csv,json}` (26 784 puntos): la Fase 3 puede
> elegir cualquier punto sin quedar amarrada al default.

### 5.3 Efecto de SMOTE — **intacto** (decisión basada en PR-AUC)

La PR-AUC es **independiente del umbral**, así que la recalibración **no la altera**. La
decisión (no adoptar SMOTE → `sin_remuestreo`) se conserva del entrenamiento original.

| estrategia | PR-AUC (VALID) | ROC-AUC (VALID) |
|---|---|---|
| **sin_remuestreo** *(elegida)* | 0.9330 | 0.9556 |
| costo_sensible | 0.9331 | 0.9556 |
| smote | 0.9327 | 0.9551 |

---

## 6. Enfoque: recalibración post-hoc "lean" (sin reentrenar el booster)

Las probabilidades held-out no estaban persistidas en disco, así que para elegir un umbral
post-hoc se necesita reproducirlas. El flujo lean:

1. **Construye** features / etiqueta / cortes idénticos a la 2a (`preparar_datos`,
   compartido con el entrenamiento → cero deriva de splits).
2. **Reproduce solo** la estrategia elegida (`sin_remuestreo`) ajustada en TRAIN, en
   **CPU determinista** (semilla 42) → probabilidades de VALID/TEST. **No** re-corre
   SMOTE / costo-sensible / CV ni re-decide nada.
3. **Re-elige el umbral** en VALID (piso real 0.80 + margen), calcula los puntos de
   operación y la curva PR, evalúa TEST **una sola vez**.
4. **Aplica:** carga el `.joblib` existente, le fija el nuevo umbral (**el booster de
   producción no se reentrena**) y reescribe meta + curva PR + registro + reporte.

> La PR-AUC de TEST reproducida (0.9343) coincide con la del registro GPU original
> (0.9342) dentro del ruido numérico: **es el mismo modelo**. Un test verifica que las
> probabilidades del artefacto no cambian tras la recalibración.

---

## 7. Artefacto y metadatos

- **`models/clasificacion_v1.joblib`** — el **mismo booster** (LightGBM, sin SMOTE,
  reajustado sobre todo el histórico no degenerado), con el **nuevo umbral por defecto**.
  Se re-picklea bajo `spc.models.clasificacion` (portable, carga en proceso limpio).
- **`models/clasificacion_v1.meta.json`** — nuevo `umbral` (+ `umbral_anterior`),
  `criterio_umbral`, `puntos_operacion`, `curva_pr_ref`, `metricas_valid`/`metricas_test`
  y matrices de confusión **al nuevo umbral**, `fecha_recalibracion`, `nota_recalibracion`.
  Se conserva `metricas_valid_por_estrategia` (registro de la decisión de SMOTE).
- **Train GPU → predict CPU:** el booster se entrenó en GPU; la recalibración reproduce
  las probabilidades en **CPU determinista** y el artefacto predice en CPU.

---

## 8. Reproducir

```bash
# Recalibración post-hoc del umbral (CPU determinista por defecto; NO reentrena el booster):
python scripts/recalibrar_umbral_clasificacion.py

# Variantes:
python scripts/recalibrar_umbral_clasificacion.py --full   # reproducir sin tope de filas (lento)
python scripts/recalibrar_umbral_clasificacion.py --gpu    # reproducir probabilidades en GPU
```

Salidas regeneradas (gitignored): `models/clasificacion_v1.{joblib,meta.json}`,
`data/processed/curva_pr_clasificacion_2b.{csv,json}`,
`data/processed/metricas_clasificacion_2b.{csv,json}` (con filas de puntos de operación),
y el reporte `docs/reporte_clasificacion_2b.md`.

> El **entrenamiento** del modelo (no necesario para esta corrección) sigue siendo
> `python scripts/train_clasificacion.py` (GPU por defecto). El flujo offline completo es
> **entrenar → recalibrar**.

---

## 9. Cargar y predecir (lo que usará la Fase 3)

```python
from pathlib import Path
from spc.models.clasificacion import cargar_predictor

predictor, meta = cargar_predictor(Path("models/clasificacion_v1.joblib"))

# Clase + probabilidad de demanda_alta (usa el umbral por defecto del artefacto = 0.3185):
salida = predictor.predecir(historico_integrado)
#   -> DataFrame [clase_demanda_alta (0/1), probabilidad_demanda_alta]

# Otro punto de operación sin recablear nada (la curva PR está en disco):
salida_f1 = predictor.predecir(historico_integrado, umbral=0.4022)   # máx F1
solo_proba = predictor.predecir_proba(historico_integrado)            # pd.Series [0,1]
```

`historico_integrado` debe traer el esquema del dataset analítico
(`spc.data.integration`). La clase 1 = "demanda alta" = riesgo de quiebre según el
contrato de ALMACÉN.

---

## 10. Tests (46 passed)

```
======================= 46 passed in 480.43s (0:08:00) ========================
```

Cobertura nueva/actualizada de la corrección (`tests/test_clasificacion.py`):

| Test | Qué garantiza |
|---|---|
| `test_umbral_elegido_en_valid_marco_negocio` | El default usa **piso real 0.80** (no 0.5 ni 0.50). |
| `test_seleccionar_umbral_usa_piso_real_080_con_margen` | Piso efectivo = 0.80 + margen; el punto respeta el piso. |
| `test_default_retrocede_recall_vs_recall_prioritario` | El piso 0.80 alcanza **menos recall** que el viejo 0.50 (operativo no degenerado). |
| `test_curva_pr_columnas_y_rango` | La curva PR persistible tiene `(umbral, precisión, recall)` en `[0,1]`. |
| `test_puntos_de_operacion_tres_puntos_un_default` | 3 puntos, exactamente 1 default; el default marca ≤ filas que el recall-prioritario. |
| `test_recalibracion_default_en_valid_no_degenerado` | El default se elige **en VALID** y no opera en el régimen degenerado. |
| `test_recalibracion_actualiza_umbral_sin_cambiar_el_booster` | La recalibración cambia **solo** el umbral; el booster da **las mismas probabilidades**; persiste curva PR + registro. |

(Se mantienen los tests previos de la 2b: no-fuga de futuro/etiqueta, SMOTE-solo-en-fold,
selección-de-estrategia-en-VALID, portabilidad, metadatos, supera al baseline en PR-AUC.)

---

## 11. Decisión de diseño diferida — etiqueta no estacionaria

`demanda_alta` usa el **P75 histórico fijo de TRAIN**; como las ventas crecen, la
prevalencia sube en valid/test. Un **percentil móvil** (P75 por ventana reciente)
definiría "demanda alta" relativa al **régimen actual**, no a un umbral histórico
congelado. Cambia el **objetivo** (no solo el punto de operación), así que se **documenta
y no se aplica** en esta corrección de umbral. (Otras diferidas: calibración de
probabilidades; métodos de demanda intermitente para familias de bajo volumen.)

---

## 12. Archivos y entregables

**Código / scripts / tests**
- [`src/spc/models/clasificacion.py`](../src/spc/models/clasificacion.py) — piso real 0.80 + margen en `seleccionar_umbral`; `curva_pr`, `puntos_de_operacion`; `preparar_datos` compartido; flujo lean `recalibrar_umbral` / `aplicar_recalibracion` / persistencia / reporte / `cli_recalibrar`.
- [`scripts/recalibrar_umbral_clasificacion.py`](../scripts/recalibrar_umbral_clasificacion.py) — entrypoint delgado (nuevo).
- [`tests/test_clasificacion.py`](../tests/test_clasificacion.py) — +6 tests (ver §10).

**Documentación**
- [`docs/reporte_clasificacion_2b.md`](reporte_clasificacion_2b.md) — reporte regenerado (nuevo default + tabla de puntos de operación + matriz al nuevo umbral).
- [`docs/decisiones/0005-clasificacion-almacen-2b.md`](decisiones/0005-clasificacion-almacen-2b.md) — ADR actualizado (cambio de criterio + por qué + tabla + nota de etiqueta no estacionaria).

**Artefactos** (gitignored, regenerables)
- `models/clasificacion_v1.{joblib,meta.json}` (mismo booster, nuevo umbral).
- `data/processed/curva_pr_clasificacion_2b.{csv,json}` (curva PR de VALID).
- `data/processed/metricas_clasificacion_2b.{csv,json}` (+ filas de puntos de operación).

---

## 13. Criterio de "hecho" — verificado ✅

- [x] Umbral por defecto re-elegido **en VALID** con criterio de negocio real (piso 0.80, no 0.50), con margen para que aguante en TEST.
- [x] **Curva PR + tabla de puntos de operación** persistidas y en el reporte.
- [x] TEST evaluado **una sola vez** al nuevo default; métricas honestas (valid 0.820/0.866, test 0.809/0.874).
- [x] Artefacto/meta, registro, reporte y ADR actualizados; **tests en verde (46/46)**.
- [x] El modelo, la conclusión de SMOTE y la validación **siguen intactos** (probabilidades idénticas, verificado por test).
- [x] Operativo **accionable**: 37.4 % marcado, precisión 0.81 (no degenerado).

> No se avanza a la 2c. La capa API/servicio no se tocó.
