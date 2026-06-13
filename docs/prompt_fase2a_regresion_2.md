

Vas a trabajar en mi proyecto **SPC (Sistema Predictivo de Comercialización)**. Antes de escribir una sola línea de código, **lee estos tres documentos del repo** para alinearte con el plan ya validado: `docs/plan_maestro_spc.md`, `docs/reporte_eda.md` y `docs/contrato_datos.md`. No improvises decisiones que ya estén tomadas ahí; si algo del plan contradice lo que te pido aquí, **detente y pregúntame** antes de continuar.

### Contexto del proyecto (resumen — la fuente de verdad son los docs)

SPC es un **motor de previsión para comercialización ofrecido como API**, agnóstico al sector. Tiene tres campos de negocio: **VENTAS** (regresión), **COMPRAS** (derivado del pronóstico) y **ALMACÉN** (clasificación + clustering). Estamos validándolo técnicamente con el dataset *Store Sales — Corporación Favorita*.

Principios de arquitectura que **no se negocian**:

- **Separación estricta por capas.** El **motor de ML no conoce HTTP**, la API no conoce el negocio del cliente, y el negocio no conoce el algoritmo. Las dependencias apuntan hacia adentro.
- En esta subfase trabajas **solo en el motor de ML y en datos/features**, nunca en la capa API ni en la de servicio. **Prohibido importar FastAPI, Pydantic o cualquier cosa de la capa web** en el código de modelado.
- **Entrenamiento offline → artefactos serializados.** El entrenamiento ocurre aquí, en la Fase 2, y produce un artefacto serializado. En producción la API solo **carga y predice**; nunca entrena en caliente.
- **Reproducibilidad de extremo a extremo:** mismos datos + mismo código + mismo entorno → mismos artefactos y métricas. Fija semillas.
- **Documentación viva y en español.** El código va comentado en español. Al cerrar la subfase, actualizas el plan vivo y registras la decisión en un ADR.

### Estado actual y alineación de la estructura (haz esto PRIMERO)

- **Fase 0 (setup)** y **Fase 1 (datos)** ya están hechas, pero **empecé con una estructura de carpetas propia que no coincide del todo con la del plan**. Antes de codear la regresión, **alinea la estructura del repo a la sección 5 ("Estructura de carpetas propuesta") de `docs/plan_maestro_spc.md`**: renombra/mueve/crea lo necesario para que el árbol del repo coincida con el del plan (`src/spc/` con `config/`, `data/`, `features/`, `synthetic/`, `models/`, `service/`, `utils/`; más `data/`, `notebooks/`, `docs/`, `tests/`, etc.).
  - **No rompas el trabajo ya hecho** de Fase 0/1: mueve el código de integración de datos y el dataset al lugar que les corresponde según el plan, ajustando imports y rutas; conserva el historial con `git mv` cuando aplique.
  - Primero **muéstrame un mapeo "estructura actual → estructura del plan"** (qué se mueve, renombra o crea) y **espera mi visto bueno** antes de tocar archivos.
- Tras alinear: existe (o debe quedar) un **dataset analítico integrado** (30 columnas, 27 predictoras) en `data/processed/`, que ya reproduce las cifras del EDA (3 000 888 filas; 31.30 % de ceros en `sales`; 22.37 % de positivos en `demanda_alta`).
- El **EDA ya está hecho** y fundamenta las decisiones de modelado. Cifras clave que debes respetar/reproducir:
  - `log1p` sobre el objetivo reduce la asimetría de **7.36 → 0.41** (por eso modelamos en escala log1p).
  - `sales` tiene **31.3 % de ceros** (zero-inflation) — tenlo presente al evaluar residuos.
  - Correlaciones de señal: `en_promocion` ≈ 0.43, `transacciones` ≈ 0.23 con el objetivo.
- El objetivo de esta subfase es **2a — Regresión (VENTAS)** únicamente. **No avances a 2b (clasificación) ni 2c (clustering).**

### Decisiones ya tomadas para esta subfase 

- ⚠️ **Modelos:** dos modelos para contraste — un **baseline ingenuo** (media móvil / *naïve* estacional) y un modelo de **gradient boosting (LightGBM o XGBoost)** como modelo de producción. Opcionalmente un **lineal** (p. ej. regresión Ridge sobre las features) como referencia intermedia interpretable. El de producción debe **superar al baseline**.
- ⚠️ **Granularidad:** el contrato trabaja a nivel de **categoría/familia** por defecto (la data de prueba está a nivel `family`). Modela a nivel `(fecha, punto_venta_id, producto_id/familia)`.
- ⚠️ **Intervalos de predicción:** *opcionales en 2a*. Implementa primero el punto de pronóstico. Si sobra margen, añade intervalos (p. ej. cuantiles de boosting o residuos empíricos) como mejora; si no, déjalo documentado como pendiente para fase posterior.

### Tarea — Fase 2a: Regresión (VENTAS)

**Objetivo:** entrenar y validar un modelo de regresión que pronostique la demanda (`sales` / `unidades_vendidas`), con métricas registradas, que supere a un baseline, sin fuga de futuro, y que deje un artefacto serializado y versionado.

#### Requisitos técnicos

1. **Objetivo y transformación.** Entrena sobre `log1p(sales)`. **Todas las métricas finales se reportan en la escala original de unidades**: invierte con `expm1` antes de calcular MAE/RMSE. No reportes métricas en escala log como si fueran unidades.

2. **Features.** Construye, en un módulo de *feature engineering* reutilizable:
   - **Calendario:** día de semana, día del mes, mes, semana del año, indicadores de fin de semana, banderas de feriado/evento (`evento_activo`).
   - **Promoción:** `en_promocion` (y, si aporta, rezagos/medias móviles de promoción).
   - **Transacciones:** ⚠️ **cuidado con la fuga** — en pronóstico real no conoces las transacciones futuras del periodo a predecir. Usa **solo rezagos** de `transacciones` (p. ej. t-1, t-7) o medias móviles del pasado; **nunca** la transacción del mismo periodo que estás prediciendo.
   - **Rezagos y ventanas del objetivo:** lags (p. ej. t-1, t-7, t-14) y medias/medianas móviles. **Calcúlalos solo con información pasada**, agrupando por serie `(punto_venta_id, producto_id)`, y desplazando antes de cualquier ventana para no incluir el valor actual.

3. **Validación temporal sin fuga de futuro.** Usa **corte por fecha** y/o **`TimeSeriesSplit`**. Jamás mezcles fechas futuras en train. Los rezagos y estadísticos móviles se computan respetando el orden temporal por serie. Documenta explícitamente las fechas de corte train/validación/test.

4. **Baseline obligatorio.** Implementa al menos un baseline (media móvil y/o *naïve* estacional, p. ej. "lo mismo que hace 7 días"). El modelo de producción **debe superarlo** en MAE y RMSE sobre el conjunto de validación/test, en escala de unidades.

5. **Métricas registradas.** Calcula y **registra de forma persistente** (CSV/JSON de métricas y/o log estructurado) al menos MAE y RMSE en unidades, para baseline y para cada modelo, por cada *fold*/corte. Que quede trazable qué modelo ganó y por cuánto.

6. **Artefacto serializado y versionado.** Serializa el pipeline de producción ya entrenado (incluye el preprocesamiento/feature engineering necesario para predecir) en `models/` (que está *gitignored*). Junto al artefacto, guarda **metadatos**: versión del modelo (p. ej. `regresion_v1`), fecha de entrenamiento, lista de features, transformación usada (`log1p`), métricas alcanzadas, y semilla. El artefacto debe poder **cargarse y predecir** sin reentrenar (así lo consumirá la API en la Fase 3).

#### Dónde va el código (respeta la estructura del repo ya alineada al plan)

- *Feature engineering* en `src/spc/features/`.
- Modelo de regresión en `src/spc/models/regresion.py`.
- Utilidades de métricas/serialización en `src/spc/utils/`.
- **Entrenamiento como script/función offline reproducible** (no notebook obligatorio), invocable con un comando.
- Tests en `tests/` (pytest): al menos que el feature engineering no filtre futuro (un test que verifique que los lags no usan el valor actual), que el artefacto serializa y recarga, y que el modelo supera al baseline en una muestra.

#### Criterio de validación de la subfase (defínelo como "hecho")

- La regresión **supera al baseline** en MAE y RMSE en escala de unidades, sobre validación temporal.
- Las métricas quedan **registradas** y son reproducibles.
- El **artefacto está serializado y versionado** con su métrica y metadatos.
- Los **tests pasan**, incluido el de no-fuga de futuro.

### Restricciones de proceso

- Trabaja en una **rama de feature** salida de `develop` (Git Flow), p. ej. `feature/fase2a-regresion`. No toques `main`. (La alineación de estructura puede ir en su propio commit o rama, p. ej. `chore/alinear-estructura-plan`, antes de empezar el modelado.)
- **No implementes la capa API ni la de servicio.** No avances a 2b ni 2c.
- Cuando termines, **propón** (sin ejecutar todavía) la actualización del plan vivo (`docs/plan_maestro_spc.md`) y un **ADR** que registre el modelo elegido, las features, la estrategia de validación temporal y las métricas obtenidas. Muéstrame el diff antes de commitear.
- Antes de empezar a codear el modelado, **muéstrame un plan corto** de archivos que crearás/modificarás y el enfoque de validación temporal, y espera mi visto bueno.

### Para arrancar (en este orden)

1. Lee los tres documentos del repo (`plan_maestro_spc.md`, `reporte_eda.md`, `contrato_datos.md`).
2. Inspecciona la **estructura actual** del repo y preséntame el **mapeo de alineación** a la sección 5 del plan; espera mi OK y ejecútalo.
3. Inspecciona el dataset en `data/processed/` para confirmar columnas y tipos reales.
4. Preséntame tu **plan de implementación** de la regresión (archivos + enfoque de validación temporal) antes de escribir código de modelado.


