# ADR-0024 — Rediseño 3×3: un formato por dominio, modelos sklearn livianos en el momento, datos sintéticos

- **Estado:** Aceptado
- **Fecha:** 2026-06-30
- **Relacionado:** [ADR-0002](0002-modelo-regresion-ventas.md) (regresión Favorita), [ADR-0005](0005-clasificacion-almacen-2b.md) (clasificación), [ADR-0006](0006-clustering-perfilado-2c.md) (clustering), [ADR-0023](0023-prediccion-agnostica-auto-entrenada.md) (motor agnóstico, cuya orquestación se reutiliza)

## Contexto

La revisión del docente (Walter Cueva) cambió el rumbo del motor de ML. El sistema estaba
montado sobre **Corporación Favorita** (~3M filas) y un **único objetivo** (`units_sold`) del
que todo derivaba; las tres "casillas" reales de modelo estaban repartidas de forma dispareja:

| Dominio | Antes |
|---|---|
| VENTAS | solo regresión (`regresion_v3`, zoo pesado XGBoost/LightGBM/Optuna/GPU) |
| COMPRAS | sin modelo propio (lógica derivada del pronóstico de ventas) |
| ALMACÉN | clasificación (`demanda_alta = sales > P75 familia`) + clustering (KMeans) |

El docente pidió, en concreto:

1. **Cada dominio con los TRES modelos** (regresión, clasificación, clustering): 9 en total.
2. **Variables con sentido de negocio**, genéricas para PYMEs, investigadas desde cero, con
   **un solo formato por dominio** que alimente los tres modelos.
3. **Modelos ya hechos de scikit-learn que corran rápido y en el momento** en el backend
   (no boosters pesados con HPO/GPU), sobre **datos sintéticos realistas** que reemplazan a
   Favorita.
4. Corregir variables mal definidas (`ingreso`, `en_promocion`, `fin_de_semana`, `feriado`).

## Decisión

Se añade un **camino 3×3 por dominio** que convive con el resto y reemplaza el diseño basado
en Favorita como dirección del motor.

1. **Un formato por dominio** (`spc.synthetic.esquemas`, fuente única de la verdad):
   - **VENTAS** — fila por (fecha, tienda, sku, día): `unidades_vendidas`, `precio_unitario`,
     `ingreso` (**calculada** = unidades×precio), `en_promocion` (**bandera 0/1**),
     `descuento_pct`, `metodo_pago`, `canal_venta`, `es_fin_de_semana` (**bandera 0/1**),
     `dias_a_proximo_feriado` (**reemplaza** la bandera `feriado`).
   - **COMPRAS** — fila por (fecha_orden, proveedor, sku): `cantidad_pedida`,
     `precio_unitario_compra`, `costo_total` (calculada), `lead_time_dias`,
     `cantidad_recibida`, `cumplimiento` (calculada = recibida/pedida), `metodo_pago`,
     `descuento_volumen`.
   - **ALMACÉN** — foto de stock por (fecha, tienda, sku, día): `stock_actual`,
     `stock_minimo/maximo`, `demanda_diaria_promedio`, `dias_de_cobertura` (calculada),
     `rotacion`, `tiempo_reposicion_dias`, `zona_almacen`.

   Diccionario fundamentado en referencias reconocidas: **UCI Online Retail II**, datasets
   retail tipo **Rossmann/Favorita** (banderas de promoción/feriado) e **indicadores estándar
   de inventario/compras** (días de cobertura, rotación, punto de reorden, stock de seguridad
   `z·σ·√L`, análisis ABC, lead time, fill rate).

2. **Datos sintéticos por dominio** (`spc.synthetic.{ventas,compras,almacen}`,
   `scripts/generar_datos_sinteticos.py`): realistas (estacionalidad, promociones, quiebres,
   arquetipos de proveedor) y **reproducibles** por semilla. Reemplazan a Favorita.

3. **Modelos sklearn livianos en el momento** (`spc.models.zoo_liviano`): cada petición
   **entrena al vuelo** y predice. Se **reutiliza la orquestación leak-safe del motor
   agnóstico** (features genéricas, corte temporal adaptativo, selección honesta), pero con
   un **zoo solo sklearn** (Ridge / RandomForest / HistGradientBoosting para regresión;
   LogisticRegression / RandomForest para clasificación; KMeans + escalado para clustering).
   **Se descartan** LightGBM/XGBoost/Optuna/GPU en este camino.

4. **Los 9 modelos** (qué predice cada uno): VENTAS → `unidades_vendidas` / `demanda_alta`
   (P75 categoría, train-only) / segmento de SKU; COMPRAS → `cantidad_pedida` /
   `entrega_con_retraso` (P75 lead time, train-only) / segmento de proveedor; ALMACÉN →
   `dias_de_cobertura` / `riesgo_quiebre` (stock < demanda×reposición) / ABC de SKU.
   La configuración leak-safe vive en `spc.service.dominios` (las columnas derivadas del
   objetivo —`ingreso`, `costo_total`, `dias_de_cobertura`— se **excluyen** como features).

5. **Contrato 3×3** (`/v2/{ventas,compras,almacen}`, `spc.api.routers.dominios_3x3` +
   `spc.service.motor_3x3`): el cliente envía las filas de su dominio y recibe los **tres
   bloques** (regresión + clasificación + clustering) en una sola respuesta. Cada dominio
   expone además `/v2/{dominio}/demo` que corre sobre los datos sintéticos del sistema.

## Anti-fuga (rigor heredado)

- Umbrales de etiqueta (`demanda_alta` P75, `entrega_con_retraso` P75) fijados **solo en
  TRAIN**; selección en VALID; TEST evaluado una vez; semilla 42.
- En ALMACÉN, `stock_actual`/`demanda_diaria_promedio` entran como **solo-pasado** (sus
  valores del día revelarían `dias_de_cobertura`/`riesgo_quiebre`).
- En COMPRAS, `costo_total` se excluye (revelaría `cantidad_pedida`); el grano es de
  **órdenes**, así que los rezagos usan ventanas cortas (1,2,3,6), no diarias.

## Consecuencias

- **Favorita retirada**: los CSV versionados se movieron a `data/_archivo_favorita/`
  (referencia histórica). `train.csv` nunca estuvo versionado.
- **Compatibilidad**: los endpoints retail antiguos (`/sales`, `/purchases`, `/inventory`,
  `/auto/*`) y sus artefactos congelados **siguen vivos temporalmente** para no romper el
  frontend; se retirarán cuando el frontend migre al contrato `/v2`.
- **Fuera de alcance** (por pedido del docente): informes, manual de usuario, capturas,
  pruebas de aceptación y despliegue.

## Pruebas

- `tests/test_sinteticos.py` — reproducibilidad y conformidad de esquema; correcciones de
  variables; dos clases en las etiquetas derivables.
- `tests/test_zoo_liviano.py` — los 9 modelos: regresión solo-sklearn con WAPE honesto;
  clasificación con PR-AUC ≥ azar; clustering con silueta saludable y reproducible.
- `tests/api/test_dominios_3x3.py` — los endpoints `/v2` devuelven los tres bloques y las
  entradas mal formadas devuelven el error uniforme.
