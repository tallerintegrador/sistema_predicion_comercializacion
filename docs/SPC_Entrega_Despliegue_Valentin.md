## **Sistema Predictivo de Comercialización (SPC)** 

Documento de entrega para el despliegue — del estado de la Fase 3 a la decisión de la Fase 4 

## **De:** Camila 

**Para:** Valentín 

**Asunto:** Qué se hizo tras la retroalimentación del docente, qué falta, y cómo continuar Fecha: 17 de junio de 2026 

## **1. Propósito de este documento** 

Camila terminó las subfases de la Fase 3 y subió todos los cambios a la rama. Este documento le entrega a Valentín (y a su asistente de IA) el panorama completo para que continúe con el despliegue: qué tenía el proyecto antes de la retroalimentación del docente, qué recomendó el docente, qué se hizo en respuesta, qué quedó pendiente, y una recomendación sobre el camino a seguir. Al final hay prompts listos para pegar en la IA de Valentín según el camino que elija. 

## **2. Estado del proyecto antes de la retroalimentación** 

Cuando se presentó al docente, el proyecto ya tenía completas las fases 0 (configuración), 1 (datos y análisis exploratorio) y 2 (motor de Machine Learning), y una primera versión de la Fase 3 (la capa de API/servicio, backend desplegado, sin frontend). 

Se mostró el motor entrenado sobre el dataset de retail Corporación Favorita (3 000 888 filas, 54 tiendas, 33 familias) y la API con sus endpoints. El entrenamiento había tardado cerca de dos días. Los artefactos del modelo, ya finalizados y congelados, son (todas las métricas medidas sobre Favorita): 

- **Regresión (regresion_v3):** ensemble (XGBoost + XGB-Tweedie + LightGBM + LGBMPoisson). WAPE recursivo (honesto) 14.59 %, frente a 20.67 % del baseline ingenuo: 6 puntos de mejora. 

- **Clasificación (clasificacion_v1):** LightGBM, sin remuestreo. Umbral de operación 0.3185, precisión 0.809, recall 0.874, PR-AUC 0.9343. 

- **Agrupamiento de tiendas (clustering_tiendas_v1):** k=2, silueta 0.6742. 

- **Agrupamiento de familias (clustering_familias_v1):** k=3 (elegido a propósito), silueta 0.659. 

La observación central del docente fue que se estaba invirtiendo demasiado tiempo en entrenar y poco en la plataforma genérica, que es el verdadero objetivo del proyecto. 

## **3. Lo que recomendó el docente** 

De la reunión salieron once recomendaciones, más una decisión de fondo sobre el significado de “predecir”. 

1. **Entregar el mejor modelo ya entrenado, sin reentrenar en cada consulta.** 

SPC — Documento de entrega para el despliegue   ·   Página 1 

2. **La plataforma debe ser agnóstica al rubro: los datos los pone el cliente.** 

3. **Recibir los datos del cliente y predecir sobre ellos (un modelo de un rubro no transfiere bien a otro).** 

4. **Definir y exigir un contrato o diccionario de datos como entrada obligatoria.** 

5. **Ofrecer un catálogo de tipos de predicción por dominio (ventas, compras, inventario).** 

6. **Soportar dos modos según el volumen: en línea (síncrono) y por lote (asíncrono).** 

7. **No fijar parámetros del modelo que dependan de los datos del cliente.** 

8. **Usar datos sintéticos para las pruebas.** 

9. **Tratar el aumento de datos como un experimento riguroso.** 

10. **Habilitar varios canales de entrada: Excel, API/JSON y, a futuro, móvil.** 

11. **Priorizar la plataforma genérica por encima del entrenamiento.** 

**Decisión de fondo:** ¿qué significa “predecir” cuando el cliente sube sus propios datos? Se plantearon tres opciones: (A) modelo congelado, Favorita como cliente de ejemplo; (B) en el modo lote, ajustar/entrenar un modelo con los datos del cliente y pronosticar sobre ellos; e (híbrida) entregar A ahora y dejar B como experimento futuro medido. Se aprobó la híbrida como norte, entregando A primero. Esta decisión es la que hoy define el camino que debe elegir Valentín (ver sección 8). 

SPC — Documento de entrega para el despliegue   ·   Página 2 

## **4. Qué se hizo en las subfases 3.0 a 3.7** 

Cada subfase se planificó, se ejecutó y se validó antes de avanzar a la siguiente. En resumen sencillo: 

- **3.0 — Replanteamiento.** Se rediseñó la Fase 3 para encajar las recomendaciones, sin tocar código todavía, y se tomaron las decisiones base (numeración de ADRs, idioma del contrato, modos, método de stock, opción híbrida con A primero). 

- **3.1 — Contrato endurecido.** El contrato de datos quedó como única fuente de verdad, versión 1.0.1, con nombres en inglés y validación estricta: si llega un dato mal formado, se rechaza con un error claro que dice qué campo falló. 

- **3.2 — Catálogo.** Se publicó GET /catalog, un “menú de servicios” honesto que se arma solo a partir de lo que la API realmente entrega, con una prueba que falla si el catálogo promete algo que no existe. 

- **3.3 — Canal Excel.** Segunda puerta de entrada para clientes no técnicos: descargan una plantilla, la llenan y la suben; por dentro reutiliza exactamente la misma validación y predicción que el JSON (resultado idéntico, comprobado). 

- **3.4 — Modos en línea y por lote.** El mismo endpoint decide por el número de filas: envíos chicos responden al instante; envíos grandes devuelven un comprobante y se procesan en segundo plano. El resultado por ambos caminos es idéntico por construcción. 

- **3.5 — Auditoría de parámetros.** Se confirmó que ningún parámetro del modelo está “escrito a mano” (todo se lee del propio modelo), y las decisiones de negocio (colchones, lead time, etc.) se volvieron configurables sin tocar código. 

- **3.6 — Documentación honesta.** Se escribieron el documento de alcance/validación/limitaciones, el del experimento de aumento de datos, y el ADR de transferibilidad, con cada métrica verificada contra su fuente. 

- **3.7 — Pruebas integrales y revisión final.** Se completó la matriz de pruebas (3 dominios × JSON/Excel × en línea/lote × errores) y se redactaron el checklist de despliegue y el guion de demo. 

**Resultados:** la batería completa pasa 156/156 (incluido el motor) y las pruebas de la API 100/100. El sistema quedó listo para demo y para un piloto controlado. 

SPC — Documento de entrega para el despliegue   ·   Página 3 

## **5. Comparación: recomendación del docente vs. lo que se hizo** 

Las once recomendaciones quedaron atendidas: 

|**Recomendación**|**Qué se hizo**|**Dónde**|
|---|---|---|
|1. Entregar el mejor<br>modelo,<br>sin<br>reentrenar|El modelo se entrega congelado y solo predice; no<br>se reentrena por consulta.|ADR-0009|
|2.<br>Plataforma<br>agnóstica; datos del<br>cliente|El cliente trae sus datos por el contrato; la<br>plataforma no conoce su negocio.|3.1, doc alcance|
|3. Predecir sobre<br>datos del cliente;<br>transferibilidad|Límite<br>de<br>transferibilidad<br>declarado<br>con<br>honestidad; ajuste por cliente como dirección<br>futura.|ADR-0009, 3.6|
|4.<br>Contrato<br>obligatorio|Contrato v1.0.1, validación estricta de toda<br>entrada.|3.1|
|5.<br>Catálogo<br>por<br>dominio|GET /catalog, derivado del código y honesto.|3.2|
|6. Modos en línea y<br>por lote|Ruteo por número de filas; lote asíncrono in-<br>process.|3.4, ADR-0008|
|7.<br>No<br>fijar<br>parámetros<br>del<br>cliente|Auditoría:<br>modelo<br>desde<br>metadata;<br>política<br>configurable.|3.5, ADR-0010|
|8. Datos sintéticos<br>para pruebas|Toda la suite usa fixtures sintéticos, sin GPU ni<br>datos reales.|3.1-3.7|
|9.<br>Aumento<br>de<br>datos<br>como<br>experimento|Experimento SMOTE formalizado y descartado con<br>evidencia.|3.6|
|10. Varios canales<br>(Excel)|Ingesta por Excel + plantilla; móvil queda como<br>futuro.|3.3|
|11.<br>Priorizar<br>plataforma<br>sobre<br>entrenamiento|Plataforma<br>construida<br>y<br>probada;<br>modelo<br>congelado.|Toda la Fase 3|



## **6. Lo que no se hizo o no se pudo hacer (y por qué)** 

Esto es lo que queda abierto. La mayoría depende de GPU o de configuración de producción, que es el terreno de Valentín. 

|**Pendiente**|**Por qué quedó abierto**|**A cargo de**|
|---|---|---|
|Reentrenar / ajustar con<br>los datos del cliente<br>(opción B / híbrida)|Se decidió entregar primero el modelo<br>congelado (A) y dejar el ajuste por cliente<br>como experimento medido. Requiere GPU<br>y validación.|Decisión de Valentín<br>(sección 8)|



SPC — Documento de entrega para el despliegue   ·   Página 4 

|**Pendiente**|**Por qué quedó abierto**|**A cargo de**|
|---|---|---|
|Intervalos de predicción<br>(interval_80)|El modelo aún no los produce; se<br>documentó como diferido en vez de<br>inventarlos.|Modelado<br>(Valentín,<br>GPU)|
|objetivo_cuantil (el P75)<br>en<br>la<br>metadata<br>del<br>artefacto|La metadata no expone el número; hoy se<br>usa un respaldo documentado de 0.75.<br>Conviene exponerlo al reconstruir el<br>artefacto.|Valentín<br>(al<br>reconstruir, GPU)|
|Verificar<br>el<br>umbral<br>0.3185 y el ensemble a<br>escala completa|Son cabos de la Fase 2 que requieren la<br>máquina con GPU y los datos crudos, que<br>Camila no tiene.|Valentín (GPU)|
|Robustez del lote (multi-<br>worker)|El lote guarda los trabajos en memoria; un<br>solo proceso. Escalar exige un almacén<br>compartido (SQLite o cola externa), aún no<br>implementado.|Despliegue<br>(sección<br>8)|
|CORS real y re-medir el<br>umbral de filas|Hoy CORS abierto y umbral medido en<br>dev; en producción hay que fijar el origen<br>real y re-medir con el hardware/modelo<br>reales.|Despliegue<br>(sección<br>8)|
|Canal móvil|Se dejó explícitamente como puerta futura,<br>sin backend nuevo.|Futuro|
|Actualizar notion/* con<br>los nombres en inglés|Tarea manual menor; no la pudo hacer la<br>IA.|Camila|



SPC — Documento de entrega para el despliegue   ·   Página 5 

## **7. Estado técnico (referencia para la IA de Valentín)** 

Resumen del estado actual del código en la rama, para orientar a la IA antes de continuar. 

## **Arquitectura (separación estricta de capas)** 

- **Capa API:** routers/ (ventas, compras, almacen, excel, jobs), schemas/, ingest/ (plantilla y lector de Excel), ruteo.py (decisión en línea/lote), jobs.py (almacén de trabajos + executor), catalog.py, errors.py. 

- **Capa de servicio/política:** ventas_service, compras_service, almacen_service y politica.py (fórmula única de stock de seguridad). 

- **Motor de ML (congelado):** artefactos bajo models/, consumidos vía objetos cargados; adaptador.py traduce los nombres inglés (público) ↔ español (interno). La capa interna está en español por diseño y no debe cambiarse. 

## **Contrato y endpoints** 

- **Contrato:** docs/contrato_datos.md v1.0.1, nombres en inglés, validación estricta (strict), errores estructurados {error:{type,message,details:[{field,problem}]}}. 

- **Endpoints:** POST /sales, /purchases, /inventory (JSON); POST /{dominio}/excel (subida); GET /{dominio}/template (descarga de plantilla); GET /catalog; GET /jobs/{id} y GET /jobs/{id}/result; /health. 

- **Modos:** el mismo endpoint decide por número de filas del histórico. En línea → 200 con el resultado; lote → 202 con job_id, procesado en segundo plano (en memoria, un solo worker). 

## **Variables de configuración (sin tocar código)** 

|**Variable**|**Default**|**Para qué**|
|---|---|---|
|SPC_ONLINE_MAX_ROWS|2000|Umbral de filas<br>en línea vs lote<br>(re-medir<br>en<br>producción)|
|SPC_EXCEL_MAX_BYTES|25 MB|Tope de tamaño<br>de archivo Excel<br>(guarda<br>anti-<br>abuso)|
|SPC_BATCH_WORKERS|1|Hilos<br>del<br>procesado<br>por<br>lote|
|SPC_CORS_ORIGINS|(abierto)|Orígenes<br>permitidos; fijar al<br>frontend real en<br>producción|
|SPC_PURCHASES_SAFETY_FACTOR|0.30|Colchón<br>de<br>seguridad<br>de<br>COMPRAS|



SPC — Documento de entrega para el despliegue   ·   Página 6 

|**Variable**|**Default**|**Para qué**|
|---|---|---|
|SPC_INVENTORY_LEAD_TIME_DEFAULT|7|Lead<br>time<br>por<br>defecto<br>si<br>el<br>cliente<br>no<br>lo<br>envía|
|SPC_INVENTORY_DEMAND_WINDOW|28|Días<br>recientes<br>para<br>estimar<br>demanda|
|SPC_INVENTORY_Z_BASE / Z_HIGH_VOLUME|1.28 / 1.65|Nivel de servicio<br>(método<br>service_level)|
|SPC_{PURCHASES,INVENTORY}_SAFETY_METHOD|coverage_days<br>/ service_level|Método de stock<br>por<br>dominio;<br>unificar = cambiar<br>a coverage_days|



## **ADRs y documentos clave** 

- **ADRs:** 0007 (capa API), 0008 (modos de ejecución), 0009 (transferibilidad / modelo congelado), 0010 (política de inventario y stock). 

**Documentos:** docs/fase-3/alcance_validacion_limitaciones.md, experimento_aumento_datos.md, checklist_despliegue.md, guion_demo.md, plantillas/. Pruebas: tests/api (rápidas) y la batería completa (incluye motor, ~1h40). 

- **Documentos:** 

SPC — Documento de entrega para el despliegue   ·   Página 7 

## **8. La decisión de Valentín: dos caminos** 

La gran pregunta abierta es la “opción B”: implementar el reentrenamiento/ajuste con los datos del cliente, que necesita GPU. Hay dos caminos, y conviene aclarar que no son excluyentes: el Camino A se inserta antes del despliegue, pero el despliegue (Camino B) hay que hacerlo de todos modos al final. 

## **Camino B — Desplegar primero (recomendado)** 

Desplegar la plataforma con el modelo congelado tal como está, y cerrar los pendientes de producción. El ajuste por cliente queda documentado como mejora posterior. 

**A favor:** es lo que el docente pidió (plataforma por encima del entrenamiento), respeta la decisión híbrida ya aprobada (A primero), es de menor riesgo cerca del cierre y entrega un producto completo y honesto. La limitación de transferibilidad ya está documentada, que es justo lo que el docente valoró. 

**En contra:** para un cliente de otro rubro, el modelo congelado da una señal limitada; la “verdadera” agnosticidad (ajustar por cliente) queda para después. 

## **Camino A — Implementar el ajuste por cliente primero** 

Aprovechar la GPU de Valentín para que, en el modo lote, el sistema ajuste un modelo a los datos que sube cada cliente y pronostique sobre ellos, antes de desplegar. 

**A favor:** responde de lleno a la crítica de transferibilidad del docente; es la versión más “genérica de verdad” y daría un proyecto más ambicioso. 

**En contra:** es un desarrollo de ML e infraestructura considerable (pipeline de entrenamiento por cliente + el experimento que valide que aporta), choca con el “dejen de gastar tiempo entrenando” del docente y es más riesgoso cerca del cierre. Además, igual hay que desplegar después. 

## **Recomendación** 

**Camino B primero.** Desplegar la plataforma con el modelo congelado y dejar el ajuste por cliente (Camino A) como experimento medido posterior, solo si queda tiempo y se valida que mejora sobre el modelo actual. Esto honra la decisión híbrida aprobada, la prioridad del docente y el plazo. Si Valentín tiene tiempo de sobra y GPU disponible, puede hacer el Camino A antes de desplegar para un proyecto más fuerte; pero no es lo recomendado si el cierre está cerca. 

**Guía de fases para el Camino B (despliegue) — Fase 4** 

- **4.0 Checkpoint de despliegue:** leer checklist_despliegue.md, elegir dónde se aloja, proponer la arquitectura de despliegue y pausar. 

- **4.1 Configuración de producción:** fijar CORS al frontend real, re-medir SPC_ONLINE_MAX_ROWS con el hardware/modelo reales (script bench_umbral_online.py), fijar artefactos y variables. 

- **4.2 Cerrar pendientes de modelo:** exponer objetivo_cuantil (P75) en la metadata del artefacto y verificar los cabos de la Fase 2 (umbral 0.3185 y ensemble a escala) en GPU. 

- **4.3 Robustez del lote (opcional):** si se quiere más de un worker, pasar el almacén de trabajos a SQLite o cola compartida; si no, documentar el worker único. 

SPC — Documento de entrega para el despliegue   ·   Página 8 

- **4.4 Empaquetado y despliegue:** contenedor (Docker), despliegue en el host, un solo worker, variables de entorno, health checks. 

- **4.5 Frontend conectado (si aplica):** conectar el frontend a la API desplegada con el CORS real. 

- **4.6 Pruebas de humo y monitoreo básico:** verificar en producción los flujos clave con datos sintéticos. 

- **4.7 Entrega y cierre.** 

**Guía de fases para el Camino A (ajuste por cliente) — antes del despliegue** 

- **A.0 Checkpoint:** diseñar el ajuste por cliente dentro del modo lote (subida grande → ajustar modelo con los datos del cliente → pronosticar), respetando las capas; definir el experimento que valide que aporta. Pausar. 

- **A.1 Pipeline de ajuste por cliente (GPU):** implementarlo reutilizando el contrato. 

- **A.2 Experimento medido (honesto):** comparar el ajuste por cliente contra el modelo congelado / un baseline sobre datos retenidos del cliente; activar solo si mejora. 

- **A.3 Integración:** conectar al modo lote (en el catálogo, client_adjustment pasaría de “planed” a “available” si se valida) y actualizar el ADR-0009. 

- **A.4 Luego, desplegar:** continuar con la Fase 4 del Camino B. 

## **9. Pendientes concretos para Valentín** 

- **Decidir el camino (A o B)** con base en la sección 8. 

- **Cabos de modelo en GPU:** verificar que el umbral 0.3185 transfiere al artefacto reentrenado con todo el histórico; confirmar la estabilidad del ensemble a escala completa; exponer objetivo_cuantil (P75) en la metadata. 

- **Producción:** CORS real, re-medir el umbral de filas, decidir si se necesita más de un worker (y con ello el almacén compartido). 

- **Desplegar el backend y, si aplica, el frontend.** 

SPC — Documento de entrega para el despliegue   ·   Página 9 

## **10. Prompt para continuar con la IA (una vez subida la rama)** 

Pegar en la IA de Valentín. El primero es para el camino recomendado (despliegue). Más abajo hay una variante por si elige el Camino A. 

**Prompt principal — Camino B (despliegue, recomendado)** 

```
CONTEXTO DEL PROYECTO
```

```
Trabajo en SPC (Sistema Predictivo de Comercialización), una plataforma que da tres
servicios de predicción por API: pronóstico de ventas (/sales), sugerencia de compras
(/purchases) y alertas de inventario (/inventory). Es agnóstica al rubro: el cliente
trae sus datos por un contrato estándar.
```

```
Mi compañera (PM) ya terminó y subió a la rama toda la Fase 3 ampliada (subfases 3.0 a
```

- `3.7). Estado actual del código:` 

- `Contrato en docs/contrato_datos.md v1.0.1, nombres en ingles, validacion estricta (strict), errores estructurados {error:{type,message,details:[{field,problem}]}}.` 

- `Arquitectura en 3 capas: API (routers/, schemas/, ingest/, ruteo.py, jobs.py, catalog.py, errors.py) -> servicio/politica (ventas/compras/almacen_service, politica.py) -> motor de ML congelado (artefactos en models/, adaptador.py traduce ingles publico <-> espanol interno). La capa interna en espanol es por diseno; NO cambiarla.` 

- `Endpoints: POST /sales|/purchases|/inventory (JSON); POST /{dominio}/excel; GET /{dominio}/template; GET /catalog; GET /jobs/{id} y /jobs/{id}/result; /health.` 

- `Modos: el mismo endpoint decide por nro de filas del history. Chico -> 200 sincrono; grande -> 202 con job_id, procesado en segundo plano (en memoria, un solo worker).` 

- `Variables de entorno: SPC_ONLINE_MAX_ROWS (2000), SPC_EXCEL_MAX_BYTES (25MB), SPC_BATCH_WORKERS (1), SPC_CORS_ORIGINS, y las constantes de politica` 

- `(SPC_PURCHASES_SAFETY_FACTOR, SPC_INVENTORY_LEAD_TIME_DEFAULT, _DEMAND_WINDOW,` 

- `_Z_BASE, _Z_HIGH_VOLUME, _SAFETY_FALLBACK_FACTOR) y el metodo de stock` 

```
  SPC_{PURCHASES,INVENTORY}_SAFETY_METHOD = coverage_days|service_level.
```

- `ADRs 0007 (API), 0008 (modos), 0009 (transferibilidad), 0010 (politica inventario).` 

- `Pruebas: tests/api (rapidas) y la bateria completa (incluye motor, ~1h40). Todo verde.` 

- `Docs guia: docs/fase-3/checklist_despliegue.md y guion_demo.md.` 

```
PRINCIPIOS A RESPETAR
```

- `No tocar el motor de ML ni la capa interna en espanol; el modelo se entrega congelado.` 

- `Mantener la separacion de capas y el contrato como frontera.` 

- `Honestidad: nada de valores inventados; lo diferido se etiqueta.` 

- `Yo tengo GPU y los datos crudos, asi que puedo cerrar los cabos de modelo.` 

## `ENCARGO — FASE 4 (DESPLIEGUE)` 

```
Vamos a desplegar la plataforma con el modelo congelado y cerrar los pendientes de
produccion. Empieza por la FASE 4.0 como CHECKPOINT (PASO 0): NO escribas codigo
todavia.
```

`1. Lee docs/fase-3/checklist_despliegue.md y el estado actual del repo.` 

`2. Propon el plan de despliegue: donde se aloja, contenedor, variables de entorno a fijar (incluido SPC_CORS_ORIGINS al frontend real y re-medir SPC_ONLINE_MAX_ROWS con bench_umbral_online.py en el hardware real), la restriccion de un solo worker (job store en memoria, ADR-0008) y si conviene pasar a un almacen compartido.` 

`3. Propon como cerrar los pendientes de modelo que requieren GPU: exponer` 

- `objetivo_cuantil (P75) en la metadata del artefacto, y verificar el umbral 0.3185 y el ensemble a escala completa (cabos de la Fase 2).` 

`4. Entrega una propuesta con subfases 4.0 a 4.7 y DETENTE para mi aprobacion antes de implementar.` 

**Variante — Camino A (ajuste por cliente, si decides hacerlo antes de desplegar)** 

Usar el mismo bloque CONTEXTO DEL PROYECTO de arriba, y reemplazar el ENCARGO por este: 

SPC — Documento de entrega para el despliegue   ·   Página 10 

```
ENCARGO — AJUSTE POR CLIENTE (antes del despliegue)
```

```
Antes de desplegar, vamos a implementar el ajuste/entrenamiento con los datos del
cliente dentro del modo lote (la opcion B de la decision hibrida). Tengo GPU.
Empieza por un CHECKPOINT (PASO 0): NO escribas codigo todavia.
```

`1. Disena como, en el modo lote, una subida grande puede ajustar un modelo a los datos del cliente y pronosticar sobre ellos, respetando las capas y reutilizando el contrato. El modo en linea sigue usando el modelo congelado.` 

`2. Define el EXPERIMENTO MEDIDO que valide si el ajuste por cliente realmente mejora sobre el modelo congelado / un baseline, usando datos retenidos del cliente. Solo se activa si mejora (honestidad: si no mejora, se documenta y no se activa).` 

`3. Propon como quedaria integrado al modo lote (en el catalogo, client_adjustment pasaria de planned a available solo si se valida) y que cambia en el ADR-0009.` 

`4. Entrega una propuesta con subfases (A.0 a A.4, y luego la Fase 4 de despliegue) y DETENTE para mi aprobacion antes de implementar.` 

**Nota final:** cualquiera sea el camino, conviene mantener la disciplina de checkpoint que usamos en toda la Fase 3: que la IA proponga y se detenga a esperar aprobación antes de implementar, y que cada cambio se valide con las pruebas antes de avanzar. 

SPC — Documento de entrega para el despliegue   ·   Página 11 

