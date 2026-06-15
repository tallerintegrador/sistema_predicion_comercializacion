# Auditoría de cierre — Fase 2a (Regresión / VENTAS)

> **Fecha:** 2026-06-14 · **Rama:** `develop` · **Alcance:** solo Fase 2a (Regresión de VENTAS). No incluye 2b ni capa API/servicio.
> **Modo:** reporte de estado con evidencia concreta. No se aplicaron correcciones; al final se proponen los arreglos.

---

## Resumen ejecutivo

| # | Ítem | Estado |
|---|---|---|
| 1 | Test de no-fuga de futuro | ✅ **SÍ** (3 passed) |
| 2 | Serialización (carga + predice + feature engineering) | ⚠️ **PARCIAL** (pickle bajo `__main__`, no portable) |
| 3 | Metadatos completos | ✅ **SÍ** (transformación = `identidad`, no `log1p` literal) |
| 4 | Métrica honesta persistida | ⚠️ **PARCIAL** (en meta y desgloses; **no** en `metricas_regresion_2a.csv/json`) |
| 5 | Selección sobre VALID o TEST | ❌ **NO** (gate ensemble decidido en TEST) |
| 6 | Headline honesto | ❌ **NO** (cita MAE 51.308 teacher-forced en vez de la recursiva) |

**Veredicto:** la 2a **aún no** cumple el criterio de "hecho". Bloqueantes reales: **#2** (artefacto no portable) y **#5** (selección sobre TEST contamina la métrica reportada). #4 y #6 son de trazabilidad/consistencia del entregable.

---

## 1. Test de no-fuga de futuro — **SÍ** ✅

Existe y pasa en verde. Archivo: `tests/test_features_regresion.py`.

- `test_lags_no_usan_el_valor_actual` (línea 10): verifica que `sales_lag_1[0]` es `NaN` (sin pasado), que `lag_1`/`lag_7` son exactamente `sales[k-1]`/`sales[k-7]`, y que `sales_rmean_7[k]` usa solo la ventana `[t-7, t-1]` (jamás incluye `t`).
- `test_modificar_el_futuro_no_altera_features_pasadas` (línea 41): garantía fuerte — inflar la venta más futura de cada serie en `+1e6` **no cambia ninguna** columna de rezago/ventana (`shift` antes de la ventana).
- `test_transacciones_solo_como_rezago` (línea 31): `transactions` no entra como feature del periodo; solo como rezago.

Salida de `pytest` (intérprete del `venv`):

```
tests\test_features_regresion.py ...                                     [100%]
============================== 3 passed in 1.03s ==============================
```

---

## 2. Serialización del artefacto — **PARCIAL** ⚠️

El artefacto `regresion_v3` **sí carga y predice sin reentrenar e incluye el feature engineering** (la clase `PredictorRegresion` reconstruye las features con `construir_features` dentro de `predecir()`, `src/spc/models/regresion.py` L426).

Demostración real (cargado desde `models/regresion_v3.joblib`):

```
Artefacto cargado: models\regresion_v3.joblib
  modelo        : Ensemble(XGBoost+XGBoost_Tweedie+LightGBM_Tweedie+LightGBM)
  tipo objeto   : PredictorRegresion
Prediccion de prueba sobre 560 filas -> n predicciones: 560, todas >= 0: True
Forecast recursivo 7 dias: (28, 4) -> ['date','store_nbr','family','demanda_pronosticada']
```

**PERO** hay un defecto de portabilidad: el artefacto fue serializado ejecutando el módulo **como script** (`if __name__ == "__main__": cli()`, L1809 → `entrenar()` llama a `serializar_artefacto`, L1741). Por eso las clases quedaron pickleadas bajo `__main__`, no bajo `spc.models.regresion`. La carga **falla de fábrica**:

```
AttributeError: module '__main__' has no attribute 'PredictorRegresion'
...y tras aliasar solo esa:
AttributeError: module '__main__' has no attribute 'ModeloEnsemble'
```

Solo cargó después de inyectar manualmente `__main__.PredictorRegresion` **y** `__main__.ModeloEnsemble`. La capa de servicio que haga `cargar_artefacto("regresion_v3.joblib")` se romperá. El test `test_artefacto_serializa_recarga_y_predice_igual` pasa porque ahí el módulo se importa normalmente (clases en `spc.models.regresion`), así que **el test no detecta este caso** — solo afecta al artefacto de producción ya generado.

---

## 3. Metadatos del artefacto — **SÍ** (con matiz) ✅

Existe `models/regresion_v3.meta.json` junto al `.joblib`, con todo lo exigido:

| Campo requerido | Presente | Valor |
|---|---|---|
| versión | ✅ | `regresion_v3` |
| fecha de entrenamiento | ✅ | `2026-06-14` |
| lista de features | ✅ | 50+ features (`sales_lag_*`, `sales_rmean_*`, calendario, oil, categóricas…) |
| transformación | ✅ (matiz) | `transformacion_objetivo: "identidad"`, `espacio_objetivo: "unidades"` |
| semilla | ✅ | `42` |
| **métricas del modelo de producción** | ✅ | `metricas_test` (TF) **y** `metricas_test_recursivo` (honesta) |

**Matiz sobre `log1p`:** el campo de transformación dice `"identidad"`, no `"log1p"`. Es correcto: el **ensemble** combina submodelos ya en unidades, y los miembros log invierten internamente con `expm1`. El `log1p` queda documentado en el encabezado del reporte y en `config_features`, pero el predictor de producción reporta `identidad`. No es un error, pero conviene saberlo si esperabas ver `log1p` literal en el meta.

---

## 4. Métrica honesta persistida — **PARCIAL** ⚠️

La métrica honesta recursiva del ensemble **sí está en disco**, pero **no en el registro de métricas** canónico:

- ✅ En `models/regresion_v3.meta.json` → `metricas_test_recursivo`: `MAE 59.389`, `RMSE 205.007`, `WAPE 12.713`, y `metricas_test_recursivo_baseline`.
- ✅ Desgloses en `data/processed/wape_recursivo_por_familia.csv`, `_por_tienda.csv`, `_semanal.csv`, `_mensual.csv` (persistidos en `persistir_metricas`, L1372).
- ❌ **NO** en `data/processed/metricas_regresion_2a.csv` ni en su `.json`. Ese registro solo contiene filas `split ∈ {valid, test, cv_fold_*}` de los modelos **individuales** en teacher forcing. **No hay ninguna fila `Ensemble` ni ninguna fila recursiva** (grep de `Ensemble|recursiv|honest` sobre el CSV: 0 coincidencias).

Es decir: la métrica guía del proyecto vive en el meta del artefacto, pero el "registro de métricas" canónico de la 2a no la incluye como fila propia. **Pendiente.**

---

## 5. ¿Selección sobre VALID o TEST? — **Sobre TEST** ❌

Evidencia en código (`src/spc/models/regresion.py` L1234-1280):

- Los **pesos/miembros** del ensemble se eligen en VALID (`construir_ensemble(..., idx_valid, ...)`, L1235). ✔️
- El **ganador individual** se elige por CV temporal sobre TRAIN+VALID (`_elegir_ganador`, no toca TEST). ✔️
- **PERO** la decisión ensemble-vs-individual se toma comparando WAPE recursivo calculado **sobre TEST**:

```python
metricas_rec_ens, _ = evaluar_recursivo(pred_ens_honesto, analytic, cortes)  # cortes.test_ini..test_fin
if metricas_rec_ens["WAPE"] < metricas_rec["WAPE"]:   # gate sobre TEST
```

Y `evaluar_recursivo` proyecta exactamente el rango `cortes.test_ini..test_fin` (L748-756).

**Conclusión:** TEST se usó para seleccionar (ensemble 12.713% vs `LightGBM_Tweedie` 13.618%, ambos recursivos sobre TEST). Por tanto el WAPE/MAE honesto reportado queda **ligeramente optimista** (el conjunto que decidió es el mismo que se reporta).

**Recomendación:** correr la evaluación recursiva también en VALID y mover ahí el gate ensemble-vs-individual; reportar TEST **una sola vez, intacto**.

---

## 6. Coherencia del headline — **NO** ❌

El headline del reporte cita el número teacher-forced inflado. En `docs/reporte_regresion_2a.md` L35:

```
- MAE elegido = 51.308 vs mejor baseline = 90.840 -> mejora 43.5%.
- RMSE elegido = 179.453 vs mejor baseline = 297.306 -> mejora 39.6%.
```

Ese `51.308` es `metricas_test` (teacher forcing, rezagos reales del horizonte) — el mismo del meta. La métrica **honesta** (recursiva, la que el propio reporte llama "métrica guía") está más abajo:

- **MAE 59.389 vs baseline honesto 96.535 → 38.5%**
- **WAPE 12.71% vs 20.67% → −7.95 pts**

El encabezado debería abrir con la honesta, no con la teacher-forced.

---

## Correcciones propuestas (no ejecutadas — se mostrarán diffs antes de commitear)

1. **(P2 · bloqueante) Regenerar `regresion_v3` de forma portable.** Hacer que el guardado ocurra siempre con las clases resueltas a `spc.models.regresion` (entrenar vía import, p. ej. desde `scripts/`, en lugar de ejecutar `regresion.py` como `__main__`), y/o mover `cli()` a un entrypoint delgado en `scripts/`. Añadir un **test de portabilidad** que cargue el `.joblib` en un proceso limpio sin aliasar `__main__`.
2. **(P4) Persistir la fila honesta del ensemble** en `metricas_regresion_2a.csv/json`: agregar filas `modelo="Ensemble(...)"` con `split="test_recursivo"` (y los baselines recursivos), dentro de `persistir_metricas`.
3. **(P5 · bloqueante) Mover el gate ensemble-vs-individual a VALID:** calcular `evaluar_recursivo` sobre VALID para decidir, dejar TEST solo para el reporte final (una vez). Ajustar `criterio_seleccion` para registrar que la decisión fue en VALID.
4. **(P6) Reescribir el headline** del reporte para encabezar con la métrica honesta recursiva (MAE 59.39 vs 96.54 → 38.5%; WAPE 12.71% vs 20.67%), y degradar el 51.308 TF a "referencia teacher-forced (optimista)".
5. **(P3 · menor)** Aclarar en el meta/reporte que `transformacion_objetivo="identidad"` corresponde al ensemble en unidades y que los submodelos usan `log1p` internamente (evita lectura errónea).

---

## ¿Queda cumplido el criterio de "hecho" de la 2a tras estos arreglos?

En esta lectura: **casi, pero todavía no**. Los puntos 1 y 3 ya cumplen. Los bloqueantes reales para declarar cerrada la 2a son **#2 (artefacto no portable)** y **#5 (selección sobre TEST contamina la métrica reportada)**; #4 y #6 son de trazabilidad/consistencia del entregable. Con las 4-5 correcciones aplicadas y los tests en verde (incluido el nuevo de portabilidad), **sí** se considera la 2a cerrada de forma consistente.
