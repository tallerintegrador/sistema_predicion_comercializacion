# Reporte de Clasificacion (Fase 2b) - ALMACEN (`demanda_alta`)

> Generado por `spc.models.clasificacion`. Objetivo: `demanda_alta = sales > P75 de su familia` (umbral P75 fijado **solo en TRAIN**). Validacion temporal sin fuga; seleccion de estrategia y umbral en **VALID**; TEST evaluado **una sola vez**. La cantidad que define la etiqueta (`sales` actual) **no es feature**: solo rezagos/ventanas pasadas, igual que la 2a.

## Etiqueta y desbalance

- **Prevalencia de positivos (TRAIN):** 0.2244 (~1:3.5) — el desbalance moderado que anticipaba el EDA (~22 %).
- **La prevalencia sube en valid/test** (VALID 0.3488, TEST 0.3465): el umbral P75 se fija en TRAIN y, como las ventas crecen en el tiempo, mas dias superan ese umbral historico. Por eso la **linea sin-skill de la PR-AUC es la prevalencia del split evaluado** (no la de train); los `Dummy` lo confirman abajo.
- **Familias totales:** 33. **Degeneradas excluidas (P75<=0)**: ['BABY CARE', 'BOOKS'] (2 de 33). En ellas `demanda_alta` se reduce a 'vendio algo' en vez de 'demanda alta' (etiqueta ruidosa); se documentan y se excluyen del train/eval.

## Cortes temporales (heredados de la 2a)

- **Train:** <= 2017-07-14
- **Valid:** 2017-07-15 .. 2017-07-30  (seleccion de estrategia y umbral)
- **Test:** 2017-07-31 .. 2017-08-15  (evaluado una sola vez)

## Efecto de SMOTE - comparacion de estrategias (VALID, al umbral elegido)

Mismo booster base (LightGBM). SMOTE aplicado **solo en train, dentro de cada fold** (SMOTENC, via `imblearn.Pipeline`). PR-AUC es independiente del umbral (metrica principal de la minoritaria); recall/F1/precision al umbral de negocio elegido en VALID.

| estrategia | PR_AUC | Recall | F1 | Precision | ROC_AUC | umbral |
| --- | --- | --- | --- | --- | --- | --- |
| sin_remuestreo | 0.933 | 0.9935 | 0.6654 | 0.5002 | 0.9556 | 0.0175 |
| costo_sensible | 0.9331 | 0.993 | 0.6656 | 0.5006 | 0.9556 | 0.0339 |
| smote | 0.9327 | 0.9914 | 0.6658 | 0.5012 | 0.9551 | 0.0192 |

**Decision:** estrategia = **`sin_remuestreo`** (SMOTE NO se adopta). estrategia mas simple (sin_remuestreo < costo_sensible < smote) cuya PR-AUC en VALID esta dentro de 0.005 de la mejor; SMOTE solo se adopta si SUPERA a la costo-sensible por mas de esa tolerancia.

- PR-AUC VALID por estrategia: {'sin_remuestreo': 0.933, 'costo_sensible': 0.9331, 'smote': 0.9327}.
- Recall VALID por estrategia: {'sin_remuestreo': 0.9935, 'costo_sensible': 0.993, 'smote': 0.9914}.
- SMOTE solo se adoptaria si superara a la costo-sensible por > 0.005 de PR-AUC en VALID. Mostrar que no aporta es un resultado valido.

## Umbral elegido (marco de negocio)

- **Umbral = 0.0175** (no el 0.5 por defecto). Criterio: max recall sujeto a precision >= 0.50 (marco de negocio: fallar un positivo -no detectar demanda alta- cuesta mas que una falsa alarma).
- En VALID al umbral: precision=0.5002, recall=0.9935.

## Resultado final en TEST (configuracion elegida, una sola vez)

- **PR-AUC = 0.9342** vs linea sin-skill (prevalencia TEST) 0.3465 -> **x2.70** sobre el azar.
- **Recall (minoritaria) = 0.9959** | **F1 = 0.6511** | **Precision = 0.4836**.
- ROC-AUC (contexto) = 0.9582.
- (VALID de referencia: PR-AUC 0.9330, recall 0.9935.)
- Nota: la precision en TEST (0.4836) queda apenas por debajo del piso de 0.50 usado en VALID; es el efecto esperado de fijar el umbral en VALID y evaluar TEST una sola vez (sin reajustar a TEST).

### Matriz de confusion en TEST (al umbral elegido)

|  | pred 0 | pred 1 |
|---|---|---|
| **real 0** | 7635 (TN) | 9868 (FP) |
| **real 1** | 38 (FN) | 9243 (TP) |

## Referencia interpretable y baselines triviales (TEST)

Regresion logistica en pipeline propio (estandarizacion + one-hot + `class_weight='balanced'`) y `DummyClassifier` (mayoritario/estratificado, PR-AUC ~ prevalencia = sin-skill).

| modelo | PR_AUC | Recall | F1 | Precision | ROC_AUC |
| --- | --- | --- | --- | --- | --- |
| LogisticReg(balanced) | 0.8696 | 0.9285 | 0.749 | 0.6276 | 0.9215 |
| Dummy(mayoritario) | 0.3465 | 0.0 | 0.0 | 0.0 | 0.5 |
| Dummy(estratificado) | 0.3486 | 0.2395 | 0.2861 | 0.3551 | 0.5044 |

## Jerarquia de metricas

**PR-AUC** (principal, minoritaria, independiente del umbral) -> **recall** (marco de negocio: no detectar demanda alta cuesta mas) -> **F1** -> **precision**. **Accuracy no** se usa como principal (enganha con clases desbalanceadas). ROC-AUC es contexto.

## Notas de diseno

- Features reutilizadas de la 2a (`spc.features.temporales`), leak-safe: `sales` actual, `family_sales_p75` y `demanda_alta` **no** son features.
- Umbral P75 fijado **solo en TRAIN** (no mira el futuro).
- SMOTE **solo en train, dentro de cada fold** (nunca valid/test ni el dataset completo). SMOTE interpola en el espacio de features ignorando el tiempo (discutible en datos panel): por eso es un candidato a evaluar, no un default.
- Booster entrena en GPU, **predice en CPU** (artefacto portable).

## Mejoras diferidas (documentadas, no implementadas)

- **Calibracion de probabilidades** (Platt/isotonica) si la probabilidad se usa para decisiones de stock.
- **Metodos especificos de demanda intermitente** para las familias de bajo volumen (las degeneradas excluidas y las de P75 entero bajo).
