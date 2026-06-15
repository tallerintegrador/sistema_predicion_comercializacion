# ADR 0006 — Clustering / Perfilado (Fase 2c): segmentación de tiendas y familias; cierre de Fase 2

- **Estado:** Propuesto (2026-06-15) — pendiente de revisión de diffs antes de mergear a `develop`.
- **Fase:** 2c — Clustering (perfilado). **Cierra la Fase 2** (motor de ML).
- **Contexto previo:** `docs/plan_maestro_spc.md`, `docs/reporte_eda.md` (§8.3),
  `docs/contrato_datos.md`, cierres 2a (`README_fase2a.md`, ADR `0004`) y 2b
  (`README_fase2b_umbral.md`, ADR `0005`).
- **Reporte detallado:** `docs/reporte_clustering_2c.md`.
- **No toca** la capa API/servicio ni avanza a la Fase 3.

## Contexto

El clustering atraviesa SPC como capa de **perfilado**: segmenta puntos de venta y
familias para ajustar políticas de stock y enriquecer la respuesta de ALMACÉN. El plan
pide segmentar **tiendas** y **familias** con **KMeans** sobre perfiles agregados,
**reproducir el orden de magnitud de la silueta del EDA** (≈0.61 tiendas k=2, ≈0.71
familias k=2) y producir **perfiles interpretables**, dejando artefactos portables y
versionados con su métrica. Se heredan las lecciones de la 2a/2b: **escala obligatoria
dentro del artefacto**, selección principiada (no hardcodeada), reproducibilidad de
extremo a extremo (semilla 42) y **artefacto portable desde el inicio**.

## Decisiones

### 1. Dos tareas separadas; perfil agregado (un vector por entidad)

A diferencia de la 2a/2b (features **por fila**), aquí la serie de cada entidad se
**agrega a un vector**: un perfil por `store_nbr` (54 tiendas) y uno por `family` (33
familias). Cada tarea tiene su **propio** `StandardScaler + KMeans` (no se mezclan en un
solo modelo). La agregación vive en `src/spc/features/perfiles.py` (funciones **puras**,
reutilizadas en entrenamiento y en predicción).

### 2. Feature engineering de perfiles + escala obligatoria

Diccionario documentado (también en el reporte y el meta del artefacto):

- **Tiendas:** `venta_media`, `venta_mediana`, `cv_ventas` (dispersión), `tasa_ceros`
  (intermitencia), `ventas_total` (volumen), `promo_media` (intensidad de promoción),
  `transacciones_media` (flujo), `ratio_finde` (estacionalidad finde/semana),
  `pct_demanda_alta`.
- **Familias:** `venta_media`, `tasa_ceros`, `cv_ventas`, `sensibilidad_promo` (venta
  media con − sin promo), `ventas_total`, `promo_media`, `pct_demanda_alta`.

**Escala obligatoria:** KMeans es por distancia → se estandariza (StandardScaler) antes
de agrupar; el scaler viaja **dentro del Pipeline del artefacto** (lección de escala de
la 2a). Las columnas de **varianza cero** se descartan (p. ej. `familias_activas`=33,
constante en esta data). Se eligieron features **self-contained** por entidad (volumen
absoluto en vez de relativo al catálogo) para poder asignar una entidad nueva sin
reagregar el resto.

### 3. Selección de k principiada (silueta + apoyo) → k=2 en ambas

Se evaluó **k=2..10** (tiendas) y **k=2..8** (familias) con `KMeans(init="k-means++",
n_init=25, random_state=42)`, reportando **silueta** (principal), **inercia** (codo),
**Davies-Bouldin** y **Calinski-Harabasz**. La **curva silueta vs k** se persiste.

| tarea | k=2 | k=3 | k=4 | elegido |
|---|---|---|---|---|
| tiendas (silueta) | **0.4615** | 0.4339 | 0.3279 | **k=2** |
| familias (silueta) | **0.6495** | 0.6239 | 0.4158 | **k=2** |

La silueta elige **k=2** en ambas tareas, **coincidiendo con el EDA**. k=2 no es trivial:
da segmentos legibles y útiles (grande vs pequeño; continuo vs intermitente). k=3 quedó
cerca en familias (0.6239) y separaría más fino las intermitentes, pero la silueta y la
**parsimonia** favorecen k=2.

### 4. Reproducción del orden de magnitud del EDA — **exacta**

Con el **set EXACTO del EDA**, el pipeline recupera la silueta del EDA **a 4 decimales**:

| tarea | silueta set EDA (k=2) | referencia EDA | silueta set producción (k=2) |
|---|---|---|---|
| tiendas | **0.6075** | 0.6075 | 0.4615 |
| familias | **0.7052** | 0.7052 | 0.6495 |

La coincidencia exacta del set EDA **valida el pipeline**. El set de producción (más
rico) da una silueta algo menor porque añade ejes (`cv_ventas`, `tasa_ceros`,
`ratio_finde`) que no se alinean con el corte limpio por volumen del EDA: medir en más
dimensiones baja un poco la silueta, pero el **orden de magnitud se mantiene** y k=2 sigue
siendo óptimo. Se prioriza **interpretabilidad** manteniendo la métrica de referencia
documentada (diferencia por **features, no por implementación**).

### 5. Perfiles interpretables (entregable central)

Para cada clúster: tamaño, **centroides en unidades originales** (se invierte el escalado)
y **etiqueta narrativa** derivada de esos valores. Persistidos en
`data/processed/perfiles_clustering_{tiendas,familias}_2c.csv` y en el meta.

- **Tiendas — seg 1 (13):** "alto volumen, venta continua, alta promo, alta demanda"
  (venta media 708, transacciones 2 901, `pct_demanda_alta` 0.55). **seg 0 (41):** "bajo
  volumen, intermitente, baja promo, baja demanda" (venta media 247, transacciones 1 129,
  `pct_demanda_alta` 0.12).
- **Familias — seg 0 (3):** `BEVERAGES`, `GROCERY I`, `PRODUCE` — "alto volumen, venta
  continua, alta promo, alta demanda" (venta media 2 504, `onpromotion` medio 14.4).
  **seg 1 (30):** "bajo volumen, intermitente, baja promo, baja demanda".

**Familias intermitentes (información, no ruido):** `BOOKS` y `BABY CARE` (las degeneradas
de la 2b), junto a `HARDWARE`/`HOME APPLIANCES`, caen en el segmento de bajo volumen e
intermitente. A k=2 el corte dominante es por volumen, así que comparten clúster con el
resto de familias pequeñas; un k mayor las aislaría más, pero la silueta elige k=2.

### 6. Artefacto portable, CPU determinista; asignación de entidad nueva

- **Dos artefactos** `models/clustering_{tiendas,familias}_v1.joblib` (+ `.meta.json`),
  cada uno un `Pipeline(StandardScaler + KMeans)` envuelto en `PerfiladorClustering`.
  Serializados **vía import** (`scripts/train_clustering.py`); la clase se picklea bajo
  `spc.models.clustering` (no `__main__`). **Test de portabilidad** en subproceso limpio.
- `perfilar(historico_integrado)` reagrega el historico de una entidad **nueva** (misma
  lógica que en entrenamiento), la escala con el scaler del pipeline y devuelve su
  **`segmento` + etiqueta narrativa**, sin reentrenar.
- **CPU puro y determinista (sin GPU).** El clustering opera sobre 54/33 entidades: la GPU
  de la 2a/2b (boosters sobre 3M filas) **no aporta** aquí y dañaría la reproducibilidad;
  no hay RAPIDS/cuML en el entorno. Decisión consultada y confirmada.
- **Vínculo con el contrato:** el `segmento_tienda` de la respuesta de ALMACÉN proviene
  del artefacto de tiendas. El perfilado de familias apoya políticas de stock por tipo de
  demanda.
- **Metadatos:** versión, fecha, features y su diccionario, **k elegido y criterio**,
  **silueta y curva vs k** (+ DB/CH/inercia), reproducción EDA, **centroides en unidades**,
  nº por clúster, etiquetas, semilla, `n_init`, nota de alcance y de portabilidad.
- **Registro persistente** `data/processed/metricas_clustering_2c.{csv,json}`: silueta /
  inercia / DB / CH por k, para tiendas y familias, en el set de producción **y** en el de
  reproducción del EDA.

### 7. Alcance temporal (estático vs as-of-time)

Segmentación **descriptiva y estática**: el perfil se calcula sobre el histórico
disponible y es **recomputable** desde el histórico que envíe el cliente (coherente con el
contrato). **Mejora diferida:** perfil **as-of-time** si en el futuro el segmento se usa
como **feature predictiva en t** (para no mirar el futuro).

## Métricas (resumen)

| tarea | n | k | silueta (producción) | silueta (set EDA) = ref EDA | segmentos |
|---|---|---|---|---|---|
| tiendas | 54 | 2 | 0.4615 | 0.6075 = 0.6075 | 13 grande / 41 pequeña |
| familias | 33 | 2 | 0.6495 | 0.7052 = 0.7052 | 3 gigantes / 30 resto |

## Criterio de "hecho" verificado

- [x] KMeans sobre perfiles de **tiendas y familias**, k **elegido por silueta** (curva
      reportada) y justificado (k=2, coincide con el EDA).
- [x] **Silueta reportada** y reproduciendo el **orden de magnitud del EDA** (exacta con el
      set EDA; diferencia del set rico explicada).
- [x] **Perfiles legibles** (centroides en unidades + etiqueta narrativa), persistidos.
- [x] Artefactos **portables**, serializados y **versionados con su métrica**; registro
      persistido.
- [x] Tests en verde: scaler dentro del pipeline, reproducibilidad (semilla→asignación),
      silueta válida y con separación, **portabilidad en proceso limpio**, **asignación de
      entidad nueva**, perfiles no degenerados (sin clúster vacío, cada uno con etiqueta),
      intermitentes en su segmento.

## Mejoras diferidas (documentadas, no implementadas)

- **Perfil as-of-time** si el segmento pasa a ser feature predictiva en t.
- **Métodos alternativos de clustering** (jerárquico, DBSCAN) como contraste; KMeans es el
  principal por el plan.

## Reproducibilidad

`python scripts/train_clustering.py` (o vía import). CPU determinista; semilla 42,
`n_init=25`. Mismos datos + mismo código + mismo entorno → mismos artefactos y métricas
(KMeans determinista, sin jitter de GPU). Features, k, silueta y centroides versionados en
el meta de cada artefacto.
