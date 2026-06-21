# ADR 0011 — Persistencia incremental del corpus (Fase A MEJORADO)

- **Estado:** Aceptado (2026-06-19).
- **Fase:** A (MEJORADO) — primer paso del "Camino A" del documento de entrega
  ([SPC_Entrega_Despliegue_Valentin.md](../SPC_Entrega_Despliegue_Valentin.md) §8), en su
  versión **simple y sin GPU en el servidor**: acumular el corpus del cliente con cada uso
  para habilitar mejoras futuras del modelo.
- **Contexto previo:** [ADR-0008](0008-modos-ejecucion.md) (modos en línea/lote, modelo
  congelado), [ADR-0009](0009-transferibilidad-modelo-congelado.md) (modelo congelado;
  ajuste por cliente como dirección futura), `docs/contrato_datos.md` (frontera agnóstica).
  Recomendaciones del docente 2 y 3 (plataforma agnóstica; el cliente trae sus datos).
- **No toca** el motor de ML ni la capa interna en español ni el **cuerpo** del contrato.
  Añade una **capa de persistencia** nueva (`spc.service.repositorio`) y un punto de captura
  en el ruteo (`spc.api.ruteo`). El modelo se sigue entregando **congelado** (ADR-0009).

## Contexto

Hasta hoy la plataforma **predice y descarta**: cada petición se responde con el modelo
congelado y los datos del cliente no se guardan. El "Camino A" del documento pide que el
sistema **acumule** los datos del cliente para poder ajustar/mejorar el modelo con el
tiempo. La versión completa del Camino A (pipeline de entrenamiento por cliente en GPU +
experimento medido) es costosa y arriesgada cerca del cierre.

La decisión del usuario fue hacer la **versión MEJORADA simple**: construir ahora la
**acumulación** (la base de datos que hace posible "entrenar más y más") y dejar el
reentrenamiento como un **paso manual posterior** que reutiliza los scripts existentes.

## Decisión

**Cada predicción exitosa se guarda en una base SQLite** (biblioteca estándar, cero
dependencias nuevas), capturada en el **único hogar del flujo de predicción**
(`spc.api.ruteo.responder_segun_volumen`), de modo que cubre **los tres dominios**
(`sales`/`purchases`/`inventory`), **ambos canales** (`json`/`excel`) y **ambos modos**
(`online`/`batch`) con un solo punto de enganche.

### 1. Qué se guarda

- **`observations`** — el bloque `history` del cliente **normalizado** (`date`, `store_id`,
  `product_id`, `units_sold`, `on_promotion`, `transactions`, `event_active`). Es el
  **corpus que crece** con cada uso.
- **`submissions`** — una fila por petición para **auditoría/replay**: `client_id`,
  `domain`, `channel`, `mode`, `model_version`, `n_rows`, los **parámetros** de la petición
  (`horizon`, `granularity`, `replenishment_params`…) y la respuesta serializada. El
  bloque `history` **no** se duplica aquí: ya vive normalizado en `observations` (la
  petición se reconstruye uniendo ambas por `submission_id`). Así la base no crece dos
  veces con el mismo dato.

### 1.b Deduplicación e idempotencia (corpus apto para entrenar)

El corpus es un **activo de entrenamiento**, no un log de eventos: filas repetidas
**sesgarían** un reentrenamiento (sobre-ponderan las series que el cliente reenvía). Por
eso la acumulación es **idempotente**: un índice **UNIQUE** sobre la identidad de la serie
(`client_id`, `store_id`, `product_id`, `date`) + `INSERT OR IGNORE` garantiza que
**reenviar el mismo `history` no agrega filas**. Política ante misma serie+fecha con valor
distinto (corrección): se **conserva la primera** (`keep-first`); una corrección posterior
del mismo punto se ignora — limitación conocida y aceptada para esta fase.

Como **red de seguridad**, `scripts/exportar_corpus.py` **vuelve a deduplicar** antes de
exportar (cubre bases creadas sin el índice y el modo `--raw`). **Regla:** el corpus
**debe deduplicarse antes de entrenar**; el export ya lo hace.

### 2. Multi-cliente sin tocar el contrato

Cada envío se etiqueta con un **`client_id`** tomado del header **`X-Client-Id`** (default
`"default"` si no se envía). Es **metadato de transporte**, no un campo del cuerpo: el
contrato (v1.0.1) **no cambia**. Esto habilita corpus —y un eventual ajuste— **por
cliente** a futuro, alineado con la visión agnóstica del docente.

### 3. Best-effort: la persistencia nunca rompe la predicción

El guardado va envuelto en `try/except` con log: si la base falla, la **predicción se
responde igual** (la disponibilidad no se degrada por una falla de almacenamiento). Si la
persistencia está desactivada (`SPC_PERSIST_ENABLED=0`) o no se inicializó, el ruteo
simplemente no acumula. **La respuesta de predicción es byte-idéntica con o sin
persistencia.**

### 4. El reentrenamiento es un puente MANUAL (no automático)

El ciclo "entrenar más y más" es deliberado y fuera de línea:

1. `python scripts/exportar_corpus.py --out data/corpus.parquet [--client-id X]` exporta el
   corpus en el **esquema analítico** (reutiliza `adaptador.historico_a_analitico`, la
   misma traducción contrato→motor que la predicción).
2. Reentrenar en **GPU** con los scripts existentes (`scripts/train_regresion.py`, …),
   con el rigor de validación de siempre.
3. Reemplazar el artefacto en `models/`; la API carga el nuevo modelo al reiniciar.

El **reentrenamiento automático en el servidor queda diferido** (necesita GPU y un
experimento medido que demuestre mejora). En el catálogo, `client_adjustment` **sigue
`planned`** (ADR-0009): esta fase construye la *acumulación*, no el *ajuste por cliente*.

## Configuración (entorno, con defaults documentados)

| Variable | Default | Para qué |
|---|---|---|
| `SPC_PERSIST_ENABLED` | `true` | Activa/desactiva la persistencia del corpus. |
| `SPC_DB_PATH` | `<base>/data/spc.db` | Ruta del archivo SQLite del corpus. |

## Consecuencias

- **A favor:** primer paso real del Camino A con riesgo mínimo; honesto (no promete ajuste
  por cliente que no se ha validado); reutiliza el chokepoint de ruteo y el patrón de
  inyección (`app.state`) ya existentes; sin dependencias nuevas; el modelo sigue congelado.
- **Deuda asumida y explícita:** (a) el reentrenamiento no es automático; (b) el almacén de
  trabajos por lote sigue **in-process** (no se migró a SQLite en esta fase, ver §8 del
  documento de entrega); (c) la captura por lote ocurre **al completar** el job (si el job
  falla, no se persiste esa entrada).
- **Privacidad/operación:** la base acumula datos del cliente; en producción debe
  considerarse retención, respaldo y acceso. Se documenta como nota operativa.
- **`X-Client-Id` sin autenticación (pendiente de producción):** hoy el `client_id` es un
  header **declarativo y suplantable** (cualquiera puede enviarlo). Sirve para segmentar el
  corpus en dev/piloto, **no** para aislar clientes con garantías. En producción debe
  **ligarse a autenticación** (API key / token → `client_id` verificado) antes de tratar la
  separación por cliente como confiable.

## Referencias

- [ADR-0008 — Modos de ejecución](0008-modos-ejecucion.md)
- [ADR-0009 — Transferibilidad: modelo congelado](0009-transferibilidad-modelo-congelado.md)
- [Documento de entrega para el despliegue (§8, Camino A)](../SPC_Entrega_Despliegue_Valentin.md)
- [contrato_datos.md](../contrato_datos.md)
