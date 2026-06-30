# movilidad — ejemplo agnóstico `/auto/*`

Viajes por ruta: lluvia y eventos empujan demanda, ocio en findes vs ruta de aeropuerto, sensibilidad al combustible.

- **Objetivo (`target`)**: `viajes`
- **Fecha (`date`)**: `fecha`
- **Claves de serie**: `ruta` → 3 series
- **Horizonte**: 14 días · **Granularidad**: day
- **Histórico**: 270 filas · **Futuro**: 42 filas
- **Features** (·fut = conocida a futuro, ·pas = solo pasado): `clima`·fut, `es_feriado`·fut, `finde`·fut, `evento_cercano`·fut, `precio_combustible`·fut, `tarifa_base`·fut, `cancelaciones_prev`·pas, `tiempo_espera_prev`·pas

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
  -d @examples/auto_dominios/movilidad/sales_request.json
```

El motor entrena-y-predice en una sola llamada: declara el esquema, manda el histórico en `rows` y (ventas) el plan de drivers en `future`. No sabe que esto es movilidad; solo ve columnas. En `inventory`/`purchases`, `items` lleva el estado por serie (stock actual derivado de la demanda media del histórico).
