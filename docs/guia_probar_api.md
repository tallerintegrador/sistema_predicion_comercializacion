# Guía para probar la API (Fase 3) — paso a paso

Pensada para verificar el servicio **sin programar**: levantar el servidor, abrir
Swagger y enviar peticiones de ejemplo. Todo corre en local; no se necesita internet
ni datos crudos.

## 0. ¿Qué vas a ver?

Un servidor web local con tres "botones" (endpoints):

- **POST /sales** — cuánto se va a vender (pronóstico).
- **POST /purchases** — cuánto reponer (cantidad a pedir + punto de reorden).
- **POST /inventory** — riesgo de quiebre, stock recomendado y segmento de la tienda.

Y una página visual (**Swagger**) para probarlos con clics.

## 1. Abrir una terminal en la carpeta del proyecto

- En VS Code: menú **Terminal → New Terminal** (se abre ya en la carpeta del proyecto).
- O abre **PowerShell** y entra a la carpeta:
  ```powershell
  cd "C:\Users\lucia\OneDrive\Documents\sistema_predicion_comercializacion"
  ```

## 2. (Solo si es una máquina nueva) Instalar dependencias

En esta máquina **ya está todo instalado**. En una máquina nueva, una sola vez:
```powershell
python -m venv venv
venv\Scripts\python -m pip install -e .
```

## 3. Levantar el servidor

```powershell
venv\Scripts\python -m uvicorn spc.api.main:app
```

Verás algo como:
```
INFO:     Started server process [...]
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
```
Eso significa que **el servidor está arriba** en `http://127.0.0.1:8000`. Déjalo
corriendo (esta terminal queda "ocupada" mostrando los registros).

> Si ves un error de "artefacto no encontrado", asegúrate de estar en la carpeta del
> proyecto (debe existir la carpeta `models/` con los `.joblib`).

## 4. Abrir Swagger (la forma más fácil, visual)

En el navegador, abre:
```
http://127.0.0.1:8000/docs
```
Verás los tres endpoints documentados con sus ejemplos.

### Probar SALES desde Swagger

1. Haz clic en **POST /sales** para desplegarlo.
2. Botón **"Try it out"** (arriba a la derecha del bloque).
3. En el recuadro del cuerpo verás un ejemplo pequeño (2 filas). Para un resultado
   **realista**, reemplázalo por el contenido de
   `examples/api/ventas_request.json` (ábrelo, selecciona todo, copia y pega).
4. Botón azul **"Execute"**.
5. Abajo, en **"Server response"**, deberías ver **Code 200** y un cuerpo con
   `field: "sales"`, `model: "regresion_v3"` y la lista `forecast`.

Repite lo mismo con **POST /purchases** (pega `compras_request.json`) y **POST /inventory**
(pega `almacen_request.json`).

> El ejemplo pequeño que trae Swagger por defecto **también funciona** (devuelve 200),
> pero con solo 2 días de historia el pronóstico es pobre. Los archivos de
> `examples/api/` traen 70 días para que el resultado tenga sentido.

## 5. Alternativa sin copiar/pegar (PowerShell)

Con el servidor corriendo, abre **otra** terminal (la primera está ocupada) y:

```powershell
cd "C:\Users\lucia\OneDrive\Documents\sistema_predicion_comercializacion"

# SALES
Invoke-RestMethod -Uri http://127.0.0.1:8000/sales -Method Post `
  -ContentType "application/json" -InFile examples\api\ventas_request.json |
  ConvertTo-Json -Depth 6

# PURCHASES
Invoke-RestMethod -Uri http://127.0.0.1:8000/purchases -Method Post `
  -ContentType "application/json" -InFile examples\api\compras_request.json |
  ConvertTo-Json -Depth 6

# INVENTORY
Invoke-RestMethod -Uri http://127.0.0.1:8000/inventory -Method Post `
  -ContentType "application/json" -InFile examples\api\almacen_request.json |
  ConvertTo-Json -Depth 6
```

## 6. Ver que los errores se manejan bien

Envía algo inválido a propósito (en Swagger o por PowerShell):
```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8000/sales -Method Post `
  -ContentType "application/json" -Body '{"horizon":0,"history":[]}'
```
Debe responder **422** con un cuerpo claro: `{"error":{"type":"validation", ...}}`,
no un error feo del servidor.

## 7. Detener el servidor

En la terminal donde corre uvicorn: **Ctrl + C**.

## 8. Correr los tests automáticos (opcional)

```powershell
venv\Scripts\python -m pytest tests/api -q
```
Entrena modelos diminutos sobre datos sintéticos y prueba los tres endpoints (casos
válidos e inválidos), **sin datos crudos ni GPU**. Deben pasar todos.

---

## Cómo leer las respuestas

**SALES** → lista `forecast`, una fila por `(date, store_id, product_id)`:
- `forecast_demand`: unidades esperadas ese día.
- `model`: versión del artefacto usado (p. ej. `regresion_v3`).

**PURCHASES** → lista `recommendation`, por producto:
- `expected_demand_horizon`: demanda total esperada en lead time + cobertura.
- `reorder_point`: nivel de stock que dispara una nueva orden.
- `replenishment_quantity`: unidades sugeridas a pedir.

**INVENTORY** → lista `alerts`, por producto:
- `demand_class` (high/low) y `high_demand_probability`.
- `stockout_risk`: `true` si el stock actual no cubre la demanda esperada.
- `recommended_stock` / `safety_stock`: stock objetivo y colchón.
- `store_segment`: segmento del clustering (perfil de la tienda).
