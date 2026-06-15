# Reporte de Clasificacion (Fase 2b) - ALMACEN (`demanda_alta`)

> Generado por `spc.models.clasificacion`. Objetivo: `demanda_alta = sales > P75 de su familia` (umbral P75 fijado **solo en TRAIN**). Validacion temporal sin fuga; seleccion de estrategia y umbral en **VALID**; TEST evaluado **una sola vez**. La cantidad que define la etiqueta (`sales` actual) **no es feature**: solo rezagos/ventanas pasadas, igual que la 2a.

> **Punto de operacion recalibrado (post-hoc).** El default ya **no** es el recall-prioritario (precision>=0.50), que degeneraba en marcar ~71 % de las filas con precision ~0.48 (lift de solo ~1.4x sobre la prevalencia). El nuevo default usa un **piso REAL de precision (0.80)** y toma el maximo recall que lo respeta. El **booster de produccion no cambio**: es solo recalibracion del umbral (las probabilidades del modelo son las mismas).

## Etiqueta y desbalance

- **Prevalencia de positivos (TRAIN):** 0.2244 (~1:3.5) — el desbalance moderado que anticipaba el EDA (~22 %).
- **La prevalencia sube en valid/test** (VALID 0.3488, TEST 0.3465): el umbral P75 se fija en TRAIN y, como las ventas crecen en el tiempo, mas dias superan ese umbral historico. Por eso la **linea sin-skill de la PR-AUC es la prevalencia del split evaluado** (no la de train); los `Dummy` lo confirman abajo.
- **Familias totales:** 33. **Degeneradas excluidas (P75<=0)**: ['BABY CARE', 'BOOKS'] (2 de 33). En ellas `demanda_alta` se reduce a 'vendio algo' en vez de 'demanda alta' (etiqueta ruidosa); se documentan y se excluyen del train/eval.

## Cortes temporales (heredados de la 2a)

- **Train:** <= 2017-07-14
- **Valid:** 2017-07-15 .. 2017-07-30  (seleccion de estrategia y umbral)
- **Test:** 2017-07-31 .. 2017-08-15  (evaluado una sola vez)

## Efecto de SMOTE - comparacion de estrategias (VALID)

Mismo booster base (LightGBM). La decision de SMOTE descansa en la **PR-AUC** (metrica principal de la minoritaria, **independiente del umbral**); por eso la recalibracion del umbral **no la altera**. ROC-AUC de contexto (tambien independiente del umbral).

| estrategia | PR_AUC_valid | ROC_AUC_valid |
| --- | --- | --- |
| sin_remuestreo | 0.933 | 0.9556 |
| costo_sensible | 0.9331 | 0.9556 |
| smote | 0.9327 | 0.9551 |

**Decision (intacta):** estrategia = **`sin_remuestreo`** (SMOTE NO se adopta). estrategia mas simple (sin_remuestreo < costo_sensible < smote) cuya PR-AUC en VALID esta dentro de 0.005 de la mejor; SMOTE solo se adopta si SUPERA a la costo-sensible por mas de esa tolerancia.

## Umbral por defecto (marco de negocio: piso REAL de precision)

- **Umbral = 0.3185** (no el 0.5 por defecto, **ni** el viejo recall-prioritario). Criterio: max recall sujeto a precision >= 0.80 (piso de negocio REAL, no 0.50; margen +0.02 en VALID -> piso efectivo 0.82- para que el piso aguante en TEST).
- En VALID al umbral: precision=0.8201, recall=0.8658, F1=0.8423.
- En TEST al umbral: precision=0.8090, recall=0.8742, F1=0.8403 (el piso de precision aguanta gracias al margen +0.02 en VALID).

### Puntos de operacion (umbral elegido en VALID; TEST informativo)

Para que la **Fase 3** elija segun su tolerancia (no quede amarrada a un solo umbral). La **curva PR completa** (umbral, precision, recall) de VALID se persiste en `data/processed/curva_pr_clasificacion_2b.csv`.

| punto | umbral | P_valid | R_valid | F1_valid | P_test | R_test | F1_test | %marcado_test |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| max recall s.t. precision >= 0.80 (DEFAULT) | 0.3185 | 0.8201 | 0.8658 | 0.8423 | 0.809 | 0.8742 | 0.8403 | 37.4 |
| max F1 | 0.4022 | 0.8558 | 0.8347 | 0.8451 | 0.8483 | 0.8387 | 0.8435 | 34.3 |
| max recall s.t. precision >= 0.50 (referencia) | 0.0174 | 0.5001 | 0.9934 | 0.6653 | 0.4818 | 0.9959 | 0.6494 | 71.6 |

## Resultado final en TEST (default elegido en VALID, una sola vez)

- **PR-AUC = 0.9343** vs linea sin-skill (prevalencia TEST) 0.3465 -> **x2.70** sobre el azar (independiente del umbral; no cambia con la recalibracion).
- Al **default**: precision=0.8090, recall=0.8742, F1=0.8403. ROC-AUC (contexto) = 0.9582.
- El operativo es **accionable**: marca 10029 filas (37.4 %) como riesgo (antes ~71 %), con precision ~0.81 (antes ~0.48).
- (VALID de referencia: precision 0.8201, recall 0.8658.)

### Matriz de confusion en TEST (al default)

|  | pred 0 | pred 1 |
|---|---|---|
| **real 0** | 15587 (TN) | 1916 (FP) |
| **real 1** | 1168 (FN) | 8113 (TP) |

## Referencia interpretable y baselines triviales (TEST, umbral 0.5)

Regresion logistica en pipeline propio (estandarizacion + one-hot + `class_weight='balanced'`) y `DummyClassifier` (mayoritario/estratificado, PR-AUC ~ prevalencia = sin-skill). Recall/F1/precision al **0.5 por defecto** (no al umbral de negocio); la PR-AUC es la comparacion limpia.

| modelo | PR_AUC | Recall | F1 | Precision | ROC_AUC |
| --- | --- | --- | --- | --- | --- |
| LogisticReg(balanced) | 0.8696 | 0.9285 | 0.749 | 0.6276 | 0.9215 |
| Dummy(mayoritario) | 0.3465 | 0.0 | 0.0 | 0.0 | 0.5 |
| Dummy(estratificado) | 0.3486 | 0.2395 | 0.2861 | 0.3551 | 0.5044 |

## Jerarquia de metricas

**PR-AUC** (principal, minoritaria, independiente del umbral) -> **recall** (marco de negocio: no detectar demanda alta cuesta mas) -> **F1** -> **precision**. El **umbral por defecto** ya no maximiza recall a ciegas: exige un **piso real de precision (0.80)** para que el operativo sea accionable. **Accuracy no** se usa como principal (enganha con clases desbalanceadas). ROC-AUC es contexto.

## Notas de diseno

- Features reutilizadas de la 2a (`spc.features.temporales`), leak-safe: `sales` actual, `family_sales_p75` y `demanda_alta` **no** son features.
- Umbral P75 fijado **solo en TRAIN** (no mira el futuro).
- SMOTE **solo en train, dentro de cada fold** (nunca valid/test ni el dataset completo).
- Booster entrena en GPU, **predice en CPU** (artefacto portable). La recalibracion reproduce las probabilidades en **CPU determinista** y solo cambia el umbral del artefacto (el modelo no se reentrena).

## Mejoras diferidas (documentadas, no implementadas)

- **Calibracion de probabilidades** (Platt/isotonica) si la probabilidad se usa para decisiones de stock por nivel de servicio.
- **Etiqueta no estacionaria:** `demanda_alta` usa el **P75 historico fijo de TRAIN**; con ventas crecientes la prevalencia sube en valid/test. Un **percentil movil** (P75 por ventana reciente) definiria 'demanda alta' relativa al regimen actual. Es una decision de **diseno de etiqueta** diferida (cambia el objetivo, no solo el umbral); se documenta y no se aplica aqui.
- **Metodos especificos de demanda intermitente** para las familias de bajo volumen (las degeneradas excluidas y las de P75 entero bajo).
