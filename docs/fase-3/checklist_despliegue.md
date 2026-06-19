# Checklist de "listo para desplegar" — puerta a Fase 4 (despliegue)

> Documento vivo. Vive en `docs/fase-3/checklist_despliegue.md`.
>
> Cierra la **Fase 3.7**: enumera lo que hay que verificar y fijar antes de un
> despliegue real, y —con **honestidad estricta**— separa lo que **ya sostiene la
> demo** de lo que **queda abierto** y a cargo de quién. No promete nada que la API no
> haga hoy. Atiende las recomendaciones del docente sobre datos sintéticos (8) y
> plataforma lista (11).
>
> Estado de pruebas al cerrar Fase 3.7: **batería completa 156/156 en verde** (PASO A,
> incluye el motor) y **`tests/api` 100/100 en verde** tras añadir los tests de esta
> fase. Reproducible con fixtures sintéticos, sin GPU ni `data/raw`.

---

## 1. Cómo se lanza (configuración de proceso)

- [ ] **Un solo worker de uvicorn.** El almacén de trabajos por lote es **in-process y
  en memoria** ([ADR-0008](../decisiones/0008-modos-ejecucion.md)): con `--workers > 1`
  un `job_id` creado por un proceso **no es visible** para otro. Lanzar exactamente:
  ```powershell
  venv\Scripts\python -m uvicorn spc.api.main:app --host 0.0.0.0 --port 8000 --workers 1
  ```
  Escalar a más procesos exige primero un almacén compartido (p. ej. SQLite/Redis); hoy
  **no** está implementado.
- [ ] **Mantener `SPC_BATCH_WORKERS=1`** (default). Más hilos no dan persistencia ni
  visibilidad entre procesos; solo acotan memoria. FIFO con 1 hilo es lo previsto.
- [ ] Los **trabajos por lote se pierden al reiniciar** el proceso (sin persistencia).
  Aceptable para la demo y un piloto de un solo proceso; documentado en ADR-0008.

## 2. Variables de entorno (con sus defaults)

Todas son **opcionales**: sin configurar nada, la API se comporta como en los tests.
**Los defaults reproducen la salida histórica** (no cambian el resultado); cambiarlas es
una decisión de política/operación, no del modelo.

| Variable | Default | Para qué | Acción en producción |
|---|---|---|---|
| `SPC_ONLINE_MAX_ROWS` | `2000` | Frontera filas en línea↔lote (`len(history)`) | **Re-medir** con modelo y hardware reales (`scripts/bench_umbral_online.py`) y ajustar |
| `SPC_EXCEL_MAX_BYTES` | `26214400` (25 MB) | Tope plano anti-abuso del `.xlsx` subido | Ajustar al tamaño real de los Excel de lote |
| `SPC_BATCH_WORKERS` | `1` | Hilos del executor de lote in-process | Dejar en `1` (ver §1) |
| `SPC_CORS_ORIGINS` | `*` | Orígenes CORS permitidos (coma-separados) | **Fijar al origen del frontend** (no dejar `*` en prod) |
| `SPC_PURCHASES_SAFETY_FACTOR` | `0.30` | Colchón de PURCHASES (coverage_days) | Política del cliente |
| `SPC_PURCHASES_SAFETY_METHOD` | `coverage_days` | Método de stock de PURCHASES | Knob de política (`coverage_days`\|`service_level`) |
| `SPC_INVENTORY_SAFETY_METHOD` | `service_level` | Método de stock de INVENTORY | Poner en `coverage_days` lo **unifica** con PURCHASES |
| `SPC_INVENTORY_LEAD_TIME_DEFAULT` | `7` | Lead time si el cliente no lo envía (días) | Política del cliente |
| `SPC_INVENTORY_DEMAND_WINDOW` | `28` | Ventana (días) para μ/σ de la demanda | Política del cliente |
| `SPC_INVENTORY_Z_BASE` | `1.28` (~90%) | Nivel de servicio base (z) | Política del cliente |
| `SPC_INVENTORY_Z_HIGH_VOLUME` | `1.65` (~95%) | Nivel de servicio del segmento alto volumen (z) | Política del cliente |
| `SPC_INVENTORY_SAFETY_FALLBACK_FACTOR` | `0.5` | Respaldo de service_level si σ no es estimable | Política del cliente |
| `SPC_INVENTORY_COVERAGE_FACTOR` | `0.30` | Factor usado solo si INVENTORY pasa a coverage_days | Política del cliente |

Knobs de política y su porqué: [ADR-0010](../decisiones/0010-politica-inventario-stock.md).
Verificado por tests: cambiar una variable cambia el resultado de forma esperable y los
defaults **no** alteran la salida (`tests/api/test_politica_config.py`).

- [ ] CORS fijado al frontend real (`SPC_CORS_ORIGINS`), no `*`.
- [ ] `SPC_ONLINE_MAX_ROWS` re-medido con el modelo/HW de producción.

## 3. Artefactos del motor (propiedad de modelado)

- [ ] La carpeta **`models/`** contiene los tres artefactos congelados: **regresión**
  (SALES), **clasificación** (INVENTORY) y **clustering de tiendas** (segmento). La API
  los **carga al arrancar** y **no los regenera** (propiedad de Valentín; la API solo
  consume). Si faltan, el arranque falla con un error claro de "artefacto no encontrado".
- [ ] La versión del modelo se **lee de la metadata** del artefacto (no se clava en el
  código); aparece en `metadata.model` de SALES y en `GET /catalog`.

## 4. Superficie pública y contrato

- [ ] **`GET /health`** responde `{"status":"ok"}` (liveness).
- [ ] **`/docs`** (Swagger) renderiza y documenta los tres endpoints con sus ejemplos.
- [ ] **`GET /catalog`** describe dominios, entradas/salidas reales, canales/modos y la
  **versión del contrato** (`1.0.1`, fuente única `CONTRACT_VERSION`, alineada con el
  encabezado de [contrato_datos.md](../contrato_datos.md)). El catálogo se **deriva de
  los esquemas**: no puede prometer un campo/canal que la API no entrega (anclado por
  `test_catalog_*`, incluido el cruce con OpenAPI).
- [ ] **Contrato de error uniforme**: validación (422), regla de negocio (400), Excel mal
  formado (422 con hoja/fila/columna), archivo grande (413), job inexistente (404) y
  cualquier fallo inesperado (500 controlado) devuelven **el mismo cuerpo** `{"error":{...}}`,
  **sin volcados de pila**. El 400 de regla de negocio es **idéntico** en línea y por lote.

## 5. Compuertas pre-despliegue (correr y dejar en verde)

- [ ] Batería **completa** en verde (incluye el motor, ~1h40):
  ```powershell
  venv\Scripts\python -m pytest -q
  ```
- [ ] Suite de **API** en verde (rápida, sin GPU):
  ```powershell
  venv\Scripts\python -m pytest tests/api -q
  ```
- [ ] (Opcional) Lint/format/tipos: `ruff check .`, `black --check .`, `mypy`.

## 6. Pendientes que NO se cierran desde aquí (abiertos)

Requieren GPU / `data/raw` / coordinación; se documentan, **no** se intentan en Fase 3.7.

- [ ] **`objetivo_cuantil` (P75) en la metadata del artefacto** — *model-adjacent, de
  Valentín.* Hoy el cuantil de "demanda alta" usa un **fallback documentado (0.75)**
  porque la metadata aún no lo expone como número. Exponerlo en la próxima
  reconstrucción del artefacto. La API ya lo leería de ahí si existiera
  (`test_politica_config.py::test_cuantil_demanda_alta_se_lee_de_metadata_si_existe`).
- [ ] **`interval_80` diferido** — el modelo de regresión aún no produce intervalo de
  predicción; la respuesta lo **omite** (declarado en `/catalog` y en el contrato).
- [ ] **Reentrenamiento / ajuste por cliente a escala completa** — requiere GPU y datos
  crudos; es la dirección futura (opción B/híbrida, marcada `planned` en `/catalog`). De
  Valentín / fase posterior. Ver [ADR-0009](../decisiones/0009-transferibilidad-modelo-congelado.md).
- [ ] **Actualización manual de `notion/*`** — el backlog/estado en Notion se actualiza a
  mano; no hay sincronización automática.

## 7. Resumen de la puerta

✅ **Sostiene la demo y un piloto de un proceso:** los tres dominios por JSON y Excel, en
línea y por lote, con errores claros y catálogo honesto; todo verificado con datos
sintéticos.
⚠️ **Antes de un despliegue "de verdad":** fijar CORS, re-medir el umbral de filas,
confirmar artefactos en `models/`, y asumir las limitaciones del lote de un solo proceso
(§1) y los pendientes de modelado (§6).
