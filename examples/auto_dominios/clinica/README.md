# clinica — ejemplo agnóstico `/auto/*`

Atenciones diarias en una clínica: estacionalidad de gripe en invierno, caída en feriados y fines de semana, campañas de salud.

- **Objetivo (`target`)**: `pacientes_atendidos`
- **Fecha (`date`)**: `fecha`
- **Claves de serie**: `sede`, `especialidad` → 6 series
- **Horizonte**: 14 días · **Granularidad**: day
- **Histórico**: 540 filas · **Futuro**: 84 filas
- **Features** (·fut = conocida a futuro, ·pas = solo pasado): `dia_semana`·fut, `es_feriado`·fut, `temporada_gripe`·fut, `campaña_salud`·fut, `temperatura`·fut, `ausentismo_prev`·pas, `derivaciones_prev`·pas

Los tres comparten `schema` + `rows`; cambia solo el endpoint y su bloque extra.

| Endpoint | Archivo | Extra |
|---|---|---|
| `POST /auto/forecast` | `sales_request.json` | `horizon`, `future` |
| `POST /auto/inventory` | `inventory_request.json` | `items` (`current_stock`, `lead_time_days`=2), `high_demand_quantile`=0.75 |
| `POST /auto/purchases` | `purchases_request.json` | `items` (+ `target_coverage_days`=7) |

## Uso

```bash
curl -X POST http://localhost:8000/auto/forecast \
  -H "Content-Type: application/json" \
  -d @examples/auto_dominios/clinica/sales_request.json
```

El motor entrena-y-predice en una sola llamada: declara el esquema, manda el histórico en `rows` y (ventas) el plan de drivers en `future`. No sabe que esto es clinica; solo ve columnas. En `inventory`/`purchases`, `items` lleva el estado por serie (stock actual derivado de la demanda media del histórico).
