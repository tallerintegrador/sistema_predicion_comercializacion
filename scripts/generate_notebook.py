"""Genera el notebook EDA completo con interpretaciones."""
import json
from pathlib import Path

cells = []


def md(source):
    cells.append({"cell_type": "markdown", "metadata": {}, "source": [source]})


def code(source):
    cells.append(
        {
            "cell_type": "code",
            "metadata": {},
            "source": [source],
            "outputs": [],
            "execution_count": None,
        }
    )


# === TITLE ===
md(
    """# Analisis Exploratorio de Datos (EDA) - Sistema Predictivo de Comercializacion

> **Objetivo:** Explorar, limpiar y caracterizar el dataset *Store Sales - Corporacion Favorita* para validar su aptitud para modelos de regresion, clasificacion y clustering.
>
> **Metodologia:** Pipeline reproducible implementado en el paquete `spc`. Se analizan 7 archivos CSV con historial de ventas (2013-2017), tiendas, productos, promociones, transacciones, precio del petroleo y calendario de feriados.

---"""
)

# === SETUP ===
md(
    """## 1. Configuracion del Entorno y Ejecucion del Pipeline

Cargamos las librerias necesarias y ejecutamos el pipeline completo que realiza: carga de datos, perfilado, calidad, analisis univariado/bivariado/temporal, integracion de fuentes, correlaciones, clasificacion y clustering."""
)

code(
    """import os
from pathlib import Path
import pandas as pd
import numpy as np
import json as _json
import warnings
from IPython.display import display, Image, Markdown

warnings.filterwarnings('ignore')
pd.set_option('display.max_columns', None)
pd.set_option('display.max_rows', 100)
pd.set_option('display.float_format', lambda x: f'{x:,.4f}')

# Ubicar la raiz del proyecto
root = Path.cwd()
if root.name == 'notebooks':
    root = root.parent
os.chdir(root)

import spc

# Ejecutar pipeline completo
resultados = spc.run_pipeline()

processed = Path('data/processed')
figures = Path('figures')

print("Pipeline ejecutado exitosamente.")
print(f"Figuras generadas: {resultados['n_figuras']}")
print(f"Reporte en: {resultados['reporte']}")"""
)

# === PERFILADO ===
md(
    """---
## 2. Perfilado General de Archivos

Se verifican los 7 archivos del dataset. La tabla muestra dimensiones, peso en memoria, rango temporal y estadisticas clave de cada archivo."""
)

code(
    """perfil = pd.read_csv(processed / 'resumen_perfil_archivos.csv')
display(perfil)"""
)

md(
    """### Interpretacion
- **train.csv** es el archivo principal con ~3 millones de filas y rango 2013-2017. Contiene la variable objetivo `sales`.
- **test.csv** cubre solo 16 dias (16-31 agosto 2017), lo que confirma separacion temporal limpia con train.
- **stores.csv** es la tabla maestra de 54 tiendas con atributos geograficos y de tipo.
- **transactions.csv** registra flujo diario de clientes por tienda.
- **oil.csv** contiene la serie macro del precio del petroleo WTI (con huecos naturales en fines de semana).
- **holidays_events.csv** cataloga 350 feriados/eventos con alcance nacional, regional y local.

> **Conclusion:** Todos los archivos esperados estan presentes y con tamanos coherentes."""
)

# === CALIDAD ===
md(
    """---
## 3. Calidad de Datos

Se evaluan nulos, duplicados, valores anomalos y consistencia referencial."""
)

code(
    """print("=== Columnas con valores nulos ===")
display(pd.read_csv(processed / 'resumen_nulos_columnas.csv'))
print()
print("=== Chequeos de calidad ===")
calidad = _json.loads((processed / 'resumen_calidad.json').read_text())
for k, v in calidad.items():
    print(f"  {k}: {v}")"""
)

md(
    """### Interpretacion
- **Sin duplicados** en ninguno de los 7 archivos.
- **Nulos:** solo `oil.dcoilwtico` tiene 43 nulos originales (3.5%), correspondientes a dias de mercado cerrado. Adicionalmente hay 486 fechas faltantes dentro del rango (fines de semana y feriados bursatiles).
- **Consistencia referencial:** todas las tiendas de train/test/transactions existen en stores (0 huerfanas).
- **Solapamiento temporal:** 0 fechas compartidas entre train y test (particion limpia).
- **Ventas negativas:** 0 (dato limpio).
- **Ventas en cero:** 939,130 filas (31.3%) — fenomeno real de familias sin demanda ciertos dias.
- **Feriados transferidos:** 12 eventos con `transferred=True` que requieren tratamiento especial.

> **Conclusion:** La calidad es alta. Los unicos nulos son operativos (petroleo) y se manejan con forward-fill."""
)

# === VARIABLE OBJETIVO ===
md(
    """---
## 4. Variable Objetivo: `sales`

Analizamos la distribucion de la variable a predecir para entender su forma, escala y anomalias."""
)

code(
    """print("=== Estadisticos descriptivos de sales ===")
display(pd.read_csv(processed / 'sales_descriptivos.csv'))"""
)

code(
    """print("=== Distribucion original de sales ===")
display(Image(filename=str(figures / '01_distribucion_sales.png'), width=700))"""
)

md(
    """### Interpretacion - Distribucion Original
- La distribucion es **extremadamente asimetrica** (asimetria = 7.36) con una cola derecha muy larga.
- El **31.3% de las observaciones son ceros** (familias sin ventas ese dia).
- La mediana (11.0) es drasticamente menor que la media (357.8), confirmando el sesgo positivo.
- Curtosis = 154.6 indica una concentracion extrema con outliers lejanos (max = 124,717).
- **Coeficiente de variacion = 3.08** (desviacion estandar es 3x la media): alta heterogeneidad.

> **Implicacion para modelado:** No se puede usar la variable cruda como objetivo de regresion lineal."""
)

code(
    """print("=== Distribucion log-transformada ===")
display(Image(filename=str(figures / '02_distribucion_log_sales.png'), width=700))"""
)

md(
    """### Interpretacion - Distribucion Log-Transformada
- Tras aplicar `log1p(sales)`, la asimetria se reduce de 7.36 a **0.41** (casi simetrica).
- La curtosis pasa de 154.6 a **-1.15** (ligeramente platicurtica, sin colas extremas).
- La forma bimodal se debe a la masa de ceros (log1p(0) = 0) versus las ventas positivas.

> **Decision:** Usar `log1p(sales)` como objetivo para modelos de regresion. Considerar modelos zero-inflated o tratar ceros como clase separada."""
)

# === TOP FAMILIAS ===
code(
    """print("=== Top 10 familias por ventas totales ===")
display(pd.read_csv(processed / 'sales_por_familia.csv').head(10))"""
)

code(
    """display(Image(filename=str(figures / '06_top_familias_ventas.png'), width=700))"""
)

md(
    """### Interpretacion - Familias de Producto
- **GROCERY I** y **BEVERAGES** dominan con >50% de las ventas totales combinadas.
- Existe enorme disparidad: la familia top vende 53,000x mas que la ultima (BOOKS).
- El % de ceros varia entre familias: PRODUCE tiene 28% vs GROCERY I con 8%, indicando patrones de demanda diferenciados.
- El coeficiente de variacion tambien difiere: PRODUCE (1.62) es mas volatil que CLEANING (0.69).

> **Implicacion:** Los modelos deben considerar la familia como variable segmentadora clave."""
)

# === UNIVARIADO ===
md(
    """---
## 5. Analisis Univariado

Se examinan las distribuciones individuales de variables categoricas y numericas."""
)

code(
    """print("=== Variables categoricas ===")
display(pd.read_csv(processed / 'univariado_categoricas.csv'))
print()
print("=== Variables numericas ===")
display(pd.read_csv(processed / 'univariado_numericas.csv'))"""
)

md(
    """### Interpretacion
**Categoricas:**
- **family:** 33 categorias, distribucion uniforme (cada familia tiene exactamente las mismas filas por tienda-dia).
- **store_nbr:** 54 tiendas con distribucion uniforme.
- **city:** 22 ciudades; Quito concentra la mayor cantidad de tiendas (18 de 54).
- **type:** 5 tipos de tienda; D es el mas comun (18 tiendas).
- **cluster:** 17 clusters comerciales; el cluster 3 es el mas poblado.

**Numericas:**
- **onpromotion:** Mediana = 0 (la mayoria de filas no tienen articulos en promocion). Fuertemente sesgada (asimetria = 11.2).
- **transactions:** Media = 1,695; CV moderado. Refleja flujo de clientes.
- **dcoilwtico:** Precio del petroleo entre $26-$111. Solo 43 nulos originales.

> **Conclusion:** Las variables categoricas son limpias y balanceadas. Las numericas presentan asimetria positiva tipica de datos de retail."""
)

# === TEMPORAL ===
md(
    """---
## 6. Analisis Temporal

Se examina la tendencia, estacionalidad y efectos de calendario sobre las ventas."""
)

md("""### 6.1 Tendencia de Ventas Diarias""")

code(
    """display(Image(filename=str(figures / '03_tendencia_ventas_diarias.png'), width=800))"""
)

md(
    """### Interpretacion - Tendencia
- **Tendencia creciente** sostenida de 2013 a 2017 (ventas diarias medias crecieron de 385K a 855K).
- **Volatilidad alta** con picos pronunciados en diciembre y caidas en enero.
- Se observa un **quiebre en abril 2016** (terremoto de Ecuador) con pico anomalo seguido de caida.
- La estacionalidad intra-anual es clara y repetitiva.

> **Implicacion:** Los modelos necesitan capturar tanto la tendencia como la estacionalidad."""
)

md("""### 6.2 Estacionalidad Anual (Year-over-Year)""")

code(
    """print("=== Ventas anuales ===")
display(pd.read_csv(processed / 'ventas_anuales.csv'))"""
)

code(
    """display(Image(filename=str(figures / '13_estacionalidad_anual.png'), width=800))"""
)

code(
    """display(Image(filename=str(figures / '14_heatmap_anio_mes.png'), width=800))"""
)

md(
    """### Interpretacion - Estacionalidad Anual
- **Crecimiento consistente:** YoY de +49% (2014), +15% (2015), +20% (2016), +8% (2017 parcial).
- El **perfil mensual se repite** cada ano con el mismo patron: picos en nov-dic, valle en feb.
- El heatmap muestra que el crecimiento es **uniforme entre meses** (toda la curva sube, no solo algunos meses).
- 2017 es parcial (enero-agosto), por lo que su total anual no es comparable.

> **Decision:** Usar variables `year` y `month` como predictoras; la tendencia aporta senal significativa."""
)

md("""### 6.3 Indice Estacional Mensual""")

code(
    """print("=== Indice estacional mensual (1.0 = nivel tipico del anio) ===")
display(pd.read_csv(processed / 'indice_estacional_mes.csv'))"""
)

code(
    """display(Image(filename=str(figures / '04_estacionalidad_mensual.png'), width=700))"""
)

md(
    """### Interpretacion - Estacionalidad Mensual
- **Diciembre** es el mes pico con indice **1.35** (35% por encima de la media anual).
- **Noviembre** (1.11), **septiembre** (1.07) y **octubre** (1.07) tambien estan por encima.
- **Febrero** es el valle mas profundo con indice **0.86** (14% por debajo de la media).
- El patron es coherente con el ciclo comercial: fiestas navidenas, regreso a clases, Dia de la Madre.

> **Implicacion:** La variable `month` tiene fuerte poder predictivo. Considerar features ciclicas (sin/cos)."""
)

md("""### 6.4 Estacionalidad por Dia de Semana""")

code(
    """display(Image(filename=str(figures / '05_estacionalidad_dia_semana.png'), width=700))"""
)

md(
    """### Interpretacion - Dia de Semana
- **Domingo** y **sabado** son los dias de mayor venta (fin de semana de compras).
- **Jueves** tiende a ser el dia mas bajo entre semana.
- La variable `dayofweek` y la bandera `is_weekend` capturan este efecto.

> **Implicacion:** Incluir `dayofweek` e `is_weekend` como predictoras."""
)

md("""### 6.5 Efecto de Feriados y Eventos""")

code(
    """print("=== Efecto por tipo de feriado ===")
display(pd.read_csv(processed / 'efecto_tipo_feriado.csv'))"""
)

code(
    """display(Image(filename=str(figures / '15_efecto_tipo_feriado.png'), width=700))"""
)

md(
    """### Interpretacion - Feriados
- Los **"Additional"** (feriados adicionales decretados, como post-terremoto 2016) generan el mayor pico: venta diaria promedio 48% superior al dia normal.
- Los **"Transfer"** (feriados trasladados) y **"Bridge"** (puentes) tambien superan la media.
- Los **"Holiday"** regulares son sorprendentemente neutros (similar al dia sin feriado), posiblemente por cierre parcial de tiendas.
- Los **"Work Day"** (dias laborales de compensacion) estan por encima del promedio.

> **Decision:** Las banderas `holiday_national`, `holiday_any` y el tipo de evento son predictoras valiosas."""
)

md("""### 6.6 Dias Pico de Ventas""")

code(
    """print("=== Top 10 dias con mayores ventas ===")
display(pd.read_csv(processed / 'dias_pico_ventas.csv'))"""
)

md(
    """### Interpretacion
- Los picos coinciden con: inicios de mes (efecto quincena/sueldo), feriados nacionales y eventos como Dia de la Madre, Navidad.
- El **1 de abril 2017** es el dia record, asociado al periodo posterior al terremoto de 2016 (acopio masivo).
- La concentracion de picos en 2016-2017 refleja tanto el crecimiento tendencial como eventos especificos."""
)

# === INTEGRACION ===
md(
    """---
## 7. Integracion de Fuentes

Se construye el dataset analitico unificado combinando las 7 fuentes originales."""
)

code(
    """print("=== Resultado de integracion ===")
integracion = _json.loads((processed / 'resumen_integracion.json').read_text())
for k, v in integracion.items():
    print(f"  {k}: {v}")
print()
print("=== Catalogo de columnas del dataset integrado ===")
display(pd.read_csv(processed / 'catalogo_columnas.csv'))"""
)

md(
    """### Interpretacion - Integracion
**Decisiones de integracion:**
1. `train` + `stores` por `store_nbr` (muchos-a-uno validado).
2. `transactions` por `date` + `store_nbr`; faltantes marcados con bandera `transactions_missing`.
3. `oil` reindexado al calendario de train; imputado con forward-fill/backward-fill.
4. `holidays_events` desagregado por alcance (nacional/regional/local); transferidos excluidos.

**Resultado:** Dataset de **3,000,888 filas x 30 columnas** (27 predictoras potenciales).
- 8.19% de filas con transacciones faltantes (dias sin dato, marcados).
- 0% de petroleo faltante despues del relleno temporal.
- 8.49% de filas con algun feriado/evento activo.

> **Conclusion:** La integracion es completa y trazable. Cada imputacion queda documentada con banderas booleanas."""
)

# === BIVARIADO Y CORRELACIONES ===
md(
    """---
## 8. Analisis Bivariado y Correlaciones

Se evaluan las relaciones entre variables predictoras y el objetivo `sales`."""
)

md("""### 8.1 Efecto de Promociones""")

code(
    """print("=== Ventas con y sin promocion ===")
display(pd.read_csv(processed / 'relacional_promo_flag.csv'))"""
)

code(
    """display(Image(filename=str(figures / '07_promocion_vs_sales.png'), width=700))"""
)

md(
    """### Interpretacion - Promociones
- Las filas **con promocion** tienen ventas promedio **7.2x mayores** que sin promocion (1,138 vs 158).
- La mediana con promocion (373) es **124x la mediana sin promocion** (3.0).
- La relacion es monotona: a mayor cantidad de articulos en promo, mayor venta media.
- `onpromotion` es la **variable con mayor correlacion lineal** con sales (r = 0.43).

> **Implicacion:** `onpromotion` es el predictor mas importante. Su ausencia en la mayoria de filas (mediana=0) sugiere que modelos de arbol la captaran mejor que lineales."""
)

md("""### 8.2 Transacciones vs Ventas""")

code(
    """display(Image(filename=str(figures / '08_transacciones_vs_sales.png'), width=700))"""
)

md(
    """### Interpretacion - Transacciones
- Relacion **positiva fuerte** entre transacciones y ventas a nivel tienda-dia.
- La linea de regresion muestra tendencia lineal clara.
- `transactions_filled` es el **segundo predictor mas correlacionado** (r = 0.23).
- Nota: en produccion (test), esta variable puede no estar disponible en tiempo real.

> **Implicacion:** Usar transacciones como feature si se dispone del dato; alternativamente usar rezagos."""
)

md("""### 8.3 Precio del Petroleo vs Ventas""")

code(
    """display(Image(filename=str(figures / '09_petroleo_vs_sales.png'), width=700))"""
)

md(
    """### Interpretacion - Petroleo
- La correlacion global petroleo-ventas es **negativa (r = -0.07)** pero es **espuria**.
- Al colorear por ano se revela que: el petroleo **bajo** de 2014 a 2016 mientras las ventas **subieron** (tendencia temporal opuesta).
- Dentro de cada ano, la relacion es debil o inexistente.
- Ecuador exporta petroleo, asi que un precio alto deberia **estimular** la economia, pero el efecto es indirecto.

> **Decision:** Incluir `dcoilwtico` como variable contexto, pero su senal predictiva directa es baja. Posible uso en interacciones o como proxy macro."""
)

md("""### 8.4 Ventas por Tipo de Tienda y Cluster""")

code(
    """print("=== Ventas por tipo de tienda ===")
display(pd.read_csv(processed / 'relacional_type_sales.csv'))"""
)

code(
    """display(Image(filename=str(figures / '17_dist_log_sales_por_tipo.png'), width=700))"""
)

code(
    """display(Image(filename=str(figures / '12_sales_promedio_cluster.png'), width=700))"""
)

md(
    """### Interpretacion - Tipo y Cluster
- Las tiendas **tipo A** tienen la mayor venta media (706), seguidas de D (351) y B (327).
- Los **clusters** muestran heterogeneidad significativa: el cluster 5 vende 4x mas que el cluster 3.
- El boxplot por tipo revela distribuciones diferenciadas (A tiene mayor mediana y rango intercuartil).

> **Implicacion:** Tanto `type` como `cluster` son features segmentadoras utiles para el modelado."""
)

md("""### 8.5 Matriz de Correlaciones""")

code(
    """print("=== Correlaciones numericas ===")
display(pd.read_csv(processed / 'correlaciones_numericas.csv', index_col=0))"""
)

code(
    """display(Image(filename=str(figures / '10_correlaciones_numericas.png'), width=750))"""
)

md(
    """### Interpretacion - Correlaciones
- **onpromotion - sales:** r = 0.43 (la correlacion mas fuerte).
- **transactions_filled - sales:** r = 0.23.
- **year - sales:** r = 0.08 (captura la tendencia creciente).
- **dcoilwtico - sales:** r = -0.07 (espuria, ya explicado).
- **is_weekend - sales:** r = 0.05.
- No hay multicolinealidad critica entre predictoras (las correlaciones entre features son moderadas).

> **Conclusion:** Se identifican 2 predictoras fuertes (promo, transacciones) y varias moderadas (calendario, tipo, cluster)."""
)

md("""### 8.6 Penetracion de Promociones en el Tiempo""")

code(
    """display(Image(filename=str(figures / '16_penetracion_promo_mensual.png'), width=800))"""
)

md(
    """### Interpretacion
- La penetracion de promociones **aumento drasticamente** a partir de 2015 (de ~10% a ~40% de las filas).
- Esto indica un **cambio de estrategia comercial** en la cadena.
- Los modelos deben considerar que la relacion promo-ventas puede tener interaccion temporal."""
)

md("""### 8.7 Ranking de Senal Lineal""")

code(
    """print("=== Senal lineal contra sales (correlacion) ===")
display(pd.read_csv(processed / 'senal_regresion.csv'))"""
)

md(
    """### Interpretacion
Las variables con mayor senal lineal para predecir `sales` son:
1. **onpromotion** (r=0.43) - senal comercial directa.
2. **transactions_filled** (r=0.23) - flujo de clientes.
3. **year** (r=0.08) - tendencia temporal.
4. **dcoilwtico** (r=-0.07) - variable macro (senal espuria).
5. **is_weekend** (r=0.05) - patron semanal.

> Nota: La correlacion lineal subestima relaciones no lineales. Modelos de arbol (XGBoost, LightGBM) pueden capturar interacciones no detectables aqui."""
)

# === CLASIFICACION ===
md(
    """---
## 9. Aptitud para Clasificacion (Demanda Alta)

Se define un objetivo binario `demanda_alta = sales > P75(sales dentro de la familia)` para evaluar si la data soporta tareas de clasificacion."""
)

code(
    """print("=== Balance de clases (umbral por familia) ===")
display(pd.read_csv(processed / 'clasificacion_demanda_alta.csv'))
print()
print("=== Balance con umbral global (P75 = 195.85) ===")
display(pd.read_csv(processed / 'clasificacion_umbral_global.csv'))"""
)

code(
    """display(Image(filename=str(figures / '11_balance_clases_demanda.png'), width=600))"""
)

md(
    """### Interpretacion - Clasificacion
- **Definicion por familia:** 77.6% clase negativa vs 22.4% positiva. Ratio de desbalance = **3.47:1**.
- **Definicion global:** 75.0% vs 25.0%. Ratio = 3:1.
- Ambas definiciones presentan desbalance moderado que **justifica tecnicas de balanceo (SMOTE, class_weight)**.
- La definicion **por familia es preferible** porque distribuye los positivos equitativamente entre categorias (evita que GROCERY I domine).

> **Conclusion:** El dataset es apto para clasificacion binaria con objetivo derivado. El desbalance esta cuantificado y requiere tratamiento explicito."""
)

# === CLUSTERING ===
md(
    """---
## 10. Aptitud para Clustering (Segmentacion)

Se valida si las tiendas y familias forman grupos naturales diferenciables."""
)

code(
    """print("=== Coeficiente de silueta por k (tiendas) ===")
display(pd.read_csv(processed / 'silhouette_tiendas.csv'))
print()
print("=== Perfil de segmentos de tiendas (mejor k) ===")
display(pd.read_csv(processed / 'perfil_segmentos_tiendas.csv'))"""
)

code(
    """display(Image(filename=str(figures / '18_segmentacion_tiendas_kmeans.png'), width=700))"""
)

code(
    """display(Image(filename=str(figures / '19_silueta_k_tiendas.png'), width=700))"""
)

md(
    """### Interpretacion - Clustering
- **Mejor k para tiendas = 2** con silueta = **0.61** (buena separacion).
- **Segmento 0** (44 tiendas): ventas medias bajas (263), transacciones moderadas (1,195), baja demanda alta (14%).
- **Segmento 1** (10 tiendas): ventas altas (776), alto flujo (3,144), alta demanda (61%). Son las tiendas "premium".
- La curva de silueta decrece hasta k=5 y luego se estabiliza - k=2 es la particion mas clara.
- **Familias:** silueta optima de **0.71** con k=2, aun mejor separacion.

> **Conclusion:** La data es **apta para clustering**. Los segmentos son interpretables y diferenciables, validando la segmentacion como herramienta analitica."""
)

# === METRICAS FINALES ===
md(
    """---
## 11. Resumen de Metricas y Conclusiones Finales

### Metricas Clave del EDA"""
)

code(
    '''print("=" * 70)
print("           METRICAS CLAVE DEL ANALISIS EXPLORATORIO")
print("=" * 70)
print()
print("--- DATASET ---")
print("  Archivos procesados:          7/7 (todos presentes)")
print("  Filas en train:               3,000,888")
print("  Rango temporal:               2013-01-01 a 2017-08-15 (4.6 anios)")
print("  Tiendas:                      54")
print("  Familias de producto:         33")
print("  Columnas integradas:          30 (27 predictoras)")
print()
print("--- CALIDAD ---")
print("  Duplicados:                   0 (en todos los archivos)")
print("  Nulos en train:               0%")
print("  Nulos en oil:                 3.5% (imputados con ffill)")
print("  Ventas en cero:               31.3% (939,130 filas)")
print("  Ventas negativas:             0")
print("  Consistencia referencial:     100% (0 tiendas huerfanas)")
print()
print("--- VARIABLE OBJETIVO (sales) ---")
print("  Media:                        357.78")
print("  Mediana:                      11.00")
print("  Desviacion estandar:          1,102.00")
print("  Asimetria (cruda):            7.36")
print("  Asimetria (log1p):            0.41  --> transformacion recomendada")
print("  Curtosis (cruda):             154.56")
print("  Curtosis (log1p):             -1.15")
print("  Coef. variacion:              3.08")
print()
print("--- PREDICTORAS MAS RELEVANTES ---")
print("  1. onpromotion:               r = 0.4279  (senal fuerte)")
print("  2. transactions_filled:       r = 0.2331  (senal moderada)")
print("  3. year:                      r = 0.0811  (tendencia)")
print("  4. dcoilwtico:                r = -0.0748 (espuria)")
print("  5. is_weekend:                r = 0.0519  (patron semanal)")
print()
print("--- ESTACIONALIDAD ---")
print("  Mes pico (diciembre):         Indice = 1.349  (+35%)")
print("  Mes valle (febrero):          Indice = 0.862  (-14%)")
print("  Crecimiento YoY promedio:     ~23% (2014-2016)")
print()
print("--- CLASIFICACION (demanda_alta) ---")
print("  Clase positiva:               22.37% (671,267 filas)")
print("  Clase negativa:               77.63% (2,329,621 filas)")
print("  Ratio desbalance:             3.47:1")
print("  Tecnica recomendada:          SMOTE / class_weight")
print()
print("--- CLUSTERING ---")
print("  Mejor k (tiendas):            2")
print("  Silueta (tiendas):            0.6075")
print("  Mejor k (familias):           2")
print("  Silueta (familias):           0.7052")
print()
print("--- FIGURAS GENERADAS ---")
print("  Total:                        19 figuras en figures/")
print()
print("=" * 70)
print("                         VEREDICTO FINAL")
print("=" * 70)
print()
print("  REGRESION:      APTA - Objetivo numerico con 27 predictoras integradas.")
print("  CLASIFICACION:  APTA - Desbalance cuantificado, justifica SMOTE.")
print("  CLUSTERING:     APTA - Silueta positiva, segmentos interpretables.")
print()
print("  RECOMENDACIONES:")
print("    1. Transformar sales con log1p para regresion.")
print("    2. Validacion temporal estricta (sin fuga de futuro).")
print("    3. Ingenieria de rezagos y medias moviles.")
print("    4. Codificacion adecuada de categoricas de alta cardinalidad.")
print("    5. Balanceo de clases para el modulo de clasificacion.")
print("    6. Usar segmentos de tiendas como feature adicional.")
print("=" * 70)'''
)

md(
    """---
## 12. Artefactos Generados

| Tipo | Ubicacion | Contenido |
|------|-----------|-----------|
| Tablas intermedias | `data/processed/*.csv` | 40+ archivos con metricas, perfiles y segmentaciones |
| Figuras | `figures/01..19_*.png` | 19 visualizaciones del analisis |
| Reporte completo | `reporte_eda.md` | Documento detallado con todas las tablas y figuras |
| Notebook reproducible | `notebooks/eda.ipynb` | Este notebook |

> **Para regenerar todo el analisis**, basta con ejecutar la primera celda de codigo (`spc.run_pipeline()`)."""
)

# === BUILD NOTEBOOK ===
nb = {
    "nbformat": 4,
    "nbformat_minor": 5,
    "metadata": {
        "kernelspec": {
            "display_name": "Python 3",
            "language": "python",
            "name": "python3",
        },
        "language_info": {"name": "python", "version": "3.11.0"},
    },
    "cells": cells,
}

out_path = Path("notebooks/eda.ipynb")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(nb, f, ensure_ascii=False, indent=1)

print(f"Notebook generado con {len(cells)} celdas en {out_path}")
