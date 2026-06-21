# Datos sintéticos para probar SPC (Excel listos para usar)

> Generador reutilizable y reproducible de planillas Excel **ya llenas** que respetan
> EXACTAMENTE las plantillas del sistema, para evaluar el **modo en línea vs lote** y el
> **reentrenamiento por cliente**. Scripts: [`scripts/generar_sinteticos.py`](../scripts/generar_sinteticos.py)
> y [`scripts/validar_sinteticos.py`](../scripts/validar_sinteticos.py).

---

## 1. Resumen para una PM (no técnico)

El sistema recibe datos de los clientes en **planillas Excel** (una por dominio:
**ventas**, **compras**, **inventario**). Para poder probarlo de punta a punta sin
pedirle datos reales a ningún cliente, creamos un **set de planillas de juguete pero
realistas**: cada una trae ventas con su estacionalidad (más los fines de semana, picos
en fechas especiales, promociones, productos que casi no se venden, etc.), todo
**inventado pero verosímil**.

Con este set respondemos dos preguntas del producto:

1. **¿Cuándo el sistema responde al instante y cuándo lo hace "en diferido"?**
   El sistema atiende **al instante** (respuesta inmediata) los envíos chicos y procesa
   **en diferido** (te da un "número de ticket" y avisa cuando termina) los envíos
   grandes. La frontera está en **2.000 filas de historial**. Tenemos planillas a cada
   lado de esa línea —incluida una con 2.000 (instantánea) y otra con 2.001 (diferida)—
   para comprobar que la decisión es exacta.

2. **¿Tenemos con qué probar el "reentrenamiento por cliente"?** (la función que está en
   construcción). Sí: incluimos una planilla con **mucha historia** (2 años, para que
   reentrenar tenga sentido), otra **muy corta** (el caso honesto de "no alcanzan los
   datos") y otra con **demanda intermitente** (muchos ceros, para ver que aguanta).

Cada planilla **pasa la validación del sistema** (formato correcto) y **cae en el modo
esperado**, verificado automáticamente. También dejamos **3 planillas rotas a propósito**
para mostrar que el sistema las **rechaza con un mensaje claro** en vez de fallar.

**En una frase:** ya tenemos datos de prueba listos, variados y verificados, para
demostrar el sistema y, cuando esté lista, la función de reentrenamiento.

---

## 2. Dónde están y cómo se generan

- **Archivos generados:** `data/synthetic/` (y `data/synthetic/invalidos/` los rotos).
  Esta carpeta está **gitignored** (no se versiona): los `.xlsx` se **regeneran** con un
  comando. Si necesitas versionarlos, copialos a una carpeta fuera de `data/`.
- **Manifiesto:** `data/synthetic/MANIFIESTO.csv` (perfil y uso de cada archivo).
- **Resultados de validación:** `data/synthetic/resultados_validacion.csv`.

```bash
# 1) Generar todo el set (reproducible: misma semilla -> mismos archivos)
./venv/Scripts/python.exe scripts/generar_sinteticos.py --out data/synthetic --seed 42

# 2) Validar cada archivo contra el sistema real (strict + modo 200/202; rotos -> 422)
./venv/Scripts/python.exe scripts/validar_sinteticos.py --dir data/synthetic --models models
```

**Dependencias:** solo `numpy`, `pandas` y `openpyxl` (ya en el proyecto). **Sin GPU, sin
datos crudos.** Todo deriva de `--seed` (por defecto 42).

---

## 3. Cómo se garantiza la conformidad con el contrato

- El generador **no escribe los nombres de columna a mano**: los toma de
  `spc.api.ingest.esquema_excel.PLANTILLAS`, la **misma fuente** que el sistema usa para
  generar y validar sus plantillas. Si el contrato cambia, los archivos lo siguen solos.
- Hojas y encabezados (en inglés) por dominio:
  - **ventas:** `history` + `parameters` (`granularity`, `horizon`).
  - **compras:** `history` + `replenishment_params` (`current_stock`, `lead_time_days`, `target_coverage_days`).
  - **inventario:** `history` + `inventory_status` (`current_stock`, `lead_time_days` opcional).
- Rangos respetados: `units_sold ≥ 0`, `on_promotion` entero `≥ 0`, `transactions ≥ 0`
  (vacío en días sin venta de las series intermitentes), `lead_time_days`/
  `target_coverage_days` enteros `> 0`, `horizon` entero `1–365`, `granularity` en
  `day/week/month`, fechas ISO válidas, **sin columnas extra**.
- **Realismo:** cada serie `(store_id, product_id)` =
  `nivel_base × tendencia × estacionalidad_semanal × estacionalidad_anual +
  picos_por_promoción + eventos + ruido`, con intermitencia (ceros) opcional. Los
  `product_id` son **familias reales** de Corporación Favorita (BEVERAGES, GROCERY, …).

---

## 4. Manifiesto del set

Modo decidido por `len(history)` contra `SPC_ONLINE_MAX_ROWS` (**2.000**):
`≤ 2.000` → **200 en línea**; `> 2.000` → **202 lote**.

| Archivo | Dominio | T×P×D | Filas history | Modo | Uso | gran./horiz. |
|---|---|---|---:|---|---|---|
| `ventas_online_pequeno.xlsx` | sales | 1×1×150 | 150 | **200 línea** | online | day / 7 |
| `ventas_online_medio.xlsx` | sales | 2×3×200 | 1.200 | **200 línea** | online | week / 8 |
| `ventas_frontera_bajo.xlsx` | sales | 1×1×2000 | **2.000** | **200 línea** | frontera (tope línea) | day / 30 |
| `ventas_frontera_alto.xlsx` | sales | 1×1×2001 | **2.001** | **202 lote** | frontera (mín. lote) | day / 30 |
| `ventas_lote_grande.xlsx` | sales | 5×10×200 | 10.000 | **202 lote** | lote | month / 6 |
| `ventas_lote_masivo.xlsx` | sales | 10×25×200 | 50.000 | **202 lote** | lote/estrés (1,4 MB) | day / 30 |
| `ventas_retrain_rico.xlsx` | sales | 5×8×730 | 29.200 | **202 lote** | **reentrenamiento** (split temporal) | day / 28 |
| `ventas_retrain_escaso.xlsx` | sales | 1×1×80 | 80 | **200 línea** | **reentrenamiento** ("no alcanza") | day / 7 |
| `ventas_retrain_intermitente.xlsx` | sales | 3×5×200 | 3.000 | **202 lote** | **reentrenamiento** (robustez/ceros) | day / 14 |
| `compras_pequeno.xlsx` | purchases | 2×3×120 | 720 (+6) | **200 línea** | online | — |
| `compras_grande.xlsx` | purchases | 5×8×100 | 4.000 (+40) | **202 lote** | lote | — |
| `inventario_pequeno.xlsx` | inventory | 2×3×120 | 720 (+6) | **200 línea** | online | — |
| `inventario_grande.xlsx` | inventory | 5×8×100 | 4.000 (+40) | **202 lote** | lote | — |

`(+N)` = filas de la hoja `replenishment_params` / `inventory_status` (una por serie).

**Archivos rotos a propósito** (`data/synthetic/invalidos/`, deben dar **422**):

| Archivo | Qué tiene mal |
|---|---|
| `mal_texto_en_numero.xlsx` | Texto `"N/D"` en la columna numérica `units_sold`. |
| `mal_falta_columna.xlsx` | Falta la columna obligatoria `units_sold`. |
| `mal_obligatorio_vacio.xlsx` | Celda vacía en el campo obligatorio `store_id`. |

---

## 5. Resultado de la validación (última corrida)

Validado contra el **motor real** (`models/`), con persistencia desactivada
(`SPC_PERSIST_ENABLED=0`), subiendo cada archivo a `POST /{dominio}/excel`:

- **13/13** archivos válidos: **pasan la validación strict** y **caen en el modo
  esperado** (200 en línea / 202 lote). El mayor (50.000 filas) pesa **1,44 MB**, muy por
  debajo del tope de **25 MB**.
- **3/3** archivos rotos: **rechazados con 422** y un detalle de error legible (hoja/fila/columna).

La tabla completa queda en `data/synthetic/resultados_validacion.csv` (la regenera el
validador en cada corrida).

---

## 6. Cómo los uso yo misma

**Probar el modo en línea vs lote (manual, contra una API levantada):**

```bash
# en línea -> 200 con el resultado
curl -F "file=@data/synthetic/ventas_online_pequeno.xlsx" http://localhost:8000/sales/excel

# lote -> 202 con un job_id; luego consultar estado/resultado
curl -F "file=@data/synthetic/ventas_lote_grande.xlsx" http://localhost:8000/sales/excel
#   -> {"job_id": "...", "status_url": "/jobs/<id>", "result_url": "/jobs/<id>/result"}
```

- **Frontera exacta:** sube `ventas_frontera_bajo.xlsx` (2.000 → 200) y luego
  `ventas_frontera_alto.xlsx` (2.001 → 202) para ver el salto con una sola fila de diferencia.
- **Compras / inventario:** mismos endpoints `/purchases/excel` y `/inventory/excel`.
- **Errores:** sube los de `invalidos/` y verás el cuerpo de error uniforme (422).

**Cuando la función de reentrenamiento por cliente esté lista**, estos son los archivos a usar:

- `ventas_retrain_rico.xlsx` — **caso principal**: 40 series con **2 años** de historia
  diaria → alcanza para un **split temporal** (entrenar con el pasado, evaluar con lo
  reciente) con sentido.
- `ventas_retrain_escaso.xlsx` — **caso honesto de "no alcanza"**: 80 días de una sola
  serie; sirve para verificar que el sistema **avisa** que no hay datos suficientes en vez
  de reentrenar con basura.
- `ventas_retrain_intermitente.xlsx` — **robustez**: 15 series con muchos ceros (demanda
  intermitente); sirve para ver que el reentrenamiento no se rompe con series "difíciles".

> Sugerencia: etiqueta cada subida con el header `X-Client-Id` (p. ej. `acme`) para que el
> corpus por cliente quede separado; es opcional y no cambia la predicción.

---

## 7. Reproducibilidad y mantenimiento

- **Semilla única:** `--seed` controla todo; misma semilla → mismos bytes. Cambia la
  semilla para obtener otro set igual de válido.
- **Ajustar el set:** edita la lista `PERFILES` en `scripts/generar_sinteticos.py` (cada
  entrada define tiendas×productos×días, fechas, patrón de demanda, modo esperado y uso).
  El validador recalcula el modo esperado a partir de las filas, así que no hay que
  sincronizar nada a mano.
- **No se tocó el sistema:** los scripts solo **generan datos** y **usan** la API como
  cliente (TestClient). La fuente de verdad sigue siendo el contrato.
