# Fase 2a — Regresión (VENTAS): cierre con revisión de auditoría

> **Estado: ✅ CERRADA** (2026-06-14). Motor de ML de la regresión de demanda
> `sales`, entrenado **offline** y serializado como artefacto que la API solo
> **carga y predice** (no reentrena en caliente). Capa de motor: no conoce HTTP ni
> el negocio del cliente.
>
> Este documento es el **reporte detallado y autocontenido** del cierre. Para el
> detalle de tablas ver [`reporte_regresion_2a.md`](reporte_regresion_2a.md); para
> las decisiones, el [ADR 0004](decisiones/0004-cierre-fase2a-revision.md).

---

## 1. Resultado en una línea

| | Valor |
|---|---|
| **Modelo de producción** | `Ensemble(XGBoost + XGBoost_Tweedie + LightGBM + LightGBM_Poisson)` |
| **Pesos del ensemble** | `[0.256, 0.254, 0.250, 0.240]` (convexos, elegidos en VALID) |
| **Artefacto** | `models/regresion_v3.joblib` (+ `.meta.json`) |
| **Métrica guía (WAPE honesto recursivo, TEST)** | **14.59 %** |
| **vs mejor baseline honesto** | 20.67 % → **−6.08 puntos** |
| **MAE / RMSE honesto vs baseline** | 68.15 vs 96.54 (**−29.4 %**) · 235.73 vs 348.38 (**−32.3 %**) |
| **Validación** | temporal sin fuga · selección en **VALID** · TEST evaluado **una sola vez** |
| **Entrenamiento** | **GPU** (boosters) · el artefacto **predice en CPU** (portable) |
| **Tests** | **27 passed** (no-fuga, serialización, gate-en-valid, portabilidad) |

---

## 2. Qué se corrigió (auditoría → cierre)

La auditoría ([`auditoria_fase2a.md`](auditoria_fase2a.md)) detectó dos bloqueantes y
varios puntos de trazabilidad. Todos resueltos:

| # | Hallazgo | Corrección |
|---|---|---|
| 1 | **Selección sobre TEST** (gate ensemble decidido en el mismo conjunto que se reporta → métrica optimista) | Gate movido a **VALID** (recursivo honesto). TEST se evalúa **una vez** sobre el modelo ya elegido. `criterio_seleccion.decision_en="valid"`. |
| 2 | **Artefacto no portable** (pickle bajo `__main__` → `AttributeError` al cargar desde proceso limpio) | Entrenamiento **vía import** (`scripts/train_regresion.py`); se quitó el bloque `if __name__=="__main__"`. Artefacto regenerado. **Test de portabilidad** en subproceso limpio. |
| 3 | **Métrica honesta sin fila propia** en el registro canónico | `persistir_metricas` agrega filas `split="test_recursivo"` (modelo + baselines) a `metricas_regresion_2a.{csv,json}`. |
| 4 | **Headline teacher-forced** (optimista) | Reporte abre con la **métrica honesta recursiva**; el número teacher-forced queda como "referencia optimista". |
| 5 | Ambigüedad de `transformacion_objetivo="identidad"` | `nota_transformacion` en meta + reporte: el modelo predice en **unidades**; los submodelos `log` invierten con `expm1` internamente. |
| 6 | (extra) GPU | Boosters entrenan en GPU; el artefacto predice en **CPU** (portable). |

> **Aviso esperado y cumplido:** al dejar de seleccionar sobre TEST, el WAPE honesto
> subió de **12.71 %** (contaminado) a **14.59 %** (correcto). No es un retroceso; es
> el número honesto. No se "ajustó" nada para recuperar el 12.71 %.

---

## 3. Protocolo de validación temporal (sin fuga)

Cortes por fecha derivados de la fecha máxima observada (espejo del horizonte real de
*Store Sales — Corporación Favorita*):

| Split | Rango | Uso |
|---|---|---|
| **Train** | `<= 2017-07-14` | Ajuste de modelos |
| **Valid** | `2017-07-15 .. 2017-07-30` (16 d) | Pesos del ensemble + **gate ensemble-vs-individual** |
| **Test** | `2017-07-31 .. 2017-08-15` (16 d) | **Reporte final, evaluado una sola vez** |

- **Validación cruzada temporal** *expanding* (3 folds de 14 días dentro de
  TRAIN+VALID, nunca toca TEST) → elige el **ganador individual** por estabilidad.
- **Sin fuga de futuro:** todo rezago/ventana se calcula por serie
  `(store_nbr, family)` con `shift` **antes** de la ventana; transacciones solo como
  rezago; promoción del día sí (planificada). Verificado por tests (ver §8).
- **Teacher forcing vs recursivo honesto:** la métrica por split alimenta los rezagos
  con ventas **reales** del horizonte (optimista). La **métrica guía** es el
  pronóstico **recursivo multi-paso** (autorregresivo, como en producción): el modelo
  reinyecta sus propias predicciones día a día.

---

## 4. Métricas

### 4.1 Métrica guía — recursivo honesto (TEST, una sola vez)

| fuente (recursivo) | WAPE | MAE | RMSE | RMSLE |
|---|---|---|---|---|
| **Ensemble (producción)** | **14.59 %** | **68.15** | **235.73** | 0.423 |
| baseline naïve(t-7) | 20.67 % | 96.54 | 348.38 | 0.617 |
| baseline media_móvil_7 | 23.26 % | 108.66 | 359.82 | 0.531 |

**Mejora vs mejor baseline honesto:** MAE −29.4 % · RMSE −32.3 % · WAPE −6.08 pts.

> *Referencia teacher-forced (optimista, NO es la métrica guía):* el ensemble alcanza
> WAPE 12.40 % · MAE 57.91 · RMSE 202.39 cuando se le dan los rezagos reales del
> horizonte. Sirve solo como cota superior optimista.

### 4.2 Comparación de modelos (TEST, teacher forcing, ordenado por MAE)

| modelo | WAPE | MAE | RMSE | RMSLE |
|---|---|---|---|---|
| LightGBM_Tweedie *(ganador individual)* | 12.41 | 57.96 | 197.09 | 0.389 |
| XGBoost_Tweedie | 12.43 | 58.05 | 211.74 | 0.387 |
| XGBoost | 13.07 | 61.05 | 216.07 | 0.384 |
| LightGBM_Poisson | 13.22 | 61.77 | 214.66 | 0.401 |
| LightGBM | 14.18 | 66.23 | 234.33 | 0.386 |
| HistGradientBoosting | 14.45 | 67.50 | 236.53 | 0.387 |
| RandomForest | 16.35 | 76.38 | 305.82 | 0.411 |
| baseline media_móvil_7 | 19.45 | 90.84 | 297.31 | 0.449 |
| baseline naïve(t-7) | 21.46 | 100.23 | 350.06 | 0.569 |
| Ridge | — | 743.72 *(retirado, no apto)* | — | — |

> **Jerarquía de métricas:** WAPE → MAE → RMSE → RMSLE. El **MAPE (~34 %) está
> inflado** por el 31 % de ceros en `sales` (excluye los días de venta cero y
> sobre-pondera series de bajo volumen); no se usa como métrica principal. `R²` es
> contexto, no criterio de selección.

---

## 5. Selección del modelo de producción

1. **Ganador individual** = `LightGBM_Tweedie`, elegido por **estabilidad** en la CV
   temporal (regla: dentro de la banda de ruido del MAE de CV, menor `RMSE_std`).
2. **Pesos/miembros del ensemble** = combinación convexa de los mejores boosters en
   VALID (`top-k=4`).
3. **Gate ensemble-vs-individual (en VALID, recursivo honesto):**
   - WAPE VALID ensemble = **12.18 %** vs individual `LightGBM_Tweedie` = **14.25 %**
     → **gana el ensemble** (−2.1 pts). Es el modelo de producción.
4. **Artefacto final:** los submodelos del ensemble se **reajustan sobre todo el
   histórico etiquetado** (2 950 992 filas). El submuestreo de comparación es 250 000.

> La composición difiere del artefacto previo (que mezclaba `LightGBM_Tweedie` en vez
> de `LightGBM_Poisson`): el `top-k` por MAE en VALID cambió al comparar con
> submuestreo de 250 k en lugar de `--full`. Diferencia esperada de la nueva corrida.

---

## 6. Artefacto: portabilidad y train-GPU / predict-CPU

- **Portabilidad.** El entrenamiento se lanza **por import** (`scripts/train_regresion.py`
  o el console-script `spc-train-regresion`), nunca ejecutando `regresion.py` como
  `__main__`. Así `PredictorRegresion` / `ModeloEnsemble` se picklean bajo
  `spc.models.regresion` y el `.joblib` **carga desde un proceso limpio** (la API hace
  `cargar_artefacto` sin aliasar `__main__`).
- **Train GPU → predict CPU.** Los boosters entrenan en GPU, pero tras `fit` la
  predicción de XGBoost se conmuta a `device="cpu"` (`_post_fit_cpu`). El artefacto se
  **sirve sin GPU** en producción (verificado: submodelos XGBoost con `device=cpu`).
- **Contenido del meta** (`regresion_v3.meta.json`): versión, fecha, modelo,
  `criterio_seleccion` (con `decision_en="valid"`, `wape_valid_*`, miembros, pesos),
  `transformacion_objetivo`, `nota_transformacion`, 59 features (6 categóricas),
  config de features, cortes temporales, `metricas_test` (TF), `metricas_test_recursivo`
  (honesta) + baselines, semilla 42, `n_filas_comparacion` / `n_filas_artefacto_final`.

---

## 7. GPU

- Hardware verificado: **NVIDIA RTX 3050 Laptop (4 GB)**.
- **Boosters en GPU:** XGBoost `device="cuda"` (`tree_method="hist"`), LightGBM
  `device="gpu"` (backend OpenCL del wheel). LightGBM CUDA no está compilado en el
  wheel y no se usa.
- **HistGradientBoosting, RandomForest, Ridge = CPU**: scikit-learn no tiene backend
  GPU (límite de la librería, no una decisión).
- Flag `usar_gpu`: **True** por defecto en `entrenar`/`cli` (producción); **False** en
  `entrenar_y_comparar` (suite de tests portable, sin dependencia de GPU). Semilla 42
  fija (la GPU introduce un ruido numérico mínimo, reproducible).

---

## 8. Reproducir

```bash
# Entrenamiento offline (GPU por defecto; comparación con submuestreo de 250k,
# artefacto final sobre todo el histórico):
python scripts/train_regresion.py

# Variantes:
python scripts/train_regresion.py --full          # comparar también sobre todo el histórico
python scripts/train_regresion.py --cpu            # forzar CPU (sin GPU)
python scripts/train_regresion.py --sin-ensemble   # solo modelos individuales
python scripts/train_regresion.py --hpo            # búsqueda de hiperparámetros (Optuna)

# Equivalente vía console-script (tras `pip install -e .`):
spc-train-regresion
```

Salidas regeneradas (gitignored): `models/regresion_v3.{joblib,meta.json}`,
`data/processed/metricas_regresion_2a.{csv,json}`, los desgloses
`wape_recursivo_*.csv`, `importancias_regresion_2a.csv`, y el reporte
`docs/reporte_regresion_2a.md`.

---

## 9. Cargar y predecir (lo que usará la Fase 3)

La capa de servicio/API solo **carga y predice**. El predictor reconstruye las
features internamente desde un histórico ya integrado.

```python
from pathlib import Path
from spc.models.regresion import cargar_predictor

predictor, meta = cargar_predictor(Path("models/regresion_v3.joblib"))

# Predicción por fila (teacher forcing: asume rezagos reales conocidos):
serie = predictor.predecir(historico_integrado)            # pd.Series (unidades, >= 0)

# Pronóstico recursivo multi-horizonte (autorregresivo, como en producción):
fc = predictor.pronosticar_horizonte(historico_integrado, "2017-08-16", "2017-08-22")
#   -> DataFrame [date, store_nbr, family, demanda_pronosticada]
```

`historico_integrado` debe traer el esquema del dataset analítico
(`spc.data.integration`). El pronóstico recursivo nulifica las ventas del horizonte y
reinyecta sus predicciones para alimentar los rezagos del día siguiente.

---

## 10. Tests (27 passed)

```
======================= 27 passed in 283.18s (0:04:43) ========================
```

Cobertura clave de la 2a:

| Test | Qué garantiza |
|---|---|
| `test_features_regresion.py` (3) | **No-fuga de futuro**: rezagos = valor desplazado; ventanas solo miran el pasado; inflar la venta más futura no altera ninguna feature; transacciones solo como rezago. |
| `test_regresion.py::test_modelo_supera_al_baseline` | El ganador supera al baseline (MAE y RMSE). |
| `test_regresion.py::test_artefacto_serializa_recarga_y_predice_igual` | Carga sin reentrenar, predice idéntico, incluso sobre un subconjunto de una serie. |
| `test_regresion.py::test_metadatos_artefacto_completos` | Metadatos completos (versión, features, semilla, criterio, métricas…). |
| `test_regresion.py::test_metrica_honesta_recursiva_supera_baseline` | La métrica guía (WAPE recursivo) existe y bate al baseline honesto. |
| `test_regresion.py::test_gate_ensemble_se_decide_en_valid` | **El gate se decide en VALID**, no en TEST. |
| `test_portabilidad.py` (2) | Clases bajo `spc.models.regresion` (no `__main__`); el artefacto **carga y predice en un subproceso limpio**. |

---

## 11. Mejoras diferidas (documentadas, no implementadas)

- **Intervalos de predicción:** cuantiles de boosting (`quantile`/`pinball`) o residuos
  empíricos del holdout.
- **Enfoque zero-inflated / two-part:** clasificar cero vs. positivo y regredir solo
  los positivos (31 % de ceros); evaluar si reduce el sesgo en series intermitentes.
- **Familias intermitentes de bajo volumen:** algunas familias (`BOOKS`, `BABY CARE`,
  `HOME APPLIANCES`…) muestran **WAPE alto** en el desglose pero **MAE trivial**
  (fracciones de unidad): el WAPE se dispara al dividir errores minúsculos entre ventas
  casi nulas. No afecta el WAPE agregado (ponderado por volumen) ni al negocio.

---

## 12. Archivos y entregables

**Código / scripts / tests**
- [`src/spc/models/regresion.py`](../src/spc/models/regresion.py) — motor de la 2a (gate en VALID, GPU, persistencia, reporte).
- [`scripts/train_regresion.py`](../scripts/train_regresion.py) — entrypoint delgado (entrena vía import → artefacto portable).
- [`tests/test_portabilidad.py`](../tests/test_portabilidad.py), [`tests/test_regresion.py`](../tests/test_regresion.py), [`tests/test_features_regresion.py`](../tests/test_features_regresion.py).

**Documentación**
- [`docs/reporte_regresion_2a.md`](reporte_regresion_2a.md) — reporte generado (tablas, desgloses, importancias).
- [`docs/decisiones/0004-cierre-fase2a-revision.md`](decisiones/0004-cierre-fase2a-revision.md) — ADR de cierre.
- [`docs/decisiones/0002-...`](decisiones/0002-modelo-regresion-ventas.md) · [`0003-...`](decisiones/0003-cierre-fase2a-regresion.md) — antecedentes.
- [`docs/auditoria_fase2a.md`](auditoria_fase2a.md) · [`docs/plan_maestro_spc.md`](plan_maestro_spc.md) · [`docs/contrato_datos.md`](contrato_datos.md).

**Artefactos** (gitignored, regenerables)
- `models/regresion_v3.joblib` + `regresion_v3.meta.json`.
- `data/processed/metricas_regresion_2a.{csv,json}` (incluye filas `split="test_recursivo"`).
- `data/processed/wape_recursivo_{por_familia,por_tienda,semanal,mensual}.csv`, `importancias_regresion_2a.csv`.

---

## 13. Criterio de "hecho" — verificado ✅

- [x] Selección **en VALID**; TEST evaluado una sola vez (métrica honesta no contaminada).
- [x] Artefacto **portable** (carga en proceso limpio; test dedicado).
- [x] Métrica honesta **persistida** como fila del registro canónico.
- [x] Headline honesto; transformación aclarada.
- [x] Supera al baseline honesto (MAE −29.4 %, RMSE −32.3 %, WAPE −6.08 pts).
- [x] No-fuga + portabilidad + gate-en-VALID testeados (**27/27 verde**).

> No se avanza a la 2b. La capa API/servicio no se tocó.
