# Pruebas Documentadas de la Experimentación

**SPC — Sistema de Predicción y Comercialización**

- **Tipo:** Experimentos de modelado (ML) documentados
- **Diseño:** validación temporal, selección en VALID, TEST una vez, sin fuga, semilla 42
- **Total de Experimentos:** 5
- **Universidad Privada Antenor Orrego — Proyecto de Taller Integrador I**

## Índice de Experimentos

| N° | Experimento | Decisión |
|----|-------------|----------|
| 1 | Selección del modelo de regresión de ventas (Fase 2a, Favorita) | Adoptado |
| 2 | Aumento de datos con SMOTE en clasificación desbalanceada (experimento medido) | Adoptado |
| 3 | Mejor objetivo de regresión en almacén: fórmula vs demanda futura (Fase 2e) | Adoptado |
| 4 | Clustering honesto de proveedores (fin de la circularidad, Fase 3c) | Adoptado |
| 5 | Evaluación offline 3×3: los 9 modelos vs baseline (Fase 4, ADR-0025) | Adoptado |

## Experimento 1 — Selección del modelo de regresión de ventas (Fase 2a, Favorita)

- **Objetivo:** Pronosticar unidades vendidas (sales) con exceso de ceros (~31 %).
- **Hipótesis:** Un ensemble de boosters con objetivos para conteos (Tweedie/Poisson) supera al mejor pronóstico ingenuo (naïve estacional / media móvil).
- **Diseño (leak-safe):** Validación TEMPORAL (entrenar con el pasado, evaluar con el futuro); selección en VALID, TEST se mide una sola vez; sin fuga de datos (umbrales/transformaciones fijados solo en TRAIN); semilla = 42; reproducible. Métrica guía: WAPE honesto (recursivo). Se comparan 7 modelos + 2 baselines.
- **Métrica:** WAPE (menor = mejor), con MAE/RMSE/RMSLE de apoyo.

| Modelo / fuente | WAPE % | MAE | RMSE |
|---|---|---|---|
| LightGBM_Tweedie (mejor individual, TEST teacher-forced) | 12.41 | 57.96 | 197.09 |
| Ensemble XGB+XGB_Tweedie+LGBM+LGBM_Poisson (honesto recursivo) | 14.59 | 68.15 | 235.73 |
| BASELINE naive_estacional(t-7) | 20.67 | 96.54 | 348.38 |
| BASELINE media_movil_7 | 23.26 | 108.66 | 359.82 |

- **Resultado:** El ensemble (elegido por menor WAPE honesto sobre VALID: 12.18 % vs 14.25 % del mejor individual) da WAPE honesto 14.59 % frente al mejor baseline 20.67 %.
- **Decisión:** **SE ADOPTA el ensemble: mejora 6.08 puntos de WAPE (−29 % de MAE, −32 % de RMSE) sobre el baseline. Ridge se retira (no apto). Artefacto regresion_v3.**
- **Fuente (trazabilidad):** docs/reporte_regresion_2a.md

## Experimento 2 — Aumento de datos con SMOTE en clasificación desbalanceada (experimento medido)

- **Objetivo:** Medir si SMOTE (SMOTENC) mejora la detección de la clase minoritaria demanda_alta (desbalance ~1:3.5).
- **Hipótesis:** Sintetizar ejemplos de la minoritaria (SMOTE) mejora la PR-AUC frente a no remuestrear o a costo-sensible.
- **Diseño (leak-safe):** Validación TEMPORAL (entrenar con el pasado, evaluar con el futuro); selección en VALID, TEST se mide una sola vez; sin fuga de datos (umbrales/transformaciones fijados solo en TRAIN); semilla = 42; reproducible. SMOTE solo sobre el TRAIN de cada fold (imblearn.Pipeline); un test verifica que VALID conserva su prevalencia. Tolerancia de PR-AUC fijada de antemano = 0.005.
- **Métrica:** PR-AUC en VALID (principal para la minoritaria, independiente del umbral).

| Estrategia | PR-AUC (VALID) | ROC-AUC (VALID) |
|---|---|---|
| sin_remuestreo (elegida) | 0.9330 | 0.9556 |
| costo_sensible | 0.9331 | 0.9556 |
| smote (SMOTENC) | 0.9327 | 0.9551 |

- **Resultado:** Las tres estrategias difieren en < 0.001 de PR-AUC (dentro de la tolerancia). SMOTE no supera a la base ni a la costo-sensible, y costaba ~20 min vs ~30 s.
- **Decisión:** **NO SE ADOPTA SMOTE. Se elige la estrategia más simple dentro de la tolerancia (sin_remuestreo). Mostrar con números que el aumento de datos no aporta ES el entregable del experimento.**
- **Fuente (trazabilidad):** docs/fase-3/experimento_aumento_datos.md; models/clasificacion_v1.meta.json

## Experimento 3 — Mejor objetivo de regresión en almacén: fórmula vs demanda futura (Fase 2e)

- **Objetivo:** Evitar que el modelo prediga una identidad trivial (dias_de_cobertura = stock/demanda).
- **Hipótesis:** Cambiar el objetivo a la demanda futura (demanda_dia) da una tarea con señal real y aprendible.
- **Diseño (leak-safe):** Validación TEMPORAL (entrenar con el pasado, evaluar con el futuro); selección en VALID, TEST se mide una sola vez; sin fuga de datos (umbrales/transformaciones fijados solo en TRAIN); semilla = 42; reproducible. Anti-fuga: la media de demanda y la cobertura contienen el consumo del día → se usan solo con retraso o se excluyen.
- **Métrica:** R² y WAPE sobre la demo (semilla 42).

| Objetivo | ¿Aprende? | R² | WAPE % |
|---|---|---|---|
| dias_de_cobertura (antes) | No (≈ fórmula) | — | — |
| demanda_dia (ahora) | Sí | 0.84 | 16.4 |

- **Resultado:** Con demanda_dia el modelo aprende señal real (R²=0.84, no 1.0), y los KPIs de inventario (cobertura, punto de reposición, stock de seguridad) se derivan del pronóstico.
- **Decisión:** **SE ADOPTA demanda_dia como objetivo de almacén (mayor valor de negocio). Bloque indicadores_inventario en /v2/almacen.**
- **Fuente (trazabilidad):** docs/reporte_mejoras_modelos.md (Fase 2)

## Experimento 4 — Clustering honesto de proveedores (fin de la circularidad, Fase 3c)

- **Objetivo:** Evitar auto-engaño: antes los proveedores se fabricaban en 3 cajas fijas y el modelo 'descubría' esas 3 cajas.
- **Hipótesis:** Generando proveedores desde rangos continuos con solape, los grupos emergen de los datos y k lo decide el modelo (mejor silueta).
- **Diseño (leak-safe):** Datos sintéticos con arquetipos continuos (no cajas). k por mejor silueta en compras; k=3 fijo en almacén por interpretación ABC de negocio.
- **Métrica:** Silueta (−1..1, mayor = grupos más separados) + interpretación de cada grupo.

| Clustering | Antes | Ahora | Lectura |
|---|---|---|---|
| Compras (proveedores) | k=3, silueta 0.586 | k=2, silueta 0.383 | Más realista; solape |
| Almacén (SKU, ABC) | k=2 auto | k=3 fijo, silueta 0.406 | Interpretación A/B/C |

- **Resultado:** La silueta BAJA es la prueba de que los datos son más realistas (continuo, no fronteras duras). La segmentación sigue siendo accionable para priorizar.
- **Decisión:** **SE ADOPTA el clustering desde continuo (k automático en compras) y k=3 A/B/C en almacén. Se documenta la silueta real sin inflarla.**
- **Fuente (trazabilidad):** docs/reporte_mejoras_modelos.md (Fase 3)

## Experimento 5 — Evaluación offline 3×3: los 9 modelos vs baseline (Fase 4, ADR-0025)

- **Objetivo:** Demostrar con números que cada uno de los 9 modelos (3 dominios × 3 tareas) aporta, no solo que corre.
- **Hipótesis:** Cada regresión gana a su baseline; cada clasificación supera al azar (prevalencia); cada clustering da grupos interpretables.
- **Diseño (leak-safe):** Validación TEMPORAL (entrenar con el pasado, evaluar con el futuro); selección en VALID, TEST se mide una sola vez; sin fuga de datos (umbrales/transformaciones fijados solo en TRAIN); semilla = 42; reproducible. Datasets grandes (8 tiendas, un año; 20 proveedores). Reproducible con scripts/evaluar_modelos.py.
- **Métrica:** Regresión: WAPE vs baseline. Clasificación: PR-AUC/ROC-AUC/F1 vs prevalencia. Clustering: k + silueta.

| Dominio · tarea | Métrica modelo | Referencia | Veredicto |
|---|---|---|---|
| Ventas · regresión (WAPE) | 10.3 % | baseline 20.6 % | ✅ 50.8 % mejor |
| Compras · regresión (WAPE) | 8.5 % | baseline 13.5 % | ✅ 37.0 % mejor |
| Almacén · regresión (WAPE) | 16.1 % | baseline 22.4 % | ✅ 28.3 % mejor |
| Ventas · demanda_alta (F1 / PR-AUC) | 0.905 / 0.972 | azar 0.371 | ✅ |
| Compras · entrega_con_retraso (F1 / PR-AUC) | 0.667 / 0.602 | azar 0.231 | ✅ |
| Almacén · riesgo_quiebre (recall / PR-AUC) | 0.821 / 0.666 | azar 0.026 | ✅ (evento raro) |
| Ventas · clustering (k / silueta) | 3 / 0.331 | — | grupos por volumen |
| Compras · clustering (k / silueta) | 2 / 0.445 | — | velocidad vs costo |
| Almacén · clustering (k / silueta) | 3 / 0.414 | — | ABC por demanda |

- **Resultado:** 9/9 modelos aportan: las 3 regresiones ganan al baseline (28–51 %); las 3 clasificaciones superan de largo al azar; los 3 clusterings dan grupos accionables. Punto flojo declarado: riesgo_quiebre (evento raro → precisión baja, recall alto).
- **Decisión:** **SE VALIDA el rediseño 3×3. Además se arregló el umbral de 'entrega con retraso' (recall ~0.04 → 0.85).**
- **Fuente (trazabilidad):** docs/reporte_mejoras_modelos.md (Fase 4); scripts/evaluar_modelos.py

---

**Evidencia gráfica.** Figuras de apoyo en figures/: 11_balance_clases_demanda.png (desbalance), 18_segmentacion_tiendas_kmeans.png (clustering), 19_silueta_k_tiendas.png (silueta vs k), distribuciones y estacionalidad del EDA.

Salidas de las corridas en `final/evidencias/pruebas/experimentacion/`.