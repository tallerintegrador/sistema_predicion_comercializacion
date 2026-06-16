# Plan Maestro — SPC: Sistema Predictivo de Comercialización

> Documento vivo. Versión 0.7 (Fase 0, 1, **Fase 2 (motor de ML)** y **Fase 3 (API) COMPLETAS** — Fase 3: capa de servicio + FastAPI que sirve los tres contratos sobre los artefactos de Fase 2 sin reentrenar, decisión en ADR `0007`. Fase 2: 2a + 2b + 2c cerradas; 2a re-auditada y cerrada definitivamente —selección en VALID, artefacto portable, métrica honesta recursiva—; **2b — clasificación de ALMACÉN cerrada**: etiqueta `demanda_alta` honesta con P75 train-only, **SMOTE evaluado y descartado** (no aporta sobre desbalance moderado), modelo LightGBM sin remuestreo con umbral de negocio con piso real de precisión, artefacto portable versionado; **2c — clustering/perfilado cerrada**: KMeans sobre perfiles agregados de tiendas y familias, **k=2 elegido por silueta** (coincide con el EDA), **reproducción exacta de la silueta del EDA** con el set EDA (0.6075 tiendas / 0.7052 familias), perfiles interpretables con centroides en unidades + etiqueta, dos artefactos portables CPU-deterministas que asignan una entidad nueva a su segmento —de aquí sale el `segmento_tienda` del contrato de ALMACÉN—). **Las tres familias de modelos (regresión, clasificación, clustering) quedan entrenadas y validadas, con artefactos serializados, portables y versionados con su métrica.** Se actualiza al cierre de cada fase, dejando rastro en el registro de decisiones (ADR).

---

## 1. Nombre y descripción del producto (una página)

**SPC — Sistema Predictivo de Comercialización.**

SPC es un **motor de previsión para comercialización ofrecido como servicio (API)**. Está pensado para PYMEs que ya tienen su propio sistema y su base de datos operativa, pero que **no tienen capacidad de predicción**. El cliente conserva su sistema; nos delega solo la inteligencia predictiva: envía sus datos por API y recibe analítica y pronósticos.

SPC es **agnóstico al sector** (bodega, farmacia, restaurante, etc.). No conoce el negocio del cliente; conoce un **contrato de datos** abstracto —punto de venta, producto/categoría, unidades, promoción, calendario— al que el cliente mapea su información. Esto permite que el mismo motor sirva a cualquier rubro y que la validación sea puramente técnica: el origen de los datos (reales o sintéticos) no altera el funcionamiento.

El servicio responde en **tres campos**, sustentados cada uno en una familia de modelos distinta:

| Campo | Pregunta de negocio | Familia de modelo | Salida principal |
|---|---|---|---|
| **VENTAS** | ¿Cuánto se va a vender? | **Regresión** | Pronóstico de demanda por periodo, producto, categoría y tipo. |
| **COMPRAS** | ¿Cuánto debo reponer? | **Derivado** del pronóstico de ventas + parámetros logísticos | Cantidad a reponer por producto/periodo y punto de reorden. |
| **ALMACÉN** | ¿Hay riesgo de quiebre? ¿Cuánto stock tener? | **Clasificación** (demanda alta/baja) + **clustering** para perfilar | Alerta de riesgo de quiebre, clase de demanda y stock recomendado. |

El **clustering** atraviesa el sistema como capa de *perfilado*: segmenta puntos de venta y familias de producto para ajustar políticas (p. ej. niveles de servicio distintos por segmento) y para enriquecer las features de los otros dos modelos.

**Alcance deliberadamente reducido:** solo ventas, compras y almacén. Sin agentes ni multiagente. Enfoque holístico (producto general, no atado a una empresa). Validación técnica con métricas, no con usuarios finales.

**Datos de validación:** *Store Sales — Corporación Favorita* (retail de Ecuador, diario 2013–2017). El EDA ya confirmó que la data es **rica y suficiente**: 3 000 888 filas, 54 tiendas, 33 familias, 27 predictoras integradas, y aptitud verificada para los tres tipos de modelo. Se usarán **datos reales primero** y **sintéticos después** (SMOTE) para experimentar el desbalance de clasificación.

---

## 2. Arquitectura tecnológica

### 2.1 Principios

- **Modular por capas.** Cada capa tiene una responsabilidad única y se puede testear y reemplazar de forma aislada.
- **El motor de ML no conoce HTTP; la API no conoce el negocio del cliente; el negocio no conoce el algoritmo.** Las dependencias apuntan hacia adentro (la API depende del servicio, el servicio depende del motor; nunca al revés).
- **Reproducibilidad de extremo a extremo:** mismos datos + mismo código + mismo entorno → mismos artefactos y métricas.
- **El contrato de datos es la frontera estable.** Lo que cambie por dentro (modelos, features) no debe romper el contrato público.

### 2.2 Capas y componentes

| Capa | Responsabilidad | Componentes principales | Stack |
|---|---|---|---|
| **Cliente / Presentación** | Consumir el servicio y mostrar resultados | Demo web (carga de datos, visualización de pronósticos) + consumidores externos vía API | React + Vite |
| **API (interfaz)** | Exponer el contrato de datos por campo, validar entradas, documentar | Routers `ventas`, `compras`, `almacen`; esquemas Pydantic; Swagger; CORS; manejo de errores | FastAPI |
| **Servicio / Orquestación** | Lógica de negocio agnóstica al algoritmo | Derivación de **compras** (pronóstico + lead time + cobertura); política de **almacén** (riesgo de quiebre, stock de seguridad); orquesta llamadas al motor | Python |
| **Motor de ML** | Predecir | Pipeline de *feature engineering*; modelo de **regresión**; modelo de **clasificación** (+SMOTE); modelo de **clustering**; carga de artefactos serializados | scikit-learn, XGBoost/LightGBM, imbalanced-learn |
| **Datos** | Integrar, validar y generar | Pipeline de integración de los 7 CSV → dataset analítico (30 col); validación de esquema; generación de datos sintéticos | pandas; (PostgreSQL opcional) |
| **Transversal** | Soporte a todas las capas | Configuración, logging, manejo de errores, pruebas (pytest), registro de decisiones | — |

### 2.3 Diagrama de flujo (cliente → API → motor de ML → respuesta)

```
                              SPC — Sistema Predictivo de Comercialización
  ┌──────────────┐
  │   CLIENTE    │  Su sistema + su BD (cualquier sector).
  │   (PYME)     │  Mapea sus datos al CONTRATO DE DATOS.
  └──────┬───────┘
         │  HTTPS / JSON   POST /ventas | /compras | /almacen
         ▼
  ╔══════════════════════════════════════════════════════════════════════╗
  ║                          CAPA API  (FastAPI)                           ║
  ║   • CORS            • Validación de entrada (Pydantic, contrato)       ║
  ║   • Swagger/OpenAPI • Manejo de errores → respuestas claras           ║
  ╚══════════════════════════════╦═══════════════════════════════════════╝
                                  │  datos validados (DTO interno)
                                  ▼
  ╔══════════════════════════════════════════════════════════════════════╗
  ║                  CAPA SERVICIO / ORQUESTACIÓN                          ║
  ║   ventas → llama regresión                                            ║
  ║   compras → usa pronóstico + lead time + cobertura  → reposición       ║
  ║   almacen → clasificación + perfil de clúster      → riesgo/stock      ║
  ╚══════════════════════════════╦═══════════════════════════════════════╝
                                  │  matriz de features
                                  ▼
  ╔══════════════════════════════════════════════════════════════════════╗
  ║                        MOTOR DE ML                                     ║
  ║   ┌───────────────┐  ┌────────────────────┐  ┌───────────────────┐    ║
  ║   │  Feature Eng. │→ │  Regresión (sales) │  │  Clustering        │    ║
  ║   │  (lags, log1p,│  │  log1p + temporal  │  │  (segmenta tiendas │    ║
  ║   │  calendario)  │→ │────────────────────│  │   / familias)      │    ║
  ║   └───────────────┘  │  Clasificación     │  └───────────────────┘    ║
  ║          ▲           │  (demanda_alta,    │          │                 ║
  ║          │           │   +SMOTE en train) │          │                 ║
  ║   ┌──────┴────────┐  └────────────────────┘          │                 ║
  ║   │  Artefactos   │◄─────────── carga modelos ────────┘                 ║
  ║   │  serializados │  (entrenados offline en Fase 2)                     ║
  ║   └───────────────┘                                                    ║
  ╚══════════════════════════════╦═══════════════════════════════════════╝
                                  │  predicciones
                                  ▼
  ┌──────────────────────────────────────────────────────────────────────┐
  │   RESPUESTA JSON  → pronóstico / reposición / alerta + metadatos       │
  └──────────────────────────────┬───────────────────────────────────────┘
                                  ▼
                          ┌──────────────┐
                          │   CLIENTE    │  (o demo React)
                          └──────────────┘

  ── Capa de DATOS (offline, Fase 1) ───────────────────────────────────────
  7 CSV crudos → integración reproducible → dataset analítico (30 col)
              → generación sintética (SMOTE) → entrenamiento (Fase 2)
```

El entrenamiento ocurre **offline** (Fases 1–2) y produce artefactos serializados. En producción, la API solo **carga** esos artefactos y predice; no entrena en caliente.

---

## 3. Contrato de datos por campo

El contrato usa nombres **genéricos y agnósticos al sector**. El cliente mapea su vocabulario (SKU, local, sucursal…) a estos campos. Granularidad por defecto: diaria; configurable a semanal/mensual.

### Convención común de campos

| Campo genérico | Tipo | Significado | Equivalente en la data de prueba |
|---|---|---|---|
| `fecha` | date (ISO `YYYY-MM-DD`) | Fecha de la observación | `date` |
| `punto_venta_id` | str/int | Local, tienda o sucursal | `store_nbr` |
| `producto_id` o `categoria` | str | Producto o familia | `family` |
| `unidades_vendidas` | float ≥ 0 | Demanda observada | `sales` |
| `en_promocion` | int ≥ 0 | Ítems en promoción (0 si no aplica) | `onpromotion` |
| `transacciones` | float ≥ 0 *(opcional)* | Flujo de clientes/tickets | `transactions` |
| `evento_activo` | bool *(opcional)* | Feriado/evento relevante | `holiday_any` |

---

### 3.1 VENTAS — pronóstico de demanda (regresión)

**Datos mínimos que envía el cliente:** un histórico de la serie por `(fecha, punto_venta_id, producto_id)` con `unidades_vendidas`. Recomendado (mejora la señal, según el EDA): `en_promocion` (corr 0.43) y `transacciones` (corr 0.23). Más parámetros de la petición: `horizonte` y `granularidad`.

**Qué devuelve:** por cada `(punto_venta_id, producto_id, periodo futuro)`, la demanda pronosticada en unidades, con intervalo opcional.

**Ejemplo de entrada**
```json
{
  "granularidad": "dia",
  "horizonte": 7,
  "historico": [
    {"fecha": "2017-08-01", "punto_venta_id": "1", "producto_id": "BEVERAGES",
     "unidades_vendidas": 1820, "en_promocion": 5, "transacciones": 1543},
    {"fecha": "2017-08-02", "punto_venta_id": "1", "producto_id": "BEVERAGES",
     "unidades_vendidas": 1675, "en_promocion": 0, "transacciones": 1490}
  ]
}
```

**Ejemplo de salida**
```json
{
  "campo": "ventas",
  "modelo": "regresion_v1",
  "pronostico": [
    {"fecha": "2017-08-16", "punto_venta_id": "1", "producto_id": "BEVERAGES",
     "demanda_pronosticada": 1742.5, "intervalo_80": [1450.0, 2080.0]},
    {"fecha": "2017-08-17", "punto_venta_id": "1", "producto_id": "BEVERAGES",
     "demanda_pronosticada": 1690.2, "intervalo_80": [1402.0, 2015.0]}
  ],
  "metadatos": {"escala": "unidades", "transformacion_interna": "log1p"}
}
```

---

### 3.2 COMPRAS — reposición (derivado del pronóstico)

**Datos mínimos que envía el cliente:** lo necesario para convertir demanda en una orden de reposición — `stock_actual` por producto, `lead_time_dias` (tiempo de entrega del proveedor) y una `politica` (días de cobertura objetivo o nivel de servicio). El pronóstico de demanda se calcula internamente a partir del mismo histórico de VENTAS.

**Qué devuelve:** por producto/periodo, la cantidad sugerida a reponer y el punto de reorden.

**Ejemplo de entrada**
```json
{
  "historico": [ "... igual que en VENTAS ..." ],
  "parametros_reposicion": [
    {"punto_venta_id": "1", "producto_id": "BEVERAGES",
     "stock_actual": 900, "lead_time_dias": 3, "dias_cobertura_objetivo": 7}
  ]
}
```

**Ejemplo de salida**
```json
{
  "campo": "compras",
  "recomendacion": [
    {"punto_venta_id": "1", "producto_id": "BEVERAGES",
     "demanda_esperada_horizonte": 12200,
     "punto_de_reorden": 5400,
     "cantidad_a_reponer": 11300,
     "justificacion": "demanda_pronosticada + stock_seguridad - stock_actual"}
  ],
  "metadatos": {"supuesto": "demanda y lead time aproximados; revisar política del cliente"}
}
```

---

### 3.3 ALMACÉN — riesgo de quiebre y stock recomendado (clasificación)

**Datos mínimos que envía el cliente:** histórico de demanda por producto (para clasificar `demanda_alta`) y `stock_actual`. Opcionalmente `lead_time_dias` para afinar el riesgo.

**Qué devuelve:** clase de demanda (alta/baja) con probabilidad, bandera de riesgo de quiebre y stock recomendado (incluye stock de seguridad).

**Ejemplo de entrada**
```json
{
  "historico": [ "... igual que en VENTAS ..." ],
  "estado_inventario": [
    {"punto_venta_id": "1", "producto_id": "BEVERAGES",
     "stock_actual": 300, "lead_time_dias": 3}
  ]
}
```

**Ejemplo de salida**
```json
{
  "campo": "almacen",
  "alertas": [
    {"punto_venta_id": "1", "producto_id": "BEVERAGES",
     "clase_demanda": "alta", "probabilidad_demanda_alta": 0.87,
     "riesgo_quiebre": true,
     "stock_recomendado": 1600,
     "stock_seguridad": 420,
     "segmento_tienda": 1}
  ],
  "metadatos": {"umbral": "demanda_alta = ventas > P75 de su familia"}
}
```

> Nota de diseño: VENTAS, COMPRAS y ALMACÉN comparten el mismo bloque `historico`, de modo que el cliente puede pedir los tres en una sola integración. COMPRAS y ALMACÉN reutilizan el pronóstico y el clasificador internamente.

---

## 4. Plan por fases

Cada fase se cierra con una **validación tuya** antes de pasar a la siguiente. Las métricas y criterios buscan validación técnica (lo que exige el profesor), no de usuario.

### Fase 0 — Setup
- **Objetivo:** dejar el proyecto reproducible y gobernado desde el primer commit.
- **Entregables:** repositorio con Git Flow (ramas `main`/`develop`); estructura de carpetas (sección 5); entorno reproducible (`requirements.txt`/`pyproject.toml` + instrucciones); `README`; este plan vivo en `docs/`; registro de decisiones (ADR) iniciado; configuración de pruebas (pytest) y linting.
- **Criterio de validación:** un tercero clona el repo, crea el entorno con un comando y ejecuta `pytest` (aunque sea un test trivial) sin errores.
- **Dependencias:** ninguna.

### Fase 1 — Datos
- **Objetivo:** pipeline de integración **reproducible** de los 7 CSV al dataset analítico, más generación de datos sintéticos para experimentar.
- **Entregables:** módulo de integración (train+stores+transactions+oil+holidays → dataset de **30 columnas, 27 predictoras**, aplicando las decisiones ya documentadas en el EDA: banderas de faltantes en transacciones, relleno de petróleo con bandera, feriados por alcance); validación de esquema de entrada; módulo de generación sintética (SMOTE para clasificación; opcionalmente sintéticos para experimentación); tests de calidad de datos.
- **Criterio de validación:** el pipeline **reproduce las cifras del EDA** (3 000 888 filas; 30 columnas; 31.30 % de ceros en `sales`; 22.37 % de positivos en `demanda_alta`). Los tests de esquema pasan.
- **Dependencias:** Fase 0.

### Fase 2 — Motor de ML
- **Objetivo:** entrenar y validar las tres familias de modelos, con métricas registradas.
- **Sub-fases y entregables:**
  - **2a — Regresión (VENTAS):** objetivo `sales` transformado con **log1p** (el EDA muestra que reduce la asimetría de 7.36 → 0.41); **validación temporal sin fuga de futuro** (corte por fecha / `TimeSeriesSplit`); features de calendario, promoción, transacciones y rezagos. Comparar contra un **baseline** (media móvil / *naïve* estacional).
    - **[HECHO — 2026-06-14, cerrada con revisión de auditoría]** Se compararon 2 baselines + 7 regresores (Ridge, RandomForest, HistGradientBoosting, LightGBM/XGBoost y sus variantes Tweedie/Poisson) bajo **validación temporal sin fuga** + CV expanding, con los **boosters entrenados en GPU** (XGBoost `cuda`, LightGBM `gpu`; el artefacto predice en **CPU**, portable). La **selección ensemble-vs-individual se decide sobre VALID** (pronóstico recursivo honesto), **no sobre TEST**; TEST se evalúa **una sola vez** sobre el modelo ya elegido. **Modelo de producción: `Ensemble(XGBoost+XGBoost_Tweedie+LightGBM+LightGBM_Poisson)`** (`regresion_v3`), que gana al individual `LightGBM_Tweedie` en VALID (WAPE recursivo **12.18 % vs 14.25 %**). **Métrica guía = pronóstico recursivo multi-paso honesto sobre TEST: WAPE 14.59 % · MAE 68.15 · RMSE 235.73**, frente al mejor baseline honesto recursivo (WAPE 20.67 % · MAE 96.54 · RMSE 348.38): **MAE −29.4 %, RMSE −32.3 %, WAPE −6.08 pts**. El número *teacher-forced* (WAPE 12.40 %) queda como **referencia optimista**, no como headline. Artefacto **portable** (serializado vía import, no `__main__`; test de carga en proceso limpio) con metadatos enriquecidos; la **métrica honesta se persiste como fila `split="test_recursivo"`** en `data/processed/metricas_regresion_2a.{csv,json}`. El **MAPE (~34 %) se marca como inflado** por el 31 % de ceros y no se usa como principal; Ridge se **retira** (no apto). Detalle en `docs/reporte_regresion_2a.md`; decisiones en ADR `0002`/`0003` (selección y cierre iniciales) y **`0004` (cierre con revisión de auditoría)**. **Diferido (documentado):** intervalos de predicción; enfoque zero-inflated/two-part; familias intermitentes de bajo volumen (WAPE alto pero MAE trivial, fracciones de unidad).
  - **2b — Clasificación (ALMACÉN):** objetivo `demanda_alta` (> P75 por familia); **SMOTE aplicado solo en train** (nunca en validación/test); comparar métricas **con y sin** SMOTE.
    - **[HECHO — 2026-06-14]** Clasificador de **demanda alta** con el **harness temporal y el feature engineering leak-safe de la 2a reutilizados** (`spc.features.temporales`; ni `sales` actual, ni `family_sales_p75`, ni `demanda_alta` son features). Etiqueta **honesta**: P75 por familia fijado **solo en TRAIN**. Se excluyen **2 familias degeneradas** (`BABY CARE`, `BOOKS`, P75=0 → etiqueta "vendió algo"). **Experimento central — efecto de SMOTE:** tres estrategias sobre la misma validación temporal con el mismo booster (LightGBM) — **sin remuestreo**, **costo-sensible** (`scale_pos_weight`) y **SMOTE (SMOTENC) solo en el train de cada fold** vía `imblearn.Pipeline`. **Resultado: SMOTE no aporta** (PR-AUC VALID 0.9327 vs 0.9330 sin remuestreo; desbalance moderado ~1:3.5) ni la costo-sensible mejora de forma material → se elige la **más simple, sin remuestreo** (`clasificacion_v1`). **Selección y umbral en VALID; TEST evaluado una sola vez.** **Umbral de negocio** (recall-prioritario, riesgo de quiebre cuesta más): max recall con precisión ≥ 0.50 → umbral 0.0175. **Métricas TEST (minoritaria):** **PR-AUC 0.934** (sin-skill = prevalencia TEST 0.347 → ×2.70), **recall 0.996**, F1 0.651, precisión 0.484, ROC-AUC 0.958; baseline trivial PR-AUC ≈ 0.346; referencia logística (bien montada) PR-AUC 0.870. Hallazgo honesto: la prevalencia sube de 0.224 (train) a ~0.347 (valid/test) por el umbral train-only + crecimiento de ventas. Artefacto **portable** (serializado vía import, test de carga en proceso limpio), **GPU-train/CPU-predict**, devuelve **clase y probabilidad**; registro `data/processed/metricas_clasificacion_2b.{csv,json}` (una fila por estrategia × split). Detalle en `docs/reporte_clasificacion_2b.md`; decisión en ADR **`0005`**. **Diferido (documentado):** calibración de probabilidades (Platt/isotónica); métodos de demanda intermitente para familias de bajo volumen.
  - **2c — Clustering (perfilado):** KMeans sobre perfiles de tiendas y familias; reproducir el orden de magnitud del EDA (silueta ≈ **0.61** en tiendas con k=2, ≈ **0.71** en familias); perfiles interpretables.
    - **[HECHO — 2026-06-15, refinado con diagnóstico de contribución]** **KMeans** sobre **perfiles agregados** (un vector por entidad) de **tiendas** (54) y **familias** (33), cada tarea con su **propio `StandardScaler + KMeans`** dentro de un `Pipeline` serializado (escala **dentro** del artefacto, lección de la 2a). La agregación (`spc.features.perfiles`) produce un **set rico** (nivel, dispersión, intermitencia, volumen, promoción, transacciones, estacionalidad, demanda); el modelo **desplegado** usa solo el **subconjunto que separa**, elegido por **diagnóstico reproducible** (`diagnosticar_contribucion`: leave-one-out de silueta + correlación con volumen + PCA). El diagnóstico muestra estructura **casi unidimensional (volumen)** — PC1 **69 %** (tiendas) / **62 %** (familias) — y que `cv_ventas`/`tasa_ceros`/`ratio_finde`/`sensibilidad_promo` son **polizones** (suben la silueta al quitarse). **Set desplegado:** tiendas *depurado* `[venta_media, venta_mediana, ventas_total, pct_demanda_alta]`; familias *alineado al EDA* `[ventas_total, venta_media, promo_media, pct_demanda_alta]`. **k por silueta E interpretabilidad:** **tiendas k=2** (silueta **0.6742**, máximo); **familias k=3 DELIBERADO** (silueta **0.6590**) sobre el máximo k=2 (0.71) para **aislar las familias intermitentes** (`BABY CARE`/`BOOKS`/`HARDWARE`/`HOME APPLIANCES`) en su propio segmento — tipo de demanda accionable para stock. **Silueta del modelo desplegado = métrica oficial** (piso ≥ 0.50); la **reproducción exacta del set EDA** (0.6075 / 0.7052 = referencia a 4 decimales) se conserva como **validación de plomería** (set/k independientes). **Transparencia explícita** (reporte/ADR/meta `segmentacion_dominada_por_volumen=true`): la separación es por **volumen**; promo/demanda/intermitencia son **co-variables descriptivas**, no ejes independientes; etiquetas = niveles de volumen + tipo de demanda. **Dos artefactos** `clustering_{tiendas,familias}_v1` portables (serializados vía import, test de carga en proceso limpio), **CPU puro y determinista** (sin GPU; semilla 42, `n_init=25`), capaces de **asignar una entidad nueva** sin reentrenar (de aquí sale el `segmento_tienda` del contrato de ALMACÉN). Registro `data/processed/metricas_clustering_2c.{csv,json}` (desplegado + validación EDA). Detalle en `docs/reporte_clustering_2c.md`; decisión en ADR **`0006` (Aceptado)**. **Diferido (documentado):** perfil **as-of-time** (si el segmento pasa a feature predictiva en t); métodos alternativos (jerárquico, DBSCAN) como contraste.
- **Criterio de validación:** regresión supera al baseline en MAE/RMSE (en escala original de unidades); clasificación reporta F1/recall/PR-AUC **de la clase minoritaria** y muestra el efecto de SMOTE; clustering reporta silueta y perfiles legibles. Todos los artefactos quedan serializados y versionados con su métrica. **[CUMPLIDO — Fase 2 (motor de ML) COMPLETA.]** Resumen de estado para abrir la **Fase 3 (API)**: tres familias de modelos entrenadas, validadas y **serializadas como artefactos portables** (GPU-train/CPU-predict los boosters; CPU puro el clustering), cada una versionada con su métrica oficial — **regresión** `regresion_v3` (WAPE recursivo honesto TEST **14.59 %**, MAE −29 %/RMSE −32 % vs baseline); **clasificación** `clasificacion_v1` (PR-AUC TEST **0.934**, recall 0.996 al umbral de negocio); **clustering** `clustering_{tiendas,familias}_v1` (silueta desplegada **0.6742** tiendas k=2 / **0.6590** familias k=3). Listos para que la capa de servicio/API los **cargue y sirva** por los tres campos (VENTAS, COMPRAS, ALMACÉN) sin reentrenar.
- **Dependencias:** Fase 1.

### Fase 3 — API
- **Objetivo:** exponer el contrato de datos (sección 3) por los tres campos.
- **Entregables:** servicio FastAPI con routers `ventas`/`compras`/`almacen`; esquemas Pydantic que implementan el contrato; **Swagger** funcional; CORS; validación de entradas y **manejo de errores** con respuestas claras; capa de servicio con la lógica de compras y almacén; tests de endpoints (pytest).
- **Criterio de validación:** Swagger documenta los tres contratos; los tests cubren casos válidos e inválidos (entradas mal formadas → error controlado); las respuestas coinciden con los ejemplos de la sección 3.
- **Dependencias:** Fase 2.
- **[HECHO — 2026-06-15]** Capa de servicio + API FastAPI **dentro del paquete** (`src/spc/api/` y `src/spc/service/`), con la **separación de capas sostenida** (`api → service → motor`; el motor no importa nada de la API; el servicio no importa la API). **Esquemas Pydantic** estrictos (`extra="forbid"`, rangos del contrato) que implementan los tres contratos con sus ejemplos. La **frontera estable es el contrato**: `service/adaptador.py` traduce el bloque `historico` genérico al **esquema del dataset analítico** que el motor consume (calendario derivado de `fecha`; `evento_activo`→`holiday_any`; petróleo y metadatos de tienda **desconocidos**→NaN como *cold-start* documentado; `demanda_alta` recalculado con P75 por familia para el perfilado). **Nada de artefacto hard-codeado:** los artefactos se resuelven por **glob de versión** (la API sobrevive a un cambio de artefacto sin tocar código) y el **umbral (≈0.3185), la composición del ensemble y los segmentos** viven **dentro** de los objetos `Predictor*`/`Perfilador*` (el `meta` se lee solo para `metadatos`/Swagger). **VENTAS** = pronóstico recursivo (+ esqueleto futuro; `semana`/`mes` por agregación); **COMPRAS** = reposición derivada (sin modelo; política **días de cobertura**, stock de seguridad = 30 % de la demanda en lead time); **ALMACÉN** = clasificación (umbral del artefacto) + `segmento_tienda` del clustering + proxy de demanda para el stock (nivel de servicio modulado por el segmento). **Manejo de errores** uniforme (`{error:{tipo,mensaje,detalles}}`): 422 validación, 400 negocio, 503 motor no cargado, 500 controlado; **nunca un 500 sin manejar**. **Swagger** con los tres contratos + ejemplos; **CORS** configurable (`SPC_CORS_ORIGINS`). **Tests** de endpoints (pytest + `TestClient`) con **artefactos diminutos entrenados sobre fixtures sintéticos** — válidos e inválidos por endpoint, **sin `data/raw/` ni GPU**. Decisión en ADR **`0007`**. **Diferido (documentado):** intervalos de predicción (`intervalo_80`), política por nivel de servicio en COMPRAS, integración con dato real (Fase 4).

### Fase 4 — Frontend / demo
- **Objetivo:** demostrar el flujo completo de extremo a extremo.
- **Entregables:** app React + Vite que permite cargar datos (o usar un set de ejemplo), llamar al API y visualizar pronóstico, reposición y alertas de almacén.
- **Criterio de validación:** un recorrido end-to-end (cargar datos → ver resultados de los tres campos) funciona contra el API local.
- **Dependencias:** Fase 3.

### Fase 5 — Despliegue y documentación final *(opcional según tiempo)*
- **Objetivo:** empaquetar y cerrar la documentación.
- **Entregables:** Dockerfile(s) y `docker-compose` (API + frontend; PostgreSQL opcional); documentación final (README, guía de reproducción, contrato de datos consolidado, ADR al día).
- **Criterio de validación:** `docker compose up` levanta el sistema; el README permite reproducir el proyecto desde cero.
- **Dependencias:** Fases 3 y 4.

---

## 5. Estructura de carpetas propuesta

```
spc/
├── README.md
├── pyproject.toml              # o requirements.txt + setup
├── .gitignore                  # ignora data/raw, models/, entornos
├── .github/workflows/          # CI: tests + lint
├── docs/
│   ├── plan_maestro.md         # este documento (vivo)
│   ├── contrato_datos.md       # contrato consolidado por campo
│   ├── reporte_eda.md          # EDA ya generado
│   └── decisiones/             # ADR (registro de decisiones)
│       └── 0001-stack-y-arquitectura.md
├── data/
│   ├── raw/                    # 7 CSV originales (gitignored)
│   ├── processed/              # dataset analítico integrado
│   └── synthetic/              # salidas de SMOTE / sintéticos
├── notebooks/
│   └── eda.ipynb               # EDA reproducible
├── src/spc/                    # paquete principal (código comentado en español)
│   ├── config/                 # configuración y constantes
│   ├── data/                   # integración de fuentes + validación de esquema
│   ├── features/               # feature engineering (lags, log1p, calendario)
│   ├── synthetic/              # generación sintética (SMOTE)
│   ├── models/
│   │   ├── regresion.py        # VENTAS
│   │   ├── clasificacion.py    # ALMACÉN (+SMOTE)
│   │   └── clustering.py       # perfilado de tiendas/familias
│   ├── service/                # lógica de negocio
│   │   ├── compras.py          # reposición derivada
│   │   └── almacen.py          # riesgo de quiebre + stock recomendado
│   └── utils/                  # logging, serialización, métricas
├── api/                        # capa FastAPI
│   ├── main.py
│   ├── routers/                # ventas.py, compras.py, almacen.py
│   ├── schemas/                # modelos Pydantic (contrato de datos)
│   └── deps/                   # carga de artefactos, dependencias compartidas
├── frontend/                   # React + Vite (demo)
├── models/                     # artefactos serializados (gitignored)
├── tests/                      # pytest (datos, modelos, API)
└── docker/                     # Dockerfile(s) + docker-compose
```

---

## 6. Riesgos y supuestos

### Supuestos
1. El cliente puede mapear sus datos al **contrato de datos** y aporta un histórico mínimo por serie. Para COMPRAS también aporta `stock_actual`, `lead_time_dias` y su política de cobertura (parámetros de negocio que SPC no puede inventar).
2. La validación es técnica: la data de Corporación Favorita es **representativa suficiente** para validar el motor; datos sintéticos complementan la experimentación.
3. La granularidad por defecto es diaria; semanal/mensual se obtienen por agregación.
4. El entrenamiento es offline y periódico; en producción la API solo predice con artefactos ya entrenados.

### Riesgos y mitigaciones

| Riesgo | Impacto | Mitigación |
|---|---|---|
| **Ceros y asimetría en `sales`** (31.3 % ceros, asimetría 7.36) | Sesga la regresión | log1p (validado en EDA); considerar enfoque *zero-inflated* / modelar la demanda nula explícitamente. |
| **Fuga de futuro** en validación temporal | Métricas infladas, modelo inútil en producción | Cortes por fecha / `TimeSeriesSplit`; rezagos calculados solo con pasado; jamás SMOTE fuera de train. |
| **Desbalance de clases** (22.37 % positivos, 3.47:1) | Clasificador que ignora la clase minoritaria | SMOTE solo en train; reportar métricas de la clase minoritaria (PR-AUC, recall), no accuracy. |
| **Cold-start del cliente** (poco histórico) | Pronóstico pobre para clientes nuevos | Definir histórico mínimo en el contrato; *fallback* a perfil de clúster / baseline; comunicar incertidumbre en la respuesta. |
| **Heterogeneidad de datos de PYMEs** | El mapeo al contrato falla o pierde señal | Validación de esquema estricta en la capa de datos; mensajes de error claros; campos opcionales degradan con elegancia. |
| **Faltantes operativos** (transacciones 8.19 %, petróleo) | Features ruidosas | Banderas de faltantes e imputación documentada (ya resuelto en el pipeline de integración). |
| **Alta cardinalidad** (`family`, `store_nbr`) | Codificación pesada / *overfitting* | Codificación apropiada (target/ordinal con cuidado temporal); modelos de árboles/boosting que la toleran. |
| **Correlación espuria del petróleo** (negativa global por tendencia temporal) | Conclusiones falsas | Tratada como variable macro de contexto, no causal; el EDA ya la marca como espuria. |
| **Sobre-ingeniería del alcance** | No terminar a tiempo | Alcance fijo en ventas/compras/almacén; Fase 5 opcional; entregar por fases validables. |

---

## Anexo — Decisiones abiertas para tu validación

1. **Modelo de regresión inicial:** ¿partimos de un baseline + LightGBM/XGBoost, o exiges también un lineal explícito para contraste? (Sugiero ambos: lineal como referencia, boosting como modelo de producción.)
2. **`producto_id` vs `categoria` en el contrato:** la data de prueba trabaja a nivel de **familia**. ¿Dejamos el contrato a nivel categoría por defecto y producto como granularidad opcional?
3. **Intervalos de predicción:** ¿los incluimos desde la Fase 2 o los dejamos como mejora posterior?
4. **PostgreSQL/Docker:** confirmados como opcionales (Fase 5), ¿correcto?
