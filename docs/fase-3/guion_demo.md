# Guion de demo — presentación SPC (Fase 3)

> Documento vivo. Vive en `docs/fase-3/guion_demo.md`.
>
> Pensado para que lo siga una **PM no técnica**: pasos con clics y comandos listos para
> copiar. La idea que se demuestra: **SPC es una plataforma; el cliente trae sus datos
> por un contrato y recibe tres servicios, por JSON o Excel, en línea o por lote, con
> errores claros y promesas honestas.** Todo corre en local, sin internet ni datos crudos.
>
> Guía hermana, más detallada: [guia_probar_api.md](../guia_probar_api.md).

**Duración:** ~8–10 min. **Mensaje de cierre:** "el método está validado sobre Favorita;
la plataforma está lista para que un cliente traiga sus datos".

---

## 0. Preparación (antes de presentar)

Abre una terminal en la carpeta del proyecto y levanta el servidor con **un solo worker**:

```powershell
cd "C:\Users\lucia\OneDrive\Documents\sistema_predicion_comercializacion"
venv\Scripts\python -m uvicorn spc.api.main:app --workers 1
```

Cuando veas `Uvicorn running on http://127.0.0.1:8000`, **déjalo corriendo**. Abre el
navegador en **http://127.0.0.1:8000/docs** (Swagger). Eso es todo el setup.

> Para el paso 4 (lote) usarás una **segunda terminal** con el umbral bajo; lo indica ese paso.

---

## 1. El catálogo: "lista de servicios" honesta

En Swagger, abre **GET /catalog → Try it out → Execute** (o ve a
http://127.0.0.1:8000/catalog).

**Qué decir / señalar:**
- Los **tres dominios**: `sales`, `purchases`, `inventory`, con qué entra y qué sale de cada uno.
- Los **canales** (`json`, `excel`) y **modos** (`online`, `batch`) marcados **`available`**;
  el ajuste por cliente aparece **`planned`** (somos honestos: aún no se entrega).
- La **versión del contrato** (`contract_version: 1.0.1`).
- Las **notas/limitaciones** por dominio (p. ej. SALES no entrega `interval_80` todavía).

> Mensaje: "El catálogo se genera del código real, así que no puede prometer algo que la
> API no haga."

## 2. Predicción JSON en línea (el caso típico)

En Swagger, **POST /sales → Try it out**. Pega el ejemplo realista de
`examples/api/ventas_request.json` (ábrelo, copia todo) y **Execute**.

**Qué mostrar en la respuesta (200):**
- `field: "sales"` y `model` (la versión real del artefacto, p. ej. `regresion_v3`).
- La lista `forecast`: una fila por `(date, store_id, product_id)` con `forecast_demand`.
- `metadata.scale: "units"`.

(Opcional) Repite con **POST /purchases** (`compras_request.json`) y **POST /inventory**
(`almacen_request.json`) para mostrar los tres servicios con el **mismo bloque de historia**.

## 3. Excel: la misma puerta, sin programar

Demuestra que **Excel es solo otra puerta al mismo contrato**:

1. **GET /sales/template → Execute → Download file**: se descarga `sales_template.xlsx`
   con hojas `history`, `parameters` e `instructions` (encabezados en inglés).
2. (Ya viene con una fila de ejemplo lista para usar.)
3. **POST /sales/excel → Try it out → "Choose File"**, sube el `.xlsx` y **Execute**.

**Qué decir:** "El resultado es **idéntico** al del JSON del paso 2 — los mismos datos por
Excel dan la misma respuesta. El cliente puede operar solo con Excel."

## 4. Modo por lote: envíos grandes sin bloquear

El lote se activa cuando el envío supera el umbral de filas. Para demostrarlo con un
ejemplo pequeño, **bajamos el umbral** en una **segunda terminal**:

```powershell
cd "C:\Users\lucia\OneDrive\Documents\sistema_predicion_comercializacion"
$env:SPC_ONLINE_MAX_ROWS = "1"
venv\Scripts\python -m uvicorn spc.api.main:app --workers 1 --port 8001
```

Abre http://127.0.0.1:8001/docs y repite **POST /sales** con `ventas_request.json`:

1. Ahora la respuesta es **202** con un `job_id`, `status_url` y `result_url`
   (no esperas el cálculo: te dan un comprobante).
2. **GET /jobs/{job_id}** (pega el `job_id`): el `status` pasa de `running` a **`done`**.
3. **GET /jobs/{job_id}/result**: **200** con **la misma respuesta** que daría en línea.

**Qué decir:** "Para un envío grande, la API responde al instante con un comprobante y
procesa en segundo plano; el resultado es el mismo. Mismo dato, mismo resultado."

> Al terminar la demo, cierra esta terminal (Ctrl + C) para no dejar el umbral bajo.

## 5. Un error claro (no un "error feo")

En Swagger (cualquiera de los dos puertos), **POST /sales** con un cuerpo inválido a
propósito. Por ejemplo, en PowerShell:

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8000/sales -Method Post `
  -ContentType "application/json" -Body '{"horizon":0,"history":[]}'
```

**Qué mostrar:** responde **422** con un cuerpo claro
`{"error":{"type":"validation","message":"...","details":[{"field":"...","problem":"..."}]}}`,
señalando **qué campo** falló y **por qué** — nunca un volcado de pila.

> Variante (regla de negocio): pedir un producto que no está en el historial devuelve
> **400 `invalid_request`** con un mensaje claro — **igual** en línea y por lote.

## 6. Cierre: honestidad sobre el alcance

Cierra apuntando a los documentos que sostienen las promesas (no improvises cifras):

- **Alcance, validación y límites:** [alcance_validacion_limitaciones.md](alcance_validacion_limitaciones.md)
  — qué se midió sobre Favorita y qué **no** se promete a otro rubro.
- **Aumento de datos (experimento):** [experimento_aumento_datos.md](experimento_aumento_datos.md).
- **Decisiones clave:** modos de ejecución [ADR-0008](../decisiones/0008-modos-ejecucion.md),
  transferibilidad del modelo congelado [ADR-0009](../decisiones/0009-transferibilidad-modelo-congelado.md),
  política de inventario/stock [ADR-0010](../decisiones/0010-politica-inventario-stock.md).
- **Listo para desplegar / pendientes:** [checklist_despliegue.md](checklist_despliegue.md).

**Frase de cierre:** "El método está validado sobre Favorita; la plataforma está lista
para que un cliente traiga sus datos. El rendimiento sobre Favorita demuestra el método,
no se transfiere como garantía a otro negocio."

---

## Apéndice — recuperación rápida si algo falla

- **"artefacto no encontrado" al arrancar** → asegúrate de estar en la carpeta del
  proyecto (debe existir `models/` con los `.joblib`).
- **El puerto está ocupado** → usa otro `--port` (p. ej. `--port 8002`).
- **El lote no cambia a 202** → confirma que pusiste `$env:SPC_ONLINE_MAX_ROWS = "1"`
  en **esa** terminal antes de levantar uvicorn.
- **Plan B sin servidor** → `venv\Scripts\python -m pytest tests/api -q` corre los tres
  dominios (JSON y Excel, en línea y lote, casos válidos y de error) sobre datos
  sintéticos; sirve como evidencia si no hay proyector/red.
