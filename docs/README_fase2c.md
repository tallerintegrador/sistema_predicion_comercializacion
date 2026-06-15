# Fase 2c — Clustering / Perfilado (cierre de la Fase 2)

> **Estado: ✅ CERRADA** (2026-06-15). Segmentación de **tiendas** y **familias** con
> **KMeans** sobre perfiles agregados. **Cierra la Fase 2** (motor de ML): las tres
> familias de modelos —regresión, clasificación, clustering— quedan entrenadas y
> validadas, con artefactos serializados, portables y versionados con su métrica.
>
> Reporte detallado: [`reporte_clustering_2c.md`](reporte_clustering_2c.md).
> Decisión: [ADR 0006](decisiones/0006-clustering-perfilado-2c.md).
> No toca la capa API/servicio ni avanza a la Fase 3.

---

## 1. Resultado en una línea

| tarea | entidades | k (silueta) | silueta producción | silueta set EDA = ref EDA | segmentos |
|---|---|---|---|---|---|
| **tiendas** | 54 | **2** | 0.4615 | **0.6075 = 0.6075** | 13 grande / 41 pequeña |
| **familias** | 33 | **2** | 0.6495 | **0.7052 = 0.7052** | 3 gigantes / 30 resto |

**k=2 elegido por silueta** en ambas tareas (coincide con el EDA). La **reproducción del
EDA es exacta a 4 decimales** con el set de features del EDA → el pipeline está validado;
el set de producción (más rico e interpretable) baja un poco la silueta por **features, no
por implementación**. Dos artefactos portables, **CPU deterministas**, que asignan una
entidad nueva a su segmento sin reentrenar.

---

## 2. Qué se construyó

- **`src/spc/features/perfiles.py`** — agregación de la serie a **un vector por entidad**
  (funciones puras, reutilizadas en entrenamiento **y** en predicción). Diccionario de
  features documentado.
- **`src/spc/models/clustering.py`** — `PerfiladorClustering` = `Pipeline(StandardScaler +
  KMeans)` envuelto; selección de k por silueta (curva + DB/CH/inercia); centroides en
  unidades + etiqueta narrativa; persistencia (registro, perfiles, reporte, artefactos).
- **`scripts/train_clustering.py`** — entrypoint delgado (serializa vía import →
  artefacto portable).
- **Tests** (`tests/test_clustering.py`, extensión de `tests/test_portabilidad.py`):
  scaler dentro del pipeline, reproducibilidad (semilla→asignación), silueta válida y con
  separación, **portabilidad en proceso limpio**, **asignación de entidad nueva**,
  perfiles no degenerados, intermitentes en su segmento.

## 3. Perfiles (centroides en unidades originales)

**Tiendas (k=2):**

| segmento | n | venta_media | transacciones_media | pct_demanda_alta | etiqueta |
|---|---|---|---|---|---|
| 1 | 13 | 707.7 | 2 901 | 0.55 | alto volumen, continua, alta promo, alta demanda |
| 0 | 41 | 246.8 | 1 129 | 0.12 | bajo volumen, intermitente, baja promo, baja demanda |

**Familias (k=2):**

| segmento | n | venta_media | onpromotion medio | etiqueta |
|---|---|---|---|---|
| 0 | 3 | 2 504 | 14.4 | alto volumen, continua, alta promo (`BEVERAGES`, `GROCERY I`, `PRODUCE`) |
| 1 | 30 | 143 | 1.4 | bajo volumen, intermitente (incluye `BOOKS`/`BABY CARE`) |

Las **familias intermitentes** (`BOOKS`, `BABY CARE` — las degeneradas de la 2b) caen en
el segmento de bajo volumen: información, no ruido.

## 4. Vínculo con el producto

El **`segmento_tienda`** de la respuesta de ALMACÉN (contrato) proviene del artefacto de
tiendas: `perfilar(historico_integrado)` asigna una tienda nueva a su segmento. El
perfilado de familias apoya políticas de stock por tipo de demanda.

## 5. Decisiones de diseño (lecciones 2a/2b aplicadas)

- **Escala obligatoria dentro del artefacto** (StandardScaler en el pipeline; nunca se
  agrupa sin escalar).
- **Selección de k principiada** (no hardcodeada): silueta + inercia/DB/CH, curva
  persistida; k=2 justificado (silueta máxima + parsimonia + interpretabilidad).
- **Artefacto portable desde el inicio** (serializado vía import; test en subproceso
  limpio).
- **CPU determinista, sin GPU**: 54/33 entidades → la GPU no aporta y dañaría la
  reproducibilidad. Semilla 42, `n_init=25`.
- **Alcance estático/descriptivo**; **as-of-time diferido** (si el segmento pasa a feature
  predictiva en t).

## 6. Reproducir

```bash
python scripts/train_clustering.py
```

Genera `models/clustering_{tiendas,familias}_v1.joblib` (+ `.meta.json`),
`data/processed/metricas_clustering_2c.{csv,json}`, las tablas de perfiles/segmentos y
`docs/reporte_clustering_2c.md`. Mismos datos + mismo código → mismos artefactos.

**Suite de tests:** `python -m pytest` → **57 passed**.
