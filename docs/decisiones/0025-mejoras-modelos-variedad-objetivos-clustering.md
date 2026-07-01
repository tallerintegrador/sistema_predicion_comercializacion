# ADR-0025 — Mejoras de calidad predictiva: variedad de datos (b), objetivo de almacén (e) y clustering honesto (c)

- **Estado:** Aceptado (en construcción por fases — ver "Estado por punto")
- **Fecha:** 2026-07-01
- **Rama:** `feature/mejoras-modelos-camila` (no se une a `main` hasta revisión del equipo)
- **Relacionado:** [ADR-0024](0024-rediseno-3x3-sklearn-sintetico.md) (rediseño 3×3 que se mejora aquí), [ADR-0023](0023-prediccion-agnostica-auto-entrenada.md) (motor de features/pronóstico que se reutiliza)

## Contexto

Tras el rediseño 3×3 (ADR-0024), una revisión de calidad detectó tres mejoras para que los
9 modelos no solo **corran**, sino que **aporten valor** y sean **creíbles** ante el docente:

- **(b) Variedad de datos.** El catálogo sintético eran **8 productos fijos**; pedir más
  los **repetía**. Con tan pocas entidades distintas, el clustering y la clasificación no
  eran creíbles.
- **(e) Objetivo de almacén.** La regresión de almacén predecía `dias_de_cobertura`, que es
  **casi una fórmula** (stock ÷ demanda): el modelo apenas la reproducía, sin valor.
- **(c) Clustering de proveedores circular.** Los proveedores se fabricaban metidos en
  **3 cajas fijas** (premium/estándar/económico) y el clustering "descubría" esas mismas 3
  cajas: una validación circular.

Un cuarto punto (d: encadenar compras con el pronóstico de ventas en vivo) se dejó
**fuera de alcance** a propósito (alto riesgo de acoplar dominios de distinto grano).

Reglas que se respetan en todo: **solo scikit-learn liviano** (sin GPU/LightGBM/XGBoost),
**reproducible por semilla (42)**, **sin fuga de datos** (calcular con el pasado, excluir
columnas calculadas como features) y **sin tocar el motor viejo** ni sus endpoints.

## Estado por punto

| Punto | Fase | Estado |
|---|---|---|
| (b) Variedad de datos | 1 | **Aceptado** (este ADR, abajo) |
| (e) Objetivo de almacén = demanda futura | 2 | **Aceptado** (este ADR, abajo) |
| (c) Clustering de proveedores honesto + k=3 ABC en almacén | 3 | **Aceptado** (este ADR, abajo) |

---

## (b) — Variedad de datos sintéticos con demo ágil

### Decisión

1. **Catálogo de productos ilimitado y sin repetir.** `spc.synthetic.comun.productos(n)`
   deja de reciclar 8 SKUs fijos y genera **`n` SKUs únicos** (`SKU-001…SKU-{n}`) con una
   **categoría cíclica** (`CATEGORIAS`: Bebidas, Abarrotes, Lácteos, Limpieza, Snacks,
   Cuidado personal). Es **retrocompatible**: para `n ≤ 8` produce exactamente el catálogo
   anterior, así los tests existentes (que piden ≤ 8) obtienen datos idénticos.

2. **Los defaults de los generadores son el tamaño de LA DEMO** (entrenamiento en el momento):
   - **ventas:** 2 tiendas × **40 productos** × 120 días (≈ 9.600 filas).
   - **almacén:** 2 tiendas × **40 productos** × 120 días (≈ 9.600 filas).
   - **compras:** **20 proveedores** × 4 productos × 24 órdenes (≈ 1.920 filas).

### Por qué así (hallazgo medido, no supuesto)

Se midió el tiempo de cada demo por bloque. **El clustering es instantáneo (~0,2 s); lo
lento es la regresión**, porque el **pronóstico se calcula serie por serie**
(combinación tienda×producto o proveedor×producto). Conclusión clave:

> El tiempo de la demo crece con el **nº de series**, casi nada con los días. Con
> 8 tiendas × 40 productos = **320 series**, la demo tardaba **>110 s** aunque se
> recortaran los días; recortar por debajo de ~45–60 días rompe los promedios de 28 días.

Por eso la variedad se concentra donde **sí** importa para el clustering —**los productos**
(ventas/almacén, que agrupa SKUs) y **los proveedores** (compras, que agrupa proveedores)—
y se mantienen **pocas tiendas/productos-por-proveedor**, que solo multiplican series sin
enriquecer el clustering. Las tiendas no son entidades del clustering; solo inflan el tiempo.

Esta decisión se tomó con validación explícita del equipo no técnico (se prefirió "demo
ágil con clustering intacto" sobre "máxima variedad con demo lenta"). La **variedad
completa** (muchas tiendas, muchos días) se ejercita en el **experimento offline** (Fase 4),
donde el tiempo no importa.

### Resultado (medido en el equipo de desarrollo)

| Demo | Filas | Entidades del clustering | Tiempo | Clustering |
|---|---|---|---|---|
| `/v2/ventas/demo` | 9.600 | 40 SKUs | 46,8 s | k=2, silueta 0,31 |
| `/v2/compras/demo` | 1.920 | 20 proveedores | 32,7 s | k=3, silueta 0,59 |
| `/v2/almacen/demo` | 9.600 | 40 SKUs | 70,0 s | k=2, silueta 0,44 |

(Almacén es el más lento; la Fase 2 —punto e— reoptimiza su regresión y volverá a medirse.)

### Archivos tocados

- `src/spc/synthetic/comun.py` — `CATEGORIAS` + `productos(n)` genera SKUs únicos.
- `src/spc/synthetic/ventas.py`, `compras.py`, `almacen.py` — nuevos valores por defecto
  (tamaño demo) y docstrings que explican el porqué.

### Consecuencias

- La demo mantiene su agilidad y **gana variedad creíble** (40 SKUs / 20 proveedores).
- Los **tests siguen verdes** (35/35) sin cambios: usan parámetros explícitos ≤ 8 → datos
  idénticos; `test_sinteticos.py` no cuenta productos.
- Reproducibilidad intacta (semilla 42; `test_reproducible_misma_semilla` en verde).
- **Deuda consciente:** el rendimiento del pronóstico escala con el nº de series (limitación
  del motor de pronóstico serie-a-serie). Si en el futuro se quisiera una demo con muchas
  tiendas, habría que optimizar el pronóstico o aligerar los modelos (fuera de alcance aquí).

### Pruebas

- `tests/test_sinteticos.py`, `tests/test_zoo_liviano.py`, `tests/api/test_dominios_3x3.py`
  — en verde tras el cambio (se añadieron pruebas del catálogo grande de 40 SKUs únicos).

---

## (e) — Objetivo de regresión de almacén: de `dias_de_cobertura` a `demanda_dia`

### Problema

La regresión de almacén predecía **`dias_de_cobertura`**, que es **casi una fórmula**
(`stock_actual ÷ demanda_diaria_promedio`). El modelo no "aprendía" nada útil: apenas
reproducía una división. Predecir eso no aporta valor de negocio.

### Decisión

1. **Nuevo objetivo: `demanda_dia`** — las unidades **consumidas ese día** (la demanda).
   Predecir la **demanda futura** sí es un problema real y aprendible (tiene estacionalidad
   semanal, nivel por producto y ruido). Se añadió como columna al esquema de almacén
   (`spc.synthetic.esquemas.ALMACEN`) y el generador ya la produce (era el consumo diario
   que antes se usaba solo internamente).

2. **Los KPIs clásicos se siguen MOSTRANDO, ahora derivados del pronóstico.** `dias_de_cobertura`,
   el **punto de reposición** y el **stock de seguridad** dejan de predecirse y se **calculan**
   a partir de la demanda prevista, por serie (tienda×sku), en un bloque nuevo
   `indicadores_inventario` de la respuesta `/v2/almacen`:
   - `stock_seguridad = z · σ(demanda) · √(tiempo_reposicion)` con z≈1.65 (~95 % de servicio).
   - `punto_reposicion = demanda_prevista · tiempo_reposicion + stock_seguridad`.
   - `dias_cobertura_proyectada = stock_actual / demanda_prevista`.
   - `alerta_reposicion = stock_actual ≤ punto_reposicion`.

### Anti-fuga (cuidado especial)

`demanda_diaria_promedio` y `dias_de_cobertura` **contienen** el consumo del día (son medias
o ratios que incluyen `demanda_dia`), así que **no** pueden ser features del día:
- `dias_de_cobertura` se **excluye** por completo de las entradas.
- `demanda_diaria_promedio` y `stock_actual` entran **solo-pasado** (solo sus rezagos).
- Se **quita `rotacion`** de las features de esta regresión (es un agregado de **toda** la
  serie, dudoso para pronóstico honesto).
- Los rezagos del propio objetivo (`tgt_lag_*`) los añade el motor de features (capturan la
  estacionalidad semanal), calculados siempre con el pasado.

### Resultado (demo, datos sintéticos, semilla 42)

| Métrica | Antes (`dias_de_cobertura`) | Ahora (`demanda_dia`) |
|---|---|---|
| ¿Aprendible? | No (≈ fórmula stock/demanda) | **Sí** (R²=0,84, WAPE=16,4 %) |
| Valor de negocio | Bajo | Pronóstico de demanda + KPIs derivados |
| Tiempo de la demo | 70,0 s | **57,6 s** (más ágil, menos features) |

R²=0,84 (no 1,0) confirma que hay **señal real** que el modelo captura, no una identidad
trivial. El pronóstico de demanda alimenta directamente los KPIs de reposición.

### Archivos tocados

- `src/spc/synthetic/esquemas.py` — nueva columna `demanda_dia`; `objetivo_regresion` pasa a `demanda_dia`.
- `src/spc/synthetic/almacen.py` — el generador guarda `demanda_dia` (consumo diario).
- `src/spc/service/dominios.py` — objetivo y features leak-safe de la regresión de almacén.
- `src/spc/service/motor_3x3.py` — bloque `indicadores_inventario` (KPIs derivados del pronóstico).
- Pruebas: `tests/test_sinteticos.py` (nuevo objetivo), `tests/api/test_dominios_3x3.py` (indicadores).

### Consecuencias

- El **contrato** de `/v2/almacen` gana el campo `demanda_dia` en las filas de entrada y un
  bloque `indicadores_inventario` en la respuesta. La clasificación (`riesgo_quiebre`) y el
  clustering (ABC) **no cambian**.
- La demo de almacén queda más ágil (57,6 s) sin reducir tiendas.

### Pruebas

- Suite afectada **39/39 en verde** (35 previas + 2 del catálogo grande + 2 de almacén:
  objetivo `demanda_dia` e `indicadores_inventario`).

---

## (c) — Clustering honesto: proveedores continuos + k=3 (ABC) en almacén

Esta fase tiene **dos decisiones** que comparten el tema "que el clustering sea honesto":
uno donde el nº de grupos **debe emerger** (compras) y otro donde se **fija por negocio**
(almacén). Son opuestos a propósito, y por buenas razones distintas.

### c.1 — Proveedores desde un continuo (compras): quitar la circularidad

**Problema.** Los proveedores se fabricaban metidos en **3 arquetipos fijos**
(premium/estándar/económico) y el clustering "descubría" esas mismas 3 cajas. Es una
validación **circular**: encontramos lo que nosotros mismos plantamos.

**Decisión.** En `spc.synthetic.compras.py` cada proveedor se muestrea desde **rangos
continuos** a lo largo de un eje latente de "calidad de servicio" (`_perfil_continuo`):
un `q∈[0,1]` correlaciona costo, lead time y cumplimiento —una estructura latente que
**sabemos que existe**— pero con **ruido** en cada dimensión para que los grupos se
**solapen** y no formen cajas nítidas. El clustering de compras usa **k automático** (el
que maximiza la silueta): ahora el nº de grupos es un **resultado del experimento**, no un
molde impuesto.

**Cómo se valida (honestidad).** El clustering de compras se declara como **"recuperación
de segmentos latentes que sabemos que existen"** (validación legítima), **no** como un
descubrimiento a ciegas. La caída de la silueta respecto a los arquetipos fijos es **el
resultado correcto**: datos más realistas → fronteras más difusas.

**Resultado (demo, 20 proveedores, semilla 42).**
- Silueta: **0,383** (antes 0,586 con arquetipos fijos). k automático = 2.
- El lead time **sigue variando** entre proveedores (media por proveedor de 3,2 a 20,7 días;
  amplitud 17,5), así que la clasificación de "entrega con retraso" **conserva señal**.

**Nota honesta sobre el punto de corte de "entrega con retraso".** Con los datos realistas,
el modelo **discrimina muy bien** (ROC-AUC 0,87; PR-AUC 0,59 ≫ prevalencia 0,24) y a un
umbral sensato rinde bien (umbral 0,5 → precisión 0,55, recall 0,91). Pero el **selector
automático de umbral** eligió 0,963, un punto de operación roto (recall ≈ 0,04). **No es
falta de señal, es el umbral.** Es una debilidad del selector que los datos fáciles
(arquetipos) escondían y los realistas destaparon. Queda **anotado como pendiente** (no se
tocó en esta fase para no cambiar el comportamiento de clasificación sin acuerdo, y porque
el selector se comparte con otros caminos).

### c.2 — Almacén con k=3 fijo (interpretación ABC)

**Decisión.** El clustering de almacén se **fija en k=3** (A/B/C), en vez del k automático.
Aunque la silueta prefiere k=2 (0,439) sobre k=3 (0,406), la **utilidad de negocio** —tres
niveles A/B/C, el marco estándar de clasificación de inventario— pesa más que maximizar el
número. La silueta 0,406 sigue siendo **sana**. Es la misma lógica ya usada en el clustering
de familias del proyecto: cuando el negocio pide una interpretación concreta, se respeta.

Se implementó con un parámetro `k_fijo` en `ConfigDominio` (almacén=3; ventas/compras=None
→ automático) que `entrenar_clustering` respeta, **sin dejar de calcular y reportar la curva
de silueta completa** (transparencia: se ve qué k habría elegido el criterio automático).

### Cambio de una prueba (y por qué)

La prueba `test_clustering_liviano` exigía **silueta > 0,3**. Ese umbral **premiaba clusters
muy separados**, es decir, incentivaba justo la circularidad (datos artificiales) que esta
fase elimina. Se **relajó a > 0,1** (informativo: "los grupos separan algo mejor que el
azar"), documentando que una silueta más baja sobre datos realistas es **correcta**, no un
fallo.

### Archivos tocados

- `src/spc/synthetic/compras.py` — `_perfil_continuo` (muestreo continuo con solape); se
  eliminan los 3 arquetipos fijos.
- `src/spc/service/dominios.py` — `ConfigDominio.k_fijo`; almacén `k_fijo=3`.
- `src/spc/models/zoo_liviano.py` — `entrenar_clustering(..., k_fijo=...)`.
- `src/spc/service/motor_3x3.py` — pasa `cfg.k_fijo` al clustering.
- `tests/test_zoo_liviano.py` — umbral de silueta relajado (> 0,1, informativo).

### Pruebas

- Suite afectada **39/39 en verde** tras la fase. La silueta de compras baja (esperado); la
  clasificación de retraso conserva discriminación fuerte (ROC-AUC 0,87).

### Arreglo del umbral de operación de clasificación (solo camino 3×3)

Tras aprobarse, se corrigió el punto de corte **solo en el camino 3×3**, sin tocar
`spc.models.clasificacion.seleccionar_umbral` (compartido con el motor viejo).

- **Problema:** el selector automático elegía un umbral altísimo (0,963) sobre datos
  realistas → **recall ≈ 0,04**: la alerta de "entrega con retraso" no detectaba casi nada.
  No era falta de señal (ROC-AUC 0,87), sino un punto de operación roto.
- **Decisión:** nueva función `zoo_liviano._umbral_operativo`, que elige el umbral en la
  partición de **validación** (sin fuga) con **criterio de negocio**: como no detectar el
  evento es caro, **prioriza recall** — entre los umbrales con `recall ≥ 0,75` toma el de
  **mayor F1**; si ninguno lo alcanza, cae al de mayor F1. Aplica a las tres clasificaciones
  3×3 (`demanda_alta`, `entrega_con_retraso`, `riesgo_quiebre`). Es el mismo espíritu que el
  umbral fijado (0,3185) del clasificador anterior: un punto de operación elegido por su
  utilidad, no por una métrica ciega.
- **Resultado (`entrega_con_retraso`):** umbral **0,750**, **recall 0,846**, precisión 0,584,
  **F1 0,691** (antes recall 0,038 / F1 0,073). ROC-AUC y PR-AUC intactos (0,87 / 0,59).
- **Alcance:** vive **solo** en `spc.models.zoo_liviano` (camino 3×3). El motor viejo y su
  selector no se tocan.

---

## Validación con métricas offline (Fase 4)

Para respaldar con números que los 9 modelos **aportan** (no solo que corren) se añadió
`scripts/evaluar_modelos.py`: evaluación **offline** (sin presión de tiempo), con datasets
**grandes** (8 tiendas, un año), **validación temporal** y **sin fuga**. Compara cada
regresión contra baselines ingenuos y cada clasificación contra el azar. La tabla completa,
la interpretación de cada grupo del clustering y la lectura honesta están en
[`reporte_mejoras_modelos.md`](../reporte_mejoras_modelos.md).

Resumen: **9/9 modelos superan a su baseline / al azar.** Regresión 28–51 % mejor que el
pronóstico ingenuo; clasificaciones muy por encima del azar (incluida `entrega_con_retraso`
gracias al umbral arreglado); clusterings con grupos interpretables. Las siluetas modestas
(0,33–0,45) se explican como el resultado **correcto** de datos realistas (continuos), no un
fallo.

## Fuera de alcance (a propósito)

- **Punto (d):** conectar la regresión de compras con la demanda pronosticada de ventas en
  vivo. Se dejó fuera por su alto riesgo (acopla dominios de distinto grano). Queda como
  trabajo futuro.
- **Reutilizar el umbral operativo en el motor viejo:** no se toca (fuera de alcance).
