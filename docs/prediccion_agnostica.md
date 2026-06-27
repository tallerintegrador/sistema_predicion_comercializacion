# Predicción agnóstica auto-entrenada (`/auto/*`)

Guía del contrato **agnóstico al rubro** (ADR-0023). A diferencia de `/sales`·`/inventory`·
`/purchases` —que exigen el esquema retail fijo (`store_id`, `product_id`, `units_sold`...)—
los endpoints `/auto/*` dejan que el cliente **declare su propio esquema** y traiga **columnas
arbitrarias** de su sector. El sistema entrena el **algoritmo ganador** sobre esa data en la
misma llamada y predice/mejora.

## El bloque `schema`

```jsonc
{
  "schema": {
    "target": "unidades_vendidas",          // columna a predecir (numérica)
    "date": "fecha",                         // índice temporal (ISO). Sin él → tabular sin rezagos
    "series_keys": ["almacen", "sku"],       // identifican cada serie (generaliza tienda×producto)
    "features": [
      {"name": "precio",            "type": "numeric",     "known_future": true},   // elasticidad: precio planificado
      {"name": "en_promo",          "type": "numeric",     "known_future": true},   // promo planificada → valor del día + rezagos/intensidad
      {"name": "descuento_pct",     "type": "numeric",     "known_future": true},   // profundidad del descuento
      {"name": "es_feriado",        "type": "numeric",     "known_future": true},   // feriado/evento (0/1)
      {"name": "vispera_feriado",   "type": "numeric",     "known_future": true},   // acaparamiento el día previo al feriado
      {"name": "campaña_mkt",       "type": "numeric",     "known_future": true},   // inversión de marketing planificada
      {"name": "temperatura",       "type": "numeric",     "known_future": true},   // driver externo conocido (pronóstico)
      {"name": "clima",             "type": "categorical", "known_future": true},   // driver externo (hay pronóstico)
      {"name": "evento_cercano",    "type": "categorical", "known_future": true},   // feria/partido/concierto junto al local
      {"name": "categoria",         "type": "categorical", "known_future": true},   // segmento de producto
      {"name": "segmento_almacen",  "type": "categorical", "known_future": true},   // urbano/residencial/turístico
      {"name": "proveedor",         "type": "categorical", "known_future": true},   // origen del SKU
      {"name": "trafico_tienda",    "type": "numeric",     "known_future": false},  // afluencia: solo a posteriori → solo rezagos (anti-fuga)
      {"name": "transacciones",     "type": "numeric",     "known_future": false},  // tickets del día → solo rezagos
      {"name": "competidor_promo",  "type": "numeric",     "known_future": false},  // promo del rival → solo rezagos
      {"name": "precio_competidor", "type": "numeric",     "known_future": false},  // precio del rival → solo rezagos
      {"name": "quiebre_stock_prev","type": "numeric",     "known_future": false}   // quiebre histórico → solo rezagos
    ]
  },
  "rows": [ { "fecha": "...", "almacen": "lima_norte", "sku": "ARROZ-5KG", "unidades_vendidas": 52.0, "precio": 24.9, "en_promo": 0, "descuento_pct": 0, "es_feriado": 0, "vispera_feriado": 0, "campaña_mkt": 0, "temperatura": 21.4, "clima": "soleado", "evento_cercano": "ninguno", "categoria": "abarrotes", "segmento_almacen": "urbano", "proveedor": "Molinos del Norte", "trafico_tienda": 286, "transacciones": 178, "competidor_promo": 0, "precio_competidor": 25.3, "quiebre_stock_prev": 0 } ]
}
```

> **`future` (opcional, solo `/auto/sales`)** — junto a `rows` puedes enviar `future: [...]`
> con las features **conocidas a futuro** ya fijadas para cada (serie, fecha) del horizonte
> (promo/precio/feriado/campaña/clima planificados). El pronóstico las usa tal cual; sin
> `future`, esas columnas se asumen en 0 (p. ej. «sin promo»), lo que sesga el resultado si
> en realidad sí habrá promo. El ejemplo `auto_sales_request.json` trae `future` poblado.

- **`known_future: true`** — el valor del período a pronosticar se conoce de antemano
  (calendario, promoción o precio planificados): el modelo lo usa directamente.
- **`known_future: false`** — solo se conoce a posteriori (tráfico, reservas, transacciones):
  el modelo usa **únicamente sus rezagos**, nunca el valor del período (evita la fuga).
- Las **claves de serie** y las **categóricas** entran como features categóricas.
- El **objetivo del período actual nunca es feature** (solo sus rezagos/ventanas pasadas).

## Campos recomendados para mejorar la predicción

Mientras más señal declares, mejor predice. Aporta los que apliquen a tu negocio:

| Campo | Tipo | `known_future` | Por qué ayuda |
|---|---|---|---|
| Promoción / descuento | numeric | `true` | Empuja la demanda; el plan de promo del horizonte se conoce |
| Precio | numeric | `true` | Elasticidad precio-demanda |
| Feriado / evento (0/1) | numeric | `true` | Picos/valles de calendario |
| Clima / temperatura | numeric/categ. | `true` | Driver externo (hay pronóstico del clima) |
| Canal / turno / región | categorical | `true` | Segmenta el comportamiento |
| Tráfico / reservas / transacciones | numeric | `false` | Correlacionan con ventas pero **no se conocen a futuro** → solo rezagos |

## Señal que el modelo deriva solo (no la mandas)

- **Del objetivo, por serie:** rezagos (1,7,14,21,28), medias/desv./min-máx móviles, media exponencial, recencia de venta (`días desde la última venta`), intermitencia (fracción de días con venta, racha de ceros).
- **De la fecha:** día/mes/día-semana, fin de mes, quincena/payday, semana del año, codificación cíclica y **proximidad** (días a fin de mes, distancia a la quincena).
- **De cada feature `known_future`:** además del valor del día, sus **rezagos e intensidad reciente** (p. ej. "cuántos días lleva en promo", "precio de la semana pasada").

## Endpoints

| Endpoint | Qué hace | Salida |
|---|---|---|
| `POST /auto/sales` | Entrena el ganador (regresión) y pronostica `horizon` períodos (`granularity` day/week/month). | `forecast` por (período, serie) + `training` |
| `POST /auto/inventory` | Deriva `demanda_alta = target > P{q}` de la propia serie, entrena el clasificador y evalúa stock. | `alerts` por serie (clase, probabilidad, riesgo, stock recomendado/seguridad, segmento) + `training` |
| `POST /auto/purchases` | Entrena el ganador, pronostica y deriva la reposición por serie. | `recommendation` por serie (demanda esperada, punto de reorden, cantidad) + `training` |

`inventory`/`purchases` añaden `items[]`: las **claves de serie** + `current_stock` y, según
el dominio, `lead_time_days` / `target_coverage_days`.

## El bloque `training` (respuesta)

Todo `/auto/*` devuelve un resumen **honesto** del modelo entrenado al vuelo:

```jsonc
"training": {
  "winner_algorithm": "Ensemble(LightGBM+XGBoost)",  // el ganador elegido en validación
  "trained_rows": 210,                                // filas tras descartar el calentamiento
  "honest_metrics": {"WAPE": 4.2, "MAE": 4.7},        // ventana de PRUEBA temporal (pronóstico recursivo)
  "candidates": {"LightGBM": 5.1, "Ridge": 5.4},      // MAE de validación por candidato (regresión)
  "reused_cached_model": false,                       // ¿se reusó un modelo ya entrenado?
  "schema_signature": "a1b2c3d4e5f6a7b8"              // firma del esquema (clave de caché)
}
```

## Canal Excel (plantilla a medida)

Además del JSON, cada dominio expone plantilla y carga **Excel a la medida del esquema**:

| Endpoint | Qué hace |
|---|---|
| `POST /auto/{domain}/template` | Genera un `.xlsx` con las **columnas exactas de tu esquema** (objetivo, fecha, series, features) + hoja de instrucciones; inventory/purchases añaden una hoja `items`. |
| `POST /auto/{domain}/excel` | Sube el `.xlsx` (hoja `datos` [+ `items`]); el esquema y la config (`horizon`/`granularity`/`items`) viajan como campos de formulario. Entrena y predice igual que el JSON. |

En la pantalla **«Predicción a tu medida»**: declara tu esquema, pulsa **«Descargar
plantilla Excel»**, llénala y súbela con **«Cargar Excel»**. Las columnas de la plantilla
son las de tu esquema — no hay columnas fijas.

## Auto-aprendizaje (caché)

El modelo se cachea por **(cliente, esquema, datos)**. Si vuelve la **misma** data con el
mismo esquema, se reusa (`reused_cached_model: true`). Si el cliente aporta **datos nuevos**,
la firma cambia y el modelo **se reentrena solo** — el sistema aprende cuando hay datos
nuevos, sin un paso manual.

## Límites

- El pronóstico requiere `date` + `series_keys`. Sin fecha, el modo es tabular (sin horizonte).
- La primera llamada con data nueva **entrena el zoo** (más pesado que servir un congelado);
  las siguientes con la misma data reusan la caché.
- Con poca historia por serie, la métrica honesta de prueba será más pobre (cold-start); se
  reporta sin maquillar.

## Ejemplos

Listos para `curl` en [`examples/api/`](../examples/api/):
`auto_sales_request.json`, `auto_inventory_request.json`, `auto_purchases_request.json`,
reproducibles con [`generar_auto_retail.py`](../examples/api/generar_auto_retail.py) (semilla 42).
Rubro de demostración: cadena minorista **multi-país** (Perú, Bolivia, España, México) —
8 almacenes × 5 SKUs = **40 series**, 150 días, **40 features** agrupadas en cuatro familias,
todas cableadas con correlación real a la demanda y leak-safe:

- **Comerciales / calendario** (conocidas a futuro): `precio`, `en_promo`, `descuento_pct`,
  `es_feriado`, `vispera_feriado`, `campaña_mkt`, `temperatura`, `clima`, `evento_cercano`,
  `categoria`, `segmento_almacen`, `proveedor`.
- **Macro / país** (conocidas a futuro): `pais`, `moneda`, `tipo_cambio_usd`, `festividad_local`,
  `temporada`, `dia_pago_local`, `inicio_clases` — estacionalidad por **hemisferio** (verano
  dic-feb en el sur, jun-ago en el norte), feriados y día de pago locales.
- **Atributos de producto** (conocidos a futuro): `perecedero`, `vida_util_dias`, `marca`,
  `unidad_medida`, `peso_kg`.
- **Inventario / almacén** (solo pasado, de una simulación de stock por serie): `ventas_online`,
  `devoluciones`, `recepciones`, `stock_inicial_dia`, `dias_cobertura`, `rotacion_inventario`,
  `pedidos_pendientes`, `lead_time_real` — más tienda/competencia (`trafico_tienda`,
  `transacciones`, `competidor_promo`, `precio_competidor`, `quiebre_stock_prev`) y logística
  (`costo_flete`, `precio_combustible`, `confiabilidad_proveedor`).

El de ventas trae además `future` planificado por serie. Los `items` de inventory/purchases
traen, además de las claves de serie, el `current_stock`, `lead_time_days`/`target_coverage_days`
y datos del proveedor (`moq`, `costo_unitario`).

> **Nota honesta de validación.** Ampliar de 17 a 40 features **no baja el WAPE** (TEST ≈ 16.4 %
> en ambos): la data sintética tiene un piso de ruido irreducible (~13 %) que los rezagos + precio
> + promo + calendario ya casi alcanzan, y varias columnas nuevas son colineales con ellas
> (`pais`↔serie, `temporada`↔mes, `dia_pago_local`↔`g_is_payday`). El valor del cambio es la
> **cobertura agnóstica** (4 países, 40 campos de almacén) verificada **leak-safe y sin degradar**
> la métrica; las solo-pasado de inventario **sí se usan** (la media móvil de `recepciones` queda
> entre las 10 features más importantes). Más columnas mejoran la predicción solo si aportan señal
> no redundante: sobre datos reales con menos ruido, el margen sería mayor.

```bash
curl -s -X POST http://localhost:8000/auto/sales \
  -H "Content-Type: application/json" \
  -d @examples/api/auto_sales_request.json | jq '.training, (.forecast[:3])'
```
