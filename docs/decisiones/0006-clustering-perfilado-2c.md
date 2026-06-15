# ADR 0006 — Clustering / Perfilado (Fase 2c): segmentación de tiendas y familias; cierre de Fase 2

- **Estado:** Aceptado (2026-06-15) — refinado tras diagnóstico de contribución de features
  (set y k del modelo **desplegado** decididos con evidencia). Listo para mergear.
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

### 2. Feature engineering + **set desplegado decidido por diagnóstico** (no "más por defecto")

La agregación produce un **set rico** (universo de features) por entidad; el modelo
**desplegado** usa solo el **subconjunto que separa de verdad**, elegido con un
**diagnóstico de contribución** (no "más features por defecto"). El resto se conserva como
**co-variables descriptivas** (se reportan por segmento, no entran a KMeans).

- **Set rico tiendas (9):** `venta_media`, `venta_mediana`, `cv_ventas`, `tasa_ceros`,
  `ventas_total`, `promo_media`, `transacciones_media`, `ratio_finde`, `pct_demanda_alta`.
- **Set rico familias (7):** `venta_media`, `tasa_ceros`, `cv_ventas`, `sensibilidad_promo`,
  `ventas_total`, `promo_media`, `pct_demanda_alta`.

**Diagnóstico (`diagnosticar_contribucion`, reproducible, en el meta y el reporte):**
*leave-one-out* de silueta a k=2 (`delta>0` ⇒ quitar la feature **mejora** ⇒ polizón),
correlación de cada feature con la etiqueta y con el **volumen** (`ventas_total`), y **PCA**.

- **PC1 explica 69.1 % (tiendas) / 62.0 % (familias)** de la varianza y todas las features de
  volumen son colineales → la estructura es **casi unidimensional (volumen)**.
- `cv_ventas`, `tasa_ceros`, `ratio_finde`, `transacciones_media` (tiendas) y `cv_ventas`,
  `tasa_ceros`, `sensibilidad_promo`† (familias) **suben la silueta al quitarse** (polizones).

**Set DESPLEGADO decidido** (opción *(a) depurado* en tiendas, *(c) alineado al EDA* en
familias; ambas justificadas por el diagnóstico):

| tarea | set desplegado | silueta k=2 | vs set rico | vs set EDA |
|---|---|---|---|---|
| tiendas | `venta_media, venta_mediana, ventas_total, pct_demanda_alta` (4) | **0.6742** | 0.4615 | 0.6075 |
| familias | `ventas_total, venta_media, promo_media, pct_demanda_alta` (4) | 0.7052 | 0.6495 | 0.7052 |

† En familias `pct_demanda_alta` es ligeramente polizón **a k=2**, pero se **mantiene**
porque su **baja correlación con el volumen (0.22)** aporta el eje de *calidad de demanda*
que habilita el aislamiento de las intermitentes **a k=3** (ver §3).

**Escala obligatoria:** KMeans es por distancia → StandardScaler **dentro del Pipeline del
artefacto** (lección 2a). Features **self-contained** por entidad (volumen absoluto) para
asignar una entidad nueva sin reagregar el resto.

### 3. Selección de k: silueta **e** interpretabilidad → tiendas k=2, **familias k=3**

Se evaluó **k=2..10** (tiendas) y **k=2..8** (familias) con `KMeans(n_init=25,
random_state=42)`, reportando silueta + inercia + DB + CH; la curva se persiste.

- **Tiendas → k=2 (silueta 0.6742, máximo).** Confirma el chequeo de sentido: corte limpio
  grande/pequeña; k=3 baja a 0.5801 sin un tercer segmento accionable.
- **Familias → k=3 (silueta 0.6590), DELIBERADO** sobre el máximo (k=2, 0.7052). A k=2 el
  corte es "3 gigantes vs resto" (más detección de outliers que segmentación accionable). A
  **k=3 se aísla un tercer segmento de familias intermitentes** (`BABY CARE`, `BOOKS`,
  `HARDWARE`, `HOME APPLIANCES`) — un **tipo de demanda** distinto que pide otra política de
  stock. Se sacrifica algo de silueta por una segmentación **más útil**; 0.6590 sigue
  **saludable (piso ≥ 0.50)**.

### 4. Métrica oficial = **silueta del modelo desplegado**; el EDA es **validación de plomería**

La **silueta del modelo desplegado** es la métrica oficial: **tiendas 0.6742 (k=2)**,
**familias 0.6590 (k=3)**. Aparte, con el **set EXACTO del EDA** el pipeline reproduce la
silueta del EDA **a 4 decimales** (tiendas 0.6075, familias 0.7052) — una **prueba de
plomería** independiente del modelo desplegado (otro set/k), no la métrica de cabecera.

| tarea | **desplegado (oficial)** | validación EDA (plomería) = ref EDA |
|---|---|---|
| tiendas | **0.6742** (k=2, 4 features) | 0.6075 = 0.6075 |
| familias | **0.6590** (k=3, 4 features) | 0.7052 = 0.7052 |

El refinamiento **subió** la silueta desplegada de tiendas (0.4615 → 0.6742) depurando
ruido; en familias bajó levemente (0.6495 → 0.6590 a k=3) a cambio del tercer segmento
accionable.

### 5. Perfiles interpretables + **transparencia (dominado por volumen)**

Para cada clúster: tamaño, **medias en unidades originales** (desplegadas + descriptivas) y
**etiqueta narrativa**. La etiqueta es un **nivel de volumen** (+ tipo de demanda:
intermitente/continua), **no** una combinación de ejes que sugiera una riqueza
multidimensional que la separación no tiene. Persistidos en
`data/processed/perfiles_clustering_{tiendas,familias}_2c.csv` y en el meta.

- **Tiendas — seg 1 (10):** "alto volumen, venta continua" (venta media 776,
  transacciones 3 144, `pct_demanda_alta` 0.61). **seg 0 (44):** "bajo volumen,
  intermitente" (venta media 263, `pct_demanda_alta` 0.14).
- **Familias — seg 1 (3):** `BEVERAGES`, `GROCERY I`, `PRODUCE` — "alto volumen, venta
  continua" (venta media 2 504). **seg 0 (26):** "volumen medio, venta continua".
  **seg 2 (4):** `BABY CARE`, `BOOKS`, `HARDWARE`, `HOME APPLIANCES` — "bajo volumen,
  intermitente".

**Transparencia explícita (en reporte y meta, `segmentacion_dominada_por_volumen=true`):**
la separación es **por volumen** (PC1 ~60-70 % de varianza, features de volumen colineales).
Promo, transacciones, demanda alta e intermitencia son **co-variables descriptivas** que
correlacionan con el segmento, **no ejes de separación independientes**. El tercer segmento
de familias (k=3) **coincide con** las intermitentes (es el nivel de volumen más bajo), lo
que lo hace accionable sin dejar de ser un ordenamiento por volumen.

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
- **Metadatos:** versión, fecha, **set desplegado + set descriptivo**, diccionario,
  **k elegido + k de máxima silueta + criterio**, **silueta oficial (desplegado) y curva vs
  k** (+ DB/CH/inercia), **diagnóstico de contribución** (LOO/correlaciones/PCA/head-to-head),
  **`segmentacion_dominada_por_volumen` + nota de transparencia**, validación EDA, **centroides
  en unidades + co-variables descriptivas por segmento**, nº por clúster, etiquetas, semilla.
- **Registro persistente** `data/processed/metricas_clustering_2c.{csv,json}`: silueta /
  inercia / DB / CH por k, para tiendas y familias, en el modelo **desplegado** (oficial,
  `feature_set=desplegado`) **y** en la **validación EDA** (`feature_set=eda_validacion`).

### 7. Alcance temporal (estático vs as-of-time)

Segmentación **descriptiva y estática**: el perfil se calcula sobre el histórico
disponible y es **recomputable** desde el histórico que envíe el cliente (coherente con el
contrato). **Mejora diferida:** perfil **as-of-time** si en el futuro el segmento se usa
como **feature predictiva en t** (para no mirar el futuro).

## Métricas (resumen)

| tarea | n | k | **silueta desplegada (oficial)** | validación EDA = ref EDA | segmentos |
|---|---|---|---|---|---|
| tiendas | 54 | 2 | **0.6742** | 0.6075 = 0.6075 | 10 grande / 44 pequeña |
| familias | 33 | 3 | **0.6590** | 0.7052 = 0.7052 | 3 gigantes / 26 medio / 4 intermitentes |

## Criterio de "hecho" verificado

- [x] **Set de features del modelo desplegado decidido y justificado** con diagnóstico de
      contribución (LOO + correlación con volumen + PCA): tiendas depurado, familias alineado
      al EDA; co-variables polizón descartadas del clustering.
- [x] **Silueta del modelo desplegado** reportada como métrica **oficial** (tiendas 0.6742,
      familias 0.6590); **k final justificado por silueta e interpretabilidad** (tiendas k=2,
      familias k=3 deliberado para aislar intermitentes).
- [x] **Transparencia:** segmentación **dominada por volumen** dicha explícitamente (reporte,
      ADR y meta `segmentacion_dominada_por_volumen=true`); etiquetas = niveles de volumen.
- [x] **Validación EDA conservada** como prueba de plomería (reproducción exacta, set y k
      independientes del desplegado).
- [x] **Perfiles legibles** (medias en unidades + co-variables descriptivas + etiqueta),
      persistidos. Artefactos **portables**, versionados con su métrica; registro persistido.
- [x] Tests en verde: scaler dentro del pipeline, reproducibilidad, **silueta desplegada ≥
      piso 0.50**, **set desplegado = el decidido (no el descartado)**, **k deliberado en
      familias**, **diagnóstico presente y dominado por volumen**, portabilidad en proceso
      limpio, asignación de entidad nueva, perfiles no degenerados, intermitentes aisladas,
      **guarda del artefacto real**.

## Mejoras diferidas (documentadas, no implementadas)

- **Perfil as-of-time** si el segmento pasa a ser feature predictiva en t.
- **Métodos alternativos de clustering** (jerárquico, DBSCAN) como contraste; KMeans es el
  principal por el plan.

## Reproducibilidad

`python scripts/train_clustering.py` (o vía import). CPU determinista; semilla 42,
`n_init=25`. Mismos datos + mismo código + mismo entorno → mismos artefactos y métricas
(KMeans determinista, sin jitter de GPU). Features, k, silueta y centroides versionados en
el meta de cada artefacto.
