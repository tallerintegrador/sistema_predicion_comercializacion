"""Genera el Documento de Pruebas Unitarias del sistema SPC.

Mismo formato que el de caja negra (portada + índice + un cuadro por suite), reutilizando
el estilo compartido de ``scripts/_docx_estilo.py``. La lista ``SUITES`` es la única fuente
de verdad y de ella se emiten el ``.docx`` y el ``.md``. Documenta las pruebas unitarias del
núcleo puro (métricas, serialización, núcleo ML, desbalance, política, dominios,
sintéticos, zoo, features, selección de modelo, validación de tipos) y las de persistencia.

Uso:
    python scripts/gen_pruebas_unitarias.py

Salida:
    final/Pruebas Unitarias SPC.docx
    final/Pruebas Unitarias SPC.md
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _docx_estilo as est  # noqa: E402

HW = (
    "Python 3.11 en entorno virtual del proyecto; pytest 8.3.4; scikit-learn 1.9, "
    "LightGBM/XGBoost, pandas 3.0, numpy 2.4, SQLAlchemy 2. Semilla fija = 42."
)
COMANDO = "venv/Scripts/python -m pytest tests/ -v"

# ================================================================================
# Suites unitarias (única fuente de verdad)
# ================================================================================
SUITES: list[dict] = [
    {
        "num": 1,
        "archivo": "tests/test_metrics.py",
        "modulo": "spc.utils.metrics",
        "que_prueba": "Fórmulas de métricas de regresión (WAPE/MAPE/RMSE/RMSLE), clasificación centrada en la minoritaria (PR-AUC, prevalencia, matriz de confusión) y clustering (silueta).",
        "tecnica": "Propiedad exacta y valores conocidos; casos borde (denominador cero, una sola clase, <2 clusters).",
        "casos": [
            ("test_wape_valor_conocido", "WAPE = Σ|error|/Σ|actual|×100 con un valor calculado a mano", "PASA"),
            ("test_wape_denominador_cero_es_nan", "Actuales todos en cero → WAPE = NaN (sin división por cero)", "PASA"),
            ("test_mape_excluye_ceros_del_actual", "MAPE ignora las filas con y_true=0 (zero-inflation)", "PASA"),
            ("test_evaluar_en_unidades_invierte_log1p", "Métricas se reportan en unidades (expm1), no en log", "PASA"),
            ("test_classification_metrics_min_una_sola_clase_pr_auc_nan", "Sin positivos, PR-AUC/ROC-AUC = NaN (no lanza)", "PASA"),
            ("test_matriz_confusion_cuenta_correcta", "TN/FP/FN/TP correctos al umbral 0.5", "PASA"),
            ("test_clustering_metrics_dos_grupos_separados", "Silueta > 0.9 con dos grupos bien separados", "PASA"),
        ],
    },
    {
        "num": 2,
        "archivo": "tests/test_serializacion.py",
        "modulo": "spc.utils.serializacion",
        "que_prueba": "Guardado/carga de artefactos joblib + JSON de metadatos adjunto; inyección de marca temporal y nombre; no mutación de los metadatos del llamador.",
        "tecnica": "Round-trip en carpeta temporal (tmp_path); verificación de igualdad y de efectos colaterales.",
        "casos": [
            ("test_round_trip_objeto_y_metadatos", "Lo guardado se recupera idéntico (objeto + metadatos)", "PASA"),
            ("test_inyecta_guardado_utc_y_nombre_artefacto", "Se inyecta guardado_utc y el nombre del artefacto; crea el directorio padre", "PASA"),
            ("test_no_muta_los_metadatos_del_llamador", "El dict de metadatos original no se modifica", "PASA"),
            ("test_cargar_sin_meta_devuelve_dict_vacio", "Artefacto sin .meta.json → metadatos = {}", "PASA"),
        ],
    },
    {
        "num": 3,
        "archivo": "tests/test_nucleo.py",
        "modulo": "spc.models.nucleo",
        "que_prueba": "Primitivas del motor de regresión: cortes temporales, zoo de 8 modelos (5 log + 3 unidades), conversión cruda→unidades, ensamble ponderado y pesos convexos que minimizan el MAE.",
        "tecnica": "Submodelos de mentira (fakes) para no entrenar; propiedades algebraicas exactas.",
        "casos": [
            ("test_cortes_temporales_as_dict", "as_dict() describe train/valid/test por fecha", "PASA"),
            ("test_construir_zoo_inventario_y_espacios", "8 regresores; Tweedie/Poisson en espacio 'unidades'", "PASA"),
            ("test_a_unidades_espacio_log_invierte_expm1_y_recorta", "Log-espacio → expm1 y recorte a ≥0", "PASA"),
            ("test_ensemble_promedia_ponderado_en_unidades", "Ensemble = combinación convexa exacta de submodelos", "PASA"),
            ("test_mejores_pesos_son_convexos", "Pesos ≥0, suman 1; el miembro fiel pesa más", "PASA"),
        ],
    },
    {
        "num": 4,
        "archivo": "tests/test_desbalance.py",
        "modulo": "spc.models.desbalance",
        "que_prueba": "Estrategias de desbalance (sin remuestreo / costo-sensible / SMOTE), selección de umbral en VALID (máx recall con piso real de precisión) y elección de la estrategia más simple que empata en PR-AUC.",
        "tecnica": "Construcción sin entrenar; datos separables sintéticos; regla de decisión con tolerancia.",
        "casos": [
            ("test_sin_remuestreo_es_booster_desnudo", "Estrategia base = LGBMClassifier sin peso", "PASA"),
            ("test_costo_sensible_inyecta_scale_pos_weight", "costo_sensible pasa scale_pos_weight", "PASA"),
            ("test_smote_es_pipeline_con_sampler_y_clf", "SMOTE = Pipeline [SMOTENC, clf]", "PASA"),
            ("test_estrategia_desconocida_lanza", "Nombre inválido → ValueError", "PASA"),
            ("test_umbral_respeta_piso_de_precision_con_separacion_perfecta", "Umbral elegido cumple precisión ≥ 0.80", "PASA"),
            ("test_empate_elige_la_mas_simple", "Empate en PR-AUC → gana sin_remuestreo", "PASA"),
            ("test_smote_gana_solo_si_supera_la_tolerancia", "SMOTE solo se adopta si supera la tolerancia", "PASA"),
        ],
    },
    {
        "num": 5,
        "archivo": "tests/test_politica.py",
        "modulo": "spc.service.politica",
        "que_prueba": "Fórmulas de stock de seguridad (coverage_days y service_level), fallback cuando σ no es estimable, y monotonía respecto a σ.",
        "tecnica": "Valores conocidos; ningún número vive en el módulo (todo entra por argumento).",
        "casos": [
            ("test_coverage_days_es_factor_por_demanda", "coverage_days = factor × demanda(lead)", "PASA"),
            ("test_service_level_usa_z_sigma_raiz_lead", "service_level = z·σ·√lead", "PASA"),
            ("test_service_level_cae_a_fallback_si_sigma_no_estimable", "σ=NaN → factor_fallback × demanda", "PASA"),
            ("test_metodo_desconocido_recae_en_coverage", "Método no reconocido usa coverage (seguro)", "PASA"),
            ("test_service_level_crece_con_sigma", "El colchón crece de forma monótona con σ", "PASA"),
        ],
    },
    {
        "num": 6,
        "archivo": "tests/test_dominios.py",
        "modulo": "spc.service.dominios",
        "que_prueba": "Configuración 3×3 por dominio: objetivo nunca es feature (anti-fuga), etiqueta derivada produce dos clases, perfil por entidad alimenta el clustering, y almacén usa k=3 (A/B/C).",
        "tecnica": "Datos del generador sintético; propiedades de las tres tareas por dominio.",
        "casos": [
            ("test_config_de_dominio_desconocido_lanza", "Dominio inválido → KeyError", "PASA"),
            ("test_objetivo_no_es_feature_anti_fuga", "El objetivo de regresión no aparece como feature", "PASA"),
            ("test_derivar_etiqueta_produce_dos_clases", "Etiqueta de clasificación con ambas clases (ventas/compras/almacen)", "PASA"),
            ("test_perfil_entidades_indexado_por_clave", "Una fila por entidad; columnas de clustering presentes", "PASA"),
            ("test_almacen_usa_k_fijo_tres_abc", "Almacén fija k=3 con estilo de etiqueta A/B/C", "PASA"),
        ],
    },
    {
        "num": 7,
        "archivo": "tests/test_sinteticos.py",
        "modulo": "spc.synthetic",
        "que_prueba": "Generadores de datos por dominio: conformidad de esquema, reproducibilidad (semilla 42), columnas calculadas coherentes (ingreso, costo_total, cumplimiento) y señal para los tres modelos.",
        "tecnica": "Comparación de DataFrames; verificación de banderas 0/1 y de dos clases en las etiquetas.",
        "casos": [
            ("test_reproducible_misma_semilla", "Misma semilla → filas idénticas", "PASA"),
            ("test_ventas_correcciones", "ingreso = unidades × precio; banderas 0/1", "PASA"),
            ("test_compras_correcciones", "costo_total y cumplimiento calculados y coherentes", "PASA"),
            ("test_almacen_objetivo_es_demanda_dia", "Objetivo de almacén = demanda_dia (aprendible)", "PASA"),
            ("test_dominio_desconocido_lanza", "Dominio inválido → KeyError", "PASA"),
        ],
    },
    {
        "num": 8,
        "archivo": "tests/test_zoo_liviano.py / test_features_generico.py / test_seleccion_modelo.py / test_automl_no_fuga.py",
        "modulo": "spc.models.zoo_liviano, spc.features.generico, spc.service.seleccion_modelo, spc.models.automl",
        "que_prueba": "Zoo sklearn liviano (9 modelos 3×3), ingeniería de features sin fuga, regla quédate-con-el-mejor (campeón vs retador) y guarda anti-fuga del AutoML de regresión.",
        "tecnica": "Entrenamiento liviano determinista (semilla 42); verificación de no-fuga train/valid/test.",
        "casos": [
            ("test_sin_fuga_de_futuro", "Las features no contienen información del futuro", "PASA"),
            ("test_adoptado_reglas", "Menor-mejor/mayor-mejor deciden campeón vs candidato", "PASA"),
            ("test_modelo_peor_no_reemplaza_al_campeon", "Un candidato peor no reemplaza al campeón", "PASA"),
            ("test_metrica_test_no_es_perfecta_por_fuga", "El AutoML de regresión no filtra el objetivo", "PASA"),
        ],
    },
    {
        "num": 9,
        "archivo": "tests/service/test_validacion_tipos.py",
        "modulo": "spc.service.validacion_tipos",
        "que_prueba": "Validación de tipos por columna del canal v3: fecha que sea fecha, numérica que sea número; rechazo con detalle por columna/fila antes del motor.",
        "tecnica": "Partición de equivalencias sobre tipos válidos/ inválidos por columna.",
        "casos": [
            ("test_dataset_valido_no_lanza", "Datos con tipos correctos pasan", "PASA"),
            ("test_fecha_no_parseable_es_rechazada_con_detalle", "Fecha no parseable → error de tipo con detalle", "PASA"),
            ("test_numerica_con_texto_es_rechazada", "Texto en columna numérica → error de tipo", "PASA"),
        ],
    },
    {
        "num": 10,
        "archivo": "tests/persistencia/ (corpus, modelos, auth, migraciones)",
        "modulo": "spc.service.repositorio_corpus / repositorio_modelos / repositorio_auth; migraciones Alembic",
        "que_prueba": "Capa de datos sobre SQLite temporal: corpus idempotente, versionado y adopción de modelos con artefacto en disco, siembra de auth (admin + demo) y que 'alembic upgrade head' crea el esquema del ORM.",
        "tecnica": "Integración con base aislada por test; storage de Supabase deshabilitado (fallback a disco).",
        "casos": [
            ("test_reinsertar_es_idempotente", "Reenviar misma serie+fecha no duplica (keep-first)", "PASA"),
            ("test_solo_una_version_servida_por_tarea", "Solo una versión is_serving por (tenant,dominio,tarea)", "PASA"),
            ("test_cargar_adoptado_round_trip", "El modelo guardado se recupera igual desde disco", "PASA"),
            ("test_siembra_admin_y_cuentas_demo", "Admin + cuentas 256317/256370 con contraseña hasheada", "PASA"),
            ("test_upgrade_head_crea_todas_las_tablas", "Migraciones crean todas las tablas del ORM + alembic_version", "PASA"),
        ],
    },
]


def construir_docx(destino: Path) -> None:
    doc = est.nuevo_documento()
    total = sum(len(s["casos"]) for s in SUITES)
    est.portada(
        doc,
        "DOCUMENTO DE PRUEBAS UNITARIAS",
        [
            "Tipo de Prueba: Unitaria / de Integración (capa de datos)",
            "Marco: pytest 8.3.4",
            f"Total de Suites: {len(SUITES)}   |   Casos documentados: {total}",
        ],
    )
    est.tabla_indice(
        doc,
        "Índice de Suites de Prueba",
        ["N°", "Archivo", "Módulo bajo prueba", "Casos"],
        [[s["num"], s["archivo"], s["modulo"], str(len(s["casos"]))] for s in SUITES],
    )

    for s in SUITES:
        tabla = est.nueva_tabla(doc)
        est.fila_titulo(tabla, f"Suite {s['num']} — {s['archivo']}")
        est.fila_kv(tabla, "Módulo bajo prueba", s["modulo"])
        est.fila_kv(tabla, "Qué se prueba", s["que_prueba"])
        est.fila_kv(tabla, "Técnica", s["tecnica"])
        est.fila_seccion(tabla, "CASOS DE PRUEBA")
        for i, (nombre, valida, resultado) in enumerate(s["casos"], 1):
            est.fila_kv(tabla, f"{i}. {nombre}", f"{valida}\n→ Resultado: {resultado}",
                        fondo_valor=est.VERDE_OK)
        est.fila_seccion(tabla, "CONFIGURACIÓN")
        est.fila_kv(tabla, "Hardware y Software", HW)
        est.fila_kv(tabla, "Comando de ejecución", COMANDO)
        est.fila_kv(tabla, "Evidencia", "Ver final/evidencias/pruebas/unitarias/")
        doc.add_paragraph()
        if s["num"] != SUITES[-1]["num"]:
            doc.add_page_break()

    doc.save(str(destino))


def construir_md(destino: Path) -> None:
    total = sum(len(s["casos"]) for s in SUITES)
    L: list[str] = [
        "# Documento de Pruebas Unitarias",
        "",
        f"**{est.SISTEMA}**",
        "",
        "- **Tipo de Prueba:** Unitaria / de Integración (capa de datos)",
        "- **Marco:** pytest 8.3.4",
        f"- **Total de Suites:** {len(SUITES)} — **Casos documentados:** {total}",
        f"- **{est.UNIVERSIDAD}**",
        "",
        "## Índice de Suites de Prueba",
        "",
        "| N° | Archivo | Módulo bajo prueba | Casos |",
        "|----|---------|--------------------|-------|",
    ]
    for s in SUITES:
        L.append(f"| {s['num']} | {s['archivo']} | {s['modulo']} | {len(s['casos'])} |")
    L.append("")
    for s in SUITES:
        L.append(f"## Suite {s['num']} — {s['archivo']}")
        L.append("")
        L.append(f"- **Módulo bajo prueba:** {s['modulo']}")
        L.append(f"- **Qué se prueba:** {s['que_prueba']}")
        L.append(f"- **Técnica:** {s['tecnica']}")
        L.append("")
        L.append("| # | Caso (test) | Qué valida | Resultado |")
        L.append("|---|-------------|------------|-----------|")
        for i, (nombre, valida, resultado) in enumerate(s["casos"], 1):
            L.append(f"| {i} | `{nombre}` | {valida} | **{resultado}** |")
        L.append("")
        L.append(f"- **Comando:** `{COMANDO}`")
        L.append("- **Evidencia:** `final/evidencias/pruebas/unitarias/`")
        L.append("")
    destino.write_text("\n".join(L), encoding="utf-8")


def main() -> None:
    final = Path(__file__).resolve().parent.parent / "final"
    construir_docx(final / "Pruebas Unitarias SPC.docx")
    construir_md(final / "Pruebas Unitarias SPC.md")
    print(f"OK  ->  {final / 'Pruebas Unitarias SPC.docx'}")
    print(f"OK  ->  {final / 'Pruebas Unitarias SPC.md'}")


if __name__ == "__main__":
    main()
