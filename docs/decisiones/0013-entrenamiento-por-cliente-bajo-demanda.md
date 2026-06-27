# ADR 0013 — Entrenamiento por cliente bajo demanda (Camino A completo)

- **Estado:** Aceptado (2026-06-20).
- **Fase:** A (completa) — el segundo y último paso del "Camino A" del documento de entrega
  ([SPC_Entrega_Despliegue_Valentin.md](../SPC_Entrega_Despliegue_Valentin.md) §8): tras la
  **acumulación** del corpus ([ADR-0011](0011-persistencia-corpus-incremental.md)), ahora el
  **ajuste/reentrenamiento por cliente**, opt-in, local y validado.
- **Contexto previo:** [ADR-0008](0008-modos-ejecucion.md) (modos en línea/lote, modelo
  congelado, almacén in-process), [ADR-0009](0009-transferibilidad-modelo-congelado.md)
  (modelo congelado; ajuste por cliente como dirección futura), [ADR-0011](0011-persistencia-corpus-incremental.md)
  (corpus incremental + puente manual de reentrenamiento). Recomendaciones del docente
  (plataforma agnóstica; el cliente trae sus datos; aumento de datos como experimento medido).
- **No toca** el motor de ML congelado ni los artefactos base (`models/*.joblib`): se añaden
  una **capa de training** (`spc.training.*`), un **resolutor de serving por cliente**
  (`spc.service.modelo_cliente`) y endpoints `/training/*`. El único cambio al motor es un
  par de kwargs **opcionales** (`dias_test`/`dias_valid`) en `entrenar_y_comparar`, con
  **defaults que reproducen exactamente** el entrenamiento del congelado.

## Contexto

[ADR-0011](0011-persistencia-corpus-incremental.md) dejó el corpus **acumulándose** pero el
reentrenamiento como **paso manual** (`exportar_corpus.py` → `train_*.py` en GPU). El Camino A
completo pide que el **propio cliente** pueda mejorar el modelo con sus datos, **bajo demanda**
y **sin saturar** el servicio de predicción. El riesgo es doble: (a) un reentrenamiento mal
hecho degrada el servicio o el modelo; (b) prometer "ajuste por cliente" sin demostrar que
mejora sería deshonesto. La decisión enmarca el ajuste como un **experimento medido** cuyo
resultado puede ser "no mejora", siguiendo el mismo patrón ya usado con SMOTE
([experimento_aumento_datos.md](../fase-3/experimento_aumento_datos.md)).

## Decisión

Se implementa el **entrenamiento por cliente bajo demanda** para **SALES (regresión)**, bajo
cinco invariantes:

### 1. OPT-IN; el default congelado queda intacto

Solo se reentrena cuando el cliente lo pide (`POST /training/sales/excel`). El camino de
predicción por defecto (modelo **congelado**) **no cambia** para nadie más: un cliente sin
modelo adoptado recibe exactamente la misma respuesta de hoy (verificado byte a byte en
`tests/api/test_entrenamiento_cliente.py`). La capacidad se habilita a nivel de despliegue con
`SPC_CLIENT_ADJ_ENABLED` (si está off, los endpoints responden 503 y el serving es siempre el
congelado).

### 2. Local y DESACOPLADO de la predicción

El entrenamiento corre como **trabajo asíncrono in-process** en un `ThreadPoolExecutor`
**separado** del de lote (`spc.api.jobs_entrenamiento.GestorEntrenamientos`), de modo que un
entrenamiento pesado no compite por los hilos de la predicción. El disparo devuelve **202** con
un `job_id` (igual que el modo lote); el estado/fase honesta (`validating` → `training` →
`evaluating`) se consulta en `GET /training/jobs/{id}` y el resultado en
`GET /training/jobs/{id}/result`. **Seam de nube:** el trabajo solo lee el corpus (SQLite) y
escribe artefactos en `models/clientes/`; si el serving migra a la nube, el entrenamiento puede
ejecutarse en otro proceso/host sin tocar el camino de predicción.

### 3. HONESTIDAD: experimento medido + adopción condicionada

Cada reentrenamiento corre un **experimento** (`spc.training.cliente`):

1. **Validación temporal honesta**, con ventana **adaptativa a la historia** del cliente: cada
   holdout (valid y test) dura `round(dias_utiles · 0.15)` recortado a `[7, 16]` días (16 = la
   ventana del congelado). Se entrena en lo temprano, se valida en lo tardío.
2. Se mide el **WAPE recursivo** (la métrica guía del proyecto, autorregresiva) del **candidato
   por cliente** vs el **modelo congelado** vs un **baseline ingenuo** (naive t-7 / media móvil),
   los tres sobre la **misma ventana TEST** (`evaluar_recursivo` reutilizado para el congelado).
3. **Regla de adopción fijada de antemano:** se adopta el modelo por cliente **sii**
   `WAPE_candidato < WAPE_congelado − margen` (margen `SPC_CLIENT_ADJ_MIN_IMPROVEMENT`, default
   **0.0** = cualquier mejora estricta) **y** `WAPE_candidato ≤ WAPE_baseline`.
4. **"No mejora" es un resultado válido que se reporta** (`outcome=not_adopted`), no se esconde;
   el candidato igualmente se guarda para auditoría, pero **no se sirve**: sigue el congelado.

### 4. Poca historia → aviso honesto (no se entrena a ciegas)

Antes de entrenar se exige un mínimo de datos (`SPC_CLIENT_ADJ_MIN_DAYS=60`,
`MIN_ROWS=120`, `MIN_SERIES=1`, y días útiles suficientes para la ventana). Si no se cumple,
el trabajo termina con `outcome=insufficient_data` listando **qué falta**; no se entrena ni se
adopta nada.

### 5. Artefactos por cliente portables, versionados y namespaced

Cada cliente tiene `models/clientes/<slug>/regresion_v{N}.joblib` (+ `.meta.json`,
`comparacion_v{N}.json`, `adopcion.json`). Son **portables** (las clases viven en
`spc.models.regresion`, no en `__main__`, igual que el congelado) y **conviven** con los
congelados sin reemplazarlos. Reentrenar **incrementa N** (historial); adoptar mueve el puntero.
El serving por cliente se resuelve en `spc.service.modelo_cliente` (cache por slug+versión); el
modelo por cliente se sirve **solo a ESE cliente**, con un **switch reversible**
(`POST /training/sales/serving`).

### 6. Reúso de la cañería existente (sin duplicar lógica)

- **Ingesta**: el mismo `lector.leer_peticion(..., "sales")` y la misma validación **strict**
  que la predicción por Excel.
- **Traducción**: el mismo `adaptador.historico_a_analitico` contrato→motor.
- **Corpus**: la **dedup** por serie-día (recién aprobada) vive una sola vez en
  `spc.service.corpus` y la usan tanto `scripts/exportar_corpus.py` como el training. Los datos
  por defecto **funden** Excel + corpus deduplicado del cliente (`source=merged`).
- **Motor**: el pipeline honesto completo (`entrenar_y_comparar`, `evaluar_recursivo`).

> **Nota de robustez.** Un cliente nuevo no aporta petróleo (`dcoilwtico` siempre NaN) ni a
> veces transacciones; el binner de `HistGradientBoosting` no admite features todo-NaN **al
> entrenar** (sí al predecir, por eso el congelado no lo sufre). El training neutraliza esas
> columnas todo-NaN a una constante (sin señal) sobre el **mismo frame** con que se mide
> candidato y congelado, de modo que la comparación sigue siendo justa.

## Alcance y lo que NO se hace

- **Solo SALES (regresión).** Clasificación (INVENTORY) y clustering quedan **congelados / fuera
  de alcance**. PURCHASES e INVENTORY siguen sirviéndose con el motor congelado (no se ajustan
  por cliente en esta fase), aunque PURCHASES deriva de SALES.
- El **lote** sigue usando el congelado (opción A de ADR-0008): el ajuste por cliente es un
  camino aparte, no un cambio del lote.

## Configuración (entorno, con defaults documentados)

| Variable | Default | Para qué |
|---|---|---|
| `SPC_CLIENT_ADJ_ENABLED` | `true` | Habilita la capacidad de ajuste por cliente. |
| `SPC_CLIENT_MODELS_DIR` | `<base>/models/clientes` | Carpeta de artefactos por cliente. |
| `SPC_TRAINING_WORKERS` | `1` | Hilos del executor de entrenamiento (separado del de lote). |
| `SPC_CLIENT_ADJ_MIN_DAYS` | `60` | Días de historia mínimos para entrenar. |
| `SPC_CLIENT_ADJ_MIN_ROWS` | `120` | Observaciones mínimas. |
| `SPC_CLIENT_ADJ_MIN_SERIES` | `1` | Series (tienda×producto) mínimas. |
| `SPC_CLIENT_ADJ_VALID_FRAC` | `0.15` | Fracción de la historia útil por holdout. |
| `SPC_CLIENT_ADJ_MIN_WINDOW` | `7` | Mínimo de días por holdout. |
| `SPC_CLIENT_ADJ_MAX_WINDOW` | `16` | Máximo de días por holdout (= ventana del congelado). |
| `SPC_CLIENT_ADJ_MIN_IMPROVEMENT` | `0.0` | Puntos de WAPE mínimos para adoptar (0 = mejora estricta). |
| `SPC_CLIENT_ADJ_USE_GPU` | `false` | Boosters del training en GPU (por defecto CPU, local). |

## Consecuencias

- **A favor:** cierra el Camino A de forma honesta; opt-in y default intacto (riesgo acotado);
  reutiliza ingesta, corpus, adaptador y motor (cero lógica duplicada, cero dependencias nuevas);
  artefactos por cliente portables y versionados; "no mejora" se reporta. El catálogo expone
  `client_adjustment` como `available` (solo tras quedar funcional y validado).
- **Deuda asumida y explícita:** (a) el executor de entrenamiento es **in-process** (se pierde al
  reiniciar; un solo proceso), igual que el lote (ADR-0008); (b) la ventana adaptativa usa la
  misma definición que el congelado pero con holdouts más cortos para clientes pequeños — una
  validación por-serie más fina queda diferida; (c) solo SALES; (d) la fusión Excel+corpus usa
  "último gana" por serie-día (dedup), sin reconciliación de conflictos más allá de eso.
- **Privacidad/operación:** los artefactos por cliente contienen un modelo entrenado sobre datos
  del cliente; en producción aplica retención/respaldo/acceso (como el corpus de ADR-0011). El
  `client_id` del header se **sanea** (slug + hash) antes de usarse como carpeta (anti
  path-traversal).
- **Seguridad:** el entrenamiento corre con datos del cliente en un trabajo aislado; un fallo de
  entrenamiento nunca escapa del worker (se mapea a 400/500 controlado, como el lote).

## Referencias

- [ADR-0008 — Modos de ejecución](0008-modos-ejecucion.md)
- [ADR-0009 — Transferibilidad: modelo congelado](0009-transferibilidad-modelo-congelado.md)
- [ADR-0011 — Persistencia incremental del corpus](0011-persistencia-corpus-incremental.md)
- [Experimento de aumento de datos (patrón de honestidad)](../fase-3/experimento_aumento_datos.md)
- [Documento de entrega para el despliegue (§8, Camino A)](../SPC_Entrega_Despliegue_Valentin.md)
- [contrato_datos.md](../contrato_datos.md)
