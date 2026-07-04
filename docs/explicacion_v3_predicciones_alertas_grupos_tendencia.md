# SPC — Guía para explicar el sistema a tu profesor

**Sistema Predictivo de Comercialización (SPC)** · Módulos **Ventas · Compras · Almacén**
Tarjetas: **Predicciones · Alertas · Grupos · Análisis / Tendencia**

> Este documento está escrito para que puedas **explicar el sistema con tus propias palabras**,
> sin jerga innecesaria. Cada sección tiene primero la **idea simple** (para decir en voz alta) y
> luego el **detalle técnico** (por si el profesor pregunta más a fondo).

---

## 0. La idea en una frase

> "El sistema toma los datos históricos de la empresa (ventas, compras o inventario), **entrena
> varios modelos de Machine Learning en el momento**, elige automáticamente el mejor, y responde
> 4 tipos de preguntas de negocio: **¿cuánto?** (Predicciones), **¿alerta sí/no?** (Alertas),
> **¿qué grupos hay?** (Grupos), y **¿hacia dónde va la tendencia?** (Análisis)."

Hay **30 preguntas predefinidas** en total: **10 por cada módulo** (Ventas, Compras, Almacén).
Dentro de cada módulo: **4 de Predicción + 3 de Alerta + 3 de Grupos**, más **1 Tendencia** por módulo.

Todo el "cerebro" vive en un solo archivo de configuración: `src/spc/catalogo/consultas.yaml`
(el **catálogo**). El motor que lo ejecuta es `src/spc/catalogo/motor_catalogo.py`.

---

## 1. ¿De dónde salen los datos y qué días toma?

**Idea simple:** los datos son **sintéticos** (generados por el propio sistema con reglas realistas),
porque es un proyecto académico y no tenemos datos reales de una empresa. Se generan con una
**semilla fija (42)** para que siempre salgan iguales y el resultado sea **reproducible**.

**Detalle técnico** (generadores en `src/spc/synthetic/`):

| Módulo | Rango de tiempo | Tamaño (demo) | Grano de una fila |
|--------|-----------------|---------------|-------------------|
| **Ventas** | 120 días desde `2023-01-01` | 2 tiendas × 40 productos × 120 días ≈ **9.600 filas** | una venta por (fecha, tienda, producto) |
| **Almacén** | 120 días desde `2023-01-01` | 2 tiendas × 40 productos × 120 días ≈ **9.600 filas** | foto de stock por (fecha, tienda, producto) |
| **Compras** | 24 órdenes por serie desde `2023-01-01` | 20 proveedores × 4 productos × 24 órdenes ≈ **1.920 filas** | una orden de compra por (proveedor, producto) |

Puntos que puedes mencionar para sonar riguroso:

- Los datos **no son aleatorios sin sentido**: llevan **estacionalidad semanal** (los fines de
  semana venden distinto), **efecto de promociones**, **ruido controlado**, y en almacén un patrón
  de inventario **"diente de sierra"** (se consume stock cada día y se repone al tocar el mínimo).
- El almacén incluye **casos difíciles a propósito**: a veces la reposición llega tarde (quiebre de
  stock) y a veces se sobre-pide (sobrestock). Así las **alertas tienen ejemplos reales que aprender**.
- Todo es **portátil y reproducible**: misma semilla → mismos datos → mismos resultados.

---

## 2. ¿Cómo entrena? (esto es lo más importante para el profesor)

Esta es la parte donde se gana la nota. La clave es **honestidad metodológica**: el sistema está
diseñado para **no hacer trampa** (no "fuga de datos") y para **no inflar las métricas**.

### 2.1 Partición temporal (train / valid / test)

**Idea simple:** ordenamos los datos **por fecha** y los partimos en tres tramos en el tiempo:

```
|-------- 70% pasado --------|-- 15% --|-- 15% futuro --|
        ENTRENAR (train)       ELEGIR      EXAMEN FINAL
                               (valid)        (test)
```

- **TRAIN (70%)**: con esto el modelo **aprende**.
- **VALID (15%)**: con esto **elegimos qué modelo es el mejor** (comparamos candidatos).
- **TEST (15%)**: es el **examen final**. Se mira **una sola vez** y esa es la métrica que se
  reporta. El modelo **nunca vio** estos datos al entrenar.

> Frase para decir: *"Partimos por fecha, no al azar, porque predecir el futuro con datos del
> futuro sería hacer trampa. Elegimos el modelo en validación y solo tocamos el test una vez."*

Código: `partir_temporal()` en el motor (70% / 15% / 15%).

### 2.2 Se prueban varios modelos y gana el mejor (AutoML ligero)

Para cada pregunta, el sistema **entrena varios modelos candidatos** y se queda con el que mejor
puntúa en **validación**. Todos son modelos **livianos de scikit-learn** (rápidos, entrenan al vuelo):

- **Predicción (regresión):** `Ridge`, `Random Forest`, `Hist Gradient Boosting`, `Extra Trees`.
- **Alertas (clasificación):** `Regresión Logística`, `Random Forest`, `Hist Gradient Boosting`.
- **Grupos (clustering):** `K-Means`, `Aglomerativo`.
- Además siempre se añade un **`baseline` (modelo tonto de referencia)**: en regresión predice
  siempre la mediana; en clasificación predice según la clase más frecuente. **Sirve para demostrar
  que el modelo real aporta valor** (si no le gana al tonto, hay que sospechar).

> Frase para decir: *"No elegimos el modelo a mano; el sistema compite varios y elige el mejor
> por la métrica, e incluso lo compara contra un modelo trivial de referencia."*

### 2.3 Anti-fuga de datos (leak-safe) — el punto fuerte del proyecto

**Idea simple:** "fuga" es cuando, sin querer, le das al modelo una pista que **contiene la
respuesta**. Ejemplo: si quiero predecir **unidades vendidas**, **no puedo** darle el **ingreso**
como pista, porque `ingreso = unidades × precio` → sería casi copiar la respuesta.

El catálogo **excluye explícitamente** esas columnas "tramposas" en cada pregunta. Ejemplos:

- `ingreso` = unidades × precio → se excluye al predecir unidades.
- `costo_total` = cantidad × precio → se excluye al predecir cantidad.
- `dias_de_cobertura` = stock ÷ demanda → se excluye siempre.
- En las alertas por regla (almacén), las columnas que **definen** la alerta (`stock_actual`,
  `stock_minimo`…) **no se usan como pista**: la alerta se estima desde **otros factores** (categoría,
  zona, rotación). Si no, sería una tautología (adivinar algo que ya sabes).

> Frase para decir: *"Cada pregunta tiene una sección `anti_fuga` documentada: qué se excluye y por
> qué. Así las métricas son honestas y no artificialmente perfectas."*

### 2.4 Otros detalles honestos

- **Semilla fija (42)** en todo → reproducible.
- **Escalado** con `StandardScaler` (ajustado solo en train).
- **Objetivos sesgados** (ingreso, costo) se entrenan en **escala logarítmica** para estabilizar.
- **Clases desbalanceadas** (pocas alertas positivas) → `class_weight='balanced'`.
- **Umbrales de las alertas** (percentiles) se calculan **solo en train**, nunca con datos de test.
- El sistema **avisa cuando la métrica es "demasiado buena"** o cuando el objetivo es casi constante
  (nota honesta: "esto es fácil, léelo con cautela"). No esconde limitaciones.

---

## 3. Las 4 tarjetas: qué es cada una, qué valor toma, cómo explicarla

### 3.1 🔮 PREDICCIONES (Regresión) — "¿cuánto?"

**Idea simple:** predice **un número**. Ejemplo de la captura: *"Unidades según precio y promoción"*
→ estima cuántas **unidades** se venderán. El recuadro grande ("Total estimado: 86,547 unidades") es
la **suma del periodo** estimado, y la tabla desglosa por categoría.

- **Qué valor toma:** un número continuo (unidades, soles S/, días, %, índice…).
- **En qué se basa:** en las **columnas de entrada** que declara cada pregunta (precio, promoción,
  categoría, calendario, etc.), nunca en columnas derivadas del objetivo.
- **Métrica:** **WAPE** (error porcentual ponderado). **Más bajo = mejor**. Se interpreta como
  "error promedio del %": WAPE 0.20 ≈ "nos equivocamos ~20% en promedio".
- **Cómo se muestra:** valor **predicho** vs valor **real** por fila + un **resumen**:
  - Magnitudes **extensivas** (unidades, ingreso, cantidad, costo) → se **suman** ("Total estimado").
  - Magnitudes **intensivas** (%, días, rotación, cobertura) → se **promedian** ("Promedio estimado").

**Las 4 predicciones por módulo:**

| Módulo | Predice… | Se basa en (pistas) |
|--------|----------|---------------------|
| **Ventas** | (r1) unidades vendidas | precio, promoción, descuento, categoría |
| | (r2) ingreso S/ | categoría, producto, tienda, pago, canal, calendario, promo |
| | (r3) unidades por calendario | fin de semana, días a feriado, categoría |
| | (r4) unidades por canal/pago | categoría, canal, método de pago |
| **Compras** | (r1) cantidad a pedir | categoría, lead time, descuento, precio compra |
| | (r2) días de entrega (lead time) | proveedor, categoría, método de pago |
| | (r3) costo total de la orden | proveedor, categoría, lead time |
| | (r4) % de cumplimiento | proveedor, lead time, método de pago |
| **Almacén** | (r1) demanda del día | categoría, zona |
| | (r2) días de cobertura | categoría, zona, tiempo de reposición |
| | (r3) rotación | categoría, zona |
| | (r4) stock máximo recomendado | categoría, tiempo de reposición |

> Nota honesta que puedes mencionar: en Almacén las predicciones dan **"señal limitada"** a propósito,
> porque se excluyeron las columnas que serían casi-copia del objetivo. **Preferimos un error real
> honesto antes que una métrica inflada.**

### 3.2 🚨 ALERTAS (Clasificación) — "¿sí o no? / ¿qué categoría?"

**Idea simple:** responde con una **etiqueta**, no con un número. Casi siempre **sí/no** (ej.
"¿riesgo de quiebre?"). Da también una **probabilidad** por caso.

- **Qué valor toma:** una **clase** (0/1 en binaria; o una categoría en multiclase, ej. el canal).
- **Cómo se crea la etiqueta (sin fuga):**
  - **Por percentil:** ej. "demanda alta" = por encima del **P75** de su categoría (umbral fijado
    **solo en train**).
  - **Por regla determinística** (almacén): ej. "riesgo de quiebre" = `stock < demanda × reposición`.
    Las columnas de la regla **se excluyen** de las pistas.
- **Métrica:**
  - Binaria → **PR-AUC** (Average Precision). **Más alto = mejor**. Buena si ≥ 0.60.
  - Multiclase → **F1 macro**. Buena si ≥ 0.50.

**Las 3 alertas por módulo:**

| Módulo | Alerta | Etiqueta / regla |
|--------|--------|------------------|
| **Ventas** | (c1) ¿Demanda alta? | unidades > P75 de la categoría (train) |
| | (c2) ¿Por qué canal se venderá? | multiclase sobre `canal_venta` |
| | (c3) ¿Día pico? | unidades > P75 del producto (train) |
| **Compras** | (c1) ¿Entrega con retraso? | lead time > P75 global (train) |
| | (c2) ¿Cumplimiento alto? | cumplimiento > P60 (train) |
| | (c3) ¿Orden grande o pequeña? | cantidad > P50 (train) |
| **Almacén** | (c1) ¿Riesgo de quiebre? | `stock < demanda × reposición` |
| | (c2) ¿Reposición urgente? | `stock < stock_mínimo` |
| | (c3) ¿Sobrestock? | `stock > stock_máximo` |

> Frase para decir: *"Las alertas se aprenden desde factores del producto/proveedor, no desde las
> columnas que definen la alerta; por eso el modelo realmente predice, no copia."*

### 3.3 🧩 GRUPOS (Clustering) — "¿qué segmentos hay?"

**Idea simple:** **agrupa** entidades parecidas (productos, tiendas, proveedores) sin decirle de
antemano las categorías. El sistema **descubre** los grupos y les pone **nombre legible**.

- **Qué valor toma:** cada entidad recibe una **etiqueta de grupo** (ej. "Ventas: alto/medio/bajo",
  o "Clase A/B/C") + una **posición 2D** para graficarla (proyección PCA).
- **En qué se basa:** promedios por entidad de las columnas elegidas (volumen, rotación, precio…).
- **Métrica:** **Silueta** (silhouette). Mide qué tan **separados y compactos** son los grupos.
  **Más alto = mejor** (buena ≥ 0.50). Compiten K-Means y Aglomerativo; se elige el mejor.
- El **número de grupos (k)** se elige automáticamente por la silueta, **salvo el análisis ABC**
  (Almacén) que usa **k = 3 fijo** (A, B, C).

**Los 3 grupos por módulo:**

| Módulo | Agrupa… | Por |
|--------|---------|-----|
| **Ventas** | (k1) productos | volumen e ingreso |
| | (k2) productos | sensibilidad a promoción |
| | (k3) tiendas | volumen, precio, método de pago |
| **Compras** | (k1) proveedores | lead time, cumplimiento, costo (→ premium/estándar/básico) |
| | (k2) productos | precio y cantidad de compra |
| | (k3) órdenes | tamaño y descuento |
| **Almacén** | (k1) **Análisis ABC** de productos | regla de Pareto por valor acumulado (A≈80%, B 80–95%, C 95–100%) |
| | (k2) productos | rotación y cobertura |
| | (k3) zonas | presión de inventario |

> Ojo con el **ABC (Almacén k1)**: técnicamente **NO es clustering**, es una **regla de negocio de
> Pareto** (ordenar por valor y cortar por % acumulado). El sistema lo aclara en la nota técnica.

### 3.4 📈 ANÁLISIS / TENDENCIA — "¿hacia dónde va?"

**Idea simple:** es la **única** tarjeta con **línea de tiempo**. Toma el total diario de la
magnitud principal del módulo y dibuja el **histórico** + un **pronóstico** de los próximos días.

- **Qué muestra:** histórico diario + pronóstico a **14 días** (horizonte configurable) + un resumen
  ("creciente / estable / decreciente" y el % de cambio). Se puede **desglosar por categoría**.
- **Magnitud por módulo:** Ventas → unidades; Compras → cantidad pedida; Almacén → demanda del día.
- **Método:** **tendencia lineal** (mínimos cuadrados) × **estacionalidad semanal** (aprende el
  patrón de cada día de la semana). Es **referencial y honesto**: si hay menos de 8 días, no
  pronostica.

> Frase para decir: *"La tendencia no es un modelo pesado: es una recta ajustada por mínimos
> cuadrados corregida por el patrón semanal. Es una guía, no una predicción de alta precisión, y así
> lo declaramos."*

---

## 4. ¿Cómo leer las métricas? (tabla de bolsillo)

| Métrica | Se usa en | Dirección | "Buena" | Qué significa |
|---------|-----------|-----------|---------|---------------|
| **WAPE** | Predicciones | ↓ menor mejor | ≤ 0.25 | error % promedio de la predicción |
| **PR-AUC** | Alertas sí/no | ↑ mayor mejor | ≥ 0.60 | acierto detectando la clase positiva |
| **F1 macro** | Alertas multiclase | ↑ mayor mejor | ≥ 0.50 | balance precisión/cobertura por clase |
| **Silueta** | Grupos | ↑ mayor mejor | ≥ 0.50 | qué tan definidos están los grupos |

El sistema **etiqueta cada resultado** como calidad **"buena"** o **"limitada"** según estos
umbrales (definidos en `consultas.yaml` → `umbrales_calidad`) y **muestra avisos honestos**:
"señal débil", "métrica fácil", "grupos poco definidos", "pocas entidades (referencial)", etc.

---

## 5. Ejemplo completo con la captura (para narrar en la defensa)

La tarjeta de la imagen es **VEN-R1: "Unidades según precio y promoción"** (una **Predicción**):

1. **Pregunta de negocio:** ¿cuántas unidades venderé según el precio, si está en promoción y el
   descuento? (por categoría/tienda/producto).
2. **Datos:** ventas sintéticas, 120 días, ordenadas por fecha.
3. **Se basa en (pistas):** precio, en promoción, descuento %, categoría. **Excluye `ingreso`**
   (sería fuga: ingreso = unidades × precio).
4. **Entrenamiento:** train 70% / valid 15% / test 15%; compiten Ridge, Random Forest, Hist Gradient
   Boosting, Extra Trees + baseline; gana el de menor **WAPE** en validación.
5. **Resultado mostrado:** "Total estimado (periodo): **86,547 unidades**" (suma del tramo predicho),
   y el desglose por categoría (Primeros auxilios 6,545; Analgésicos 6,028; …).
6. **Honestidad:** si el WAPE fuera alto, aparecería el aviso "señal débil"; y el modelo se compara
   contra el baseline para probar que aporta.

> Cierre para el profesor: *"En resumen, el sistema es un AutoML ligero, leak-safe y honesto: entrena
> al vuelo, elige el mejor modelo por validación, reporta la métrica de test una sola vez, documenta
> qué excluye para no hacer trampa, y avisa cuando un resultado es limitado o demasiado fácil."*

---

## 6. Mapa de archivos (por si preguntan "¿dónde está esto en el código?")

| Qué | Archivo |
|-----|---------|
| Catálogo de las 30 preguntas (fuente de verdad) | `src/spc/catalogo/consultas.yaml` |
| Motor que entrena y ejecuta cada pregunta | `src/spc/catalogo/motor_catalogo.py` |
| Carga/validación del catálogo | `src/spc/catalogo/config.py` |
| Generadores de datos sintéticos | `src/spc/synthetic/{ventas,compras,almacen}.py` |
| API (endpoints v3) | `src/spc/api/routers/catalogo_v3.py` |
| Interfaz (React) | `frontend/src/components/v3/` |

---

### Glosario rápido (di esto si preguntan un término)

- **Regresión:** predecir un número. · **Clasificación:** predecir una etiqueta (sí/no o categoría).
- **Clustering:** descubrir grupos parecidos sin etiquetas previas.
- **Fuga de datos (leakage):** darle al modelo una pista que contiene la respuesta → métrica falsa.
- **Baseline:** modelo trivial de referencia para saber si el modelo real vale la pena.
- **WAPE / PR-AUC / F1 / Silueta:** las 4 "notas" según el tipo de pregunta (ver tabla §4).
- **Estacionalidad semanal:** el patrón de que cada día de la semana se comporta distinto.
</content>
</invoke>
