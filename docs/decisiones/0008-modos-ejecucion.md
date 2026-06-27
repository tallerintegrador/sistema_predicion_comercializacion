# ADR 0008 — Modos de ejecución (en línea / por lote)

- **Estado:** Aceptado (2026-06-19).
- **Fase:** 3.4 — Modos de ejecución. **Abre** el modo por lote sobre la API de Fase 3.
- **Contexto previo:** `docs/contrato_datos.md` (§7, un solo contrato para canales y
  modos), ADR-0007 (capa API), Fase 3.3 (canal Excel). Recomendaciones del docente 6
  (ruteo por nº de filas) y 1 (un solo contrato).
- **No toca** el motor de ML ni la lógica de negocio: el ruteo y lo asíncrono viven en
  la capa API/servicio. El lote llama al **mismo flujo de predicción** que el modo en
  línea (cero lógica duplicada), usando el **modelo congelado**.

## Contexto

La API sirve hoy el contrato por tres campos en modo **en línea** (una petición
síncrona; JSON y Excel). Para envíos grandes (muchas series), una respuesta síncrona
puede tardar demasiado y atar la conexión. La Fase 3.4 añade un modo **por lote**
(asíncrono) sin cambiar el contrato ni el motor: cambia *cómo* se procesa (en segundo
plano), no *qué* se calcula. El principio rector es la **equivalencia**: el mismo dato
por línea y por lote debe dar el **mismo resultado**.

## Decisiones

### 1. Ruteo por número de filas en el MISMO endpoint (opción A)

El mismo `POST /sales` · `/purchases` · `/inventory` (y `POST /{dominio}/excel`)
decide por **número de filas** de la petición ya validada:

- `len(history) <= umbral` → **en línea**: procesa y devuelve **200** con el resultado
  (comportamiento de siempre, intacto).
- `len(history) > umbral` → **por lote**: acepta el envío y devuelve **202** con un
  `job_id` (más `status_url` y `result_url`).

Se descartó exponer endpoints `/batch` separados: duplicarían la superficie y obligarían
al cliente a elegir transporte. La opción A es la más fiel al contrato §7 ("un solo
contrato para todos los canales y modos"): el cliente integra una vez y el **tamaño**
decide el transporte, no el cliente. Ambos códigos (200 y 202) se documentan en Swagger
(`responses=`), igual que 400/422.

El ruteo vive en **una sola pieza** (`spc/api/ruteo.py`) que tanto el canal JSON como el
Excel invocan tras validar, de modo que la decisión es idéntica para ambos y no hay
lógica de predicción duplicada.

### 2. La frontera = `len(history)`, configurable; default MEDIDO

- **Definición de "fila" (uniforme para los tres dominios y para JSON y Excel):** el
  número de filas del bloque **`history`** (`len(history)`). Es el bloque compartido y
  el verdadero motor del volumen (series × días); `replenishment_params` /
  `inventory_status` son pequeños por construcción. En Excel se cuentan las filas de
  datos de la hoja `history` (la misma petición validada que el JSON).
- **Configurable:** `SPC_ONLINE_MAX_ROWS` (sin nada clavado).
- **Default `2_000`, elegido midiendo** (`scripts/bench_umbral_online.py`) el tiempo del
  flujo síncrono de SALES. Medición **indicativa** (artefacto diminuto, máquina de
  desarrollo; da orden de magnitud y escalado, no un SLA):

  | filas `history` | series | tiempo síncrono aprox. |
  |---:|---:|---:|
  | 1.000 | 6 | ~1,6 s |
  | 2.000 | 11 | ~2,1 s |
  | 5.000 | 28 | ~4,1 s |
  | 10.000 | 56 | ~6,9 s |
  | 50.000 | 278 | ~23,7 s |

  El coste escala ~linealmente con el nº de series. Se eligió **2.000** porque mantiene
  la respuesta síncrona **cómodamente por debajo de unos pocos segundos** (~2 s),
  mientras que 10.000 ya rondaba ~7 s. **Producción debe re-medir** con el modelo y el
  hardware reales y ajustar `SPC_ONLINE_MAX_ROWS`. Tests y demo lo bajan por variable de
  entorno para forzar el modo lote con fixtures pequeños.

### 3. Lote **in-process**, en memoria (P5)

- Almacén de trabajos **en memoria** (`dict` protegido por lock) + un
  `concurrent.futures.ThreadPoolExecutor` (`SPC_BATCH_WORKERS`, default 1), ambos en
  `app.state.jobs` (inyectable y testeable, como el registro de artefactos).
- **Sin Celery/Redis** (P5): cero dependencias de terceros nuevas; solo stdlib
  (`uuid`, `threading`, `concurrent.futures`, `datetime`).
- El worker llama al **mismo `procesar`** que el modo en línea y **serializa el
  resultado igual** que la respuesta síncrona (`response_model` + `exclude_none`,
  `mode="json"`), de modo que el resultado recuperado es **byte-equivalente** al online.
- **Mapeo de errores idéntico al online:** una regla de negocio incumplida
  (`SolicitudInvalida`) se guarda como **400** `invalid_request` con el mismo cuerpo;
  cualquier otro fallo, como **500** `internal_error` controlado.

#### Limitaciones honestas (aceptadas para la demo)

- **Volatilidad:** los trabajos se **pierden al reiniciar** el proceso (no hay
  persistencia).
- **Restricción de despliegue — un solo proceso/worker:** los trabajos en memoria
  **no se comparten entre procesos**. Con varios workers de uvicorn (`--workers > 1`,
  o varias réplicas) un `job_id` creado por un proceso no es visible para otro
  (un envío daría 202 en un worker y 404 en otro al consultar). Por tanto, **el modo
  lote exige desplegar con un solo proceso/worker** (`--workers 1`) hasta migrar a un
  almacén compartido.

### 4. Endpoints del lote

- **Envío:** sin endpoint nuevo — lo hace el mismo endpoint de predicción (202 con
  `JobAccepted`).
- **Estado:** `GET /jobs/{job_id}` → `JobStatus` (`queued`/`running`/`done`/`error`).
- **Resultado:** `GET /jobs/{job_id}/result` → fiel a "el mismo dato da el mismo
  resultado":
  - `done` → **200** con la respuesta del dominio (idéntica al online);
  - `error` → el **mismo código y cuerpo** que daría el online (p. ej. **400**);
  - `queued`/`running` → **202** con el estado (aún no listo).
- **`job_id` inexistente** → **404** `not_found`, con el cuerpo de error uniforme.

### 5. Lote contra el modelo CONGELADO (opción A); ajuste por cliente DIFERIDO

El modo lote de esta fase solo cambia **cómo** se procesa (asíncrono), no reentrena ni
ajusta nada: usa el **modelo congelado** (opción A). El **ajuste por cliente**
(opción B/híbrida) **no se implementa**; queda como **experimento futuro y medido**, que
solo se activaría si los resultados lo justifican (transferibilidad — ADR-0009). El
catálogo lo refleja: `mode batch = available`, `mode client_adjustment = planned`.

### 6. Conciencia de memoria: troceo APAGADO por defecto y condicionado

Por defecto el worker hace **una sola llamada** al flujo con la petición completa →
resultado **idéntico garantizado**. El **troceo por grupos `(store_id, product_id)`
independientes** (procesar por bloques y concatenar) queda **documentado pero APAGADO**:
solo se habilitaría tras una **prueba de identidad** que confirme que da exactamente el
mismo resultado que la llamada única. Así la equivalencia nunca está en riesgo. No se
añade código muerto: cuando se implemente, irá tras su `SPC_BATCH_CHUNK_ROWS` y su test.

### 7. Tope de tamaño de Excel reconciliado con el ruteo por filas

La frontera en línea/lote es por **filas**, no por bytes. El tope de bytes del `.xlsx`
(`SPC_EXCEL_MAX_BYTES`) deja de ser "el límite del modo en línea" y pasa a ser una
**guarda anti-abuso (DoS)** para cualquier subida; se sube a **25 MB** (antes 5 MB) para
que un Excel de lote quepa (hay que parsear el archivo para contar sus filas). El modo
en línea sigue **modesto pero medido en filas** (`SPC_ONLINE_MAX_ROWS`).

## Consecuencias

- **Positivas:** envíos grandes ya no atan la conexión; el contrato no cambia; el motor y
  el negocio quedan intactos; cero dependencias nuevas; equivalencia online↔lote probada.
- **Negativas / deuda asumida:** trabajos volátiles y atados a un solo proceso (ver §3).
  **Mejoras futuras documentadas:** (a) **persistencia / almacén compartido** (SQLite)
  para sobrevivir reinicios y permitir varios workers; (b) **cola externa**
  (Celery/Redis u otra) para escalar el procesamiento; (c) **ajuste por cliente** en
  lote (ADR-0009); (d) **troceo memory-aware** (§6). Ninguna se implementa aquí.

## Alternativas consideradas

- **Endpoints `/batch` separados** — descartado (duplica superficie; menos fiel a §7).
- **Cola externa (Celery/Redis) ya** — descartado para esta fase (P5: sobreingeniería
  para una demo; queda como mejora futura).
- **Persistencia en SQLite ya** — descartado por simplicidad; el en memoria es
  suficiente para la demo y SQLite queda documentado como el siguiente paso natural.
