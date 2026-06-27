# Experimento de aumento de datos (SMOTE) — SPC

> Documento vivo. Vive en `docs/fase-3/experimento_aumento_datos.md`.
>
> Formaliza, de forma retroactiva, el experimento de **aumento de datos** que ya se
> realizó en la Fase 2 (clasificación). Atiende la recomendación del docente 9: el
> aumento de datos como **experimento medido**, cuyo resultado puede ser "no aporta".
>
> **Honestidad estricta.** Las cifras provienen de la metadata y el reporte de
> clasificación; lo que no quedó registrado se marca `[PENDIENTE]` en vez de inventarlo.

---

## 1. Motivación

El plan del proyecto pedía **mostrar el efecto de SMOTE** (con y sin) sobre la tarea de
clasificación desbalanceada. La recomendación del docente 9 lo enmarca correctamente: el
aumento de datos es un **experimento**, no un paso obligatorio. Un resultado válido del
experimento es **descubrir que no aporta** y, en consecuencia, **no adoptarlo**. Eso es lo
que ocurrió aquí, y este documento lo deja escrito como tal.

---

## 2. Qué se probó

- **Técnica:** SMOTE en su variante **SMOTENC** (Synthetic Minority Over-sampling para
  datos con features **categóricas y numéricas**), que respeta las columnas categóricas al
  sintetizar ejemplos.
- **Tarea:** la **clasificación** de ALMACÉN/INVENTORY, objetivo
  `demanda_alta = sales > P75 de su familia`.
- **Clase minoritaria aumentada:** los positivos (`demanda_alta = 1`), la clase de
  "demanda alta". El desbalance real medido en el EDA es **moderado, ~1:3.5** (22.37 % de
  positivos con el umbral por familia).
- **Booster base (idéntico en las tres estrategias):** **LightGBM**.
- **Alcance:** el aumento de datos se probó **solo en clasificación**. La regresión
  (SALES) tiene **objetivo continuo** y no es candidata a SMOTE; el desbalance es un
  fenómeno de clasificación.

Se compararon **tres estrategias** sobre la misma validación temporal:

1. **`sin_remuestreo`** — el booster sobre los datos tal cual.
2. **`costo_sensible`** — `scale_pos_weight ≈ 3.27` (pondera la clase positiva, sin
   sintetizar datos).
3. **`smote`** — SMOTENC sobre el train.

---

## 3. Diseño leak-safe (sin fuga de datos)

El aumento de datos es una fuente clásica de fuga si se aplica mal. Aquí:

- SMOTE se aplicó **solo al train de cada fold**, mediante `imblearn.Pipeline` (SMOTENC),
  **nunca** a valid/test ni al dataset completo.
- Un **test dedicado** verifica que el conjunto de validación de cada fold **conserva su
  prevalencia original** (no balanceada): si SMOTE hubiera tocado validación, la
  prevalencia se habría alterado.
- La validación es **temporal** (cortes por fecha; selección en VALID, TEST una sola vez),
  coherente con el resto del proyecto.

Fuente del diseño: [ADR-0005 §3](../decisiones/0005-clasificacion-almacen-2b.md),
[reporte_clasificacion_2b.md](../reporte_clasificacion_2b.md).

---

## 4. Resultado (cifras reales)

La decisión descansa en la **PR-AUC** (métrica principal de la minoritaria, **independiente
del umbral**). Resultados sobre **VALID** (donde se decide):
Fuente: [clasificacion_v1.meta.json](../../models/clasificacion_v1.meta.json) (`criterio_seleccion`),
[metricas_clasificacion_2b.json](../../data/processed/metricas_clasificacion_2b.json).

| estrategia | PR-AUC (VALID) | ROC-AUC (VALID) |
|---|---|---|
| `sin_remuestreo` *(elegida)* | **0.9330** | 0.9556 |
| `costo_sensible` | 0.9331 | 0.9556 |
| `smote` (SMOTENC) | **0.9327** | 0.9551 |

- Las tres estrategias difieren en **menos de 0.001** de PR-AUC, **dentro de la tolerancia
  de 0.005** fijada de antemano.
- **SMOTE no supera** ni a la base ni a la costo-sensible (0.9327 ≤ 0.9330 ≈ 0.9331).
- **Coste:** SMOTENC añadía un coste de cómputo notable (**~20 min** frente a **~30 s** sin
  remuestreo) sin comprar mejora alguna.

---

## 5. Conclusión y decisión

**Decisión: no se adopta SMOTE.** La regla de decisión, fijada antes de mirar el
resultado, es elegir la **estrategia más simple** cuya PR-AUC en VALID esté dentro de la
tolerancia de la mejor (`sin_remuestreo` < `costo_sensible` < `smote`); SMOTE solo se
adoptaría si **superara** a la costo-sensible por más de la tolerancia. No lo hizo →
**`sin_remuestreo`**.

**Por qué SMOTE no ayuda en este problema (interpretación honesta):**

- El desbalance es **moderado** (~1:3.5), no extremo.
- El booster ya **ordena bien** la clase minoritaria sin ayuda (PR-AUC ≈ 0.93).
- SMOTE **interpola en el espacio de features ignorando el tiempo**, lo cual es discutible
  en datos de panel/temporales como estos.

Mostrar con números que el aumento de datos **no aporta** es, en sí mismo, el entregable
que pedía la recomendación 9: el experimento se hizo, se midió y se concluyó.

> **Nota de reproducibilidad.** El booster entrena en GPU, lo que introduce un jitter
> numérico mínimo (~±0.0006 de PR-AUC) entre corridas. La **decisión es estable** a ese
> ruido: en todas las corridas las tres estrategias quedan dentro de la tolerancia y se
> elige `sin_remuestreo`. Dependencia usada: `imbalanced-learn==0.14.2`.

---

## 6. Qué no se probó / `[PENDIENTE]`

- **Hiperparámetros exactos de SMOTENC** (`k_neighbors`, `sampling_strategy` / ratio
  objetivo): **`[PENDIENTE]`** — no quedaron registrados en la metadata ni en el reporte.
  No se infieren aquí. Para una formalización completa habría que recuperarlos del script
  de entrenamiento de la Fase 2 (coordinación con el equipo de modelado).
- **Otras técnicas de aumento** (ADASYN, Borderline-SMOTE, under-sampling, SMOTE-Tomek):
  no se probaron; quedaron fuera del alcance del experimento.
- **Métodos específicos de demanda intermitente** para las familias de bajo volumen
  (las degeneradas excluidas y las de P75 entero bajo): diferidos.

---

## 7. Referencias

- [ADR-0005 — Clasificación de ALMACÉN (Fase 2b): `demanda_alta`, efecto de SMOTE y umbral de negocio](../decisiones/0005-clasificacion-almacen-2b.md)
- [reporte_clasificacion_2b.md](../reporte_clasificacion_2b.md)
- [clasificacion_v1.meta.json](../../models/clasificacion_v1.meta.json)
- [reporte_eda.md §8.2](../reporte_eda.md) — desbalance real (22.37 % positivos)
- [Documento central de alcance, validación y limitaciones](alcance_validacion_limitaciones.md)
