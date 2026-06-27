# ecommerce — ejemplo agnóstico `/auto/*`

Pedidos por categoría y canal: descuentos, campañas, envío gratis, día de pago y un pico de evento comercial (cyber).

- **Objetivo (`target`)**: `pedidos`
- **Fecha (`date`)**: `fecha`
- **Claves de serie**: `categoria`, `canal` → 6 series
- **Horizonte**: 14 días · **Granularidad**: day
- **Histórico**: 540 filas · **Futuro**: 84 filas
- **Features** (·fut = conocida a futuro, ·pas = solo pasado): `indice_precio`·fut, `descuento_pct`·fut, `campaña`·fut, `envio_gratis`·fut, `es_feriado`·fut, `dia_pago`·fut, `evento_comercial`·fut, `trafico_web_prev`·pas, `devoluciones_prev`·pas

Los tres comparten `schema` + `rows`; cambia solo el endpoint y su bloque extra.

| Endpoint | Archivo | Extra |
|---|---|---|
| `POST /auto/forecast` | `sales_request.json` | `horizon`, `future` |
| `POST /auto/inventory` | `inventory_request.json` | `items` (`current_stock`, `lead_time_days`=3), `high_demand_quantile`=0.75 |
| `POST /auto/purchases` | `purchases_request.json` | `items` (+ `target_coverage_days`=10) |

## Uso

```bash
curl -X POST http://localhost:8000/auto/forecast \
  -H "Content-Type: application/json" \
  -d @examples/auto_dominios/ecommerce/sales_request.json
```

El motor entrena-y-predice en una sola llamada: declara el esquema, manda el histórico en `rows` y (ventas) el plan de drivers en `future`. No sabe que esto es ecommerce; solo ve columnas. En `inventory`/`purchases`, `items` lleva el estado por serie (stock actual derivado de la demanda media del histórico).
