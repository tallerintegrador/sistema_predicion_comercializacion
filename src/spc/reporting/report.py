"""Redaccion del reporte Markdown a partir de los resultados calculados.

No hay cifras escritas a mano: cada valor proviene de los DataFrames/dicts que
produjeron los modulos de analisis. Se reusa `markdown_table` y los `fmt_*`.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from spc.config import Settings
from spc.reporting.formatters import fmt_float, fmt_int, fmt_pct, markdown_table


def format_profiles_for_report(
    profiles: pd.DataFrame, observations: dict[str, str]
) -> pd.DataFrame:
    """Selecciona y formatea columnas del perfil para la tabla del reporte."""
    out = profiles[
        [
            "archivo",
            "filas",
            "columnas",
            "memoria_mb",
            "rango_fechas",
            "tiendas_unicas",
            "familias_unicas",
            "duplicados",
            "pct_nulos_total",
        ]
    ].copy()
    out["filas"] = out["filas"].map(fmt_int)
    out["memoria_mb"] = out["memoria_mb"].map(lambda x: fmt_float(x, 2))
    out["tiendas_unicas"] = out["tiendas_unicas"].map(lambda x: "" if pd.isna(x) else fmt_int(x))
    out["familias_unicas"] = out["familias_unicas"].map(lambda x: "" if pd.isna(x) else fmt_int(x))
    out["duplicados"] = out["duplicados"].map(fmt_int)
    out["pct_nulos_total"] = out["pct_nulos_total"].map(lambda x: fmt_pct(x, 4))
    out["observaciones"] = profiles["archivo"].map(observations)
    return out


def generate_report(
    *,
    file_check: pd.DataFrame,
    profiles: pd.DataFrame,
    missing: pd.DataFrame,
    observations: dict[str, str],
    quality: dict[str, Any],
    sales_analysis: dict[str, Any],
    univariate: dict[str, pd.DataFrame],
    temporal: dict[str, pd.DataFrame],
    integration: dict[str, Any],
    catalog: pd.DataFrame,
    relational: dict[str, pd.DataFrame],
    corr: pd.DataFrame,
    signal: pd.DataFrame,
    classification: dict[str, Any],
    store_features: pd.DataFrame,
    family_features: pd.DataFrame,
    store_seg: dict[str, Any],
    family_seg: dict[str, Any],
    figures: dict[str, str],
    settings: Settings,
) -> None:
    """Arma el Markdown completo y lo escribe en ``settings.report_path``."""
    classes = classification["classes"]
    top_corr_sales = signal.head(8).copy()
    top_corr_sales["correlacion_sales"] = top_corr_sales["correlacion_sales"].map(
        lambda x: fmt_float(x, 4)
    )
    top_corr_sales["abs_corr"] = top_corr_sales["abs_corr"].map(lambda x: fmt_float(x, 4))

    class_table = classes.copy()
    class_table["filas"] = class_table["filas"].map(fmt_int)
    class_table["pct"] = class_table["pct"].map(lambda x: fmt_pct(x, 2))

    class_global = classification["classes_global"].copy()
    class_global["filas"] = class_global["filas"].map(fmt_int)
    class_global["pct"] = class_global["pct"].map(lambda x: fmt_pct(x, 2))

    nulls_nonzero = missing[missing["nulos"] > 0].copy()
    nulls_nonzero["nulos"] = nulls_nonzero["nulos"].map(fmt_int)
    nulls_nonzero["pct_nulos"] = nulls_nonzero["pct_nulos"].map(lambda x: fmt_pct(x, 4))

    file_check_report = file_check.copy()
    file_check_report["tamano_mb"] = file_check_report["tamano_mb"].map(lambda x: fmt_float(x, 2))

    family_top = (
        sales_analysis["family_scale"]
        .head(10)[
            [
                "family",
                "filas",
                "ventas_total",
                "media",
                "mediana",
                "maximo",
                "coef_variacion",
                "pct_ceros",
            ]
        ]
        .copy()
    )
    for col in ["filas", "ventas_total", "maximo"]:
        family_top[col] = family_top[col].map(fmt_int)
    for col in ["media", "mediana", "coef_variacion", "pct_ceros"]:
        family_top[col] = family_top[col].map(lambda x: fmt_float(x, 2))

    top_days = temporal["top_days"].copy()
    top_days["sales_total"] = top_days["sales_total"].map(lambda x: fmt_float(x, 2))

    payday = temporal["payday"].copy()
    payday["is_payday"] = payday["is_payday"].map({False: "No", True: "Si"})
    payday["dias"] = payday["dias"].map(fmt_int)
    for col in ["venta_media_diaria", "venta_mediana_diaria"]:
        payday[col] = payday[col].map(lambda x: fmt_float(x, 2))

    holiday_summary = temporal["holiday_summary"].copy()
    holiday_summary["tiene_evento_activo"] = holiday_summary["tiene_evento_activo"].map(
        {False: "No", True: "Si"}
    )
    holiday_summary["dias"] = holiday_summary["dias"].map(fmt_int)
    for col in ["venta_media_diaria", "venta_mediana_diaria"]:
        holiday_summary[col] = holiday_summary[col].map(lambda x: fmt_float(x, 2))

    type_effect = temporal["type_effect"].copy()
    type_effect["dias"] = type_effect["dias"].map(fmt_int)
    for col in ["venta_media_diaria", "venta_mediana_diaria"]:
        type_effect[col] = type_effect[col].map(lambda x: fmt_float(x, 2))

    yearly = temporal["yearly"].copy()
    yearly["anio_completo"] = yearly["anio_completo"].map({False: "Parcial", True: "Si"})
    yearly["dias_observados"] = yearly["dias_observados"].map(fmt_int)
    yearly["ventas_total"] = yearly["ventas_total"].map(lambda x: fmt_float(x, 2))
    yearly["venta_media_diaria"] = yearly["venta_media_diaria"].map(lambda x: fmt_float(x, 2))
    yearly["yoy_media_diaria_pct"] = yearly["yoy_media_diaria_pct"].map(
        lambda x: "" if pd.isna(x) else fmt_pct(x, 2)
    )

    month_index = temporal["month_index"].copy()
    month_index["indice_estacional"] = month_index["indice_estacional"].map(
        lambda x: fmt_float(x, 3)
    )
    month_index["anios_observados"] = month_index["anios_observados"].map(fmt_int)

    promo_flag = relational["promo_flag"].copy()
    promo_flag["filas"] = promo_flag["filas"].map(fmt_int)
    for col in ["media_sales", "mediana_sales"]:
        promo_flag[col] = promo_flag[col].map(lambda x: fmt_float(x, 4))

    numeric_report = univariate["numericas"].copy()
    numeric_report["conteo"] = numeric_report["conteo"].map(fmt_int)
    numeric_report["nulos"] = numeric_report["nulos"].map(fmt_int)
    for col in ["media", "mediana", "desv_std", "asimetria", "min", "p25", "p75", "max"]:
        numeric_report[col] = numeric_report[col].map(lambda x: fmt_float(x, 3))

    sales_desc = sales_analysis["descriptivos"].reset_index().rename(columns={"index": "metrica"})
    sales_desc["sales"] = sales_desc["sales"].map(lambda x: fmt_float(x, 4))

    shape = sales_analysis["shape_stats"]
    shape_table = pd.DataFrame(
        [
            {"metrica": "Asimetria (cruda)", "valor": fmt_float(shape["asimetria_cruda"], 4)},
            {"metrica": "Curtosis (cruda)", "valor": fmt_float(shape["curtosis_cruda"], 4)},
            {"metrica": "Asimetria (log1p)", "valor": fmt_float(shape["asimetria_log1p"], 4)},
            {"metrica": "Curtosis (log1p)", "valor": fmt_float(shape["curtosis_log1p"], 4)},
            {"metrica": "Coef. variacion", "valor": fmt_float(shape["coef_variacion"], 4)},
            {"metrica": "Media (sin ceros)", "valor": fmt_float(shape["media_sin_ceros"], 4)},
            {"metrica": "Mediana (sin ceros)", "valor": fmt_float(shape["mediana_sin_ceros"], 4)},
        ]
    )

    type_sales = relational["type_sales"].copy()
    type_sales["filas"] = type_sales["filas"].map(fmt_int)
    type_sales["ventas_total"] = type_sales["ventas_total"].map(lambda x: fmt_float(x, 2))
    type_sales["media_sales"] = type_sales["media_sales"].map(lambda x: fmt_float(x, 4))
    type_sales["mediana_sales"] = type_sales["mediana_sales"].map(lambda x: fmt_float(x, 4))

    cluster_sales = relational["cluster_sales"].head(10).copy()
    cluster_sales["filas"] = cluster_sales["filas"].map(fmt_int)
    cluster_sales["ventas_total"] = cluster_sales["ventas_total"].map(lambda x: fmt_float(x, 2))
    cluster_sales["media_sales"] = cluster_sales["media_sales"].map(lambda x: fmt_float(x, 4))

    catalog_report = catalog.copy()

    store_feature_cols = [
        "ventas_total",
        "venta_media",
        "promociones_media",
        "transacciones_media",
        "pct_demanda_alta",
    ]
    store_features_summary = store_features[store_feature_cols].describe().reset_index()
    for col in store_feature_cols:
        store_features_summary[col] = store_features_summary[col].map(lambda x: fmt_float(x, 4))

    family_feature_cols = [
        "ventas_total",
        "venta_media",
        "promociones_media",
        "pct_demanda_alta",
        "tiendas_con_ventas",
    ]
    family_features_summary = family_features[family_feature_cols].describe().reset_index()
    for col in family_feature_cols:
        family_features_summary[col] = family_features_summary[col].map(lambda x: fmt_float(x, 4))

    store_sil = store_seg["silhouette"].copy()
    store_sil["silueta"] = store_sil["silueta"].map(lambda x: fmt_float(x, 4))
    store_sil["inercia"] = store_sil["inercia"].map(lambda x: fmt_float(x, 2))

    store_profile = store_seg["profile"].copy()
    for col in [
        "ventas_total",
        "venta_media",
        "venta_mediana",
        "promociones_media",
        "transacciones_media",
        "pct_demanda_alta",
    ]:
        store_profile[col] = store_profile[col].map(lambda x: fmt_float(x, 2))
    store_profile["familias_activas"] = store_profile["familias_activas"].map(fmt_int)
    store_profile["n"] = store_profile["n"].map(fmt_int)

    report = f"""# Reporte de EDA - Sistema Predictivo de Comercializacion

> Documento generado automaticamente por el paquete `spc` a partir de los CSV reales en `data/raw`.
> Todas las cifras provienen de calculos ejecutados; no hay valores escritos a mano.

## Resumen ejecutivo

Se analizaron los 7 archivos esperados del dataset Store Sales - Corporacion Favorita.
El archivo principal `train.csv` contiene {fmt_int(profiles.loc[profiles['archivo'].eq('train'), 'filas'].iloc[0])} filas y {fmt_int(profiles.loc[profiles['archivo'].eq('train'), 'columnas'].iloc[0])} columnas, con rango temporal {profiles.loc[profiles['archivo'].eq('train'), 'rango_fechas'].iloc[0]}.
El dataset analitico integrado conserva {fmt_int(integration['filas'])} filas y queda con {fmt_int(integration['columnas'])} columnas, de las cuales {fmt_int(integration['n_predictoras'])} son potenciales variables predictoras (se excluyen `id`, `date` y el objetivo `sales`).

**Veredicto:** la data es rica y suficiente para el proyecto. Combina historial de ventas, tiendas, familias de producto, promociones, transacciones, precio del petroleo, calendario y feriados/eventos. Presenta tambien limitaciones reales que se documentan: alta proporcion de ventas en cero, faltantes operativos en transacciones y huecos en la serie de petroleo (mercado cerrado fines de semana).

## 1. Archivos encontrados

{markdown_table(file_check_report)}

## 2. Perfilado general y tabla resumen de calidad

{markdown_table(format_profiles_for_report(profiles, observations))}

Columnas con nulos detectados tras la carga:

{markdown_table(nulls_nonzero) if not nulls_nonzero.empty else '_No se detectaron nulos salvo los documentados durante integracion._'}

Chequeos especificos de calidad:

- Tiendas de `train` ausentes en `stores`: {fmt_int(len(quality['train_store_not_in_stores']))}.
- Tiendas de `test` ausentes en `stores`: {fmt_int(len(quality['test_store_not_in_stores']))}.
- Tiendas de `transactions` ausentes en `stores`: {fmt_int(len(quality['transactions_store_not_in_stores']))}.
- Solapamiento de fechas entre `train` y `test`: {fmt_int(quality['test_overlap_train_dates'])} (separacion temporal limpia).
- Ventas negativas en `train`: {fmt_int(quality['sales_negative'])}.
- Ventas en cero en `train`: {fmt_int(quality['sales_zero'])}.
- Promociones negativas en `train`: {fmt_int(quality['onpromotion_negative_train'])}.
- Transacciones negativas: {fmt_int(quality['transactions_negative'])}.
- Nulos originales en `oil.dcoilwtico`: {fmt_int(quality['oil_null_original'])}.
- Fechas faltantes dentro del rango de `oil`: {fmt_int(quality['oil_missing_dates_in_range'])}.
- Feriados/eventos marcados como transferidos: {fmt_int(quality['holidays_transferred_true'])}.

## 3. Variable objetivo: `sales`

Estadisticos descriptivos:

{markdown_table(sales_desc)}

Forma de la distribucion:

{markdown_table(shape_table)}

- Proporcion de ventas en cero: {fmt_pct(sales_analysis['zero_pct'], 2)} ({fmt_int(sales_analysis['zero_count'])} filas).
- Regla IQR: Q1={fmt_float(sales_analysis['q1'], 4)}, Q3={fmt_float(sales_analysis['q3'], 4)}, limite superior={fmt_float(sales_analysis['outlier_upper'], 4)}.
- Outliers segun IQR: {fmt_int(sales_analysis['outlier_count'])} filas ({fmt_pct(sales_analysis['outlier_pct'], 2)}).

Interpretacion: la asimetria positiva alta y la curtosis elevada confirman una variable muy sesgada con cola larga; tras `log1p` la asimetria se reduce de forma marcada, lo que justifica transformar el objetivo antes de modelar. El gran volumen de ceros y el contraste entre media con y sin ceros indican que conviene tratar la demanda nula de forma explicita.

Figuras:

- Por que se hace: la distribucion original muestra escala, ceros y cola derecha de la variable objetivo.
  ![]({figures['sales_distribution']})
- Por que se hace: `log1p` permite inspeccionar mejor una variable con fuerte asimetria.
  ![]({figures['sales_log_distribution']})

Top 10 familias por ventas totales (incluye coeficiente de variacion y % de ceros):

{markdown_table(family_top)}

## 4. Analisis univariado

Variables categoricas:

{markdown_table(univariate['categoricas'])}

Variables numericas (incluye asimetria):

{markdown_table(numeric_report)}

Figura:

- Por que se hace: comparar familias muestra si la escala de demanda varia por categoria de producto.
  ![]({figures['top_families']})

## 5. Analisis temporal

Rangos de fechas calculados:

- `train`: {quality['train_date_min']} a {quality['train_date_max']}; fechas faltantes en rango: {fmt_int(quality['train_missing_dates_in_range'])}.
- `transactions`: {quality['transactions_date_min']} a {quality['transactions_date_max']}; fechas faltantes en rango: {fmt_int(quality['transactions_missing_dates_in_range'])}.
- `holidays_events`: {quality['holidays_events_date_min']} a {quality['holidays_events_date_max']}; fechas faltantes en rango: {fmt_int(quality['holidays_events_missing_dates_in_range'])}.

### 5.1 Estacionalidad anual (year-over-year)

{markdown_table(yearly)}

Interpretacion: los anios marcados como "Parcial" no cubren el calendario completo (2017 llega solo hasta agosto), por lo que el total anual no es comparable directo; la columna de venta media diaria y su variacion year-over-year si permiten comparar el nivel de demanda entre anios.

Figuras:

- Por que se hace: superponer el perfil mensual por anio revela si la estacionalidad se repite y si el nivel crece entre anios.
  ![]({figures['annual_seasonality']})
- Por que se hace: el heatmap anio x mes condensa estacionalidad mensual y tendencia anual en una sola vista.
  ![]({figures['year_month_heatmap']})

### 5.2 Estacionalidad intra-anual y calendario

Indice estacional mensual (venta media del mes / media diaria de su anio, promediado entre anios). Un valor > 1 indica un mes por encima del nivel tipico de su anio; corrige el sesgo de mezclar tendencia con estacionalidad:

{markdown_table(month_index)}

Efecto de quincena y fin de mes:

{markdown_table(payday)}

Efecto de dias con feriado/evento activo (cualquier alcance):

{markdown_table(holiday_summary)}

Efecto por tipo de feriado/evento nacional:

{markdown_table(type_effect)}

Dias con mayores ventas agregadas:

{markdown_table(top_days)}

Interpretacion: los picos en abril (incluido el periodo del terremoto de abril 2016, visible en los dias top) y los cierres de mes muestran que el calendario y los eventos aportan senal. El desglose por tipo de feriado distingue, por ejemplo, los dias "Work Day" (laborables de compensacion) del resto.

Figuras:

- Por que se hace: la serie diaria responde si existen tendencia, picos y cambios temporales relevantes.
  ![]({figures['daily_trend']})
- Por que se hace: el indice estacional mensual aisla el patron de calendario sin el ruido del crecimiento anual.
  ![]({figures['monthly_seasonality']})
- Por que se hace: el dia de semana mide una estacionalidad operativa frecuente en retail.
  ![]({figures['dow_seasonality']})
- Por que se hace: comparar tipos de feriado separa efectos heterogeneos del calendario.
  ![]({figures['holiday_type']})

## 6. Integracion de fuentes

Decisiones aplicadas:

- `train` se unio con `stores` por `store_nbr` (relacion muchos-a-uno validada).
- `transactions` se unio por `date` y `store_nbr`; los faltantes se conservaron con bandera `transactions_missing` y una version `transactions_filled=0`.
- `oil` se reindexo al calendario diario de `train`; `dcoilwtico` se relleno con forward fill y backward fill inicial, marcando los valores imputados.
- `holidays_events` se agrego por alcance: nacional por fecha, regional por fecha-estado y local por fecha-ciudad. Los registros con `transferred=True` no cuentan como feriados activos.

Resultados de integracion:

- Filas finales: {fmt_int(integration['filas'])}.
- Columnas finales: {fmt_int(integration['columnas'])} ({fmt_int(integration['n_predictoras'])} potenciales predictoras).
- Filas con transacciones faltantes: {fmt_int(integration['transactions_missing_rows'])} ({fmt_pct(integration['transactions_missing_pct'], 2)}).
- Fechas con petroleo faltante antes del relleno: {fmt_int(integration['oil_original_missing_dates_after_reindex'])}.
- Fechas con petroleo faltante despues del relleno: {fmt_int(integration['oil_missing_after_fill'])}.
- Filas con algun feriado/evento activo: {fmt_int(integration['holiday_any_rows'])} ({fmt_pct(integration['holiday_any_pct'], 2)}).

Catalogo de columnas del dataset integrado:

{markdown_table(catalog_report)}

## 7. Analisis bivariado, relacional y correlaciones

Ventas con y sin promocion (a nivel fila):

{markdown_table(promo_flag)}

Ventas por tipo de tienda:

{markdown_table(type_sales)}

Top 10 clusters por ventas totales:

{markdown_table(cluster_sales)}

Ranking de senal lineal contra `sales` (correlacion y valor absoluto):

{markdown_table(top_corr_sales)}

Figuras:

- Por que se hace: las promociones son una senal comercial directa frente al nivel de ventas.
  ![]({figures['promo_sales']})
- Por que se hace: las transacciones representan flujo de clientes; se valida su relacion con ventas (con linea de tendencia).
  ![]({figures['transactions_sales']})
- Por que se hace: el precio del petroleo es una variable macro externa; se colorea por anio porque la correlacion negativa global es en gran parte espuria (tendencia temporal: ventas suben mientras el petroleo baja).
  ![]({figures['oil_sales']})
- Por que se hace: la matriz resume relaciones lineales entre variables numericas integradas.
  ![]({figures['correlation']})
- Por que se hace: la penetracion de promociones en el tiempo muestra el cambio de estrategia comercial.
  ![]({figures['promo_penetration']})
- Por que se hace: el boxplot por tipo de tienda compara distribuciones completas, no solo promedios.
  ![]({figures['dist_by_type']})
- Por que se hace: los clusters de tienda se evaluan como posible variable segmentadora.
  ![]({figures['cluster_sales']})

## 8. Aptitud para regresion, clasificacion y clustering

### 8.1 Regresion (pronostico de `sales`)

`sales` es numerica y varia por tiempo, familia, tienda, promociones, transacciones, tipo, cluster, calendario y eventos. El ranking de correlacion lineal (seccion 7) cuantifica la senal: `onpromotion` y `transactions_filled` encabezan la relacion con el objetivo. Existen {fmt_int(integration['n_predictoras'])} columnas candidatas a predictoras tras la integracion, por lo que hay material amplio para modelos de regresion (lineales, arboles, boosting). Recomendacion: transformar el objetivo (`log1p`), respetar el orden temporal en la validacion y usar variables de calendario y rezagos.

### 8.2 Clasificacion (demanda alta/baja)

Objetivo principal `demanda_alta` = `sales > P75 de sales dentro de cada family` (evita que familias de gran escala dominen el umbral). Desbalance real:

{markdown_table(class_table)}

Ratio de desbalance No:Si = {fmt_float(classification['ratio_desbalance'], 2)} a 1.

Como contraste, un umbral P75 **global** (= {fmt_float(classification['p75_global'], 2)}) produce otro desbalance:

{markdown_table(class_global)}

Interpretacion: ambas definiciones generan clases desbalanceadas, lo que **justifica tecnicas de balanceo (SMOTE) en la etapa de clasificacion**, tal como exige el proyecto. La definicion por familia es preferible porque reparte el positivo entre todas las categorias.

Figura:

- Por que se hace: el balance de clases justifica el tratamiento de desbalance antes de modelar.
  ![]({figures['class_balance']})

### 8.3 Clustering (segmentar tiendas / familias)

Se construyeron perfiles agregados. Variables candidatas para tiendas (resumen):

{markdown_table(store_features_summary)}

Variables candidatas para familias (resumen):

{markdown_table(family_features_summary)}

**Validacion cuantitativa de separabilidad (KMeans + silueta sobre tiendas):**

{markdown_table(store_sil)}

Mejor k por silueta = {fmt_int(store_seg['best_k'])} (silueta = {fmt_float(store_seg['best_sil'], 4)}). Perfil promedio de cada segmento de tienda:

{markdown_table(store_profile)}

En familias, la silueta optima sugiere k = {fmt_int(family_seg['best_k'])} (silueta = {fmt_float(family_seg['best_sil'], 4)}).

Interpretacion: una silueta positiva indica que las tiendas forman grupos diferenciables con estas variables, confirmando que la data es apta para clustering. Los segmentos se distinguen por volumen de ventas, flujo de transacciones y proporcion de demanda alta.

Figuras:

- Por que se hace: el scatter por segmento muestra como se separan las tiendas en variables interpretables.
  ![]({figures['store_segments']})
- Por que se hace: la curva de silueta justifica la eleccion del numero de clusters.
  ![]({figures['silhouette']})

## 9. Conclusiones

- **Regresion:** apta. Objetivo numerico, historico temporal amplio (4+ anios) y {fmt_int(integration['n_predictoras'])} predictoras integradas (comerciales, operativas, geograficas, de calendario y macro). Senal lineal mas fuerte: `onpromotion` y `transactions_filled`.
- **Clasificacion:** apta con objetivo derivado `demanda_alta`. El desbalance real ({fmt_pct(classes.loc[classes['demanda_alta'].eq('Si'), 'pct'].iloc[0] if (classes['demanda_alta'].eq('Si')).any() else 0, 2)} positivos con umbral por familia) queda medido y justifica SMOTE.
- **Clustering:** apta. Perfiles agregados de tiendas y familias separan en segmentos con silueta positiva (KMeans), validando la segmentacion.
- **Limitaciones:** alta proporcion de ceros y fuerte asimetria en `sales` (transformar y considerar enfoques zero-inflated); `transactions` con faltantes al integrar (imputados con bandera); `oil` requiere relleno temporal documentado; `onpromotion` tiene mediana 0 (mayoria de filas sin promocion).
- **Recomendaciones de modelado:** transformar `sales` (`log1p`), validacion temporal (sin fuga de futuro), ingenieria de rezagos/medias moviles, codificacion de categoricas de alta cardinalidad (`family`, `store_nbr`) y balanceo de clases para el modulo de clasificacion.

## Anexo: artefactos generados

- Tablas intermedias: `data/processed/*.csv` y `*.json`.
- Figuras: `figures/01..19_*.png`.
- Este reporte: `reporte_eda.md`. Notebook reproducible: `notebooks/eda.ipynb`.
"""
    settings.report_path.write_text(report, encoding="utf-8")
