# Reporte de EDA - Sistema Predictivo de Comercializacion

> Documento generado automaticamente por el paquete `spc` a partir de los CSV reales en `data/raw`.
> Todas las cifras provienen de calculos ejecutados; no hay valores escritos a mano.

## Resumen ejecutivo

Se analizaron los 7 archivos esperados del dataset Store Sales - Corporacion Favorita.
El archivo principal `train.csv` contiene 3 000 888 filas y 6 columnas, con rango temporal 2013-01-01 a 2017-08-15.
El dataset analitico integrado conserva 3 000 888 filas y queda con 30 columnas, de las cuales 27 son potenciales variables predictoras (se excluyen `id`, `date` y el objetivo `sales`).

**Veredicto:** la data es rica y suficiente para el proyecto. Combina historial de ventas, tiendas, familias de producto, promociones, transacciones, precio del petroleo, calendario y feriados/eventos. Presenta tambien limitaciones reales que se documentan: alta proporcion de ventas en cero, faltantes operativos en transacciones y huecos en la serie de petroleo (mercado cerrado fines de semana).

## 1. Archivos encontrados

| archivo | encontrado | tamano_mb |
| --- | --- | --- |
| train.csv | True | 116.16 |
| test.csv | True | 0.97 |
| stores.csv | True | 0.00 |
| transactions.csv | True | 1.48 |
| oil.csv | True | 0.02 |
| holidays_events.csv | True | 0.02 |
| sample_submission.csv | True | 0.33 |

## 2. Perfilado general y tabla resumen de calidad

| archivo | filas | columnas | memoria_mb | rango_fechas | tiendas_unicas | familias_unicas | duplicados | pct_nulos_total | observaciones |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| train | 3 000 888 | 6 | 60.10 | 2013-01-01 a 2017-08-15 | 54 | 33 | 0 | 0.0000% | sin duplicados; sin nulos; 939 130 ventas en cero; 0 negativas; 4 dias faltantes en rango. |
| test | 28 512 | 5 | 0.46 | 2017-08-16 a 2017-08-31 | 54 | 33 | 0 | 0.0000% | sin duplicados; sin nulos. |
| stores | 54 | 5 | 0.00 |  | 54 |  | 0 | 0.0000% | sin duplicados; sin nulos; tabla maestra de 54 tiendas. |
| transactions | 83 488 | 3 | 1.11 | 2013-01-01 a 2017-08-15 | 54 |  | 0 | 0.0000% | sin duplicados; sin nulos; 6 dias faltantes en rango. |
| oil | 1 218 | 2 | 0.01 | 2013-01-01 a 2017-08-31 |  |  | 0 | 1.7652% | sin duplicados; nulos en dcoilwtico; 486 fechas faltantes (mercado cerrado fines de semana/feriados). |
| holidays_events | 350 | 6 | 0.01 | 2012-03-02 a 2017-12-26 |  |  | 0 | 0.0000% | sin duplicados; sin nulos; 12 eventos transferidos. |
| sample_submission | 28 512 | 2 | 0.22 |  |  |  | 0 | 0.0000% | sin duplicados; sin nulos. |

Columnas con nulos detectados tras la carga:

| archivo | columna | nulos | pct_nulos |
| --- | --- | --- | --- |
| oil | dcoilwtico | 43 | 3.5304% |

Chequeos especificos de calidad:

- Tiendas de `train` ausentes en `stores`: 0.
- Tiendas de `test` ausentes en `stores`: 0.
- Tiendas de `transactions` ausentes en `stores`: 0.
- Solapamiento de fechas entre `train` y `test`: 0 (separacion temporal limpia).
- Ventas negativas en `train`: 0.
- Ventas en cero en `train`: 939 130.
- Promociones negativas en `train`: 0.
- Transacciones negativas: 0.
- Nulos originales en `oil.dcoilwtico`: 43.
- Fechas faltantes dentro del rango de `oil`: 486.
- Feriados/eventos marcados como transferidos: 12.

## 3. Variable objetivo: `sales`

Estadisticos descriptivos:

| metrica | sales |
| --- | --- |
| count | 3 000 888.0000 |
| mean | 357.7757 |
| std | 1 101.9977 |
| min | 0.0000 |
| 1% | 0.0000 |
| 5% | 0.0000 |
| 25% | 0.0000 |
| 50% | 11.0000 |
| 75% | 195.8473 |
| 95% | 1 965.0000 |
| 99% | 5 507.0000 |
| max | 124 717.0000 |

Forma de la distribucion:

| metrica | valor |
| --- | --- |
| Asimetria (cruda) | 7.3588 |
| Curtosis (cruda) | 154.5618 |
| Asimetria (log1p) | 0.4083 |
| Curtosis (log1p) | -1.1497 |
| Coef. variacion | 3.0801 |
| Media (sin ceros) | 520.7425 |
| Mediana (sin ceros) | 78.4625 |

- Proporcion de ventas en cero: 31.30% (939 130 filas).
- Regla IQR: Q1=0.0000, Q3=195.8473, limite superior=489.6181.
- Outliers segun IQR: 447 105 filas (14.90%).

Interpretacion: la asimetria positiva alta y la curtosis elevada confirman una variable muy sesgada con cola larga; tras `log1p` la asimetria se reduce de forma marcada, lo que justifica transformar el objetivo antes de modelar. El gran volumen de ceros y el contraste entre media con y sin ceros indican que conviene tratar la demanda nula de forma explicita.

Figuras:

- Por que se hace: la distribucion original muestra escala, ceros y cola derecha de la variable objetivo.
  ![](d:/UPAO/IX/Taller Integrador I/sistema_prediccion_comercializacion/figures/01_distribucion_sales.png)
- Por que se hace: `log1p` permite inspeccionar mejor una variable con fuerte asimetria.
  ![](d:/UPAO/IX/Taller Integrador I/sistema_prediccion_comercializacion/figures/02_distribucion_log_sales.png)

Top 10 familias por ventas totales (incluye coeficiente de variacion y % de ceros):

| family | filas | ventas_total | media | mediana | maximo | coef_variacion | pct_ceros |
| --- | --- | --- | --- | --- | --- | --- | --- |
| GROCERY I | 90 936 | 343 462 720 | 3 776.97 | 3 185.00 | 124 717 | 0.76 | 8.06 |
| BEVERAGES | 90 936 | 216 954 480 | 2 385.79 | 1 784.00 | 25 413 | 0.97 | 8.06 |
| PRODUCE | 90 936 | 122 704 688 | 1 349.35 | 398.29 | 17 850 | 1.62 | 28.36 |
| CLEANING | 90 936 | 97 521 288 | 1 072.42 | 938.00 | 11 377 | 0.69 | 8.06 |
| DAIRY | 90 936 | 64 487 708 | 709.15 | 520.00 | 5 636 | 0.95 | 8.06 |
| BREAD/BAKERY | 90 936 | 42 133 944 | 463.34 | 401.00 | 4 551 | 0.79 | 8.06 |
| POULTRY | 90 936 | 31 876 004 | 350.53 | 205.74 | 12 143 | 1.14 | 8.08 |
| MEATS | 90 936 | 31 086 468 | 341.85 | 224.94 | 89 576 | 1.33 | 8.06 |
| PERSONAL CARE | 90 936 | 24 592 052 | 270.43 | 222.00 | 7 504 | 0.84 | 8.07 |
| DELI | 90 936 | 24 110 322 | 265.14 | 218.97 | 2 118 | 0.79 | 8.06 |

## 4. Analisis univariado

Variables categoricas:

| variable | cardinalidad | valor_mas_frecuente | frecuencia_maxima |
| --- | --- | --- | --- |
| family | 33 | AUTOMOTIVE | 90936 |
| store_nbr | 54 | 1 | 55572 |
| city | 22 | Quito | 18 |
| state | 16 | Pichincha | 19 |
| type | 5 | D | 18 |
| cluster | 17 | 3 | 7 |

Variables numericas (incluye asimetria):

| variable | conteo | nulos | media | mediana | desv_std | asimetria | min | p25 | p75 | max |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| onpromotion_train | 3 000 888 | 0 | 2.603 | 0.000 | 12.219 | 11.167 | 0.000 | 0.000 | 0.000 | 741.000 |
| transactions | 83 488 | 0 | 1 694.602 | 1 393.000 | 963.287 | 1.518 | 5.000 | 1 046.000 | 2 079.000 | 8 359.000 |
| dcoilwtico | 1 175 | 43 | 67.714 | 53.190 | 25.630 | 0.321 | 26.190 | 46.405 | 95.660 | 110.620 |

Figura:

- Por que se hace: comparar familias muestra si la escala de demanda varia por categoria de producto.
  ![](d:/UPAO/IX/Taller Integrador I/sistema_prediccion_comercializacion/figures/06_top_familias_ventas.png)

## 5. Analisis temporal

Rangos de fechas calculados:

- `train`: 2013-01-01 a 2017-08-15; fechas faltantes en rango: 4.
- `transactions`: 2013-01-01 a 2017-08-15; fechas faltantes en rango: 6.
- `holidays_events`: 2012-03-02 a 2017-12-26; fechas faltantes en rango: 1 814.

### 5.1 Estacionalidad anual (year-over-year)

| year | dias_observados | ventas_total | venta_media_diaria | anio_completo | yoy_media_diaria_pct |
| --- | --- | --- | --- | --- | --- |
| 2013 | 364 | 140 419 008.00 | 385 766.50 | Si |  |
| 2014 | 364 | 209 474 240.00 | 575 478.69 | Si | 49.18% |
| 2015 | 364 | 240 880 096.00 | 661 758.50 | Si | 14.99% |
| 2016 | 365 | 288 654 528.00 | 790 834.31 | Si | 19.50% |
| 2017 | 227 | 194 217 072.00 | 855 581.81 | Parcial | 8.19% |

Interpretacion: los anios marcados como "Parcial" no cubren el calendario completo (2017 llega solo hasta agosto), por lo que el total anual no es comparable directo; la columna de venta media diaria y su variacion year-over-year si permiten comparar el nivel de demanda entre anios.

Figuras:

- Por que se hace: superponer el perfil mensual por anio revela si la estacionalidad se repite y si el nivel crece entre anios.
  ![](d:/UPAO/IX/Taller Integrador I/sistema_prediccion_comercializacion/figures/13_estacionalidad_anual.png)
- Por que se hace: el heatmap anio x mes condensa estacionalidad mensual y tendencia anual en una sola vista.
  ![](d:/UPAO/IX/Taller Integrador I/sistema_prediccion_comercializacion/figures/14_heatmap_anio_mes.png)

### 5.2 Estacionalidad intra-anual y calendario

Indice estacional mensual (venta media del mes / media diaria de su anio, promediado entre anios). Un valor > 1 indica un mes por encima del nivel tipico de su anio; corrige el sesgo de mezclar tendencia con estacionalidad:

| month | indice_estacional | anios_observados |
| --- | --- | --- |
| 1 | 0.924 | 5 |
| 2 | 0.862 | 5 |
| 3 | 0.962 | 5 |
| 4 | 0.910 | 5 |
| 5 | 0.922 | 5 |
| 6 | 0.961 | 5 |
| 7 | 1.018 | 5 |
| 8 | 0.953 | 5 |
| 9 | 1.074 | 4 |
| 10 | 1.068 | 4 |
| 11 | 1.111 | 4 |
| 12 | 1.349 | 4 |

Efecto de quincena y fin de mes:

| is_payday | dias | venta_media_diaria | venta_mediana_diaria |
| --- | --- | --- | --- |
| No | 1 573 | 636 962.94 | 630 811.81 |
| Si | 111 | 645 965.94 | 660 088.19 |

Efecto de dias con feriado/evento activo (cualquier alcance):

| tiene_evento_activo | dias | venta_media_diaria | venta_mediana_diaria |
| --- | --- | --- | --- |
| No | 1 441 | 627 095.81 | 624 910.00 |
| Si | 243 | 699 588.06 | 685 673.06 |

Efecto por tipo de feriado/evento nacional:

| type | dias | venta_media_diaria | venta_mediana_diaria |
| --- | --- | --- | --- |
| Additional | 29 | 929 776.69 | 1 008 143.38 |
| Transfer | 7 | 845 275.31 | 826 373.75 |
| Bridge | 3 | 796 110.00 | 858 468.19 |
| Event | 55 | 757 393.50 | 737 819.50 |
| Work Day | 5 | 663 184.69 | 569 956.94 |
| Sin feriado nacional | 1 548 | 627 918.12 | 624 754.38 |
| Holiday | 40 | 614 994.44 | 623 748.59 |

Dias con mayores ventas agregadas:

| date | sales_total |
| --- | --- |
| 2017-04-01 | 1 463 084.00 |
| 2017-01-02 | 1 402 306.38 |
| 2017-06-04 | 1 376 511.50 |
| 2016-04-18 | 1 345 920.62 |
| 2017-05-01 | 1 306 699.38 |
| 2017-07-02 | 1 296 379.25 |
| 2016-12-23 | 1 282 145.50 |
| 2016-12-04 | 1 276 195.00 |
| 2016-04-17 | 1 271 833.75 |
| 2016-05-01 | 1 270 121.25 |

Interpretacion: los picos en abril (incluido el periodo del terremoto de abril 2016, visible en los dias top) y los cierres de mes muestran que el calendario y los eventos aportan senal. El desglose por tipo de feriado distingue, por ejemplo, los dias "Work Day" (laborables de compensacion) del resto.

Figuras:

- Por que se hace: la serie diaria responde si existen tendencia, picos y cambios temporales relevantes.
  ![](d:/UPAO/IX/Taller Integrador I/sistema_prediccion_comercializacion/figures/03_tendencia_ventas_diarias.png)
- Por que se hace: el indice estacional mensual aisla el patron de calendario sin el ruido del crecimiento anual.
  ![](d:/UPAO/IX/Taller Integrador I/sistema_prediccion_comercializacion/figures/04_estacionalidad_mensual.png)
- Por que se hace: el dia de semana mide una estacionalidad operativa frecuente en retail.
  ![](d:/UPAO/IX/Taller Integrador I/sistema_prediccion_comercializacion/figures/05_estacionalidad_dia_semana.png)
- Por que se hace: comparar tipos de feriado separa efectos heterogeneos del calendario.
  ![](d:/UPAO/IX/Taller Integrador I/sistema_prediccion_comercializacion/figures/15_efecto_tipo_feriado.png)

## 6. Integracion de fuentes

Decisiones aplicadas:

- `train` se unio con `stores` por `store_nbr` (relacion muchos-a-uno validada).
- `transactions` se unio por `date` y `store_nbr`; los faltantes se conservaron con bandera `transactions_missing` y una version `transactions_filled=0`.
- `oil` se reindexo al calendario diario de `train`; `dcoilwtico` se relleno con forward fill y backward fill inicial, marcando los valores imputados.
- `holidays_events` se agrego por alcance: nacional por fecha, regional por fecha-estado y local por fecha-ciudad. Los registros con `transferred=True` no cuentan como feriados activos.

Resultados de integracion:

- Filas finales: 3 000 888.
- Columnas finales: 30 (27 potenciales predictoras).
- Filas con transacciones faltantes: 245 784 (8.19%).
- Fechas con petroleo faltante antes del relleno: 525.
- Fechas con petroleo faltante despues del relleno: 0.
- Filas con algun feriado/evento activo: 254 760 (8.49%).

Catalogo de columnas del dataset integrado:

| columna | tipo | origen | descripcion |
| --- | --- | --- | --- |
| id | int32 | train | Identificador unico de fila |
| date | datetime64[us] | train | Fecha de la observacion |
| store_nbr | int16 | train | Numero de tienda |
| family | category | train | Familia de producto |
| sales | float32 | train | OBJETIVO: ventas (unidades) tienda-familia-dia |
| onpromotion | int16 | train | Articulos de la familia en promocion ese dia |
| city | str | stores | Ciudad de la tienda |
| state | str | stores | Provincia/estado de la tienda |
| type | category | stores | Tipo de tienda (A-E) |
| cluster | int16 | stores | Cluster comercial original de la tienda |
| transactions | float64 | transactions | Transacciones de la tienda ese dia (crudo, con nulos) |
| transactions_missing | bool | derivada | Bandera: transacciones ausentes al integrar |
| transactions_filled | int32 | derivada | Transacciones con faltantes imputados a 0 |
| dcoilwtico | float32 | oil | Precio WTI del petroleo (reindexado + ffill/bfill) |
| dcoilwtico_original_missing | bool | derivada | Bandera: cotizacion de petroleo imputada |
| holiday_national | int16 | holidays | Conteo de feriados nacionales activos ese dia |
| holiday_national_types | object | holidays | Tipos de feriado nacional activos |
| holiday_regional | int16 | holidays | Feriados regionales activos (por estado) |
| holiday_local | int16 | holidays | Feriados locales activos (por ciudad) |
| holiday_any | bool | derivada | Bandera: algun feriado/evento activo |
| holiday_event_count | int16 | derivada | Suma de feriados activos de todos los alcances |
| year | int16 | calendario | Anio |
| month | int8 | calendario | Mes |
| day | int8 | calendario | Dia del mes |
| dayofweek | int8 | calendario | Dia de semana (0=Lun) |
| is_weekend | bool | calendario | Bandera fin de semana |
| is_month_end | bool | calendario | Bandera fin de mes |
| is_payday | bool | calendario | Bandera quincena (dia 15 o fin de mes) |
| family_sales_p75 | float64 | derivada | P75 de sales dentro de la familia |
| demanda_alta | bool | derivada | OBJETIVO clasif.: sales > P75 de su familia |

## 7. Analisis bivariado, relacional y correlaciones

Ventas con y sin promocion (a nivel fila):

| en_promo | filas | media_sales | mediana_sales |
| --- | --- | --- | --- |
| Sin promo | 2 389 559 | 158.2467 | 3.0000 |
| Con promo | 611 329 | 1 137.6937 | 373.0000 |

Ventas por tipo de tienda:

| type | filas | ventas_total | media_sales | mediana_sales |
| --- | --- | --- | --- | --- |
| A | 500 148 | 353 043 840.00 | 705.8787 | 24.0000 |
| D | 1 000 296 | 351 083 296.00 | 350.9794 | 16.0000 |
| C | 833 580 | 164 434 736.00 | 197.2633 | 5.0000 |
| B | 444 576 | 145 260 640.00 | 326.7397 | 7.0000 |
| E | 222 288 | 59 822 436.00 | 269.1213 | 4.0000 |

Top 10 clusters por ventas totales:

| cluster | filas | ventas_total | media_sales |
| --- | --- | --- | --- |
| 14 | 222 288 | 157 430 528.00 | 708.2277 |
| 6 | 333 432 | 114 254 384.00 | 342.6617 |
| 8 | 166 716 | 107 928 248.00 | 647.3779 |
| 11 | 166 716 | 100 614 272.00 | 603.5070 |
| 10 | 333 432 | 85 324 432.00 | 255.8976 |
| 3 | 389 004 | 75 628 704.00 | 194.4163 |
| 13 | 222 288 | 72 102 248.00 | 324.3641 |
| 5 | 55 572 | 62 087 552.00 | 1 117.2452 |
| 15 | 277 860 | 55 296 948.00 | 199.0101 |
| 1 | 166 716 | 54 376 752.00 | 326.1640 |

Ranking de senal lineal contra `sales` (correlacion y valor absoluto):

| variable | correlacion_sales | abs_corr |
| --- | --- | --- |
| onpromotion | 0.4279 | 0.4279 |
| transactions_filled | 0.2331 | 0.2331 |
| year | 0.0811 | 0.0811 |
| dcoilwtico | -0.0748 | 0.0748 |
| is_weekend | 0.0519 | 0.0519 |
| cluster | 0.0385 | 0.0385 |
| dayofweek | 0.0369 | 0.0369 |
| month | 0.0198 | 0.0198 |

Figuras:

- Por que se hace: las promociones son una senal comercial directa frente al nivel de ventas.
  ![](d:/UPAO/IX/Taller Integrador I/sistema_prediccion_comercializacion/figures/07_promocion_vs_sales.png)
- Por que se hace: las transacciones representan flujo de clientes; se valida su relacion con ventas (con linea de tendencia).
  ![](d:/UPAO/IX/Taller Integrador I/sistema_prediccion_comercializacion/figures/08_transacciones_vs_sales.png)
- Por que se hace: el precio del petroleo es una variable macro externa; se colorea por anio porque la correlacion negativa global es en gran parte espuria (tendencia temporal: ventas suben mientras el petroleo baja).
  ![](d:/UPAO/IX/Taller Integrador I/sistema_prediccion_comercializacion/figures/09_petroleo_vs_sales.png)
- Por que se hace: la matriz resume relaciones lineales entre variables numericas integradas.
  ![](d:/UPAO/IX/Taller Integrador I/sistema_prediccion_comercializacion/figures/10_correlaciones_numericas.png)
- Por que se hace: la penetracion de promociones en el tiempo muestra el cambio de estrategia comercial.
  ![](d:/UPAO/IX/Taller Integrador I/sistema_prediccion_comercializacion/figures/16_penetracion_promo_mensual.png)
- Por que se hace: el boxplot por tipo de tienda compara distribuciones completas, no solo promedios.
  ![](d:/UPAO/IX/Taller Integrador I/sistema_prediccion_comercializacion/figures/17_dist_log_sales_por_tipo.png)
- Por que se hace: los clusters de tienda se evaluan como posible variable segmentadora.
  ![](d:/UPAO/IX/Taller Integrador I/sistema_prediccion_comercializacion/figures/12_sales_promedio_cluster.png)

## 8. Aptitud para regresion, clasificacion y clustering

### 8.1 Regresion (pronostico de `sales`)

`sales` es numerica y varia por tiempo, familia, tienda, promociones, transacciones, tipo, cluster, calendario y eventos. El ranking de correlacion lineal (seccion 7) cuantifica la senal: `onpromotion` y `transactions_filled` encabezan la relacion con el objetivo. Existen 27 columnas candidatas a predictoras tras la integracion, por lo que hay material amplio para modelos de regresion (lineales, arboles, boosting). Recomendacion: transformar el objetivo (`log1p`), respetar el orden temporal en la validacion y usar variables de calendario y rezagos.

### 8.2 Clasificacion (demanda alta/baja)

Objetivo principal `demanda_alta` = `sales > P75 de sales dentro de cada family` (evita que familias de gran escala dominen el umbral). Desbalance real:

| demanda_alta | filas | pct |
| --- | --- | --- |
| No | 2 329 621 | 77.63% |
| Si | 671 267 | 22.37% |

Ratio de desbalance No:Si = 3.47 a 1.

Como contraste, un umbral P75 **global** (= 195.85) produce otro desbalance:

| demanda_alta_global | filas | pct |
| --- | --- | --- |
| No | 2 250 666 | 75.00% |
| Si | 750 222 | 25.00% |

Interpretacion: ambas definiciones generan clases desbalanceadas, lo que **justifica tecnicas de balanceo (SMOTE) en la etapa de clasificacion**, tal como exige el proyecto. La definicion por familia es preferible porque reparte el positivo entre todas las categorias.

Figura:

- Por que se hace: el balance de clases justifica el tratamiento de desbalance antes de modelar.
  ![](d:/UPAO/IX/Taller Integrador I/sistema_prediccion_comercializacion/figures/11_balance_clases_demanda.png)

### 8.3 Clustering (segmentar tiendas / familias)

Se construyeron perfiles agregados. Variables candidatas para tiendas (resumen):

| index | ventas_total | venta_media | promociones_media | transacciones_media | pct_demanda_alta |
| --- | --- | --- | --- | --- | --- |
| count | 54.0000 | 54.0000 | 54.0000 | 54.0000 | 54.0000 |
| mean | 19 882 314.0000 | 357.7758 | 2.6028 | 1 555.8079 | 0.2237 |
| std | 13 295 367.0000 | 239.2458 | 0.5827 | 947.7575 | 0.2124 |
| min | 2 696 169.7500 | 48.5167 | 0.5545 | 163.5350 | 0.0163 |
| 25% | 11 097 154.0000 | 199.6897 | 2.1830 | 910.5686 | 0.0697 |
| 50% | 15 992 048.5000 | 287.7717 | 2.6994 | 1 335.4359 | 0.1370 |
| 75% | 24 829 693.0000 | 446.8022 | 3.0331 | 1 889.1923 | 0.3309 |
| max | 62 087 552.0000 | 1 117.2452 | 3.6712 | 4 318.9388 | 0.7505 |

Variables candidatas para familias (resumen):

| index | ventas_total | venta_media | promociones_media | pct_demanda_alta | tiendas_con_ventas |
| --- | --- | --- | --- | --- | --- |
| count | 33.0000 | 33.0000 | 33.0000 | 33.0000 | 33.0000 |
| mean | 32 534 692.0000 | 357.7757 | 2.6028 | 0.2237 | 54.0000 |
| std | 71 725 640.0000 | 788.7486 | 4.6063 | 0.0556 | 0.0000 |
| min | 6 438.0000 | 0.0708 | 0.0000 | 0.0304 | 54.0000 |
| 25% | 548 842.0000 | 6.0355 | 0.0357 | 0.2340 | 54.0000 |
| 50% | 1 962 767.0000 | 21.5840 | 0.4126 | 0.2468 | 54.0000 |
| 75% | 24 592 052.0000 | 270.4325 | 2.7154 | 0.2499 | 54.0000 |
| max | 343 462 720.0000 | 3 776.9719 | 21.0566 | 0.2500 | 54.0000 |

**Validacion cuantitativa de separabilidad (KMeans + silueta sobre tiendas):**

| k | silueta | inercia |
| --- | --- | --- |
| 2 | 0.6075 | 118.51 |
| 3 | 0.4663 | 68.19 |
| 4 | 0.3999 | 45.73 |
| 5 | 0.3539 | 37.81 |
| 6 | 0.3561 | 31.07 |
| 7 | 0.3844 | 24.60 |
| 8 | 0.3394 | 20.78 |

Mejor k por silueta = 2 (silueta = 0.6075). Perfil promedio de cada segmento de tienda:

| segmento | ventas_total | venta_media | venta_mediana | promociones_media | transacciones_media | pct_demanda_alta | familias_activas | n |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | 14 598 207.00 | 262.69 | 10.31 | 2.45 | 1 194.86 | 0.14 | 33 | 44 |
| 1 | 43 132 388.00 | 776.15 | 46.40 | 3.28 | 3 143.97 | 0.61 | 33 | 10 |

En familias, la silueta optima sugiere k = 2 (silueta = 0.7052).

Interpretacion: una silueta positiva indica que las tiendas forman grupos diferenciables con estas variables, confirmando que la data es apta para clustering. Los segmentos se distinguen por volumen de ventas, flujo de transacciones y proporcion de demanda alta.

Figuras:

- Por que se hace: el scatter por segmento muestra como se separan las tiendas en variables interpretables.
  ![](d:/UPAO/IX/Taller Integrador I/sistema_prediccion_comercializacion/figures/18_segmentacion_tiendas_kmeans.png)
- Por que se hace: la curva de silueta justifica la eleccion del numero de clusters.
  ![](d:/UPAO/IX/Taller Integrador I/sistema_prediccion_comercializacion/figures/19_silueta_k_tiendas.png)

## 9. Conclusiones

- **Regresion:** apta. Objetivo numerico, historico temporal amplio (4+ anios) y 27 predictoras integradas (comerciales, operativas, geograficas, de calendario y macro). Senal lineal mas fuerte: `onpromotion` y `transactions_filled`.
- **Clasificacion:** apta con objetivo derivado `demanda_alta`. El desbalance real (22.37% positivos con umbral por familia) queda medido y justifica SMOTE.
- **Clustering:** apta. Perfiles agregados de tiendas y familias separan en segmentos con silueta positiva (KMeans), validando la segmentacion.
- **Limitaciones:** alta proporcion de ceros y fuerte asimetria en `sales` (transformar y considerar enfoques zero-inflated); `transactions` con faltantes al integrar (imputados con bandera); `oil` requiere relleno temporal documentado; `onpromotion` tiene mediana 0 (mayoria de filas sin promocion).
- **Recomendaciones de modelado:** transformar `sales` (`log1p`), validacion temporal (sin fuga de futuro), ingenieria de rezagos/medias moviles, codificacion de categoricas de alta cardinalidad (`family`, `store_nbr`) y balanceo de clases para el modulo de clasificacion.

## Anexo: artefactos generados

- Tablas intermedias: `data/processed/*.csv` y `*.json`.
- Figuras: `figures/01..19_*.png`.
- Este reporte: `reporte_eda.md`. Notebook reproducible: `notebooks/eda.ipynb`.
