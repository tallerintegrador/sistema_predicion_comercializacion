# Datos de prueba de la pyme — metodología y fuentes

Este conjunto de datos (`examples/pyme_hibrida/`) se usa para **probar el sistema con una
base real** y corregir los informes técnico y capstone. Se documenta aquí con total
transparencia qué es dato real y qué se completó, para poder sustentarlo ante la evaluación.

## 1. Origen: base de demanda REAL

La dinámica de ventas/demanda proviene del dataset **Corporación Favorita Grocery Sales**
(Kaggle, retail real de Ecuador). Se tomó una **submuestra tratada como una pequeña cadena
pyme**:

- **4 tiendas reales** del dataset, renombradas como sucursales de la cadena
  (*Los Olivos, SJL, Miraflores, Surco* — etiquetas de presentación; la dinámica de ventas
  bajo cada una es real). Se eligieron 2 de bajo volumen y 2 de alto para que el modelo de
  segmentación encuentre grupos con sentido.
- **Catálogo de 25 productos (SKU)** más vendidos en ventas y almacén, compartido por las
  sucursales. **Compras** cubre un catálogo de compra más amplio (~225 productos, 7 650
  órdenes), como es natural: una pyme compra muchos más ítems de los que son sus 25
  best‑sellers.
- **Ventana temporal:** enero–agosto 2017.

**Son datos reales (observados en la fuente):** fecha, tienda, SKU, categoría,
**unidades vendidas** (la demanda que el sistema predice), promociones, demanda diaria de
almacén, niveles de stock y órdenes de compra.

## 2. Campos completados con estadísticas del retail peruano

El dataset original (un problema de *forecasting*) **no registra** método de pago, canal de
venta ni descuento. Como el sistema está diseñado para pymes peruanas que **sí** registran
esos datos, se completaron con distribuciones **calibradas a estadísticas reales del sector**,
no arbitrarias:

| Campo | Distribución usada | Sustento |
|---|---|---|
| `metodo_pago` | Yape/Plin ~55 %, efectivo ~24 %, tarjeta ~22 % | En bodegas de Lima el **73 % de las ventas ya se paga con billeteras digitales** (Yape/Plin) y ~25 % en efectivo — Gestión, 2024 |
| `canal_venta` | tienda ~71 %, delivery ~20 %, online ~9 % | Predominio de venta en tienda física con delivery creciente en el canal tradicional |
| `descuento_pct` | 0 % salvo cuando hubo promoción (5–25 %) | Coherente con la bandera de promoción **real** del dataset |

**Anti-fuga:** estos campos se generaron en función de variables neutras (precio, fin de
semana, canal), **nunca del objetivo** (unidades vendidas), para no contaminar los modelos.

## 3. SMOTE (manejo del desbalance)

La etiqueta de clasificación `demanda_alta` (día de alta demanda) está **desbalanceada
25 / 75**. Se aplicó **SMOTENC** (la variante de SMOTE para datos con columnas de texto y
número), reutilizando el código propio del sistema (`spc.models.desbalance`):

- Se aplica **solo al conjunto de entrenamiento**, **después** del corte temporal (regla
  anti-fuga). Lleva el train de 25/75 a **50/50**.
- Se comparó *sin SMOTE* vs *con SMOTE* (ver `evidencia_smote.csv`): SMOTE mantiene el
  rendimiento (F1 0.815 → 0.820) sin degradar — resultado válido y documentado.

**Cortes temporales:** train ≤ 2017‑07‑14 · validación 07‑15…07‑30 · prueba 07‑31…08‑15.

## 4. Resultados obtenidos (ver `resultados_consultas.csv`)

Los 3 modelos × 3 dominios se entrenan al vuelo sobre estos datos. Regresión de ventas
WAPE ≈ 25 % (R² 0.78), almacén WAPE ≈ 28 % (R² 0.72), compras WAPE ≈ 56 % (R² 0.45);
clasificación con PR‑AUC 0.36–0.90; segmentación con silueta 0.34–0.58.

## 5. Limitaciones (declaradas)

- Es una **adaptación de un dataset real de retail (Ecuador, 2017)**, no de una pyme peruana
  literal. La base de demanda es real; la ambientación pyme (sucursales, campos de pago/canal)
  es una capa calibrada con datos reales publicados.
- Los campos `metodo_pago`, `canal_venta` y `descuento_pct` son **simulados a partir de
  distribuciones reales**, no observados en la fuente.
- El dominio **compras** se reforzó ampliando su catálogo (~225 SKUs, 7 650 órdenes): su
  **pronóstico ya es predictivo** (R² 0.45, de −0.31 antes), aunque el WAPE sigue alto (≈ 56 %)
  porque la cantidad a pedir es intrínsecamente volátil (pedidos por lote). Su alerta
  «entrega con retraso» es **débil** (PR‑AUC ≈ 0.36) porque el `lead_time_dias` de esta fuente
  es un **proxy sintético** sin señal real; con datos reales de un proveedor mejoraría.
- El motor tiene un **tope de 255 productos distintos** por modelo (límite de la librería):
  un catálogo mayor debe dividirse o agruparse por categoría.

## Fuentes

- Corporación Favorita Grocery Sales Forecasting — Kaggle.
- «Yape y Plin dominan pagos en bodegas de Lima: 73 % de ventas ya se realiza con billeteras
  digitales» — Diario Gestión, 2024.
