# ADR 0007 — Capa de servicio / API (Fase 3): exposición del contrato por los tres campos

- **Estado:** Aceptado (2026-06-15).
- **Fase:** 3 — API. **Abre** la capa de servicio/API sobre el motor cerrado en Fase 2.
- **Contexto previo:** `docs/plan_maestro_spc.md` (§2 arquitectura, §3 contrato, Fase 3),
  `docs/contrato_datos.md`, cierres de Fase 2 (ADR `0004` regresión, `0005` clasificación,
  `0006` clustering).
- **No toca** el motor de ML (artefactos de Fase 2 intactos): solo los **carga y sirve**.

> **Nota (alineación de nombres, añadida 2026-06-19).** Este ADR es un **registro
> histórico** y se conserva tal cual. Usa los nombres genéricos del contrato en su forma de
> entonces (`historico`, `fecha`, `punto_venta_id`, …). El contrato **canónico vigente está
> en inglés** (v1.0.1): la frontera pública real son `history`, `date`, `store_id`, … Ver
> [`contrato_datos.md`](../contrato_datos.md) y su **sección 9** (mapeo `es → en`). La
> decisión arquitectónica de este ADR no cambia; solo cambiaron los nombres de campo.

## Contexto

El motor de ML quedó entrenado, validado y serializado en Fase 2 (regresión `regresion_v3`,
clasificación `clasificacion_v1`, clustering `clustering_{tiendas,familias}_v1`). La Fase 3
**expone el contrato de datos** (`docs/contrato_datos.md`) por tres campos —VENTAS, COMPRAS,
ALMACÉN— vía una API HTTP, con validación de entrada, manejo de errores y Swagger, **sin
reentrenar** y **respetando la separación de capas**:

```
HTTP / API  ──►  Servicio (negocio)  ──►  Motor de ML (artefactos)
 conoce HTTP       conoce el contrato        carga y predice;
 y el contrato     y las reglas de negocio   NO conoce HTTP
```

## Decisiones

### 1. Estructura: la API y el servicio viven **dentro** del paquete `spc`

- **`src/spc/api/`** (no `api/` en la raíz como dibujaba el plan §5): con layout `src/` y
  `pythonpath=["src"]`, así los tests importan `from spc.api.main import crear_app` sin rutas
  extra y la API es parte instalable del paquete. Submódulos: `main.py` (app factory),
  `dependencies.py`, `errors.py`, `routers/{ventas,compras,almacen}.py`,
  `schemas/{comunes,ventas,compras,almacen}.py`.
- **`src/spc/service/`** (singular, paquete ya existente; no `services/`): `adaptador.py`
  (contrato→motor), `artefactos.py` (carga por versión), `errores.py` (excepción de dominio),
  `ventas_service.py`, `compras_service.py`, `almacen_service.py`.
- **Dependencias hacia adentro:** `api → service → motor`. La capa de servicio **no importa
  `spc.api`** (los routers convierten Pydantic↔dict; el servicio trabaja con estructuras de
  Python y pandas). El motor **no importa nada de la API** (se sostiene la separación).

### 2. La frontera estable es el contrato; el adaptador traduce contrato→motor

El contrato envía el bloque `historico` con **nombres genéricos** (`fecha`, `punto_venta_id`,
`producto_id`, `unidades_vendidas`, `en_promocion?`, `transacciones?`, `evento_activo?`). El
motor consume el **esquema del dataset analítico integrado** (Fase 1/2). `service/adaptador.py`
es la única pieza que conoce ambos lados y traduce:

| Contrato (genérico) | Motor (dataset analítico) |
|---|---|
| `fecha` | `date` |
| `punto_venta_id` | `store_nbr` |
| `producto_id` | `family` |
| `unidades_vendidas` | `sales` |
| `en_promocion` | `onpromotion` |
| `transacciones` | `transactions_filled` (NaN si ausente) |
| `evento_activo` | `holiday_any` (feriados por alcance → 0) |
| — (derivado de `fecha`) | `year, month, day, dayofweek, is_weekend, is_month_end, is_payday` |
| — (no en el contrato) | `dcoilwtico`, `type`, `city`, `state`, `cluster` → **desconocidos** |

**Degradación con elegancia (documentada):** el calendario se deriva de `fecha`; el petróleo y
los metadatos de tienda no están en el contrato (sector-agnóstico) y se rellenan como
desconocidos — bajo el `CategoricalDtype` fijo del artefacto, las categóricas desconocidas caen
a `NaN` (los árboles lo toleran). El pronóstico se sostiene sobre **rezagos + calendario**; la
pérdida de nivel categórico es el *cold-start* esperado de un cliente nuevo. (En pandas 3 esto
emite un `FutureWarning` al castear categóricas desconocidas; es el comportamiento buscado y se
silencia en los tests.) Para ALMACÉN, el adaptador **recalcula `demanda_alta = ventas > P75 de
su familia`** sobre el histórico recibido (lo exige el perfilado).

### 3. Nada de artefacto hard-codeado: glob de versión + objetos que encapsulan el negocio

`service/artefactos.py` resuelve cada familia por **glob de versión** (`regresion_v*.joblib` → la
mayor) y la carga con `cargar_artefacto`. **La API sobrevive a un cambio de artefacto sin tocar
código:** si sale `regresion_v4` o cambian el umbral, la composición del ensemble o el `k`, basta
con dejar el nuevo `.joblib` + `.meta.json` en `models/`.

El **valor de negocio nunca se reconstruye en el código de la API**:

- **Umbral de clasificación (≈0.3185):** vive **dentro** de `PredictorClasificacion.umbral`;
  `predecir()` ya lo aplica. Se lee del `meta` solo para reportarlo en `metadatos.umbral_probabilidad`.
- **Composición/pesos del ensemble:** encapsulados en `ModeloEnsemble`; el servicio solo llama
  `pronosticar_horizonte`.
- **Segmentos/centroides del clustering:** dentro de `PerfiladorClustering`; el servicio llama
  `perfilar`. El segmento de **alto volumen** (para el nivel de servicio de ALMACÉN) se deduce
  leyendo `centroides_unidades` del `meta` (máximo `venta_media`), no por una constante.
- **`modelo` de la respuesta de VENTAS** = `meta["version"]` (p. ej. `regresion_v3`); el ejemplo
  del contrato (`regresion_v1`) es ilustrativo.

### 4. Esquemas Pydantic estrictos que implementan el contrato

- Un módulo por dominio; bloque `historico` y `ErrorResponse` compartidos en `comunes.py`.
- **Validación estricta** (`extra="forbid"`): un campo mal escrito (p. ej. `horizont`) se
  rechaza en vez de ignorarse. Rangos del contrato: `unidades_vendidas ≥ 0`, `en_promocion ≥ 0`,
  `horizonte > 0` (≤ 365), `probabilidad ∈ [0,1]`, listas con ≥ 1 elemento.
- `punto_venta_id`/`producto_id` aceptan `str`/`int` (contrato) y se normalizan a `str`.
- **`intervalo_80`** queda como campo **opcional documentado** pero **no se emite** (los
  intervalos de predicción se difirieron en Fase 2; el modelo no los produce). Los routers usan
  `response_model_exclude_none=True`.

### 5. Lógica de negocio por campo

- **VENTAS** (regresión): el adaptador añade el **esqueleto futuro** (filas del horizonte con
  calendario conocido, promoción planificada = 0, `sales` = NaN) y llama al **pronóstico
  recursivo** `pronosticar_horizonte`. `granularidad` `semana`/`mes` **agrega (suma)** el
  pronóstico diario; la `fecha` de salida es el inicio del período.
- **COMPRAS** (sin modelo): reutiliza el pronóstico diario de VENTAS sobre
  `lead_time_dias + dias_cobertura_objetivo` y aplica aritmética de inventario. **Política
  elegida con la validadora: días de cobertura.** `stock_seguridad = 30 % × demanda(lead_time)`
  (constante de política, no de artefacto); `punto_de_reorden = demanda(lead_time) +
  stock_seguridad`; `cantidad_a_reponer = max(0, demanda(lead_time+cobertura) + stock_seguridad −
  stock_actual)`.
- **ALMACÉN** (clasificación + perfilado): clase y probabilidad de la **última observación** de
  cada serie (umbral del artefacto); `segmento_tienda` del clustering de tiendas; stock dimensionado
  con un **proxy de demanda reciente** del histórico (media/desviación diarias). El **nivel de
  servicio** (z) lo **modula el segmento** (el de alto volumen recibe ~95 % vs ~90 %), leyendo el
  segmento grande del `meta`. **No usa la regresión** (el contrato define ALMACÉN como
  clasificación + perfilado).

### 6. Modelo de errores: cuerpo uniforme, nunca un 500 sin manejar

Toda salida de error usa `ErrorResponse` = `{error: {tipo, mensaje, detalles[]}}`:

| Caso | HTTP | Tipo |
|---|---|---|
| Validación de entrada (campo faltante, tipo/rango inválido) | **422** | `validacion` (con `detalles` por campo) |
| Regla de negocio (`SolicitudInvalida`: producto sin histórico, etc.) | **400** | `solicitud_invalida` |
| Motor no cargado (`ServicioNoDisponible`) | **503** | `servicio_no_disponible` |
| Error inesperado | **500** | `error_interno` (sin filtrar detalles; se registra en el log) |

**IDs desconocidos** (tienda/producto nuevos) **no son error**: degradan (categórica → NaN;
clustering asigna por perfil). El error de negocio se da cuando el producto **no está en el
histórico** (no se puede pronosticar/evaluar sin historia).

### 7. CORS, lifespan y Swagger

- Artefactos cargados **una sola vez** en el arranque (lifespan) y guardados en `app.state`; los
  routers los reciben por `Depends(obtener_registro)` (no cargan por petición).
- **CORS** configurable por `SPC_CORS_ORIGINS` (coma-separado; `*` por defecto).
- **Swagger/OpenAPI** documenta los tres contratos con **ejemplos** (de la sección 3) en cada
  request/response, `tags` por dominio y descripción del servicio. `uvicorn spc.api.main:app`.

### 8. Estrategia de tests: artefactos diminutos, sin GPU ni `data/raw`

- `tests/api/conftest.py` **entrena artefactos diminutos** con las funciones reales del motor
  sobre los fixtures sintéticos existentes, los serializa en un `models/` temporal y construye la
  app inyectando ese registro → ejercita la **ruta real de carga** (`cargar_artefacto`) y
  predicción **en CPU, sin datos crudos**.
- Los builders sintéticos se extrajeron a `tests/sintetico.py` (módulo de nombre único,
  reutilizable desde varios conftests sin colisión; `pythonpath=["src","tests"]`).
- Cobertura por endpoint: **caso(s) válido(s)** (forma y campos == ejemplos del contrato) y
  **casos inválidos** (campo faltante, tipo/rango inválido, producto sin histórico) → siempre
  error controlado, **nunca un 500**. Más Swagger (`/openapi.json` con los tres paths + ejemplos)
  y salud.

## Criterio de "hecho" verificado

- [x] FastAPI levanta y **Swagger documenta los tres contratos** (VENTAS, COMPRAS, ALMACÉN) con ejemplos.
- [x] **CORS** configurado (configurable por entorno).
- [x] Tests en verde, cubriendo **válidos e inválidos**; entradas mal formadas → **error controlado** (422/400), no 500.
- [x] Las respuestas **coinciden en forma y campos** con los ejemplos de la sección 3 del contrato.
- [x] **Sin valores de artefacto hard-codeados:** umbral, composición del ensemble y segmentos se
      leen de los objetos/`meta`; versión de artefacto resuelta por glob.
- [x] El **motor de ML no importa nada de la API**; el servicio no importa la API.
- [x] Todo corre **sin `data/raw/` y sin GPU**.

## Mejoras diferidas (documentadas, no implementadas)

- **Intervalos de predicción** (`intervalo_80`): heredado de Fase 2; el campo está en el esquema
  pero no se emite.
- **Política de reposición por nivel de servicio** (z-score sobre la variabilidad) en COMPRAS;
  hoy solo días de cobertura.
- **Integración con datos reales** de extremo a extremo y demo (Fase 4).
- **Calibración de probabilidades** y **perfil as-of-time** (ya diferidos en Fase 2).

## Reproducibilidad

`uvicorn spc.api.main:app --reload` levanta el servicio (carga la última versión de cada
artefacto desde `models/`). `pytest tests/api` corre los tests de la API (entrena artefactos
diminutos en CPU; sin `data/raw` ni GPU). Mismos artefactos + mismo código → mismas respuestas.
