# Reporte de Clustering / Perfilado (Fase 2c)

> Generado por `spc.models.clustering`. Segmenta **tiendas** y **familias** con KMeans sobre perfiles agregados (un vector por entidad). Escala obligatoria (StandardScaler **dentro** del artefacto); features del modelo **desplegado** elegidas por **diagnostico de contribucion**; k por silueta **e** interpretabilidad; centroides en **unidades originales** + etiqueta. CPU puro, determinista (semilla 42). Cierra la **Fase 2** (motor de ML).

**Metrica oficial (modelo desplegado):** **tiendas** silueta **0.6742** (k=2, 4 features); **familias** silueta **0.6590** (k=3, 4 features).

La **silueta del modelo desplegado** es la metrica oficial. La reproduccion exacta del set del EDA se conserva aparte como **validacion de plomeria** (no es el modelo desplegado).

> **Transparencia (leer antes de los perfiles):** en ambas tareas la separacion esta **dominada por el volumen** (el diagnostico lo cuantifica: PC1 concentra la mayor parte de la varianza y las features de volumen son colineales). Las features descriptivas (promo, demanda alta, intermitencia, transacciones) son **co-variables** que correlacionan con el segmento, **no ejes de separacion independientes**. Las etiquetas narrativas son **niveles de volumen** (+ tipo de demanda), para no sugerir una riqueza multidimensional que la separacion no tiene.

## Tiendas (`store_nbr`) — 54 entidades

**Set desplegado (4):** `venta_media`, `venta_mediana`, `ventas_total`, `pct_demanda_alta`  ·  **k=2**  ·  **silueta oficial = 0.6742**.

### Diccionario de features de perfil

| feature | uso | descripcion |
| --- | --- | --- |
| venta_media | clustering | Venta media diaria de la tienda (unidades). Nivel de demanda. |
| venta_mediana | clustering | Venta mediana diaria (robusta a la cola larga). Nivel tipico. |
| cv_ventas | descriptiva | Coef. de variacion (std/media) de la venta. Dispersion/volatilidad. |
| tasa_ceros | descriptiva | Fraccion de observaciones tienda-familia-dia con venta 0. Intermitencia. |
| ventas_total | clustering | Volumen total historico (suma de unidades). Tamano de la tienda. |
| promo_media | descriptiva | Intensidad de promocion (`onpromotion` medio). Apoyo comercial. |
| transacciones_media | descriptiva | Transacciones medias diarias. Flujo de clientes. |
| ratio_finde | descriptiva | Venta media de fin de semana / entre semana. Estacionalidad operativa. |
| pct_demanda_alta | clustering | Fraccion de filas con `demanda_alta=1` (>P75 de su familia). |

### Diagnostico de contribucion de features (que separa de verdad)

Sobre el set rico (9 features) a k=2. `delta_silueta_LOO` = silueta al **quitar** la feature menos la del set rico: **>0 => quitarla mejora => polizon** (no separa). `corr_volumen` alto => co-variable del volumen.

| feature | en_clustering | delta_silueta_LOO | polizon | corr_etiqueta | corr_volumen |
| --- | --- | --- | --- | --- | --- |
| venta_media | si | -0.021 | no | 0.831 | 1.0 |
| venta_mediana | si | -0.0098 | no | 0.776 | 0.957 |
| ventas_total | si | -0.021 | no | 0.831 | 1.0 |
| pct_demanda_alta | si | -0.0255 | no | 0.86 | 0.969 |
| cv_ventas | no | 0.0203 | si | 0.22 | 0.372 |
| tasa_ceros | no | 0.0644 | si | 0.429 | 0.596 |
| promo_media | no | 0.062 | si | 0.623 | 0.748 |
| transacciones_media | no | 0.0005 | si | 0.806 | 0.953 |
| ratio_finde | no | 0.0407 | si | 0.415 | 0.337 |

**PCA del set rico:** PC1 explica **69.1%** de la varianza (PC1+PC2 = 85.2%) → estructura **casi unidimensional (volumen)**. Head-to-head de silueta a k=2: rico **0.4615**, EDA **0.6075**, desplegado **0.6742**. **Decision:** se despliega el set que **maximiza la separacion manteniendo la interpretabilidad**, descartando las features polizon (suben la silueta al quitarse).

### Curva de seleccion de k

Silueta (principal, mayor mejor) + inercia (codo) + Davies-Bouldin (menor mejor) + Calinski-Harabasz (mayor mejor). El k desplegado se marca abajo.

| k | silueta | inercia | davies_bouldin | calinski_harabasz | elegido |
| --- | --- | --- | --- | --- | --- |
| 2 | 0.6742 | 62.37 | 0.5062 | 128.1 | <- elegido |
| 3 | 0.5801 | 28.05 | 0.5493 | 170.85 |  |
| 4 | 0.5078 | 17.91 | 0.5905 | 184.34 |  |
| 5 | 0.4494 | 13.25 | 0.6539 | 187.39 |  |
| 6 | 0.4149 | 10.4 | 0.6702 | 189.8 |  |
| 7 | 0.3742 | 8.41 | 0.7551 | 193.33 |  |
| 8 | 0.3685 | 6.94 | 0.6746 | 197.87 |  |
| 9 | 0.3811 | 5.63 | 0.6518 | 210.04 |  |
| 10 | 0.4034 | 4.77 | 0.6521 | 216.49 |  |

**k desplegado = 2** (silueta **0.6742**). Criterio: maxima silueta sobre el rango (k=2): corte limpio grande/pequena; k=3 baja la silueta (0.58) sin aportar un tercer segmento accionable.

### Validacion de plomeria — reproduccion exacta del set EDA

Con el set EXACTO del EDA, la silueta optima es **0.6075** (k=2), frente a la referencia del EDA **0.6075**: coincide **a 4 decimales** → el pipeline recupera el resultado del EDA (diferencias serian por **features/k elegidos**, no por implementacion). Esto es una **prueba de plomeria**, independiente del modelo desplegado.

### Perfiles legibles (medias por segmento en unidades + etiqueta)

Columnas desplegadas (clustering) primero; luego **co-variables descriptivas** (no entran a KMeans, co-varian con el volumen).

| segmento | n_entidades | venta_media | venta_mediana | ventas_total | pct_demanda_alta | cv_ventas | tasa_ceros | promo_media | transacciones_media | ratio_finde | etiqueta_narrativa |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | 44 | 262.69 | 10.306 | 1.4598207e+07 | 0.137 | 2.938 | 0.34 | 2.45 | 1194.863 | 1.32 | Tiendas: bajo volumen, intermitente |
| 1 | 10 | 776.153 | 46.4 | 4.3132388e+07 | 0.606 | 2.423 | 0.195 | 3.277 | 3143.967 | 1.534 | Tiendas: alto volumen, venta continua |

**Lectura de negocio:** el corte separa tiendas **grandes** (alto volumen, venta continua) de **pequenas** (bajo volumen, intermitentes) — las grandes son candidatas a un nivel de servicio/stock mas exigente. Este `segmento` enriquece la respuesta de ALMACEN (`segmento_tienda`). **Transparencia:** la separacion es por **volumen** (las 4 features desplegadas son medidas colineales del tamano); promo, transacciones y demanda alta (tabla, columnas descriptivas) **co-varian** con el segmento pero no son ejes de separacion independientes.

## Familias (`family`) — 33 entidades

**Set desplegado (4):** `ventas_total`, `venta_media`, `promo_media`, `pct_demanda_alta`  ·  **k=3**  ·  **silueta oficial = 0.6590**.

### Diccionario de features de perfil

| feature | uso | descripcion |
| --- | --- | --- |
| venta_media | clustering | Venta media diaria de la familia (unidades). Nivel de demanda. |
| tasa_ceros | descriptiva | Fraccion de observaciones con venta 0. Intermitencia de la familia. |
| cv_ventas | descriptiva | Coef. de variacion (std/media). Dispersion/volatilidad. |
| sensibilidad_promo | descriptiva | Venta media con promo - sin promo (unidades). Respuesta a promocion. |
| ventas_total | clustering | Volumen total historico de la familia (suma de unidades). Peso/tamano. |
| promo_media | clustering | Intensidad de promocion (`onpromotion` medio). |
| pct_demanda_alta | clustering | Fraccion de filas con `demanda_alta=1` (>P75 de su familia). |

### Diagnostico de contribucion de features (que separa de verdad)

Sobre el set rico (7 features) a k=2. `delta_silueta_LOO` = silueta al **quitar** la feature menos la del set rico: **>0 => quitarla mejora => polizon** (no separa). `corr_volumen` alto => co-variable del volumen.

| feature | en_clustering | delta_silueta_LOO | polizon | corr_etiqueta | corr_volumen |
| --- | --- | --- | --- | --- | --- |
| ventas_total | si | -0.0258 | no | 0.874 | 1.0 |
| venta_media | si | -0.0258 | no | 0.874 | 1.0 |
| promo_media | si | -0.0099 | no | 0.825 | 0.945 |
| pct_demanda_alta | si | 0.0353 | si | 0.152 | 0.22 |
| tasa_ceros | no | 0.0574 | si | 0.199 | 0.353 |
| cv_ventas | no | 0.0334 | si | 0.149 | 0.253 |
| sensibilidad_promo | no | -0.0654 | no | 0.974 | 0.912 |

**PCA del set rico:** PC1 explica **62.0%** de la varianza (PC1+PC2 = 91.3%) → estructura **casi unidimensional (volumen)**. Head-to-head de silueta a k=2: rico **0.6495**, EDA **0.7052**, desplegado **0.7052**. **Decision:** se despliega el set que **maximiza la separacion manteniendo la interpretabilidad**, descartando las features polizon (suben la silueta al quitarse). **Nota:** `pct_demanda_alta` aparece como polizon a k=2 pero se **mantiene**: su baja correlacion con el volumen aporta el eje de **calidad de demanda** que habilita el aislamiento de las intermitentes a k=3 (ver seleccion de k); a k=2 seria ruido, a k=3 es la clave del tercer segmento.

### Curva de seleccion de k

Silueta (principal, mayor mejor) + inercia (codo) + Davies-Bouldin (menor mejor) + Calinski-Harabasz (mayor mejor). El k desplegado se marca abajo.

| k | silueta | inercia | davies_bouldin | calinski_harabasz | elegido |
| --- | --- | --- | --- | --- | --- |
| 2 | 0.7052 | 58.36 | 0.5607 | 39.11 |  |
| 3 | 0.659 | 29.69 | 0.488 | 51.7 | <- elegido |
| 4 | 0.6602 | 14.57 | 0.4218 | 77.93 |  |
| 5 | 0.5622 | 9.91 | 0.5107 | 86.22 |  |
| 6 | 0.5164 | 6.49 | 0.4092 | 104.36 |  |
| 7 | 0.5293 | 4.0 | 0.397 | 138.77 |  |
| 8 | 0.5256 | 2.83 | 0.3458 | 162.93 |  |

**k desplegado = 3** (silueta **0.6590**). Criterio: k=3 DELIBERADO sobre el maximo de silueta (k=2, 0.71): k=3 aisla las familias intermitentes (BABY CARE/BOOKS/HARDWARE/HOME APPLIANCES) en su propio segmento (tipo de demanda accionable para stock); silueta 0.66, aun saludable (>0.50).

### Validacion de plomeria — reproduccion exacta del set EDA

Con el set EXACTO del EDA, la silueta optima es **0.7052** (k=2), frente a la referencia del EDA **0.7052**: coincide **a 4 decimales** → el pipeline recupera el resultado del EDA (diferencias serian por **features/k elegidos**, no por implementacion). Esto es una **prueba de plomeria**, independiente del modelo desplegado.

### Perfiles legibles (medias por segmento en unidades + etiqueta)

Columnas desplegadas (clustering) primero; luego **co-variables descriptivas** (no entran a KMeans, co-varian con el volumen).

| segmento | n_entidades | ventas_total | venta_media | promo_media | pct_demanda_alta | tasa_ceros | cv_ventas | sensibilidad_promo | etiqueta_narrativa |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | 26 | 1.5013903e+07 | 165.104 | 1.637 | 0.242 | 0.26 | 1.632 | 85.54 | Familias: volumen medio, venta continua |
| 1 | 3 | 2.2770731e+08 | 2504.039 | 14.441 | 0.25 | 0.148 | 1.116 | 1754.209 | Familias: alto volumen, venta continua |
| 2 | 4 | 40390.0 | 0.444 | 0.001 | 0.086 | 0.781 | 4.365 | 0.931 | Familias: bajo volumen, intermitente |

**Por que k=3 (y no k=2, el de maxima silueta):** a k=2 el corte es 'gigantes vs resto' (mas deteccion de outliers que segmentacion accionable). **k=3 aisla un tercer segmento de familias intermitentes** (`BOOKS`, `BABY CARE`, `HARDWARE`, `HOME APPLIANCES`: las degeneradas de la 2b + otras de demanda casi nula) en su propio grupo — un **tipo de demanda** distinto que pide otra politica de stock. Se sacrifica algo de silueta por una segmentacion mas util. **Transparencia:** sigue siendo un ordenamiento por **volumen** (tres niveles); las co-variables (intermitencia, promo) describen los niveles, no abren ejes independientes.

## Alcance temporal

Segmentacion **descriptiva y estatica**: el perfil se calcula sobre el historico disponible y es **recomputable** desde el historico que envie el cliente (coherente con el contrato). **Mejora diferida:** perfil **as-of-time** si en el futuro el segmento se usa como **feature predictiva en t** (para no mirar el futuro).

## Vinculo con el contrato (ALMACEN)

El `segmento_tienda` de la respuesta de ALMACEN proviene del artefacto de tiendas: `perfilar(historico_integrado)` asigna una tienda nueva a su segmento sin reentrenar. El perfilado de familias apoya politicas de stock por tipo de demanda.

## Mejoras diferidas (documentadas, no implementadas)

- **Perfil as-of-time** (si el segmento pasa a ser feature predictiva).
- **Metodos alternativos de clustering** (jerarquico, DBSCAN) como contraste; KMeans es el principal por el plan.
