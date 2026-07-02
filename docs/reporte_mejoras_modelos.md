# Reporte de mejoras de modelos (rama `feature/mejoras-modelos-camila`)

Este documento resume, **en lenguaje simple**, las mejoras de calidad predictiva hechas
sobre el rediseño 3×3 (ver [ADR-0025](decisiones/0025-mejoras-modelos-variedad-objetivos-clustering.md)).
Está pensado para que cualquiera del equipo, al jalar esta rama, entienda **qué se hizo,
por qué y qué resultados dio**, sin haber estado presente.

Alcance: se ejecutan los puntos **b** (más variedad de datos), **e** (mejor objetivo en
almacén) y **c** (clustering de proveedores honesto), más un **experimento de métricas
offline** que compara cada modelo contra un pronóstico "ingenuo". El punto **d** (conectar
compras con el pronóstico de ventas en vivo) queda **fuera de alcance** a propósito.

> Glosario mínimo:
> - **Serie:** una combinación seguida en el tiempo, p. ej. (tienda T01, producto SKU-003).
> - **Clustering:** agrupar entidades parecidas (aquí, productos o proveedores).
> - **Silueta:** número entre −1 y 1 que mide qué tan bien separados quedan los grupos
>   (más alto = mejor).
> - **Sin fuga de datos:** el modelo solo usa información del pasado, nunca "espía" el dato
>   que debe predecir.

---

## Fase 1 — Punto (b): más variedad en los datos sintéticos

### Qué se hizo
- Antes el catálogo eran **8 productos fijos** y, si se pedían más, **se repetían**. Ahora
  se generan **productos únicos ilimitados** (SKU-001, SKU-002, …) sin repetir, cada uno con
  su categoría. Es compatible hacia atrás: pedir 8 o menos da exactamente lo de antes.
- Los datos por defecto de la demo pasan a tener **40 productos distintos** (ventas y
  almacén) y **20 proveedores distintos** (compras), que es lo que hace **creíble** el
  clustering y la clasificación.

### Por qué se diseñó así (lo importante)
Medimos cuánto tarda cada demo. Descubrimos que **lo lento no es el clustering (instantáneo),
sino la regresión**, porque el pronóstico se calcula **serie por serie**. El tiempo depende
del **número de series** (tiendas × productos), no de los días. Con 8 tiendas × 40 productos
(320 series) la demo tardaba **más de 110 segundos**.

Solución: concentrar la variedad **donde sirve al clustering** (muchos productos, muchos
proveedores) y usar **pocas tiendas** (que solo multiplican el tiempo sin mejorar los
grupos). La variedad completa se reserva para el experimento offline (Fase 4), donde el
tiempo no importa.

### Resultados medidos

| Demo | Filas | Entidades del clustering | Tiempo | Clustering |
|---|---|---|---|---|
| `/v2/ventas/demo`  | 9.600 | 40 SKUs        | **46,8 s** | 2 grupos, silueta 0,31 |
| `/v2/compras/demo` | 1.920 | 20 proveedores | **32,7 s** | 3 grupos, silueta 0,59 |
| `/v2/almacen/demo` | 9.600 | 40 SKUs        | **70,0 s** | 2 grupos, silueta 0,44 |

**Cómo validarlo tú:** levantar la API y llamar a los tres endpoints `/demo`; deben
responder en esos tiempos aproximados y traer los tres bloques (regresión, clasificación,
clustering) con las entidades indicadas. Reproducibilidad: generar dos veces con semilla 42
da datos idénticos (cubierto por `test_reproducible_misma_semilla`).

### Estado de pruebas (Fase 1)
- `tests/test_sinteticos.py`, `tests/test_zoo_liviano.py`, `tests/api/test_dominios_3x3.py`
  → **35/35 en verde** (exit 0). No hizo falta modificar los tests.

---

## Fase 2 — Punto (e): mejor objetivo de regresión en almacén

### Qué se hizo
- **Antes:** el modelo de almacén predecía `dias_de_cobertura`, que es casi una **cuenta
  fija** (stock ÷ demanda). El modelo apenas reproducía esa división: no "aprendía" nada útil.
- **Ahora:** predice la **demanda futura** (`demanda_dia` = unidades consumidas por día), que
  sí tiene señal real (estacionalidad de la semana, nivel por producto, ruido).
- Los indicadores de siempre —**días de cobertura, punto de reposición y stock de
  seguridad**— **se siguen mostrando**, pero ahora **calculados a partir de la demanda
  prevista** (bloque `indicadores_inventario` en la respuesta de `/v2/almacen`).

### Por qué importa
Predecir una fórmula no demuestra que el modelo sirva. Predecir la demanda sí, y de la
demanda se derivan todas las decisiones de inventario (cuánto pedir, cuándo, cuánto colchón
dejar). Es la mejora de mayor valor de negocio de esta rama.

### Cómo se evitó "hacer trampa" (fuga de datos)
La media de demanda y los días de cobertura **contienen** el consumo del día, así que se usan
**solo con retraso** (información del pasado) o se **excluyen**; el modelo nunca ve el dato
que debe predecir.

### Resultados medidos (demo, semilla 42)

| | Antes (`dias_de_cobertura`) | Ahora (`demanda_dia`) |
|---|---|---|
| ¿El modelo aprende? | No (≈ fórmula) | **Sí** (R²=0,84; error WAPE 16,4 %) |
| Valor de negocio | Bajo | Pronóstico de demanda + KPIs derivados |
| Tiempo de la demo de almacén | 70,0 s | **57,6 s** |

> WAPE 16,4 % = en promedio el pronóstico se desvía ~16 % de la demanda real. R²=0,84 (no
> llega a 1,0) indica que hay **algo real que aprender**, no una identidad trivial.

**Ejemplo de indicador derivado** (tienda T01, producto SKU-001): demanda prevista ≈ 49
unidades/día, cobertura proyectada ≈ 18 días, sin alerta de reposición.

### Estado de pruebas (Fase 2)
- Suite afectada **39/39 en verde** (`test_sinteticos.py`, `test_zoo_liviano.py`,
  `test_dominios_3x3.py`): las 35 previas + 2 del catálogo grande (Fase 1) + 2 nuevas de
  almacén (nuevo objetivo `demanda_dia` e `indicadores_inventario`).

## Fase 3 — Punto (c): clustering honesto (proveedores continuos + ABC en almacén)

### Qué se hizo
1. **Proveedores realistas (compras).** Antes los proveedores se fabricaban en **3 cajas
   fijas** (premium/estándar/económico) y el modelo "descubría" esas mismas 3 cajas: hacer
   trampa a uno mismo. Ahora cada proveedor se genera desde **rangos continuos con solape**,
   así que los grupos **emergen** de los datos y el número de grupos lo decide el modelo.
2. **Almacén A/B/C (k=3 fijo).** Por tu decisión, el clustering de almacén se fija en **3
   grupos** (A/B/C), el marco clásico de inventario, aunque el número "óptimo" fuera 2.

### Por qué (honestidad)
- En **compras** queríamos quitar la circularidad: el clustering se valida como
  **"recuperar segmentos que sabemos que existen"**, no como un hallazgo mágico. Que la
  silueta baje es **la prueba de que los datos son más realistas**, no un error.
- En **almacén** mandaba la **utilidad de negocio**: tres niveles A/B/C se interpretan mejor
  que dos, y la calidad de separación sigue sana.

### Resultados medidos (demo, semilla 42)

| Clustering | Antes | Ahora | Lectura |
|---|---|---|---|
| Compras (proveedores) | k=3, silueta 0,586 | **k=2, silueta 0,383** | Más realista; grupos con solape |
| Almacén (SKU, ABC) | k=2 (automático) | **k=3 (fijo), silueta 0,406** | Interpretación A/B/C, silueta sana |

- **La clasificación de "entrega con retraso" sigue con señal fuerte.** Los lead time siguen
  variando entre proveedores (de 3,2 a 20,7 días de media). El modelo discrimina muy bien
  (ROC-AUC 0,87). A un umbral sensato (0,5): **precisión 0,55 y recall 0,91**.
- **Aviso honesto:** el *selector automático de umbral* eligió un corte malo (recall casi 0).
  **No es falta de señal** (a 0,5 el modelo va muy bien); es el punto de corte. Queda anotado
  como pendiente para afinar (ver ADR-0025 c).
- **Tiempo de demo de compras:** 34,9 s (sin cambio).

### Estado de pruebas (Fase 3)
- Suite afectada **39/39 en verde**. Se **relajó** la prueba que exigía silueta > 0,3
  (premiaba datos artificiales muy separados) a un umbral informativo > 0,1.

## Fase 4 — Experimento de métricas offline (modelo vs. baseline)

**Qué es esto.** Un experimento **fuera del endpoint en vivo** (aquí el tiempo no importa)
que entrena y evalúa los **9 modelos** sobre datasets **grandes** (8 tiendas, un año de
historia; 20 proveedores) con **validación temporal** (entrenar con el pasado, evaluar con
el futuro) y **sin fuga de datos**. Sirve para demostrar con números que cada modelo
**aporta**, no solo que corre. Reproducible con `python scripts/evaluar_modelos.py` (semilla 42).

> Cómo leer: **WAPE** = error relativo (más bajo, mejor). Un "baseline" es un pronóstico
> tonto de referencia: *"último valor"* = repetir lo de ayer; *"semana pasada"* = repetir el
> mismo día de la semana anterior. Si el modelo tiene WAPE menor que el baseline, **aporta**.

### Regresión — ¿el modelo le gana al pronóstico ingenuo?

| Dominio | Qué predice | WAPE modelo | WAPE "último valor" | WAPE "semana pasada" | Veredicto |
|---|---|---|---|---|---|
| Ventas | unidades vendidas | **10,3 %** | 20,9 % | 20,6 % | ✅ **50,8 % mejor** |
| Compras | cantidad a pedir | **8,5 %** | 13,5 % | — (grano de órdenes) | ✅ **37,0 % mejor** |
| Almacén | demanda diaria | **16,1 %** | 22,4 % | 22,7 % | ✅ **28,3 % mejor** |

**Lectura honesta:** los **tres** modelos de regresión le ganan claramente al baseline. El de
almacén (el nuevo objetivo de la Fase 2) es el de menor margen, lo cual tiene sentido: la
demanda diaria es más ruidosa; aun así mejora ~28 %.

### Clasificación — ¿detecta el evento mejor que el azar?

| Dominio | Alerta | Azar (prevalencia) | Precisión | Recall | F1 | PR-AUC | ROC-AUC |
|---|---|---|---|---|---|---|---|
| Ventas | demanda alta | 0,371 | 0,859 | 0,957 | **0,905** | 0,972 | 0,983 |
| Compras | entrega con retraso | 0,231 | 0,538 | 0,876 | **0,667** | 0,602 | 0,882 |
| Almacén | riesgo de quiebre | 0,026 | 0,420 | 0,821 | **0,556** | 0,666 | 0,985 |

**Lectura honesta:**
- **Demanda alta (ventas):** excelente (F1 0,91, PR-AUC 0,97).
- **Entrega con retraso (compras):** buena y **útil** gracias al umbral arreglado — recall
  0,88 (detecta casi todos los retrasos) con precisión 0,54. Sin el arreglo, el recall era ~0,04.
- **Riesgo de quiebre (almacén):** es un **evento raro** (solo 2,6 % de los casos), lo más
  difícil. Aun así el modelo **capta el 82 % de los quiebres** (recall 0,82) y su PR-AUC 0,67
  está **muy por encima** del azar 0,026; la precisión 0,42 significa algunas falsas alarmas,
  aceptable para una alerta de seguridad (mejor sobre-avisar que quedarse corto).

### Clustering — grupos + interpretación (no solo el número)

| Dominio | Agrupa | k | Silueta | Qué distingue a los grupos |
|---|---|---|---|---|
| Ventas | productos (SKU) | 3 (auto) | 0,331 | volumen y variabilidad de demanda |
| Compras | proveedores | 2 (auto) | 0,445 | velocidad/fiabilidad vs costo |
| Almacén | productos (ABC) | 3 (fijo) | 0,414 | nivel de demanda (A/B/C) |

**Interpretación de cada grupo:**
- **Ventas (3 grupos):** *volumen bajo* (14 SKUs, ~150 uds/día), *medio* (18 SKUs, ~202) y
  *alto* (8 SKUs, ~210 y más variable/promocionado). Útil para priorizar surtido.
- **Compras (2 grupos):** *rápidos-caros-fiables* (9 proveedores: lead ~7 días, cumplimiento
  0,95, costo 16,7) vs *lentos-baratos-menos fiables* (11 proveedores: lead ~17 días,
  cumplimiento 0,89, costo 13,2). ¡La distinción real es el **lead time/fiabilidad**! (la
  etiqueta dice "volumen" porque ordena por costo, pero lo que separa a los grupos es la
  velocidad de entrega).
- **Almacén (3 grupos A/B/C):** por nivel de demanda — *bajo* (9 SKUs, ~54 uds), *medio*
  (24 SKUs, ~65), *alto* (7 SKUs, ~82). Es el análisis ABC clásico.

**Por qué las siluetas son "modestas" (0,33–0,45) y por qué eso está BIEN:** una silueta alta
significaría grupos súper separados… que es justo lo que teníamos cuando los datos eran
artificiales (arquetipos fijos). Con datos **realistas**, los productos y proveedores forman
un **continuo** (varían de forma gradual, no en cajas nítidas), así que los grupos se solapan
y la silueta baja. La segmentación **sigue siendo útil** para priorizar (qué SKUs vigilar, qué
proveedores preferir), pero es un **degradado**, no fronteras duras. Reportamos el número real
y lo explicamos, en vez de inflarlo con datos de laboratorio.

### Veredicto global (honesto)
- **9/9 modelos aportan:** las 3 regresiones ganan al baseline (28–51 %); las 3 clasificaciones
  superan de largo al azar; los 3 clusterings dan grupos interpretables y accionables.
- El punto más flojo es el **riesgo de quiebre** (evento raro → precisión baja), y se dice
  abiertamente; su recall alto lo hace útil igual.

---

## Cierre: resumen de las 4 fases y qué queda pendiente

**Qué cambió, en una frase por fase:**
1. **(b) Variedad de datos:** catálogo de productos únicos ilimitado (40 SKUs) y demos con
   variedad creíble para el clustering, manteniéndolas ágiles (se descubrió que el costo de
   la demo depende del nº de *series*, no de los días).
2. **(e) Objetivo de almacén:** de `dias_de_cobertura` (una fórmula) a **demanda futura**
   (aprendible); los KPIs de inventario se muestran derivados del pronóstico.
3. **(c) Clustering honesto:** proveedores desde un continuo (fin de la circularidad) con k
   automático; almacén con **k=3 (A/B/C)** por interpretación de negocio.
4. **Métricas offline:** los 9 modelos superan a su baseline / al azar, con lectura honesta
   (incluidas las siluetas modestas).
   - Extra: se **arregló el umbral** de la alerta de "entrega con retraso" (solo en el camino
     3×3): de recall ~0,04 a **0,85**.

**Pendiente (a propósito o anotado):**
- **Punto (d)** — conectar compras con la demanda pronosticada de ventas en vivo: **fuera de
  alcance** (alto riesgo de acoplar dominios de distinto grano). Trabajo futuro.
- **Migración del frontend** al contrato `/v2` y retiro del motor viejo: sigue pendiente
  (no era parte de esta rama).
- El **umbral operativo** nuevo no se llevó al motor viejo/compartido (fuera de alcance).

**Reproducibilidad:** todo con semilla 42. Datos y métricas se regeneran con
`python scripts/generar_datos_sinteticos.py` y `python scripts/evaluar_modelos.py`.
