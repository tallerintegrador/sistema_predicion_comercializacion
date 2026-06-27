# Alcance, metodología de validación y limitaciones — SPC

> Documento vivo. Vive en `docs/fase-3/alcance_validacion_limitaciones.md`.
>
> Es la pieza **narrativa** del producto de cara a la presentación: explica qué es SPC,
> cómo se validó y qué **no** promete. Atiende las recomendaciones del docente sobre
> plataforma agnóstica (2, 3), transparencia (7) y aumento de datos como experimento (9).
>
> **Honestidad estricta.** Ningún número está escrito de memoria: cada cifra proviene de
> la metadata del artefacto o del reporte que la generó, y se cita su fuente. Toda
> métrica se rotula como **medida sobre los datos de Favorita**: demuestra el método, no
> es una garantía para un cliente cualquiera.

---

## 1. Resumen ejecutivo

SPC (Sistema Predictivo de Comercialización) es una **plataforma agnóstica al rubro**:
recibe el histórico de ventas de un cliente por un **contrato de datos** con nombres
genéricos y devuelve tres servicios —pronóstico de demanda (SALES), reposición
(PURCHASES) y riesgo de quiebre + perfilado (INVENTORY)— sin que el cliente conozca el
modelo por dentro.

Para **validar la metodología** se usó un cliente de ejemplo: el dataset público *Store
Sales — Corporación Favorita* (retail de supermercado, Ecuador). Favorita es el **banco
de pruebas con el que se midió que el método funciona**, no "el modelo del producto". Las
cifras de este documento (WAPE, PR-AUC, silueta) están medidas sobre Favorita y
demuestran que el enfoque es sólido **sobre ese dato**; no son una promesa de rendimiento
para un negocio distinto (ver §5.1 y [ADR-0009](../decisiones/0009-transferibilidad-modelo-congelado.md)).

La tesis central de la presentación:

> **El método está validado sobre Favorita; la plataforma está lista para que un cliente
> traiga sus datos. El rendimiento sobre Favorita demuestra el método; no se transfiere
> como garantía a otro rubro.**

---

## 2. Alcance y postura del producto

### 2.1 Plataforma agnóstica al sector

El cliente **mapea su vocabulario** (SKU, local, sucursal, categoría…) a los campos
genéricos del contrato y SPC predice sin conocer su negocio. El contrato es la **frontera
pública estable**: lo que cambie por dentro (modelos, features) no debe romperlo. Sus
nombres de campo, parámetros, enums y errores están **en inglés** (coinciden exacto con
la API); la explicación en prosa va en español. La fuente de verdad es
[contrato_datos.md](../contrato_datos.md).

El bloque `history` es **compartido** por los tres servicios: el cliente integra una vez
y puede pedir SALES, PURCHASES e INVENTORY con el mismo envío.

### 2.2 Favorita como cliente de ejemplo (no "el modelo del producto")

El motor de ML se entrenó, validó y congeló sobre Favorita en la Fase 2. Un cliente nuevo
**no reentrena nada**: opera contra el modelo congelado a través del contrato. Esto tiene
una consecuencia de honestidad que se desarrolla en §5.1: el modelo aporta una señal
**genérica y limitada** (rezagos + calendario) para un negocio que no se parezca al
retail de Favorita, y por eso el **ajuste por cliente** se documenta como dirección futura
y medida, no como característica entregada.

### 2.3 Qué entrega hoy y qué no

| Capacidad | Estado |
|---|---|
| Tres servicios por contrato (SALES, PURCHASES, INVENTORY) | **Entregado** |
| Canal JSON y canal Excel (plantilla + carga) | **Entregado** |
| Modo en línea (síncrono) y modo por lote (asíncrono) | **Entregado** (lote con limitaciones, §5.4) |
| Catálogo de predicciones (`GET /catalog`) de solo lectura | **Entregado** |
| Intervalos de predicción `interval_80` | **Diferido** (campo documentado, no emitido — §5.2) |
| Ajuste del modelo por cliente | **Dirección futura** ([ADR-0009](../decisiones/0009-transferibilidad-modelo-congelado.md)) |

---

## 3. Metodología de validación

Lo importante no es solo el número, sino **cómo se midió**. La regla transversal de la
Fase 2: **validación temporal sin fuga de futuro, selección de modelo/umbral en VALID y
TEST evaluado una sola vez** sobre la configuración ya elegida.

Cortes temporales (heredados por las tres tareas):

- **Train:** ≤ 2017-07-14
- **Valid:** 2017-07-15 .. 2017-07-30 (selección)
- **Test:** 2017-07-31 .. 2017-08-15 (una sola vez)

### 3.1 Regresión (SALES): la métrica guía es el WAPE recursivo, no el optimista

El pronóstico de demanda es **multi-paso**. Hay dos formas de medirlo y solo una es
honesta:

- **Pronóstico recursivo (autorregresivo):** el modelo proyecta el horizonte
  reinyectando **sus propias predicciones** como rezagos, igual que en producción. Es la
  **métrica guía del proyecto**.
- **Teacher forcing:** alimenta los rezagos con las ventas **reales** del horizonte
  (que en producción no se conocen). **Sobreestima** la precisión; se reporta solo como
  cota superior optimista.

La diferencia es el corazón de la historia de honestidad (ver el glosario, §7): el
proyecto **reporta el número recursivo aunque sea peor**.

### 3.2 Clasificación (INVENTORY): PR-AUC de la minoritaria + piso real de precisión

El objetivo `demanda_alta = sales > P75 de su familia` está **desbalanceado**, así que la
métrica principal es la **PR-AUC de la clase minoritaria** (independiente del umbral),
contextualizada contra la línea sin-skill (= prevalencia del split). El **punto de
operación** por defecto no maximiza recall a ciegas: exige un **piso real de precisión
(0.80)** para que el operativo sea accionable.

### 3.3 Clustering (INVENTORY/perfilado): silueta + diagnóstico del eje de separación

La calidad de segmentación se mide con la **silueta**, pero no basta el número: se
**diagnostica qué variable separa** realmente los grupos (análisis de componentes
principales + *leave-one-out* de features). Ese diagnóstico es el que revela que la
separación está **dominada por el volumen** (§4.3 y §5.3).

---

## 4. Resultados sobre los datos de Favorita

> Todas las tablas de esta sección están **medidas sobre Favorita**. Demuestran el método;
> no son garantía para un cliente de otro rubro.

### 4.1 Regresión — `regresion_v3`

Modelo de producción: **ensemble convexo** de cuatro boosters —`XGBoost` (25.6 %),
`XGBoost_Tweedie` (25.4 %), `LightGBM` (25.0 %), `LightGBM_Poisson` (24.0 %)— reajustado
sobre 2 950 992 filas del histórico etiquetado.
Fuente: [regresion_v3.meta.json](../../models/regresion_v3.meta.json),
[reporte_regresion_2a.md](../reporte_regresion_2a.md).

| Métrica (TEST, una sola vez) | Modelo | Mejor baseline honesto (naive estacional t-7) | Mejora |
|---|---|---|---|
| **WAPE recursivo (guía)** | **14.59 %** | 20.67 % | **6.08 puntos** |
| MAE recursivo | 68.15 | 96.54 | 29.4 % |
| RMSE recursivo | 235.73 | 348.38 | 32.3 % |
| R² recursivo | 0.964 | 0.922 | — |
| *WAPE teacher-forced (optimista, no es la guía)* | *12.40 %* | *—* | *cota superior* |

- **Selección honesta:** el ensemble se eligió por **menor WAPE recursivo sobre VALID**
  (12.18 %) frente al mejor individual `LightGBM_Tweedie` (14.25 %). TEST no se usó para
  elegir.
- En el desglose por familia, algunas familias intermitentes (p. ej. `BOOKS`) muestran
  WAPE altísimo pero **MAE trivial** (fracciones de unidad): el WAPE se dispara al dividir
  errores minúsculos entre ventas casi nulas. No afecta el WAPE agregado (ponderado por
  volumen) ni la decisión de negocio (ver §5.7).

### 4.2 Clasificación — `clasificacion_v1`

Modelo: **LightGBM (binary)**, estrategia **sin remuestreo** (SMOTE no se adoptó, ver el
[experimento de aumento de datos](experimento_aumento_datos.md)). Reajustado sobre
2 772 144 filas (familias no degeneradas).
Fuente: [clasificacion_v1.meta.json](../../models/clasificacion_v1.meta.json),
[reporte_clasificacion_2b.md](../reporte_clasificacion_2b.md).

| Métrica (TEST, una sola vez) | Valor | Contexto |
|---|---|---|
| **PR-AUC (minoritaria)** | **0.9343** | sin-skill (prevalencia TEST) 0.3465 → **×2.70** sobre el azar |
| Precisión (umbral 0.3185) | 0.809 | respeta el piso real 0.80 (margen +0.02 en VALID) |
| Recall (umbral 0.3185) | 0.874 | captura ~87 % de la demanda alta |
| F1 | 0.840 | |
| ROC-AUC | 0.958 | contexto |

- **Matriz de confusión (TEST, umbral 0.3185):** TN 15 587 · FP 1 916 · FN 1 168 · TP 8 113.
  El operativo marca **10 029 filas (37.4 %)** como riesgo con precisión ~0.81.
- **Prevalencia no estacionaria (hallazgo honesto):** el umbral P75 se fija en TRAIN; como
  las ventas crecen, la prevalencia sube de **0.224 (train)** a **0.349 (valid) / 0.347
  (test)**. Por eso la línea sin-skill es la del split evaluado, no la de train (ver §5.7).
- **Familias degeneradas excluidas:** `BABY CARE` y `BOOKS` (P75 = 0; 2 de 33), donde la
  etiqueta degenera en "vendió algo".

### 4.3 Clustering — perfilado de tiendas y familias

Fuente: [clustering_tiendas_v1.meta.json](../../models/clustering_tiendas_v1.meta.json),
[clustering_familias_v1.meta.json](../../models/clustering_familias_v1.meta.json),
[reporte_clustering_2c.md](../reporte_clustering_2c.md).

**Tiendas — `clustering_tiendas_v1` (KMeans, k=2, silueta 0.6742).** 54 tiendas → 44 de
bajo volumen / intermitente y 10 de alto volumen / venta continua. El segmento de alto
volumen alimenta el nivel de servicio de INVENTORY.

**Familias — `clustering_familias_v1` (KMeans, k=3, silueta 0.659).** 33 familias → 26
(volumen medio, continuo) / 3 (alto volumen, continuo) / 4 (bajo volumen, intermitente).

#### Por qué k=3 en familias, si k=2 tenía mayor silueta — y por qué no k=4

La elección de `k` en familias es **deliberada y documentada**, porque la silueta sola
no apuntaba a k=3. Curva de silueta real (set desplegado):

| k | silueta |
|---|---|
| **2** | **0.7052** ← máximo de silueta |
| 3 | 0.6590 ← **elegido** |
| 4 | 0.6602 |
| 5 | 0.5622 |

- **Por qué no k=2 (el máximo de silueta):** k=2 parte solo en "grande vs pequeña" y
  esconde a las familias **intermitentes** (BABY CARE, BOOKS, HARDWARE, HOME APPLIANCES)
  dentro del grupo pequeño. k=3 las **aísla en su propio segmento**, que es un **tipo de
  demanda accionable** para política de stock (no se repone igual una familia continua que
  una intermitente). La silueta baja de 0.71 a 0.659, pero sigue **saludable** (> 0.50).
  Se prioriza el valor de negocio sobre el máximo de la métrica, y se documenta el
  trade-off.
- **Por qué no k=4 (honestidad):** k=4 tiene una silueta **marginalmente mayor** que k=3
  (0.6602 vs 0.6590) — es decir, **no se descartó por peor silueta**; están empatados
  dentro del ruido. Se prefiere k=3 por **parsimonia**: tres segmentos ya cubren los tres
  **arquetipos de demanda accionables** (medio-continuo, alto-continuo, bajo-intermitente),
  y un cuarto corte no añade una categoría de demanda nueva que cambie una decisión de
  stock. La justificación registrada en la metadata cubre explícitamente la elección de
  k=3 sobre el máximo (k=2); el preferir k=3 a k=4 se apoya en estas dos cifras de silueta
  reales más el criterio de parsimonia.

> **Advertencia clave de transparencia (ver §5.3):** en ambos clusterings la separación
> está **dominada por el volumen**. Las etiquetas "intermitente / continuo" describen
> correlatos del volumen, no ejes de separación independientes.

---

## 5. Limitaciones honestas (consolidadas)

Esta sección reúne, en un solo lugar, lo que SPC **no** promete. Cada punto enlaza al ADR
o reporte donde se decidió o midió.

### 5.1 Transferibilidad del modelo (modelo congelado, entrenado en Favorita)

El modelo está **congelado**: se entrenó sobre el retail de supermercado de Favorita y un
cliente nuevo opera contra él **sin reentrenar**. Para un cliente nuevo, los metadatos de
tienda específicos de Favorita (tipo, ciudad, estado, cluster comercial, precio del
petróleo) **no existen en el contrato** y caen a "desconocido"; el pronóstico se sostiene
entonces sobre lo **genérico**: rezagos del propio histórico del cliente y calendario.

Hay que ser explícito y no vender de más: esa señal genérica es **limitada y sin
garantía** para un negocio que no se parezca al retail de Favorita. La expresión técnica
"degradación con elegancia" significa que el sistema **no se cae** ante datos
desconocidos (responde con lo que tiene), **no** que "funciona bien" en otro rubro: el
sistema **se degrada**. La frase correcta es "sigue respondiendo con señal reducida", no
"se mantiene el rendimiento". Cuánto se degrada para un rubro distinto **no está medido**
(no teníamos un segundo cliente), así que no se afirma.

Precisamente por esto el **ajuste por cliente** (reentrenar o calibrar con los datos del
cliente) queda como **dirección futura y medida**, que solo se activaría si los resultados
lo justifican. Detalle y postura formal en
[ADR-0009](../decisiones/0009-transferibilidad-modelo-congelado.md).

### 5.2 Intervalos de predicción diferidos (`interval_80`)

SALES devuelve la demanda esperada como **punto**, no como rango. El campo `interval_80`
existe en el contrato pero **el modelo aún no lo produce**; la respuesta lo **omite** hoy.
Se difirió desde la Fase 2 (vía cuantiles de boosting o residuos empíricos del holdout) y
se documenta en [ADR-0007 §4](../decisiones/0007-capa-api-fase3.md) y
[contrato_datos.md §3](../contrato_datos.md). Cuando se implemente, pasará de ausente a
presente sin romper el contrato.

### 5.3 Clustering dominado por volumen

El diagnóstico (PCA + *leave-one-out*) muestra que la primera componente concentra la
mayor parte de la varianza (PC1 ≈ 0.69 en tiendas, ≈ 0.62 en familias) y que las features
de volumen son colineales. **La separación es por volumen.** Las variables descriptivas
(intermitencia, promoción, % de demanda alta, transacciones) **correlacionan** con el
segmento pero **no son ejes de separación independientes**: son co-variables. Las
etiquetas narrativas ("bajo volumen, intermitente") son útiles para comunicar, pero no
deben leerse como "el modelo descubrió un patrón de intermitencia": descubrió, sobre todo,
**tamaño**. Documentado en la metadata de ambos artefactos (`nota_transparencia`,
`segmentacion_dominada_por_volumen`) y en [reporte_clustering_2c.md](../reporte_clustering_2c.md).

### 5.4 Lote in-process, un solo worker

El modo por lote procesa **en memoria, dentro del proceso** (sin Celery/Redis ni base de
datos). Dos limitaciones aceptadas para la demo:

- **Volatilidad:** los trabajos se **pierden al reiniciar** el proceso.
- **Un solo proceso/worker:** los trabajos en memoria no se comparten entre procesos; con
  varios workers de uvicorn un `job_id` creado por uno no es visible para otro. Por tanto
  **el lote exige desplegar con `--workers 1`** hasta migrar a un almacén compartido.

El resultado por lote es, por diseño, **byte-equivalente** al modo en línea. Mejoras
futuras (persistencia/SQLite, cola externa, troceo memory-aware) están documentadas en
[ADR-0008](../decisiones/0008-modos-ejecucion.md).

### 5.5 P75 (`objetivo_cuantil`) pendiente en la metadata

La etiqueta `demanda_alta` usa el cuantil **P75** de la familia. Ese nivel (0.75) es una
**definición del modelo** (no política de negocio), así que debería leerse de la metadata
del clasificador. Hoy la metadata **no lo expone como número** (solo lo menciona en prosa
en su campo `objetivo`), por lo que la capa de servicio usa un **fallback documentado de
0.75 marcado como `[PENDIENTE]`**. Es un **item de coordinación con el equipo de modelado**:
agregar `objetivo_cuantil` a la metadata en la próxima reconstrucción del artefacto; la
API lo leerá sin tocar código. Detalle en
[ADR-0010](../decisiones/0010-politica-inventario-stock.md).

### 5.6 Constantes de política: decisiones, no verdades

Los parámetros de **política de inventario** (factor de stock de seguridad 30 %, lead time
por defecto 7 días, ventana de demanda 28 días, niveles de servicio z = 1.28 / 1.65,
factor de respaldo 0.5) **no son verdades del dominio**: son **decisiones** razonables por
defecto. Todas son **configurables por entorno** (variables `SPC_*`) con los valores
históricos como default, y el método de stock de seguridad es un **knob** por dominio
(`coverage_days` | `service_level`). Cambiar la configuración **no cambia la salida por
defecto**. Importante para la honestidad: el `σ` del nivel de servicio de INVENTORY **no
es inventado** — se calcula de la demanda **real** del cliente. Detalle en
[ADR-0010](../decisiones/0010-politica-inventario-stock.md).

### 5.7 Otras limitaciones de datos y etiqueta (heredadas de Fase 2)

- **Etiqueta no estacionaria:** `demanda_alta` usa el P75 histórico fijo de TRAIN; con
  ventas crecientes, la prevalencia sube de 0.224 a ~0.347. Un percentil móvil definiría
  "demanda alta" relativa al régimen actual; cambia el objetivo y se difirió.
- **Demanda intermitente / zero-inflation:** el 31.3 % de las observaciones son ventas en
  cero; el MAPE (~32 %) está **inflado** por eso y **no se usa** como métrica principal (se
  prefiere WAPE/MAE). Las familias de muy bajo volumen tienen WAPE alto pero MAE trivial.
- **Calibración de probabilidades** (Platt/isotónica) diferida: el clasificador fija un
  punto de operación; una probabilidad calibrada permitiría políticas de stock por nivel de
  servicio sin recablear el umbral.

---

## 6. Referencias a los ADR

| ADR | Tema | Relación con este documento |
|---|---|---|
| [ADR-0007](../decisiones/0007-capa-api-fase3.md) | Capa de servicio / API (Fase 3) | Separación de capas; `interval_80` diferido (§5.2) |
| [ADR-0008](../decisiones/0008-modos-ejecucion.md) | Modos de ejecución (en línea / lote) | Limitaciones del lote (§5.4) |
| [ADR-0009](../decisiones/0009-transferibilidad-modelo-congelado.md) | Transferibilidad / modelo congelado / Favorita como cliente de ejemplo | Postura de transferibilidad (§2.2, §5.1) |
| [ADR-0010](../decisiones/0010-politica-inventario-stock.md) | Política de inventario y stock de seguridad | P75 pendiente (§5.5); constantes de política (§5.6) |

---

## 7. Glosario mínimo

- **Pronóstico recursivo (autorregresivo).** El modelo predice el horizonte paso a paso,
  **reinyectando sus propias predicciones** como rezagos para el siguiente día — igual que
  en producción, donde no se conoce el futuro. Es la **métrica guía** de SPC. Sobre TEST en
  Favorita: **WAPE 14.59 %**.
- **Teacher forcing.** Mide el modelo alimentando los rezagos con las **ventas reales** del
  horizonte (un lujo que no existe en producción). **Sobreestima** la precisión; por eso es
  la cifra **optimista que no se usa** como guía. Sobre TEST en Favorita: WAPE 12.40 %.
  → El proyecto reporta **14.59 % (recursivo)** como número honesto, **no** 12.40 %.
- **WAPE** (Weighted Absolute Percentage Error). Error absoluto agregado **ponderado por
  volumen**; fiable para series con muchos ceros (a diferencia del MAPE, que sobre-pondera
  series pequeñas). Menor es mejor.
- **PR-AUC** (área bajo la curva precisión-recall). Métrica principal para la **clase
  minoritaria** en clasificación desbalanceada; se compara contra la línea sin-skill (=
  prevalencia). Mayor es mejor.
- **Silueta.** Mide qué tan bien separados y cohesionados están los clusters (rango
  −1…1; > 0.5 se considera saludable). Una silueta alta **no dice qué variable** produce
  la separación: eso lo revela el diagnóstico (§5.3).
