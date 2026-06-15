# Reporte de Clustering / Perfilado (Fase 2c)

> Generado por `spc.models.clustering`. Segmenta **tiendas** y **familias** con KMeans sobre perfiles agregados (un vector por entidad). Escala obligatoria (StandardScaler **dentro** del artefacto); k elegido por **silueta** (curva reportada); centroides en **unidades originales** + etiqueta narrativa. CPU puro, determinista (semilla 42). Cierra la **Fase 2** (motor de ML).

## Tiendas (`store_nbr`) — 54 entidades

### Diccionario de features de perfil

| feature | descripcion |
| --- | --- |
| venta_media | Venta media diaria de la tienda (unidades). Nivel de demanda. |
| venta_mediana | Venta mediana diaria (robusta a la cola larga). Nivel tipico. |
| cv_ventas | Coef. de variacion (std/media) de la venta. Dispersion/volatilidad. |
| tasa_ceros | Fraccion de observaciones tienda-familia-dia con venta 0. Intermitencia. |
| ventas_total | Volumen total historico (suma de unidades). Tamano de la tienda. |
| promo_media | Intensidad de promocion (`onpromotion` medio). Apoyo comercial. |
| transacciones_media | Transacciones medias diarias. Flujo de clientes. |
| ratio_finde | Venta media de fin de semana / entre semana. Estacionalidad operativa. |
| pct_demanda_alta | Fraccion de filas con `demanda_alta=1` (>P75 de su familia). |

### Curva de seleccion de k (set de produccion)

Silueta (principal, mayor mejor) + inercia (codo) + Davies-Bouldin (menor mejor) + Calinski-Harabasz (mayor mejor).

| k | silueta | inercia | davies_bouldin | calinski_harabasz | elegido |
| --- | --- | --- | --- | --- | --- |
| 2 | 0.4615 | 261.02 | 0.8135 | 44.82 | <- elegido |
| 3 | 0.4339 | 186.5 | 0.879 | 40.95 |  |
| 4 | 0.3279 | 128.3 | 0.7936 | 46.47 |  |
| 5 | 0.355 | 98.87 | 0.7497 | 47.96 |  |
| 6 | 0.3078 | 82.96 | 0.8354 | 46.64 |  |
| 7 | 0.3322 | 68.25 | 0.8379 | 47.94 |  |
| 8 | 0.3315 | 56.1 | 0.7275 | 50.36 |  |
| 9 | 0.3103 | 50.2 | 0.8135 | 48.83 |  |
| 10 | 0.2794 | 46.18 | 0.8073 | 46.56 |  |

**k elegido = 2** por maxima silueta = **0.4615**.

### Reproduccion del orden de magnitud del EDA

Con el set EXACTO del EDA, la silueta optima es **0.6075** (k=2), frente a la referencia del EDA **0.6075** (k=2): coincide **a 4 decimales**. El pipeline recupera el resultado del EDA; la diferencia con el set de produccion (silueta **0.4615**) es por **features, no por implementacion**.

**Por que el set de produccion da una silueta algo menor:** el set rico anade ejes (dispersion `cv_ventas`, intermitencia `tasa_ceros`, estacionalidad `ratio_finde`) que no se alinean con el corte limpio por volumen del EDA. El k=2 sigue siendo optimo y los segmentos siguen siendo legibles, pero medir en mas dimensiones baja un poco la silueta. Se prioriza **interpretabilidad** (set rico) manteniendo el **orden de magnitud** del EDA; el set EDA queda documentado como validacion del pipeline.

### Perfiles legibles (centroides en unidades originales + etiqueta)

| segmento | n_entidades | venta_media | venta_mediana | cv_ventas | tasa_ceros | ventas_total | promo_media | transacciones_media | ratio_finde | pct_demanda_alta | etiqueta_narrativa |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | 41 | 246.835 | 9.548 | 2.965 | 0.348 | 13717131.841 | 2.4 | 1129.425 | 1.311 | 0.122 | Tiendas: bajo volumen, intermitente, baja promo, baja demanda |
| 1 | 13 | 707.665 | 40.462 | 2.457 | 0.203 | 39326350.462 | 3.242 | 2900.555 | 1.513 | 0.545 | Tiendas: alto volumen, venta continua, alta promo, alta demanda |

**Lectura de negocio:** el segmento de **alto volumen** concentra las tiendas grandes (mayor venta, mas transacciones, mas promocion y mayor proporcion de demanda alta) — candidatas a un nivel de servicio/stock mas exigente; el de **bajo volumen e intermitente** agrupa tiendas pequenas. Este `segmento` es el que enriquece la respuesta de ALMACEN (`segmento_tienda`).

## Familias (`family`) — 33 entidades

### Diccionario de features de perfil

| feature | descripcion |
| --- | --- |
| venta_media | Venta media diaria de la familia (unidades). Nivel de demanda. |
| tasa_ceros | Fraccion de observaciones con venta 0. Intermitencia de la familia. |
| cv_ventas | Coef. de variacion (std/media). Dispersion/volatilidad. |
| sensibilidad_promo | Venta media con promo - sin promo (unidades). Respuesta a promocion. |
| ventas_total | Volumen total historico de la familia (suma de unidades). Peso/tamano. |
| promo_media | Intensidad de promocion (`onpromotion` medio). |
| pct_demanda_alta | Fraccion de filas con `demanda_alta=1` (>P75 de su familia). |

### Curva de seleccion de k (set de produccion)

Silueta (principal, mayor mejor) + inercia (codo) + Davies-Bouldin (menor mejor) + Calinski-Harabasz (mayor mejor).

| k | silueta | inercia | davies_bouldin | calinski_harabasz | elegido |
| --- | --- | --- | --- | --- | --- |
| 2 | 0.6495 | 123.99 | 0.5697 | 26.75 | <- elegido |
| 3 | 0.6239 | 57.46 | 0.5678 | 45.31 |  |
| 4 | 0.4158 | 41.46 | 0.6933 | 44.19 |  |
| 5 | 0.4074 | 30.02 | 0.5895 | 46.86 |  |
| 6 | 0.3903 | 22.47 | 0.595 | 50.1 |  |
| 7 | 0.4276 | 15.49 | 0.5753 | 60.27 |  |
| 8 | 0.4297 | 10.49 | 0.4849 | 75.05 |  |

**k elegido = 2** por maxima silueta = **0.6495**.

### Reproduccion del orden de magnitud del EDA

Con el set EXACTO del EDA, la silueta optima es **0.7052** (k=2), frente a la referencia del EDA **0.7052** (k=2): coincide **a 4 decimales**. El pipeline recupera el resultado del EDA; la diferencia con el set de produccion (silueta **0.6495**) es por **features, no por implementacion**.

**Por que el set de produccion da una silueta algo menor:** el set rico anade ejes (dispersion `cv_ventas`, intermitencia `tasa_ceros`, estacionalidad `ratio_finde`) que no se alinean con el corte limpio por volumen del EDA. El k=2 sigue siendo optimo y los segmentos siguen siendo legibles, pero medir en mas dimensiones baja un poco la silueta. Se prioriza **interpretabilidad** (set rico) manteniendo el **orden de magnitud** del EDA; el set EDA queda documentado como validacion del pipeline.

### Perfiles legibles (centroides en unidades originales + etiqueta)

| segmento | n_entidades | venta_media | tasa_ceros | cv_ventas | sensibilidad_promo | ventas_total | promo_media | pct_demanda_alta | etiqueta_narrativa |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | 3 | 2504.039 | 0.148 | 1.116 | 1754.209 | 227707296.0 | 14.441 | 0.25 | Familias: alto volumen, venta continua, alta promo, alta demanda |
| 1 | 30 | 143.149 | 0.329 | 1.997 | 74.259 | 13017434.762 | 1.419 | 0.221 | Familias: bajo volumen, intermitente, baja promo, baja demanda |

**Familias intermitentes (informacion, no ruido):** `BOOKS`, `BABY CARE`, `HARDWARE`, `HOME APPLIANCES` (las degeneradas de la 2b y otras de bajo volumen) caen todas en el segmento de **bajo volumen e intermitente**. A k=2 el corte dominante es por volumen, asi que comparten cluster con el resto de familias pequenas; un k mayor (k=3 silueta 0.62, cercana) las separaria mas fino, pero la silueta elige k=2 (mas parsimonioso y legible).

## Alcance temporal

Segmentacion **descriptiva y estatica**: el perfil se calcula sobre el historico disponible y es **recomputable** desde el historico que envie el cliente (coherente con el contrato). **Mejora diferida:** perfil **as-of-time** si en el futuro el segmento se usa como **feature predictiva en t** (para no mirar el futuro).

## Vinculo con el contrato (ALMACEN)

El `segmento_tienda` de la respuesta de ALMACEN proviene del artefacto de tiendas: `perfilar(historico_integrado)` asigna una tienda nueva a su segmento sin reentrenar. El perfilado de familias apoya politicas de stock por tipo de demanda.

## Mejoras diferidas (documentadas, no implementadas)

- **Perfil as-of-time** (si el segmento pasa a ser feature predictiva).
- **Metodos alternativos de clustering** (jerarquico, DBSCAN) como contraste; KMeans es el principal por el plan.
