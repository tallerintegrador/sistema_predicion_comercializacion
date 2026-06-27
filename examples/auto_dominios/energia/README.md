# energia — ejemplo agnóstico `/auto/*`

Demanda eléctrica por subestación: curva en U con la temperatura (frío/calor suben consumo), día hábil vs feriado.

- **Objetivo (`target`)**: `demanda_kwh`
- **Fecha (`date`)**: `fecha`
- **Claves de serie**: `subestacion` → 3 series
- **Horizonte**: 14 días · **Granularidad**: day
- **Histórico**: 270 filas · **Futuro**: 42 filas
- **Features** (·fut = conocida a futuro, ·pas = solo pasado): `temperatura`·fut, `dia_habil`·fut, `es_feriado`·fut, `festividad_local`·fut, `dia_semana`·fut, `perdidas_tecnicas_prev`·pas

Los tres comparten `schema` + `rows`; cambia solo el endpoint y su bloque extra.

| Endpoint | Archivo | Extra |
|---|---|---|
| `POST /auto/forecast` | `sales_request.json` | `horizon`, `future` |
| `POST /auto/inventory` | `inventory_request.json` | `items` (`current_stock`, `lead_time_days`=1), `high_demand_quantile`=0.8 |
| `POST /auto/purchases` | `purchases_request.json` | `items` (+ `target_coverage_days`=2) |

## Uso

```bash
curl -X POST http://localhost:8000/auto/forecast \
  -H "Content-Type: application/json" \
  -d @examples/auto_dominios/energia/sales_request.json
```

El motor entrena-y-predice en una sola llamada: declara el esquema, manda el histórico en `rows` y (ventas) el plan de drivers en `future`. No sabe que esto es energia; solo ve columnas. En `inventory`/`purchases`, `items` lleva el estado por serie (stock actual derivado de la demanda media del histórico).
