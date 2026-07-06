# Auditoría Técnica — Contraste con el "Ideal del Sistema"

> **Alcance**: motor ML activo (catálogo v3), API de exposición, frontend React.
> **Método**: evidencia empírica del código. Cada hallazgo cita `[ARCHIVO: LÍNEA]`.
> **Fecha**: 2026-07-03 · Rama: `feature/mejoras-modelos-camila`
>
> Nota de arquitectura: el sistema tiene **dos motores**. El **activo** es el catálogo v3
> (`src/spc/catalogo/`), montado en `POST /v3/{modulo}` y consumido por el frontend. El motor
> `/v2` 3×3 (`src/spc/service/motor_3x3.py` + `features/generico.py`) está marcado
> `deprecated=True` [ARCHIVO: src/spc/api/routers/dominios_3x3.py -> LÍNEA: 40] y solo persiste
> para reentrenamiento/persistencia. La auditoría se centra en el motor **activo** salvo aviso.

---

## 1) Gestión de Catálogo y Configuración

**Estado**: [CUMPLE]

**Hallazgo**:
Las 30 consultas se cargan dinámicamente desde `consultas.yaml`. El archivo declara los 3
módulos (ventas/compras/almacén), sus `columnas_todas`, tipos por consulta, `columnas_entrada`,
métricas de selección y umbrales; el parser los convierte en objetos tipados sin lógica
hard-codeada por consulta.

- Carga dinámica del YAML: [ARCHIVO: src/spc/catalogo/config.py -> LÍNEA: 149-154] y
  `cargar_catalogo()` [ARCHIVO: src/spc/catalogo/config.py -> LÍNEA: 207-231].
- Parseo genérico de las 30 consultas (ninguna consulta escrita en código): [ARCHIVO:
  src/spc/catalogo/config.py -> LÍNEA: 157-204].
- Umbrales de calidad leídos del YAML (fuente única): [ARCHIVO: src/spc/catalogo/consultas.yaml
  -> LÍNEA: 918-929] → [ARCHIVO: src/spc/catalogo/config.py -> LÍNEA: 273-293].
- El router expone el catálogo iterando el singleton, sin listas fijas: [ARCHIVO:
  src/spc/api/routers/catalogo_v3.py -> LÍNEA: 58-79].
- El frontend NO hard-codea las consultas: pide el catálogo por API y lo pinta [ARCHIVO:
  frontend/src/components/v3/VistaV3Modulo.tsx -> LÍNEA: 60-76, 162-171]. La calidad la decide
  el backend [ARCHIVO: frontend/src/components/v3/ReporteCard.tsx -> LÍNEA: 60-61].

**Observaciones menores (no incumplen el ideal)**:
- El endpoint `/v3/{modulo}/demo` genera filas de ejemplo **hard-codeadas** en el router
  (nombres de categoría, rangos) [ARCHIVO: src/spc/api/routers/catalogo_v3.py -> LÍNEA:
  430-479]. Son datos de demostración, no configuración del catálogo, pero duplican el
  esquema que ya vive en `spc.synthetic`.
- El frontend mantiene un mapa `humaniza()` de nombre-columna → etiqueta legible [ARCHIVO:
  frontend/src/components/v3/renderidores.tsx -> LÍNEA: 36-66]. Es presentación, pero es
  conocimiento de dominio duplicado fuera del YAML.

---

## 2) Rigor del Pipeline de ML por Tipo de Modelo

**Estado**: [CUMPLE]

**Hallazgo**:
- **Split temporal estricto** 70/15/15 por fecha, orden cronológico estable, sin barajar:
  [ARCHIVO: src/spc/catalogo/motor_catalogo.py -> LÍNEA: 349-357] y `_preparar_temporal`
  [ARCHIVO: src/spc/catalogo/motor_catalogo.py -> LÍNEA: 360-371]. El `StandardScaler` se
  ajusta **solo en TRAIN** y transforma VALID/TEST [ARCHIVO: src/spc/catalogo/motor_catalogo.py
  -> LÍNEA: 513-516].
- **Selección en VALID, reporte en TEST**: en regresión el ganador se elige por WAPE de VALID
  y luego se reporta el WAPE de TEST (evaluado una sola vez) [ARCHIVO:
  src/spc/catalogo/motor_catalogo.py -> LÍNEA: 528-548]. Igual patrón en clasificación binaria
  [ARCHIVO: src/spc/catalogo/motor_catalogo.py -> LÍNEA: 689-713] y multiclase [ARCHIVO:
  src/spc/catalogo/motor_catalogo.py -> LÍNEA: 613-636]. Se añade un `baseline` (Dummy) como
  referencia honesta [ARCHIVO: src/spc/catalogo/motor_catalogo.py -> LÍNEA: 462-478, 481-486].
- **Métrica por tipo de problema**:
  - Regresión → **WAPE** [ARCHIVO: src/spc/catalogo/motor_catalogo.py -> LÍNEA: 429-433].
  - Clasificación binaria → **PR-AUC** (average_precision, corrige sobreestimación de
    auc(recall,precision)) [ARCHIVO: src/spc/catalogo/motor_catalogo.py -> LÍNEA: 436-446].
  - Clasificación multiclase → **F1 macro** [ARCHIVO: src/spc/catalogo/motor_catalogo.py ->
    LÍNEA: 449-450].
  - Clustering → **Silhouette** (KMeans vs. Aglomerativo compiten) [ARCHIVO:
    src/spc/catalogo/motor_catalogo.py -> LÍNEA: 861]. Excepción documentada: ALM-K1 es una
    **regla de Pareto ABC**, no clustering, y reporta `value_share_a` [ARCHIVO:
    src/spc/catalogo/motor_catalogo.py -> LÍNEA: 959-1010].

**Observación**: los campos `lags_objetivo` / `ventanas_media` declarados para las consultas de
COMPRAS [ARCHIVO: src/spc/catalogo/consultas.yaml -> LÍNEA: 349-350] **no los usa** el motor v3:
`construir_features` solo aplica one-hot sobre `columnas_entrada` [ARCHIVO:
src/spc/catalogo/motor_catalogo.py -> LÍNEA: 328-346]. Es **configuración muerta** en el motor
activo (sí la usaría el motor `/v2` deprecado). Coherente con el punto 3, pero conviene
eliminarla para no confundir.

---

## 3) Consistencia Conceptual (Predicción vs. Pronóstico)

**Estado**: [CUMPLE]

**Hallazgo**:
- Los modelos de **regresión predicen sobre factores**, no sobre el tiempo: las features son
  únicamente `columnas_entrada` con one-hot de categóricas; **no** se generan rezagos ni
  variables temporales del objetivo [ARCHIVO: src/spc/catalogo/motor_catalogo.py -> LÍNEA:
  328-346]. La fecha se usa solo para **ordenar y partir** [ARCHIVO:
  src/spc/catalogo/motor_catalogo.py -> LÍNEA: 360-371].
- El **componente temporal vive únicamente en la sección Tendencia**: `calcular_tendencia`
  (tendencia lineal + estacionalidad semanal) es la ÚNICA salida con eje de tiempo [ARCHIVO:
  src/spc/catalogo/motor_catalogo.py -> LÍNEA: 1013-1103], y es la única que proyecta a futuro
  [ARCHIVO: src/spc/catalogo/motor_catalogo.py -> LÍNEA: 1025-1058].
- El frontend refuerza la separación: "nube de puntos" real-vs-predicho para regresión
  [ARCHIVO: frontend/src/components/v3/renderidores.tsx -> LÍNEA: 153-172] y un bloque de
  tendencia aparte [ARCHIVO: frontend/src/components/v3/VistaV3Modulo.tsx -> LÍNEA: 316-322].

---

## 4) Mitigación de Fuga de Información (Data Leakage)

**Estado**: [CUMPLE] (con 1 riesgo bajo a revisar)

**Hallazgo**:
El diseño es **anti-fuga por lista blanca**: solo se convierten en features las
`columnas_entrada` explícitamente declaradas, y encima se excluyen las columnas calculadas del
módulo (`ingreso`, `costo_total`, `dias_de_cobertura`) y el propio objetivo [ARCHIVO:
src/spc/catalogo/motor_catalogo.py -> LÍNEA: 332-335]; declaradas en [ARCHIVO:
src/spc/catalogo/consultas.yaml -> LÍNEA: 30-31, 321-322, 632-633].

- Las etiquetas de clasificación por percentil se fijan **solo en TRAIN** y se mapean al resto
  [ARCHIVO: src/spc/catalogo/motor_catalogo.py -> LÍNEA: 393-408]. Las columnas que definen la
  etiqueta se excluyen de features por diseño del YAML (p. ej. anti-tautología ALM-C1/C2/C3:
  `stock_actual`/`demanda`/`tiempo_reposicion` fuera de features) [ARCHIVO:
  src/spc/catalogo/consultas.yaml -> LÍNEA: 754-772, 788-805, 821-838].
- Identidades aritméticas explícitamente excluidas: VEN-R2 (`ingreso`), COM-R3 (`costo_total`),
  ALM-R2 (`dias_de_cobertura`) [ARCHIVO: src/spc/catalogo/consultas.yaml -> LÍNEA: 84-88,
  402-408, 685-693].

**[RIESGO FUGA] (bajo) — ALM-R2 `dias_de_cobertura`**:
La consulta excluye `stock_actual` y `demanda_diaria_promedio` (correcto, evita la identidad),
pero **incluye `rotacion` como feature** [ARCHIVO: src/spc/catalogo/consultas.yaml -> LÍNEA:
672-676]. En los datos sintéticos `rotacion ≈ demanda_media·365 / stock_medio` [ARCHIVO:
src/spc/synthetic/almacen.py -> LÍNEA: 87-89] y `dias_de_cobertura = stock / demanda_prom`
[ARCHIVO: src/spc/synthetic/almacen.py -> LÍNEA: 86]: ambas dependen inversamente del stock, por
lo que hay **correlación estructural** (no identidad exacta, pero near-leak). Además hay
**inconsistencia interna**: `rotacion` está en `columnas_entrada` pero NO en
`columnas_conocidas_futuro` [ARCHIVO: src/spc/catalogo/consultas.yaml -> LÍNEA: 677-680],
contradiciendo el criterio "solo factores conocidos a futuro".

**Nota**: `rotacion` también es feature en ALM-C1/C2/C3 [ARCHIVO: src/spc/catalogo/consultas.yaml
-> LÍNEA: 757-764]; ahí es per-SKU casi constante y no define la etiqueta, por lo que **no** hay
fuga (a lo sumo el modelo aprende un baseline por producto). No se marca riesgo.

**Verificación empírica sugerida** (no ejecutada en esta auditoría): entrenar ALM-R2 con y sin
`rotacion` y comparar el WAPE de TEST; si cae drásticamente al quitarla, confirma near-leak.

---

## 5) Honestidad del Sistema y Transparencia de Métricas

**Estado**: [CUMPLE]

**Hallazgo**:
Existe lógica **real** de aviso de señal débil y notas honestas, en backend, mostradas al
usuario:
- Aviso "señal débil" por umbral del catálogo (regresión WAPE > aviso; clasificación < aviso)
  [ARCHIVO: src/spc/catalogo/motor_catalogo.py -> LÍNEA: 1144-1151].
- Nota honesta cuando una métrica sale **casi perfecta** (problema fácil, no mejor modelo)
  [ARCHIVO: src/spc/catalogo/motor_catalogo.py -> LÍNEA: 182-196].
- Nota "métrica fácil" cuando el objetivo es casi constante (CV bajo) [ARCHIVO:
  src/spc/catalogo/motor_catalogo.py -> LÍNEA: 247-262].
- Aviso de clasificador **degenerado** (predice una sola clase para todos) [ARCHIVO:
  src/spc/catalogo/motor_catalogo.py -> LÍNEA: 265-283, 1140-1143].
- Frontend: banner ámbar con el `warning`, etiqueta de calidad "buena/limitada", y el WAPE se
  presenta como **"Error promedio (menor = mejor)"**, nunca como "Precisión" [ARCHIVO:
  frontend/src/components/v3/ReporteCard.tsx -> LÍNEA: 37-55, 77-80, 96-99].

**Evaluación crítica de posible inflado**:
- Las clasificaciones de ALMACÉN por **regla determinística** (ALM-C1/C2/C3) pueden dar métricas
  altas de forma legítima; el sistema lo advierte con nota honesta [ARCHIVO:
  src/spc/catalogo/motor_catalogo.py -> LÍNEA: 156-179] y excluye de features las columnas de la
  regla, evitando fuga trivial [ARCHIVO: src/spc/catalogo/consultas.yaml -> LÍNEA: 754-756]. Es
  transparente, no maquillado.
- El único punto donde una métrica **podría estar mildemente inflada por near-leak** es
  **ALM-R2** (ver punto 4): su WAPE de TEST podría verse mejor de lo real por incluir `rotacion`.

---

## 6) Arquitectura Frontend, UX y Gráficos

**Estado**: [CUMPLE]

**Hallazgo**:
- **Separación vista de negocio ↔ detalle técnico**: todo tecnicismo (modelo ganador, métrica
  cruda, tabla de candidatos, fecha de entrenamiento) vive en un `<details>` colapsado "Ver
  detalle técnico" [ARCHIVO: frontend/src/components/ui/TechnicalDetails.tsx -> LÍNEA: 1-23] y
  [ARCHIVO: frontend/src/components/v3/ReporteCard.tsx -> LÍNEA: 85-133]. La cara principal usa
  lenguaje de negocio (Predicción / Alerta / Segmento) [ARCHIVO:
  frontend/src/components/v3/ReporteCard.tsx -> LÍNEA: 32-34].
- **Resultados accionables**: número principal (suma/promedio según magnitud del catálogo)
  [ARCHIVO: frontend/src/components/v3/renderidores.tsx -> LÍNEA: 124-146]; filtro "solo
  alertas" en clasificación [ARCHIVO: frontend/src/components/v3/renderidores.tsx -> LÍNEA:
  255-258]; tarjetas por segmento en clustering [ARCHIVO:
  frontend/src/components/v3/renderidores.tsx -> LÍNEA: 370-421].
- **Renderizado coherente con el negocio**: regresión = barras por dimensión + scatter
  real-vs-predicho; clasificación binaria = dona alerta/normal; multiclase = barras por
  categoría (tabla en el mismo orden que el gráfico) [ARCHIVO:
  frontend/src/components/v3/renderidores.tsx -> LÍNEA: 286-327]; clustering = mapa 2D con
  coordenadas reales (PCA) y aviso de que los ejes no tienen unidades de negocio [ARCHIVO:
  frontend/src/components/v3/renderidores.tsx -> LÍNEA: 412-415].

---

## 7) Desacoplamiento y Separación de Capas

**Estado**: [PARCIAL]

**Hallazgo**:
- El **núcleo ML** (`src/spc/models/`) NO importa la API ni el servicio: búsqueda de
  `from spc.api` / `from spc.service` en `models/` → **sin resultados**. El core es
  independiente. [Verificado por búsqueda, sin coincidencias].
- El motor del catálogo (`motor_catalogo.py`) depende solo de `spc.catalogo.config` y
  `spc.utils` [ARCHIVO: src/spc/catalogo/motor_catalogo.py -> LÍNEA: 40-48]; no importa API ni
  servicio. Correcto.
- La API depende del motor (dirección correcta) [ARCHIVO: src/spc/api/routers/catalogo_v3.py ->
  LÍNEA: 39-42].

**[RIESGO] — Acoplamiento invertido en la capa de servicio (legacy)**:
`src/spc/service/agnostico.py` **importa esquemas de la API** (`from spc.api.schemas.agnostico`)
[ARCHIVO: src/spc/service/agnostico.py -> LÍNEA: 18]. El servicio no debería depender de la capa
de exposición. Mitigante: pertenece al motor agnóstico `/auto` (ADR-0023), que **no está montado**
en la app (`main.py` solo incluye `auth`, `dominios_3x3`, `catalogo_v3`) [ARCHIVO:
src/spc/api/main.py -> LÍNEA: 163-165]. Es deuda de una isla legacy, no del camino activo, pero
sigue en `src/`.

**Observación**: además del núcleo ML limpio, la lógica de negocio del catálogo (derivación de
etiquetas, anti-fuga, métricas) vive en `spc.catalogo.motor_catalogo`, no dentro de scripts de
entrenamiento sueltos; los routers solo adaptan al contrato en inglés [ARCHIVO:
src/spc/api/routers/catalogo_v3.py -> LÍNEA: 189-261]. Buena separación en el camino activo.

---

## BRECHAS CRÍTICAS FRENTE AL IDEAL

Priorizadas de mayor a menor impacto:

1. **[RIESGO FUGA bajo] ALM-R2 incluye `rotacion` como feature** pese a su correlación
   estructural con `dias_de_cobertura` (ambas ∝ stock) e inconsistencia con
   `columnas_conocidas_futuro`. Puede inflar el WAPE reportado. → Quitar `rotacion` de
   `columnas_entrada` (o justificar y medir su efecto). [consultas.yaml:672-680]

2. **[Acoplamiento de capas] `service/agnostico.py` importa `spc.api.schemas`** (dependencia
   invertida). Aunque es legacy no montado, contradice el ideal de core/servicio independientes
   de la API. → Mover el schema a `service`/`domain` o archivar la isla `/auto` en `legacy/`.
   [agnostico.py:18]

3. **[Configuración muerta] `lags_objetivo`/`ventanas_media` de COMPRAS no los usa el motor
   activo.** Genera falsa expectativa de modelado temporal en regresión. → Eliminar del YAML o
   documentar que solo aplican al motor `/v2` deprecado. [consultas.yaml:349-350;
   motor_catalogo.py:328-346]

4. **[Duplicación de esquema] Datos demo hard-codeados** en `/v3/{modulo}/demo` y mapa
   `humaniza()` en el frontend duplican conocimiento del dominio fuera del YAML. → Reusar
   `spc.synthetic` en el demo; considerar exponer etiquetas legibles desde el backend/catálogo.
   [catalogo_v3.py:430-479; renderidores.tsx:36-66]

5. **[Verificación pendiente] Falta prueba empírica antifuga por consulta** que compare la
   métrica con/sin las columnas sospechosas y contra el baseline, dejando registro. El código lo
   permite (ya calcula baseline) pero no se persiste un informe por consulta. → Añadir test/reporte
   que ejecute las 30 consultas sobre sintético y verifique métrica ≤ umbral y ≥ baseline.

> **Conclusión general**: el camino **activo** (catálogo v3) cumple el ideal en catálogo dinámico,
> rigor de split/selección/métricas, separación predicción-vs-tendencia, honestidad de métricas y
> UX negocio/técnico. Las brechas son acotadas: un near-leak puntual (ALM-R2), un acoplamiento y
> configuración muerta heredados, y duplicación menor de esquema. Ninguna invalida los resultados
> del sistema, pero corregirlas cierra la distancia con el ideal descrito.

---

## PLAN DE CORRECCIÓN PROPUESTO

Ordenado por impacto/esfuerzo. No ejecutado en esta auditoría (diagnóstico + propuesta).

| # | Acción | Archivo(s) | Esfuerzo | Prioridad |
|---|--------|-----------|----------|-----------|
| 1 | **Cerrar near-leak ALM-R2**: medir WAPE con/sin `rotacion`; si domina la métrica, quitar `rotacion` de `columnas_entrada` y dejar solo `categoria`, `zona_almacen`, `tiempo_reposicion_dias`. Alinear `columnas_entrada` con `columnas_conocidas_futuro`. | `consultas.yaml:672-680` | Bajo | Alta |
| 2 | **Test antifuga automatizado**: script/test que corra las 30 consultas sobre sintético y asegure `metrica_test ≥ baseline` y `≤ metrica_casi_perfecta` (salvo reglas ALM-C*), dejando informe versionado. Reusa el `baseline` que el motor ya calcula. | nuevo `tests/test_catalogo_no_fuga.py`, `scripts/evaluar_modelos.py` | Medio | Alta |
| 3 | **Resolver acoplamiento invertido**: mover el schema que usa `service/agnostico.py` a la capa de servicio/dominio, o archivar toda la isla `/auto` bajo `legacy/`. | `service/agnostico.py:18`, `api/schemas/agnostico.py` | Medio | Media |
| 4 | **Purgar configuración muerta**: eliminar `lags_objetivo`/`ventanas_media` del YAML de COMPRAS o documentar que solo aplican al motor `/v2` deprecado. | `consultas.yaml:349-350` (y com_r2/r4) | Bajo | Media |
| 5 | **Deduplicar esquema del demo**: que `/v3/{modulo}/demo` genere filas vía `spc.synthetic` en vez de literales hard-codeados. | `catalogo_v3.py:430-479` | Bajo | Baja |
| 6 | **Etiquetas legibles desde el catálogo**: exponer el mapa columna→etiqueta en el backend (o YAML) y consumirlo en el frontend, eliminando el `humaniza()` duplicado. | `renderidores.tsx:36-66`, catálogo | Medio | Baja |

**Secuencia sugerida**: 1 → 2 (validan la honestidad del ML antes de tocar nada más) → 3 → 4 →
5 → 6. Los pasos 1–2 son los que realmente mueven la aguja frente al ideal (fuga/honestidad); 3–6
son higiene de arquitectura y mantenibilidad.
</content>
</invoke>
