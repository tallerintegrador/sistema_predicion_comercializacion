# Informe explicativo — Sistema Predictivo de Comercialización (SPC)

> Guía sencilla para entender y explicar el sistema. Pensada para presentar el proyecto
> sin tecnicismos innecesarios. Cada sección va de lo simple a lo concreto.

---

## 0. Resumen en una página (lo esencial)

El SPC es un servicio (API) que ayuda a una PYME a responder **tres preguntas de negocio**:

| Campo | Pregunta que responde | Técnica de ML | Modelo en producción |
|---|---|---|---|
| **VENTAS** (`/sales`) | ¿Cuánto voy a vender? | **Regresión** | `regresion_v3` (Ensemble de 4 boosters) |
| **ALMACÉN** (`/inventory`) | ¿Qué productos están en riesgo de quiebre y cuánto stock dejar? | **Clasificación** + **Clustering** | `clasificacion_v1` (LightGBM) + `clustering_tiendas_v1` (KMeans) |
| **COMPRAS** (`/purchases`) | ¿Cuánto debo reponer? | **Sin modelo propio**: lógica de negocio sobre el pronóstico de VENTAS | — |

Idea central, en una frase:

> El sistema tiene unos modelos **ya entrenados de fábrica** (como un empleado que ya
> estudió). En cada consulta, el cliente manda su historial de ventas en un **formato
> fijo (contrato)**, el sistema lo traduce, calcula pistas y le pide a los modelos una
> respuesta. Los modelos **no se reentrenan** en cada consulta: solo aplican lo que ya
> aprendieron.

---

## 1. La idea general (analogía del empleado)

Imagina que antes de abrir el sistema sentaste a un **empleado a estudiar** millones de
días de ventas de una cadena de supermercados real (datos de **Corporación Favorita**,
Ecuador). El empleado aprendió dos cosas distintas:

1. **Vocabulario memorizado**: qué tiendas, productos y ciudades existían (nombres
   concretos).
2. **Ritmos generales**: los fines de semana se vende más, a fin de mes hay repunte, si
   ayer vendiste mucho mañana probablemente también, etc.

Cuando terminó de estudiar, le tomamos una **"foto al cerebro"** y la guardamos en un
archivo (`.joblib`). En producción, esa foto **ya no cambia**: el empleado solo aplica
lo aprendido, nunca vuelve a estudiar.

Hay dos momentos muy diferentes:

| | **Entrenar** (estudiar) | **Predecir** (responder) |
|---|---|---|
| Cuándo | Una vez, offline | En cada petición a la API |
| Velocidad | Lento (minutos) | Rápido (instantáneo) |
| Resultado | Crea la "foto del cerebro" | Usa esa foto |

---

## 2. Los tres campos y sus modelos en detalle

### 2.1. VENTAS — Regresión (predice un número)

**Qué hace:** pronostica **cuántas unidades** se venderán de cada producto, en cada
tienda, para los próximos días (o semanas/meses).

**Modelo ganador:** `regresion_v3`, un **ensemble** (mezcla) de 4 modelos de árboles de
gradient boosting:
`Ensemble(XGBoost + XGBoost_Tweedie + LightGBM + LightGBM_Poisson)`.

- Un *ensemble* es como pedir la opinión a 4 expertos y promediarlas con pesos. Da
  resultados más estables que un solo modelo.
- Los modelos "Tweedie/Poisson" están pensados para productos con **muchos días en
  cero** (demanda intermitente), muy común en retail.

**Cómo se eligió:** se compararon varios modelos con **validación temporal** (entrenar
con el pasado, evaluar con el futuro, nunca al revés) y ganó el ensemble por tener el
mejor **WAPE honesto** (error de pronóstico realista).

**Métricas (sobre el período de prueba, agosto 2017):**

| Métrica | Modelo `regresion_v3` | Baseline "repetir hace 7 días" | Baseline "media de 7 días" |
|---|---|---|---|
| **WAPE** (error %) ↓ | **14.6 %** | 20.7 % | 23.3 % |
| **MAE** (error medio en unidades) ↓ | **68.2** | 96.5 | 108.7 |
| **R²** (qué tan bien explica, 1 = perfecto) ↑ | **0.96** | 0.92 | 0.92 |

> Lectura simple: el modelo se equivoca, en promedio, un **~15 %** — bastante mejor que
> los métodos ingenuos (~21–23 %). Cuanto más bajo el WAPE/MAE y más cerca de 1 el R²,
> mejor.

- Entrenado con **~2.95 millones de filas**.
- Cortes de tiempo: entrena hasta `2017-07-14`, valida `07-15 a 07-30`, prueba final
  `07-31 a 08-15`.

**Cómo ayuda al negocio:** saber la demanda futura permite **no quedarse sin producto**
(perder ventas) ni **comprar de más** (plata inmovilizada). Es la base de los otros dos
campos.

---

### 2.2. ALMACÉN — Clasificación + Clustering (dos modelos juntos)

ALMACÉN responde: *¿este producto está en riesgo de quiebre? ¿cuánto stock dejo?* Y usa
**dos modelos**:

#### a) Clasificación — `clasificacion_v1` (predice una etiqueta: alta / baja)

**Qué hace:** en vez de un número, dice si un producto tendrá **demanda ALTA o BAJA**, y
con qué **probabilidad**.

- "Demanda alta" se define como: **vender más que el 75 % de los productos de su misma
  familia** (el percentil 75, P75).
- **Modelo:** LightGBM (clasificador binario).
- **Umbral de decisión:** 0.3185. Este número se eligió con una regla de negocio: **"capturar
  la mayor cantidad posible de casos de demanda alta, manteniendo al menos un 80 % de
  acierto cuando avisa"**.

**Métricas (período de prueba):**

| Métrica | Valor | Qué significa (simple) |
|---|---|---|
| **PR-AUC** ↑ | **0.93** | Qué tan bien distingue alta vs baja (1 = perfecto; el azar daría ~0.35) |
| **Recall** ↑ | **0.87** | De toda la demanda alta real, detecta el 87 % |
| **Precision** ↑ | **0.81** | Cuando avisa "alta", acierta el 81 % de las veces |
| **F1** ↑ | **0.84** | Equilibrio entre Recall y Precision |
| **Accuracy** | 0.88 | % de aciertos totales |

> Comparación: una regresión logística simple llega a PR-AUC 0.87 y un modelo "tonto"
> (que siempre dice lo mismo) a 0.35. El modelo es claramente mejor que esas referencias.

**Cómo ayuda:** prioriza la atención. En lugar de revisar miles de productos uno por uno,
el sistema **marca los que probablemente tendrán demanda alta** para reforzar su stock.

#### b) Clustering de tiendas — `clustering_tiendas_v1` (agrupa sin etiquetas previas)

**Qué hace:** agrupa las tiendas en **segmentos parecidos entre sí**, sin que nadie le
diga de antemano las categorías (aprendizaje **no supervisado**).

- **Modelo:** KMeans (con datos escalados).
- **Resultado:** **2 grupos** (k=2), con una **silueta de 0.67** (mide qué tan bien
  separados están los grupos; 1 = ideal, 0.67 es una separación buena y limpia):

| Segmento | Nombre | Nº tiendas | Característica |
|---|---|---|---|
| 0 | Bajo volumen, intermitente | 44 | Venta media diaria ~263 unidades |
| 1 | Alto volumen, venta continua | 10 | Venta media diaria ~776 unidades |

- **Hallazgo transparente:** la separación es básicamente por **volumen de ventas**
  (tiendas grandes vs pequeñas).

**Cómo ayuda:** permite afinar la política de stock. Por ejemplo, a las tiendas de **alto
volumen** se les exige un **nivel de servicio más alto** (más colchón de seguridad),
porque un quiebre ahí cuesta más.

> En el contrato, este segmento se devuelve como `store_segment`.

---

### 2.3. COMPRAS — Sin modelo propio (lógica de negocio)

**Qué hace:** recomienda **cuánto reponer** de cada producto. **No entrena ningún
modelo**: reutiliza el pronóstico de VENTAS y le aplica aritmética de inventario clásica.

La fórmula, en palabras simples:

```
demanda esperada   = pronóstico de ventas durante (lead time + días de cobertura)
stock de seguridad = 30 % de la demanda durante el lead time   (colchón)
punto de reorden   = demanda en lead time + stock de seguridad
cantidad a reponer = demanda esperada + stock de seguridad − stock actual   (nunca < 0)
```

- *Lead time* = días que tarda el proveedor en entregar.
- *Días de cobertura* = días de demanda que quiero tener cubiertos.

**Cómo ayuda:** convierte el pronóstico en una **acción concreta**: "pide X unidades de
este producto".

---

## 3. Resumen: cómo ayudan los modelos (visión de negocio)

| Campo | Decisión que habilita | Riesgo que reduce |
|---|---|---|
| VENTAS | Planear la demanda futura | Quedarse corto o sobrar inventario |
| ALMACÉN | Priorizar productos en riesgo y dimensionar stock | Quiebres de stock (perder ventas) |
| COMPRAS | Cuánto pedir al proveedor | Comprar de más / de menos |

---

## 4. Las APIs: endpoints, entradas y salidas

La API se levanta con FastAPI y tiene **un endpoint por campo** + uno de salud. Todos son
`POST` (excepto salud) y devuelven JSON. La documentación interactiva (Swagger) está en
`/docs` al levantar el servicio.

### 4.0. El bloque `history` (compartido por los tres)

Los tres campos reutilizan el **mismo bloque de historial**, para que el cliente integre
una sola vez. Cada observación tiene:

| Campo | Obligatorio | Significado |
|---|---|---|
| `date` | ✅ | Fecha (YYYY-MM-DD) |
| `store_id` | ✅ | Tienda / sucursal (admite texto o número) |
| `product_id` | ✅ | Producto / categoría |
| `units_sold` | ✅ | Unidades vendidas ese día |
| `on_promotion` | ❌ | Ítems en promoción (mejora la señal) |
| `transactions` | ❌ | Flujo de clientes / tickets |
| `event_active` | ❌ | Si hubo feriado/evento |

> Los opcionales **degradan con elegancia**: si no vienen, el modelo usa lo que tenga.

### 4.1. `POST /sales` — VENTAS (pronóstico)

**Entrada:**
```json
{
  "granularity": "day",        // "day" | "week" | "month"
  "horizon": 7,                 // cuántos períodos a futuro (1–365)
  "history": [ ...observaciones... ]
}
```

**Salida:**
```json
{
  "field": "sales",
  "model": "regresion_v3",
  "forecast": [
    { "date": "2017-08-03", "store_id": "1", "product_id": "BEVERAGES", "forecast_demand": 1742.5 }
  ],
  "metadata": { "scale": "units", "internal_transform": "log1p" }
}
```
- `forecast_demand` = demanda pronosticada en unidades (siempre ≥ 0).
- Para `week`/`month`, el sistema pronostica por día y **suma** por período.

### 4.2. `POST /purchases` — COMPRAS (reposición)

**Entrada:** el `history` + los parámetros logísticos por producto:
```json
{
  "history": [ ... ],
  "replenishment_params": [
    { "store_id": "1", "product_id": "BEVERAGES",
      "current_stock": 900, "lead_time_days": 3, "target_coverage_days": 7 }
  ]
}
```

**Salida:**
```json
{
  "field": "purchases",
  "recommendation": [
    { "store_id": "1", "product_id": "BEVERAGES",
      "expected_demand_horizon": 12200, "reorder_point": 5400,
      "replenishment_quantity": 11300,
      "justification": "forecast_demand + safety_stock - current_stock" }
  ],
  "metadata": { "assumption": "...", "policy": "coverage_days" }
}
```
- ⚠️ Si pides un producto **sin historial**, devuelve **error 400** (no se puede
  pronosticar sin historia).

### 4.3. `POST /inventory` — ALMACÉN (riesgo y stock)

**Entrada:** el `history` + el estado de inventario por producto:
```json
{
  "history": [ ... ],
  "inventory_status": [
    { "store_id": "1", "product_id": "BEVERAGES", "current_stock": 300, "lead_time_days": 3 }
  ]
}
```
(`lead_time_days` es opcional; por defecto 7 días.)

**Salida:**
```json
{
  "field": "inventory",
  "alerts": [
    { "store_id": "1", "product_id": "BEVERAGES",
      "demand_class": "high", "high_demand_probability": 0.87,
      "stockout_risk": true, "recommended_stock": 1600,
      "safety_stock": 420, "store_segment": 1 }
  ],
  "metadata": { "threshold": "high_demand = sales > P75 of its family",
                "probability_threshold": 0.3185 }
}
```
- `demand_class` / `high_demand_probability` → del **clasificador**.
- `store_segment` → del **clustering**.
- `stockout_risk` → `true` si el stock actual no cubre el stock recomendado.

### 4.4. `GET /health` — Salud del servicio
Devuelve `{ "status": "ok" }`. Sirve para comprobar que el servicio está arriba.

### 4.5. Errores (uniformes)
Toda entrada mal formada devuelve un error **controlado y uniforme** (nunca un error 500
crudo):
- **422** → entrada mal formada (falta un campo, tipo inválido, nombre desconocido).
- **400** → regla de negocio incumplida (p. ej. producto sin historial).

---

## 5. La data con la que se entrenó: cómo sirve y qué memorizó

El modelo aprendió de la cadena **Corporación Favorita (Ecuador)**. Eso significa que su
**vocabulario memorizado** es:

- **Tiendas:** números **1 a 54**.
- **Productos (familias):** 33 categorías en inglés — `BEVERAGES`, `GROCERY I`, `DAIRY`,
  `CLEANING`, `PRODUCE`, `MEATS`, `POULTRY`, `PERSONAL CARE`, `BREAD/BAKERY`,
  `BEAUTY`, `DELI`, `EGGS`, `FROZEN FOODS`, `HOME CARE`, `HARDWARE`, etc.
- **Ciudades** (22, todas de Ecuador), **provincias** (16), **tipo de tienda** (A–E),
  **cluster** (1–17).

### ¿Cómo "sabe" si un producto es real?
**No lo sabe.** Solo revisa si el nombre **está en su lista memorizada**:
- `BEVERAGES` → lo conoce → usa lo aprendido de ese producto.
- `CAMIONETA` → no lo conoce → lo marca como **"desconocido"** y lo ignora (no da error).

### ¿De qué se "agarra" para predecir?
De dos tipos de pistas:
1. **El historial de números que manda el cliente** (sus ventas pasadas): de ahí calcula
   "cuánto vendió hace 7/14/28 días", promedios móviles, rachas de ceros, etc. **Esto se
   adapta a cada cliente.**
2. **El calendario** (día de la semana, fin de mes, quincena…): conocido a futuro.

---

## 6. Qué hace cuando NO encuentra datos (degradación elegante)

El sistema está diseñado para **no romperse** ante datos faltantes, pero la calidad baja:

| Situación | Qué hace el sistema |
|---|---|
| Falta un campo opcional (`transactions`, `on_promotion`) | Lo ignora, usa el resto |
| El producto/tienda **no estaba en el entrenamiento** | Lo trata como **"desconocido"** (NaN); predice con las otras pistas |
| El cliente no manda ciudad/estado/petróleo (no están en el contrato) | Se rellenan como "desconocido" |
| **Muy poco historial** (p. ej. 1 sola fila) | Las pistas de pasado quedan vacías → el modelo responde con un **promedio genérico** (resultados poco fiables) — es el problema de *arranque en frío* o *cold start* |
| Producto **sin historial** en COMPRAS / ALMACÉN | **Error 400** (no se puede pronosticar sin historia) |

> Por eso, una prueba con 1 fila y un producto inventado da números sin sentido: **no es
> un bug, es el límite del arranque en frío**. Para resultados realistas se necesitan
> **varios meses** de historial por serie y nombres de productos conocidos.

---

## 7. El contrato y "el cliente se adapta a nosotros"

### ¿Qué es el contrato?
Es el **formato fijo** que la API exige. Está definido con validación estricta
(`extra="forbid"`): si el cliente manda un campo con **otro nombre** o uno **de más**, la
API lo **rechaza** (error 422).

### ¿Quién se adapta a quién, hoy?
**Hoy, el cliente se adapta a nosotros.** Si su base de datos tiene columnas como
`fecha_venta` o `cantidad`, debe **transformarlas** a los nombres del contrato (`date`,
`units_sold`, …) antes de enviarlas.

**Por qué es lo correcto para un MVP:**
1. Un solo formato que mantener y probar (menos bugs).
2. El contrato usa **nombres genéricos, no atados a ningún sector ni país** → cualquier
   PYME puede mapear sus columnas fácilmente.
3. Es el estándar de la industria para APIs.

El sistema ya tiene **dos traducciones encadenadas**:
`cliente → contrato` (validación) y `contrato → motor de ML` (el adaptador interno).

---

## 8. Limitaciones honestas (importante para la defensa)

1. **El modelo es de Ecuador.** Acierta los **ritmos generales** (que son universales),
   pero falla en lo **específico de cada país** (feriados, temporadas locales). Una PYME
   de otro país obtendría un pronóstico **decente pero no fino**.
2. **Vía API, de momento el modelo solo reconoce el `product_id`** (si usas un nombre de
   la lista). La tienda, ciudad, etc., siempre le llegan como "desconocido".
3. **Posible bug detectado:** la tienda se convierte a texto (`"1"`) pero el modelo
   memorizó las tiendas como número (`1`), así que **ni siquiera la tienda 1 se
   reconoce** hoy. Es un arreglo pequeño (convertir a número antes de comparar).
4. **Un solo dataset no es "universal".** Sirve como base/MVP, pero está sesgado hacia el
   ritmo de esos datos.

---

## 9. Consideraciones a futuro

1. **Entrenar un modelo por cliente** con sus propios datos (lo más adaptable). El 90 %
   de las piezas ya existe: el adaptador, el entrenador (`entrenar_y_comparar`), el
   guardado y el cargador por versión. Faltaría el "pegamento": un endpoint para subir
   datos + entrenar en segundo plano, y un respaldo (*fallback*) al modelo genérico
   mientras el cliente nuevo aún no tiene el suyo.
2. **Mapeo de campos configurable por cliente:** que el cliente declare una vez "mi
   columna X = tu `date`" y el sistema renombre por detrás. Le quita fricción sin tocar
   el resto.
3. **Aceptar CSV/Excel**, no solo JSON.
4. **Detección automática de columnas** (lo avanzado, más adelante).
5. **Arreglar el bug de la tienda** (texto vs número) para que `store_id` también aporte.
6. **Intervalos de predicción** (`interval_80`): ya está previsto en el contrato, hoy
   diferido.

> Regla de oro: mantener **un solo formato interno** y agregar "traductores" en la
> entrada con el tiempo. Las pistas **relativas** (historial, calendario) viajan bien a
> cualquier país; los **nombres absolutos** (ciudad = Quito) solo sirven donde se
> entrenaron.

---

## 10. Glosario simple de métricas

| Término | En palabras simples |
|---|---|
| **Regresión** | Predecir un **número** (cuántas unidades) |
| **Clasificación** | Predecir una **etiqueta** (demanda alta / baja) |
| **Clustering** | **Agrupar** cosas parecidas sin etiquetas previas |
| **WAPE / MAE** | Cuánto se equivoca el pronóstico (más bajo = mejor) |
| **R²** | Qué tan bien explica la realidad (1 = perfecto) |
| **Precision** | Cuando el modelo avisa, ¿cuántas veces acierta? |
| **Recall** | De todos los casos reales, ¿cuántos detecta? |
| **F1** | Equilibrio entre Precision y Recall |
| **PR-AUC / ROC-AUC** | Qué tan bien separa las dos clases (1 = perfecto) |
| **Silueta** | Qué tan bien separados están los grupos del clustering (1 = ideal) |
| **Ensemble** | Mezclar varios modelos y promediarlos (más estable) |
| **Cold start (arranque en frío)** | Predecir con poca o ninguna historia → resultados pobres |
| **Lead time** | Días que tarda el proveedor en entregar |

---

*Documento generado como guía explicativa del proyecto SPC. Las cifras provienen de los
metadatos de los artefactos entrenados (`models/*.meta.json`) y del código de la capa API
(`src/spc/api/`) y de servicio (`src/spc/service/`).*
