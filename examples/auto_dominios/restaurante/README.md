# restaurante — ejemplo agnóstico `/auto/*`

Platos vendidos por local y carta: elasticidad de precio, promos en racha, clima (sol empuja ceviche), eventos y findes.

- **Objetivo (`target`)**: `platos_vendidos`
- **Fecha (`date`)**: `fecha`
- **Claves de serie**: `local`, `plato` → 6 series
- **Horizonte**: 14 días · **Granularidad**: day
- **Histórico**: 540 filas · **Futuro**: 84 filas
- **Features** (·fut = conocida a futuro, ·pas = solo pasado): `precio`·fut, `en_promo`·fut, `descuento_pct`·fut, `finde`·fut, `es_feriado`·fut, `clima`·fut, `evento_cercano`·fut, `temperatura`·fut, `reservas_prev`·pas, `delivery_prev`·pas

Los tres comparten `schema` + `rows`; cambia solo el endpoint y su bloque extra.

| Endpoint | Archivo | Extra |
|---|---|---|
| `POST /auto/forecast` | `sales_request.json` | `horizon`, `future` |
| `POST /auto/inventory` | `inventory_request.json` | `items` (`current_stock`, `lead_time_days`=1), `high_demand_quantile`=0.75 |
| `POST /auto/purchases` | `purchases_request.json` | `items` (+ `target_coverage_days`=3) |

## Uso

```bash
curl -X POST http://localhost:8000/auto/forecast \
  -H "Content-Type: application/json" \
  -d @examples/auto_dominios/restaurante/sales_request.json
```

El motor entrena-y-predice en una sola llamada: declara el esquema, manda el histórico en `rows` y (ventas) el plan de drivers en `future`. No sabe que esto es restaurante; solo ve columnas. En `inventory`/`purchases`, `items` lleva el estado por serie (stock actual derivado de la demanda media del histórico).
