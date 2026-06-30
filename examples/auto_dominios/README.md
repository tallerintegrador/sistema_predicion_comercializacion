# Ejemplos multi-dominio — motor agnóstico `/auto/*`

Cada subcarpeta es un rubro distinto con su **propio esquema**. Mismo motor, cero configuración por rubro (ADR-0023). Cada rubro trae los **3 endpoints** (`sales`, `inventory`, `purchases`) compartiendo `schema` + `rows`. Generado por `examples/api/generar_auto_dominios.py` (semilla 42).

| Dominio | Objetivo | Series | Descripción |
|---|---|---|---|
| [`clinica`](clinica/) | `pacientes_atendidos` | 6 | Atenciones diarias en una clínica: estacionalidad de gripe en invierno, caída en feriados y fines de semana, campañas de salud. |
| [`restaurante`](restaurante/) | `platos_vendidos` | 6 | Platos vendidos por local y carta: elasticidad de precio, promos en racha, clima (sol empuja ceviche), eventos y findes. |
| [`energia`](energia/) | `demanda_kwh` | 3 | Demanda eléctrica por subestación: curva en U con la temperatura (frío/calor suben consumo), día hábil vs feriado. |
| [`ecommerce`](ecommerce/) | `pedidos` | 6 | Pedidos por categoría y canal: descuentos, campañas, envío gratis, día de pago y un pico de evento comercial (cyber). |
| [`movilidad`](movilidad/) | `viajes` | 3 | Viajes por ruta: lluvia y eventos empujan demanda, ocio en findes vs ruta de aeropuerto, sensibilidad al combustible. |
