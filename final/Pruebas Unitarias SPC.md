# Documento de Pruebas Unitarias

**SPC — Sistema de Predicción y Comercialización**

- **Tipo de Prueba:** Unitaria / de Integración (capa de datos)
- **Marco:** pytest 8.3.4
- **Total de Suites:** 10 — **Casos documentados:** 50
- **Universidad Privada Antenor Orrego — Proyecto de Taller Integrador I**

## Índice de Suites de Prueba

| N° | Archivo | Módulo bajo prueba | Casos |
|----|---------|--------------------|-------|
| 1 | tests/test_metrics.py | spc.utils.metrics | 7 |
| 2 | tests/test_serializacion.py | spc.utils.serializacion | 4 |
| 3 | tests/test_nucleo.py | spc.models.nucleo | 5 |
| 4 | tests/test_desbalance.py | spc.models.desbalance | 7 |
| 5 | tests/test_politica.py | spc.service.politica | 5 |
| 6 | tests/test_dominios.py | spc.service.dominios | 5 |
| 7 | tests/test_sinteticos.py | spc.synthetic | 5 |
| 8 | tests/test_zoo_liviano.py / test_features_generico.py / test_seleccion_modelo.py / test_automl_no_fuga.py | spc.models.zoo_liviano, spc.features.generico, spc.service.seleccion_modelo, spc.models.automl | 4 |
| 9 | tests/service/test_validacion_tipos.py | spc.service.validacion_tipos | 3 |
| 10 | tests/persistencia/ (corpus, modelos, auth, migraciones) | spc.service.repositorio_corpus / repositorio_modelos / repositorio_auth; migraciones Alembic | 5 |

## Suite 1 — tests/test_metrics.py

- **Módulo bajo prueba:** spc.utils.metrics
- **Qué se prueba:** Fórmulas de métricas de regresión (WAPE/MAPE/RMSE/RMSLE), clasificación centrada en la minoritaria (PR-AUC, prevalencia, matriz de confusión) y clustering (silueta).
- **Técnica:** Propiedad exacta y valores conocidos; casos borde (denominador cero, una sola clase, <2 clusters).

| # | Caso (test) | Qué valida | Resultado |
|---|-------------|------------|-----------|
| 1 | `test_wape_valor_conocido` | WAPE = Σ|error|/Σ|actual|×100 con un valor calculado a mano | **PASA** |
| 2 | `test_wape_denominador_cero_es_nan` | Actuales todos en cero → WAPE = NaN (sin división por cero) | **PASA** |
| 3 | `test_mape_excluye_ceros_del_actual` | MAPE ignora las filas con y_true=0 (zero-inflation) | **PASA** |
| 4 | `test_evaluar_en_unidades_invierte_log1p` | Métricas se reportan en unidades (expm1), no en log | **PASA** |
| 5 | `test_classification_metrics_min_una_sola_clase_pr_auc_nan` | Sin positivos, PR-AUC/ROC-AUC = NaN (no lanza) | **PASA** |
| 6 | `test_matriz_confusion_cuenta_correcta` | TN/FP/FN/TP correctos al umbral 0.5 | **PASA** |
| 7 | `test_clustering_metrics_dos_grupos_separados` | Silueta > 0.9 con dos grupos bien separados | **PASA** |

- **Comando:** `venv/Scripts/python -m pytest tests/ -v`
- **Evidencia:** `final/evidencias/pruebas/unitarias/`

## Suite 2 — tests/test_serializacion.py

- **Módulo bajo prueba:** spc.utils.serializacion
- **Qué se prueba:** Guardado/carga de artefactos joblib + JSON de metadatos adjunto; inyección de marca temporal y nombre; no mutación de los metadatos del llamador.
- **Técnica:** Round-trip en carpeta temporal (tmp_path); verificación de igualdad y de efectos colaterales.

| # | Caso (test) | Qué valida | Resultado |
|---|-------------|------------|-----------|
| 1 | `test_round_trip_objeto_y_metadatos` | Lo guardado se recupera idéntico (objeto + metadatos) | **PASA** |
| 2 | `test_inyecta_guardado_utc_y_nombre_artefacto` | Se inyecta guardado_utc y el nombre del artefacto; crea el directorio padre | **PASA** |
| 3 | `test_no_muta_los_metadatos_del_llamador` | El dict de metadatos original no se modifica | **PASA** |
| 4 | `test_cargar_sin_meta_devuelve_dict_vacio` | Artefacto sin .meta.json → metadatos = {} | **PASA** |

- **Comando:** `venv/Scripts/python -m pytest tests/ -v`
- **Evidencia:** `final/evidencias/pruebas/unitarias/`

## Suite 3 — tests/test_nucleo.py

- **Módulo bajo prueba:** spc.models.nucleo
- **Qué se prueba:** Primitivas del motor de regresión: cortes temporales, zoo de 8 modelos (5 log + 3 unidades), conversión cruda→unidades, ensamble ponderado y pesos convexos que minimizan el MAE.
- **Técnica:** Submodelos de mentira (fakes) para no entrenar; propiedades algebraicas exactas.

| # | Caso (test) | Qué valida | Resultado |
|---|-------------|------------|-----------|
| 1 | `test_cortes_temporales_as_dict` | as_dict() describe train/valid/test por fecha | **PASA** |
| 2 | `test_construir_zoo_inventario_y_espacios` | 8 regresores; Tweedie/Poisson en espacio 'unidades' | **PASA** |
| 3 | `test_a_unidades_espacio_log_invierte_expm1_y_recorta` | Log-espacio → expm1 y recorte a ≥0 | **PASA** |
| 4 | `test_ensemble_promedia_ponderado_en_unidades` | Ensemble = combinación convexa exacta de submodelos | **PASA** |
| 5 | `test_mejores_pesos_son_convexos` | Pesos ≥0, suman 1; el miembro fiel pesa más | **PASA** |

- **Comando:** `venv/Scripts/python -m pytest tests/ -v`
- **Evidencia:** `final/evidencias/pruebas/unitarias/`

## Suite 4 — tests/test_desbalance.py

- **Módulo bajo prueba:** spc.models.desbalance
- **Qué se prueba:** Estrategias de desbalance (sin remuestreo / costo-sensible / SMOTE), selección de umbral en VALID (máx recall con piso real de precisión) y elección de la estrategia más simple que empata en PR-AUC.
- **Técnica:** Construcción sin entrenar; datos separables sintéticos; regla de decisión con tolerancia.

| # | Caso (test) | Qué valida | Resultado |
|---|-------------|------------|-----------|
| 1 | `test_sin_remuestreo_es_booster_desnudo` | Estrategia base = LGBMClassifier sin peso | **PASA** |
| 2 | `test_costo_sensible_inyecta_scale_pos_weight` | costo_sensible pasa scale_pos_weight | **PASA** |
| 3 | `test_smote_es_pipeline_con_sampler_y_clf` | SMOTE = Pipeline [SMOTENC, clf] | **PASA** |
| 4 | `test_estrategia_desconocida_lanza` | Nombre inválido → ValueError | **PASA** |
| 5 | `test_umbral_respeta_piso_de_precision_con_separacion_perfecta` | Umbral elegido cumple precisión ≥ 0.80 | **PASA** |
| 6 | `test_empate_elige_la_mas_simple` | Empate en PR-AUC → gana sin_remuestreo | **PASA** |
| 7 | `test_smote_gana_solo_si_supera_la_tolerancia` | SMOTE solo se adopta si supera la tolerancia | **PASA** |

- **Comando:** `venv/Scripts/python -m pytest tests/ -v`
- **Evidencia:** `final/evidencias/pruebas/unitarias/`

## Suite 5 — tests/test_politica.py

- **Módulo bajo prueba:** spc.service.politica
- **Qué se prueba:** Fórmulas de stock de seguridad (coverage_days y service_level), fallback cuando σ no es estimable, y monotonía respecto a σ.
- **Técnica:** Valores conocidos; ningún número vive en el módulo (todo entra por argumento).

| # | Caso (test) | Qué valida | Resultado |
|---|-------------|------------|-----------|
| 1 | `test_coverage_days_es_factor_por_demanda` | coverage_days = factor × demanda(lead) | **PASA** |
| 2 | `test_service_level_usa_z_sigma_raiz_lead` | service_level = z·σ·√lead | **PASA** |
| 3 | `test_service_level_cae_a_fallback_si_sigma_no_estimable` | σ=NaN → factor_fallback × demanda | **PASA** |
| 4 | `test_metodo_desconocido_recae_en_coverage` | Método no reconocido usa coverage (seguro) | **PASA** |
| 5 | `test_service_level_crece_con_sigma` | El colchón crece de forma monótona con σ | **PASA** |

- **Comando:** `venv/Scripts/python -m pytest tests/ -v`
- **Evidencia:** `final/evidencias/pruebas/unitarias/`

## Suite 6 — tests/test_dominios.py

- **Módulo bajo prueba:** spc.service.dominios
- **Qué se prueba:** Configuración 3×3 por dominio: objetivo nunca es feature (anti-fuga), etiqueta derivada produce dos clases, perfil por entidad alimenta el clustering, y almacén usa k=3 (A/B/C).
- **Técnica:** Datos del generador sintético; propiedades de las tres tareas por dominio.

| # | Caso (test) | Qué valida | Resultado |
|---|-------------|------------|-----------|
| 1 | `test_config_de_dominio_desconocido_lanza` | Dominio inválido → KeyError | **PASA** |
| 2 | `test_objetivo_no_es_feature_anti_fuga` | El objetivo de regresión no aparece como feature | **PASA** |
| 3 | `test_derivar_etiqueta_produce_dos_clases` | Etiqueta de clasificación con ambas clases (ventas/compras/almacen) | **PASA** |
| 4 | `test_perfil_entidades_indexado_por_clave` | Una fila por entidad; columnas de clustering presentes | **PASA** |
| 5 | `test_almacen_usa_k_fijo_tres_abc` | Almacén fija k=3 con estilo de etiqueta A/B/C | **PASA** |

- **Comando:** `venv/Scripts/python -m pytest tests/ -v`
- **Evidencia:** `final/evidencias/pruebas/unitarias/`

## Suite 7 — tests/test_sinteticos.py

- **Módulo bajo prueba:** spc.synthetic
- **Qué se prueba:** Generadores de datos por dominio: conformidad de esquema, reproducibilidad (semilla 42), columnas calculadas coherentes (ingreso, costo_total, cumplimiento) y señal para los tres modelos.
- **Técnica:** Comparación de DataFrames; verificación de banderas 0/1 y de dos clases en las etiquetas.

| # | Caso (test) | Qué valida | Resultado |
|---|-------------|------------|-----------|
| 1 | `test_reproducible_misma_semilla` | Misma semilla → filas idénticas | **PASA** |
| 2 | `test_ventas_correcciones` | ingreso = unidades × precio; banderas 0/1 | **PASA** |
| 3 | `test_compras_correcciones` | costo_total y cumplimiento calculados y coherentes | **PASA** |
| 4 | `test_almacen_objetivo_es_demanda_dia` | Objetivo de almacén = demanda_dia (aprendible) | **PASA** |
| 5 | `test_dominio_desconocido_lanza` | Dominio inválido → KeyError | **PASA** |

- **Comando:** `venv/Scripts/python -m pytest tests/ -v`
- **Evidencia:** `final/evidencias/pruebas/unitarias/`

## Suite 8 — tests/test_zoo_liviano.py / test_features_generico.py / test_seleccion_modelo.py / test_automl_no_fuga.py

- **Módulo bajo prueba:** spc.models.zoo_liviano, spc.features.generico, spc.service.seleccion_modelo, spc.models.automl
- **Qué se prueba:** Zoo sklearn liviano (9 modelos 3×3), ingeniería de features sin fuga, regla quédate-con-el-mejor (campeón vs retador) y guarda anti-fuga del AutoML de regresión.
- **Técnica:** Entrenamiento liviano determinista (semilla 42); verificación de no-fuga train/valid/test.

| # | Caso (test) | Qué valida | Resultado |
|---|-------------|------------|-----------|
| 1 | `test_sin_fuga_de_futuro` | Las features no contienen información del futuro | **PASA** |
| 2 | `test_adoptado_reglas` | Menor-mejor/mayor-mejor deciden campeón vs candidato | **PASA** |
| 3 | `test_modelo_peor_no_reemplaza_al_campeon` | Un candidato peor no reemplaza al campeón | **PASA** |
| 4 | `test_metrica_test_no_es_perfecta_por_fuga` | El AutoML de regresión no filtra el objetivo | **PASA** |

- **Comando:** `venv/Scripts/python -m pytest tests/ -v`
- **Evidencia:** `final/evidencias/pruebas/unitarias/`

## Suite 9 — tests/service/test_validacion_tipos.py

- **Módulo bajo prueba:** spc.service.validacion_tipos
- **Qué se prueba:** Validación de tipos por columna del canal v3: fecha que sea fecha, numérica que sea número; rechazo con detalle por columna/fila antes del motor.
- **Técnica:** Partición de equivalencias sobre tipos válidos/ inválidos por columna.

| # | Caso (test) | Qué valida | Resultado |
|---|-------------|------------|-----------|
| 1 | `test_dataset_valido_no_lanza` | Datos con tipos correctos pasan | **PASA** |
| 2 | `test_fecha_no_parseable_es_rechazada_con_detalle` | Fecha no parseable → error de tipo con detalle | **PASA** |
| 3 | `test_numerica_con_texto_es_rechazada` | Texto en columna numérica → error de tipo | **PASA** |

- **Comando:** `venv/Scripts/python -m pytest tests/ -v`
- **Evidencia:** `final/evidencias/pruebas/unitarias/`

## Suite 10 — tests/persistencia/ (corpus, modelos, auth, migraciones)

- **Módulo bajo prueba:** spc.service.repositorio_corpus / repositorio_modelos / repositorio_auth; migraciones Alembic
- **Qué se prueba:** Capa de datos sobre SQLite temporal: corpus idempotente, versionado y adopción de modelos con artefacto en disco, siembra de auth (admin + demo) y que 'alembic upgrade head' crea el esquema del ORM.
- **Técnica:** Integración con base aislada por test; storage de Supabase deshabilitado (fallback a disco).

| # | Caso (test) | Qué valida | Resultado |
|---|-------------|------------|-----------|
| 1 | `test_reinsertar_es_idempotente` | Reenviar misma serie+fecha no duplica (keep-first) | **PASA** |
| 2 | `test_solo_una_version_servida_por_tarea` | Solo una versión is_serving por (tenant,dominio,tarea) | **PASA** |
| 3 | `test_cargar_adoptado_round_trip` | El modelo guardado se recupera igual desde disco | **PASA** |
| 4 | `test_siembra_admin_y_cuentas_demo` | Admin + cuentas 256317/256370 con contraseña hasheada | **PASA** |
| 5 | `test_upgrade_head_crea_todas_las_tablas` | Migraciones crean todas las tablas del ORM + alembic_version | **PASA** |

- **Comando:** `venv/Scripts/python -m pytest tests/ -v`
- **Evidencia:** `final/evidencias/pruebas/unitarias/`
