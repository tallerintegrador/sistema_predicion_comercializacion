# Propuesta de Replanteamiento — Fase 3.0 (Checkpoint, sin implementación)

> **Estado:** APROBADA con ajustes (Camila + Valentín, 2026-06-18). Seguimos en **Fase 3.0**:
> el documento queda actualizado con las decisiones tomadas y **aún no se implementa nada**. Las
> decisiones aprobadas (D1–D6) se registran al final; la implementación empieza en la **Fase 3.1**
> (prompt aparte).
>
> **Disciplina respetada:** cero ediciones en `src/`, cero dependencias nuevas, ningún
> valor de artefacto hard-codeado (todo desde `meta`), todo probable con fixtures
> sintéticos (sin GPU ni `data/raw`). Convención de la API en **inglés** (requisito del
> profesor): `store_id`, `product_id`, `units_sold`, `horizon`, `granularity`, `/sales`,
> `/purchases`, `/inventory`. (En la prosa de abajo, "horizonte"/"granularidad" se refieren
> a esos campos `horizon`/`granularity`; el contrato canónico está en
> [`contrato_datos.md`](../contrato_datos.md)).

---

## 0. Recomendaciones del docente → cómo las aborda esta propuesta (índice)

| # | Recomendación | Dónde se aborda |
|---|---|---|
| 1 | Entregar el mejor modelo ya entrenado, sin reentrenar en cada consulta | §3 Decisión previa (Opción A/Híbrida); ya es así hoy |
| 2 | Plataforma agnóstica al rubro; los datos los pone el cliente | Ya implementado (contrato genérico + adaptador); §1, §2 |
| 3 | Recibir datos del cliente y predecir sobre ellos | §3 Decisión previa (la pregunta central) |
| 4 | Exigir un contrato / diccionario de datos como entrada | Ya implementado (`contrato_datos.md` + esquemas Pydantic); §1 |
| 5 | Catálogo de tipos de predicción por dominio | §2.3 (nuevo endpoint de catálogo) |
| 6 | Dos modos: en línea (síncrono) y por lote (asíncrono) | §2.2 (nuevo) |
| 7 | No fijar parámetros del modelo dependientes de los datos del cliente | Ya implementado (todo desde `meta`); §1, §4 |
| 8 | Usar datos sintéticos para las pruebas | Ya implementado (`tests/sintetico.py`); §5 |
| 9 | Tratar el aumento de datos como experimento riguroso | §3 (ligado a la decisión B) + ADR de transferibilidad |
| 10 | Varios canales: Excel (plantilla), API/JSON, móvil a futuro | §2.1 (Excel nuevo, mismo contrato) |
| 11 | Priorizar la plataforma genérica por encima del entrenamiento | §3 (recomendación: plataforma primero) |

---

## 1. Resumen del estado actual (qué existe hoy)

La Fase 3 ya está construida y desplegada. La separación estricta de capas **ya se respeta**
y es la base sobre la que se apoya todo lo nuevo:

```
HTTP / API  ──►  Servicio (negocio)  ──►  Motor de ML (artefactos)
conoce HTTP        conoce el contrato        carga y predice;
y el contrato      y las reglas de negocio   NO conoce HTTP ni el negocio del cliente
```

### 1.1 Capa de Motor de ML — `src/spc/models/` (Fase 2, congelado)

Tres familias de artefactos versionados en `models/`, que **solo se cargan y predicen** (no
se reentrenan al servir). **Ningún parámetro de negocio está en el código**: todos viven
dentro del objeto serializado o en su `*.meta.json`.

| Artefacto | Clase / interfaz estable | Valor de negocio (desde el artefacto/meta, NO hard-codeado) |
|---|---|---|
| `regresion_v3.joblib` | `PredictorRegresion.pronosticar_horizonte()` / `.predecir()` | Ensemble convexo (XGB+XGB_Tweedie+LGBM+LGBM_Poisson) y sus **pesos**, espacio "unidades", **techo** `124717.0` — todo en el objeto/`meta` |
| `clasificacion_v1.joblib` | `PredictorClasificacion.predecir()` | **Umbral** de operación `≈0.31849` (recalibrado, piso de precisión 0.80) **dentro** del objeto; se lee del `meta` solo para reportarlo |
| `clustering_tiendas_v1.joblib` | `PerfiladorClustering.perfilar()` | **k=2**, centroides y etiquetas; el segmento de "alto volumen" se deduce leyendo `centroides_unidades` del `meta` (máx `venta_media`) |
| `clustering_familias_v1.joblib` | `PerfiladorClustering.perfilar()` | **k=3** (aísla familias intermitentes); **cargado pero hoy no usado por el contrato** |

Todos son **CPU puros, deterministas y portables** (entrenan en GPU, predicen en CPU).

### 1.2 Capa de Servicio (negocio) — `src/spc/service/`

Conoce el contrato y las reglas de negocio; **no conoce HTTP** (recibe/devuelve estructuras
Python + pandas) y **no conoce el algoritmo** (usa interfaces estables del motor).

- **`adaptador.py`** — la única pieza que conoce ambos lados. Traduce el bloque `history`
  del contrato (genérico) al esquema del dataset analítico del motor (`store_nbr`, `family`,
  `sales`, calendario derivado de `date`, feriados/petróleo/metadatos de tienda como
  "desconocidos" → `NaN` con degradación elegante). También arma el **esqueleto futuro** del
  horizonte y recalcula `demanda_alta = sales > P75 de su familia`.
- **`artefactos.py`** — **carga por glob de versión** (`regresion_v*.joblib` → la mayor). La
  API **sobrevive a un cambio de artefacto sin tocar código**.
- **`ventas_service.py`** — orquesta el pronóstico recursivo y **agrega diario → semanal →
  mensual** (la lógica de agregación vive aquí, como pide el encargo).
- **`compras_service.py`** — sin modelo propio; deriva reposición del pronóstico de VENTAS.
  **Política = días de cobertura**; `safety_stock = 30 % × demanda(lead_time)` (constante de
  política, no de artefacto).
- **`almacen_service.py`** — ensambla clasificación + clustering + un proxy de demanda
  reciente. Hoy el código dimensiona el stock con **z·σ·√lead_time** (σ = desviación de la
  demanda reciente del propio cliente). **Decidido (D2):** en Fase 3.1 se unifica a **días de
  cobertura** como método por defecto (igual que COMPRAS); z·σ·√lead_time queda como **opción
  secundaria documentada**. **El código NO se toca todavía** (registrado en ADR-0010).
- **`errores.py`** — `SolicitudInvalida` (error de dominio, independiente de HTTP).

### 1.3 Capa API — `src/spc/api/`

Conoce HTTP y el contrato; **no conoce la lógica de negocio del cliente** (delega en el
servicio). FastAPI con:

- **Routers**: `POST /sales`, `POST /purchases`, `POST /inventory` (uno por campo del
  contrato) + `GET /health`.
- **Esquemas Pydantic** estrictos (`extra="forbid"`), en **inglés**, con el bloque `history`
  y el `ErrorResponse` compartidos en `comunes.py`.
- **Errores uniformes**: 422 (validación), 400 (regla de negocio), 503 (motor no cargado),
  500 controlado. Nunca un volcado de pila.
- **Carga única en el arranque** (lifespan → `app.state.registro`), CORS configurable
  (`SPC_CORS_ORIGINS`), Swagger con ejemplos por dominio.

### 1.4 Pruebas y despliegue

- `tests/api/` entrena **artefactos diminutos** con datos sintéticos (`tests/sintetico.py`),
  los serializa en un `models/` temporal e inyecta el registro en la app → ejercita la **ruta
  real de carga y predicción sin GPU ni `data/raw`**. Existe `tests/test_adaptador.py`.
- Despliegue Docker (`Dockerfile`, `requirements-api.txt` con pines exactos, `render.yaml`).
- Decisión registrada en **ADR-0007** (`docs/decisiones/0007-capa-api-fase3.md`).

### 1.5 Lo que **NO** existe hoy (y motiva esta fase)

1. **Canal Excel** (solo hay JSON).
2. **Modo por lote / asíncrono** (todo es síncrono en línea).
3. **Endpoint de catálogo** de capacidades por dominio.
4. **Umbral de volumen configurable** que decida en línea vs lote.

---

## 2. Arquitectura propuesta (qué capa recibe cada cosa nueva)

**Principio rector:** todo lo nuevo entra por la **capa API** (canales y modos son "puertas" y
"formas de procesar") y reutiliza **sin duplicar** la capa de servicio y el motor ya existentes.
El motor **no cambia**. El servicio cambia poco (un envoltorio asíncrono que reutiliza las
mismas funciones). El grueso de lo nuevo es ingestión y orquestación en la API.

### 2.1 Canal Excel — otra puerta al **mismo** contrato (capa API)

- Excel es **solo una puerta de entrada**, no lógica nueva. Un **parser de ingestión** en la
  API lee la plantilla `.xlsx` y produce **exactamente los mismos objetos Pydantic** que ya
  valida la ruta JSON (`HistoricoItem`, `ParametroReposicion`, `EstadoInventarioItem`).
- A partir de ahí, el flujo es **idéntico**: misma validación contra el mismo contrato, mismos
  servicios, mismas respuestas. Si la plantilla está mal formada, devuelve el **mismo
  `ErrorResponse`** (mapeando fila/columna de Excel → `field`).
- **Plantilla generada DESDE el contrato (D6a):** la `.xlsx` descargable se **genera a partir del
  contrato** (única fuente de verdad), para que plantilla y esquemas Pydantic **no se
  desincronicen** nunca.
- **Ubicación:** `src/spc/api/ingest/` (parser + definición de plantilla). **No toca** el
  servicio ni el motor.
- **Móvil (futuro):** al ser otro cliente HTTP del mismo JSON, **no requiere capa nueva**; se
  documenta como canal futuro sin trabajo adicional de backend.
- **Sin ADR propio (D1):** Excel se documenta en este doc de arquitectura y en el contrato; no
  abre un ADR salvo que aparezca un trade-off real.

```
JSON  ─┐
Excel ─┼─►  (parser ingestión, API)  ─►  MISMOS esquemas Pydantic  ─►  MISMOS servicios  ─►  motor
Móvil ─┘        (solo Excel)              (validación única)            (negocio único)
```

### 2.2 Modos de ejecución — en línea (síncrono) vs por lote (asíncrono)

Separados por un **umbral de volumen CONFIGURABLE** medido en **número de filas del histórico**
(D6b): vive en `Settings`/variable de entorno (p. ej. `SPC_BATCH_THRESHOLD_ROWS`), igual que hoy
`SPC_CORS_ORIGINS`.

- **En línea (síncrono)** — lo que ya existe: envío pequeño → respuesta inmediata en la misma
  petición. Sin cambios para el cliente.
- **Por lote (asíncrono)** — envío grande: la API **acepta el trabajo y responde un `job_id`**;
  el cliente consulta estado y, al terminar, descarga el resultado. El trabajo se ejecuta en
  segundo plano **llamando a las MISMAS funciones de servicio** (no hay un segundo motor ni una
  segunda lógica de negocio).
- **Decisión de modo:** la API compara el tamaño del envío con el umbral y enruta; el cliente
  también puede pedir el modo explícitamente.

**Ubicación:**
- API: un router de trabajos (`POST /jobs` submit, `GET /jobs/{id}` estado/resultado) y un
  registro de trabajos en memoria de proceso (alcance académico).
- Servicio: un **runner** delgado que envuelve a `ventas/compras/almacen_service` (reutiliza,
  no reescribe).
- Motor: **sin cambios**.

> **Alcance aprobado (D5):** lote **in-process** (tareas en segundo plano + registro de trabajos
> en memoria), **sin** cola externa (Celery/Redis). Cubre la recomendación #6 de forma
> demostrable con sintéticos; una cola/persistencia real queda como **mejora futura documentada**.

### 2.3 Catálogo de predicciones por dominio (capa API)

- Un endpoint **`GET /catalog`** que describe **solo capacidades reales**, leyendo del `meta` de
  los artefactos (versión, escala, granularidades, umbral) — **nada inventado**:
  - **sales** (regresión): pronóstico de demanda; granularidad `day`/`week`/`month`; horizonte.
  - **purchases** (derivado, sin modelo): reposición por **días de cobertura**.
  - **inventory** (clasificación + perfilado): clase de demanda + probabilidad, riesgo de
    quiebre, stock recomendado, `store_segment`.
- **Ubicación:** `src/spc/api/` (router + ensamblado desde el `meta` del registro ya cargado).
  Es **descriptivo**: no añade lógica de negocio.
- **Sin ADR propio (D1):** al ser solo lectura del `meta`, el catálogo no presenta un trade-off
  que amerite ADR; se documenta en este doc y en el contrato.

### 2.4 Dónde vive cada cosa (resumen)

| Pieza nueva | Capa | Reutiliza |
|---|---|---|
| Parser/plantilla Excel | API (`api/ingest/`) | Esquemas Pydantic + servicios existentes |
| Router de trabajos + registro | API (`api/routers/jobs.py`) | Runner de servicio |
| Runner asíncrono | Servicio (`service/jobs.py`) | `ventas/compras/almacen_service` tal cual |
| Umbral de volumen (por **nº de filas**), configurable | `config` / entorno | Patrón de `SPC_CORS_ORIGINS` |
| Endpoint de catálogo | API (`api/routers/catalog.py`) | `meta` del registro ya cargado |
| (Diferido) ajuste por cliente | Servicio (nuevo módulo aislado) | Funciones de entrenamiento del motor — **experimento; se activa solo si los resultados lo justifican** |

---

## 3. Decisión previa (la más importante): ¿qué significa "predecir" con los datos del cliente?

El motor actual es **global**: aprendió la dinámica de demanda de **Corporación Favorita** y la
encapsula en el booster. Es fuertemente **autorregresivo** (rezagos `sales_lag_*`, medias
móviles, calendario). Para un cliente de **otro rubro**, las categóricas (`store_nbr`, `family`,
ciudad, tipo de tienda) son desconocidas y caen a `NaN`: el pronóstico **ya se apoya casi por
completo en los rezagos y el calendario del propio cliente**. Es decir, hoy "predice sobre los
datos del cliente" a través de las features autorregresivas, **sin reentrenar**. Si esa
transferencia es suficiente o no es una **pregunta empírica** (recomendación #9).

| Opción | En qué consiste | Pros | Contras |
|---|---|---|---|
| **A — Modelo congelado** | El modelo sigue congelado; Favorita es "cliente de ejemplo". En línea/lote solo cambian **cómo** se procesa, no reentrenan nada. | Cumple #1 (no reentrena por consulta) y #11 (plataforma primero); rápido, determinista, ya está hecho; demostrable con sintéticos | El docente avisa (#3) que un modelo de un rubro **puede no transferir** a otro; el cliente lejano a Favorita depende de sus propios rezagos+calendario |
| **B — Ajuste por cliente en lote** | En modo lote, **ajustar un modelo a los datos que sube cada cliente** y pronosticar sobre ellos. | Honra #3 (predice sobre los datos del cliente con un modelo suyo); mejor para rubros lejanos a Favorita | Más complejo; "reentrena" (aunque por **lote**, no por consulta — matiz con #1); exige validación temporal por cliente, artefactos por cliente, más cómputo; riesgo con históricos cortos |
| **Híbrida** | En línea: modelo demo congelado. En lote: ajuste por cliente. | Reconcilia #1 (en línea no reentrena) con #3 (lote sí ajusta); en línea rápido, lote más fiel | Hay que mantener **dos caminos** de pronóstico y ser muy claro sobre cuál se usó |

### Decisión aprobada (D4): Híbrida como norte, entregando primero la Opción A

Aprobado: **Híbrida como norte, entregando primero la Opción A** (modelo congelado ahora), con el
camino de lote diseñado con una **costura limpia** para enchufar el ajuste por cliente (Opción B)
**más adelante** y solo como **experimento medido** (#9) que **se activa únicamente si los
resultados lo justifican**:

1. **Ahora:** Opción A. Es lo que pide #11 (plataforma genérica por encima del entrenamiento):
   prioricemos canales (Excel), modos (lote) y catálogo, que es donde está el valor de
   plataforma, sobre el reentrenamiento.
2. **Diseñar el lote** para que un módulo de "ajuste por cliente" se pueda **slotear** sin tocar
   la API ni el motor (vive como módulo de servicio aislado).
3. **Validar B antes de adoptarla:** ajuste por cliente solo se "enciende" si **supera al
   baseline congelado** sobre un holdout temporal de los **propios** datos del cliente. Esto se
   documenta en el ADR de transferibilidad y se prueba con sintéticos de dos "rubros" distintos.

**Por qué no B de entrada:** añade complejidad y cómputo, roza el espíritu de #1 si no se acota
a lote, y su beneficio es una **hipótesis** que aún no hemos medido. Honestidad sobre vistosidad.

---

## 4. Tabla de mapeo actualizada (contrato ↔ motor ↔ negocio)

Deja explícito que **ningún parámetro específico del artefacto está hard-codeado** (columna
derecha indica su origen real).

### 4.1 Campos de entrada (bloque `history`, compartido)

| Campo del contrato (EN) | Qué hace el MOTOR de ML | Qué hace la LÓGICA DE NEGOCIO (servicio) |
|---|---|---|
| `date` | Origen del calendario (rezagos, ciclos, feriados) | El adaptador deriva `year…is_payday` y arma el esqueleto futuro |
| `store_id` | Categórica `store_nbr` (a `NaN` si es cliente nuevo) | Identidad de serie; agrupa y rotula la salida |
| `product_id` | Categórica `family` | Identidad de serie; clave de agregación |
| `units_sold` | Objetivo `sales`; alimenta rezagos/medias | Verdad histórica; base de `demanda_alta` (P75 por familia) |
| `on_promotion` | Feature `onpromotion` (+ rezagos de promo) | Se pasa tal cual; promo futura asumida 0 (documentado) |
| `transactions` (opc.) | `transactions_filled` (NaN si ausente, degrada) | Opcional; mejora señal |
| `event_active` (opc.) | `holiday_any` (feriados por alcance → 0) | Opcional |

### 4.2 Recursos por campo (salida)

| Recurso del contrato | MOTOR de ML | LÓGICA DE NEGOCIO | Parámetro y su origen (no hard-codeado) |
|---|---|---|---|
| **`/sales`** `forecast_demand` | `pronosticar_horizonte` (recursivo, unidades) | Agrega diario→`week`/`month`; arma respuesta | Pesos/composición del ensemble y **techo**: dentro del objeto + `meta` |
| **`/purchases`** `reorder_point`, `replenishment_quantity` | Reutiliza el pronóstico de VENTAS | Aritmética de inventario; **días de cobertura** | `safety_stock = 30 %` = **constante de política** (no de artefacto), documentada |
| **`/inventory`** `demand_class`, `high_demand_probability` | `PredictorClasificacion.predecir` (umbral propio) | Toma la última observación por serie | **Umbral ≈0.31849**: dentro del objeto; al `meta` solo para reportar |
| **`/inventory`** `store_segment` | `PerfiladorClustering.perfilar` | Enriquece y afina política de stock | **k=2**, centroides, "alto volumen": leídos del objeto/`meta` |
| **`/inventory`** `recommended_stock`, `safety_stock` | (proxy de demanda reciente del histórico) | Dimensiona stock | **Decidido (D2/ADR-0010):** por defecto **días de cobertura** (como COMPRAS); z·σ·√L como secundario documentado. Código sin tocar aún |
| **`model`** (en respuestas) | — | Reporta versión | `meta["version"]` (p. ej. `regresion_v3`) |

---

## 5. Plan de módulos / carpetas (HECHO vs NUEVO)

> ✅ = ya existe (no se toca o casi) · 🟡 = se modifica levemente · 🆕 = nuevo

```
src/spc/
  models/                         ✅ MOTOR congelado (NO se toca en Fase 3.0)
    regresion.py / clasificacion.py / clustering.py / runner.py

  service/
    adaptador.py                  ✅
    artefactos.py                 ✅
    ventas_service.py             ✅ (la agregación diaria→semanal→mensual ya vive aquí)
    compras_service.py            ✅ (días de cobertura)
    almacen_service.py            🟡 unificar a DÍAS DE COBERTURA por defecto (D2/ADR-0010); z·σ secundario
    errores.py                    ✅
    jobs.py                       🆕 runner asíncrono (envuelve los servicios; no reescribe)
    ajuste_cliente.py             🆕 DIFERIDO (experimento de ajuste por cliente; módulo aislado)

  api/
    main.py                       🟡 registrar routers nuevos (jobs, catalog)
    dependencies.py               ✅
    errors.py                     ✅ (Excel reutiliza el mismo ErrorResponse)
    routers/
      ventas.py / compras.py / almacen.py   ✅
      jobs.py                     🆕 POST /jobs, GET /jobs/{id}
      catalog.py                  🆕 GET /catalog (desde meta)
    schemas/
      comunes.py / ventas.py / compras.py / almacen.py   ✅
      jobs.py                     🆕 esquemas de trabajo/estado
      catalog.py                  🆕 esquema del catálogo
    ingest/                       🆕 canal Excel (otra puerta al MISMO contrato)
      excel.py                    🆕 parser .xlsx → esquemas Pydantic existentes
      plantilla.py                🆕 generación/definición de la plantilla

  config/__init__.py              🟡 umbral por NÚMERO DE FILAS, configurable (SPC_BATCH_THRESHOLD_ROWS) (D6b)

scripts/
  generar_plantilla_excel.py      🆕 genera la plantilla .xlsx DESDE el contrato (D6a)
  sintetico_dos_rubros.py         🆕 DIFERIDO (sintéticos de 2 rubros para el experimento de transferibilidad B)

tests/
  api/ (test_ventas_api.py, conftest.py)   ✅
  test_adaptador.py               ✅
  api/test_excel_ingest.py        🆕 misma entrada por Excel ≡ por JSON
  api/test_jobs.py                🆕 lote asíncrono (submit→estado→resultado) con sintéticos
  api/test_catalog.py             🆕 catálogo refleja el meta real
  test_ajuste_cliente.py          🆕 DIFERIDO (experimento de ajuste por cliente)

docs/
  fase-3/propuesta_replanteamiento_fase3.md   🆕 (este documento)
  contrato_datos.md               🟡 fuente de verdad única: campos EN inglés (= API), prosa en español; +Excel y modos (D3)
  decisiones/0008-*.md, 0009-*.md, 0010-*.md  🆕 ADRs (ver §6)
```

**Lo que NO cambia:** todo `src/spc/models/`, `src/spc/eda/`, `src/spc/features/`, los
artefactos de `models/`, y el contrato semántico ya expuesto. Excel y lote **no introducen
lógica de negocio nueva**: son puertas y orquestación.

---

## 6. ADRs a redactar más adelante (solo lista; NO redactarlos ahora)

> **Numeración confirmada (D1):** 0007 ya existe (`0007-capa-api-fase3.md`). Los ADR de esta fase
> son **0008, 0009 y 0010**. **Excel y catálogo NO llevan ADR propio**: se documentan en este doc
> de arquitectura y en el contrato (no presentan un trade-off que lo amerite).

| ADR | Alcance (una línea) |
|---|---|
| **ADR-0008 — Modos de ejecución (en línea/lote)** | Síncrono vs asíncrono separados por umbral por **nº de filas configurable**; lote **in-process** con `job_id` reutilizando los servicios; cola/persistencia externa como mejora futura |
| **ADR-0009 — Transferibilidad del modelo (Favorita como cliente de ejemplo)** | Postura **Híbrida** (A primero, congelado); ajuste por cliente en lote como **experimento medido** que solo se activa si los resultados lo justifican; honestidad sobre el cold-start |
| **ADR-0010 — Política de inventario y stock** | **Días de cobertura por defecto** en ALMACÉN (consistente con COMPRAS); **z·σ·√lead_time como opción secundaria** claramente documentada (no por defecto); justificación de la elección |

---

## Resumen en lenguaje sencillo (para validación de una PM no técnica)

- **Hoy la plataforma ya funciona y ya es "agnóstica al rubro":** el cliente manda sus datos con
  nombres genéricos (en inglés) y recibe tres cosas: **pronóstico de ventas**, **sugerencia de
  compras** y **alertas de almacén**. El modelo **ya está entrenado** y solo se usa para
  predecir; **no se reentrena en cada consulta**.
- **Qué vamos a añadir (sin romper nada):**
  1. **Excel como nueva puerta de entrada**, además de la API/JSON. Es la *misma* validación y la
     *misma* lógica por dentro: Excel es solo otra forma de subir los datos. Móvil queda como
     puerta futura sin trabajo extra de servidor.
  2. **Dos modos según el tamaño:** envíos pequeños → respuesta al instante (como hoy); envíos
     muy grandes → la plataforma acepta el trabajo, da un **número de seguimiento** y avisa cuando
     está listo. El límite que decide uno u otro será **configurable**, no fijo en el código.
  3. **Un "catálogo"** que lista, de forma honesta, qué predicciones ofrece cada dominio.
- **La decisión grande, ya tomada:** cuando un cliente nuevo sube *sus* datos, **empezamos con el
  modelo de ejemplo (Favorita) congelado** (rápido y ya hecho); el "ajuste por cliente" en los
  envíos grandes queda como **experimento medido** que solo se activa si demuestra ser mejor
  (enfoque "Híbrido").
- **Compromiso de honestidad:** no inventamos números que los datos no soportan; mantenemos
  COMPRAS por "días de cobertura"; y todo se puede probar con datos sintéticos, sin GPU.

---

## Decisiones aprobadas (Fase 3.0) — registro

Todas las decisiones abiertas quedaron **resueltas** en este checkpoint (Camila + Valentín,
2026-06-18). Se registran aquí para trazabilidad; su implementación corresponde a la **Fase 3.1**.

| # | Tema | Resolución aprobada |
|---|---|---|
| **D1** | Numeración y alcance de ADRs | **ADR-0008** modos · **ADR-0009** transferibilidad · **ADR-0010** política de inventario y stock. **Excel y catálogo sin ADR** propio (se documentan en arquitectura/contrato) |
| **D2** | `safety_stock` de ALMACÉN | **Unificar a días de cobertura** como método por defecto (igual que COMPRAS). z·σ·√lead_time queda como **opción secundaria documentada** (ADR-0010). Se reconoce que σ sale de la demanda real del cliente (no es inventado); se prioriza consistencia. **Código sin tocar** en esta fase |
| **D3** | Contrato como fuente de verdad única | Campos en **inglés** (idénticos a la API), **prosa en español**; añadir secciones de **Excel** y de **modos en línea/lote** |
| **D4** | Significado de "predecir" | **Híbrida** como norte, entregando **primero la Opción A** (modelo congelado). Ajuste por cliente en lote = **experimento medido**, se activa solo si los resultados lo justifican |
| **D5** | Alcance del modo lote | **In-process** (sin Celery/Redis). Cola/persistencia externa = mejora futura documentada |
| **D6** | Plantilla Excel y umbral | (a) Plantilla `.xlsx` **generada DESDE el contrato**. (b) Umbral en línea/lote por **número de filas**, **configurable** |

**No quedan decisiones abiertas.** El siguiente paso es la **Fase 3.1 (implementación)**, en un
prompt aparte.

---

> **FIN DE LA FASE 3.0 (actualización aprobada).** El documento queda alineado con D1–D6 y **no se
> ha implementado nada** (cero ediciones en `src/`). Me detengo aquí y espero el prompt de la
> **Fase 3.1**.
