"""Genera el Documento de Pruebas Documentadas de la Experimentación (ML) del SPC.

Formaliza los experimentos de modelado como pruebas documentadas: cada bloque declara
hipótesis, diseño (validación temporal, semilla 42, anti-fuga), métrica, resultado y
decisión. Las cifras se **transcriben** de los reportes ya escritos en ``docs/`` y de la
metadata en ``models/`` (no se recalculan aquí), citando la fuente. Emite ``.docx`` + ``.md``
desde la lista ``EXPERIMENTOS`` (única fuente de verdad), con el estilo de ``_docx_estilo``.

Uso:
    python scripts/gen_pruebas_experimentacion.py

Salida:
    final/Pruebas de Experimentacion SPC.docx
    final/Pruebas de Experimentacion SPC.md
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _docx_estilo as est  # noqa: E402

DISENO_COMUN = (
    "Validación TEMPORAL (entrenar con el pasado, evaluar con el futuro); selección en "
    "VALID, TEST se mide una sola vez; sin fuga de datos (umbrales/transformaciones fijados "
    "solo en TRAIN); semilla = 42; reproducible."
)

# ================================================================================
# Experimentos (única fuente de verdad; cifras transcritas de docs/ y models/)
# ================================================================================
EXPERIMENTOS: list[dict] = [
    {
        "num": 1,
        "titulo": "Selección del modelo de regresión de ventas (Fase 2a, Favorita)",
        "objetivo": "Pronosticar unidades vendidas (sales) con exceso de ceros (~31 %).",
        "hipotesis": "Un ensemble de boosters con objetivos para conteos (Tweedie/Poisson) supera al mejor pronóstico ingenuo (naïve estacional / media móvil).",
        "diseno": DISENO_COMUN + " Métrica guía: WAPE honesto (recursivo). Se comparan 7 modelos + 2 baselines.",
        "metrica": "WAPE (menor = mejor), con MAE/RMSE/RMSLE de apoyo.",
        "tabla": [
            ["Modelo / fuente", "WAPE %", "MAE", "RMSE"],
            ["LightGBM_Tweedie (mejor individual, TEST teacher-forced)", "12.41", "57.96", "197.09"],
            ["Ensemble XGB+XGB_Tweedie+LGBM+LGBM_Poisson (honesto recursivo)", "14.59", "68.15", "235.73"],
            ["BASELINE naive_estacional(t-7)", "20.67", "96.54", "348.38"],
            ["BASELINE media_movil_7", "23.26", "108.66", "359.82"],
        ],
        "resultado": "El ensemble (elegido por menor WAPE honesto sobre VALID: 12.18 % vs 14.25 % del mejor individual) da WAPE honesto 14.59 % frente al mejor baseline 20.67 %.",
        "decision": "SE ADOPTA el ensemble: mejora 6.08 puntos de WAPE (−29 % de MAE, −32 % de RMSE) sobre el baseline. Ridge se retira (no apto). Artefacto regresion_v3.",
        "fuente": "docs/reporte_regresion_2a.md",
    },
    {
        "num": 2,
        "titulo": "Aumento de datos con SMOTE en clasificación desbalanceada (experimento medido)",
        "objetivo": "Medir si SMOTE (SMOTENC) mejora la detección de la clase minoritaria demanda_alta (desbalance ~1:3.5).",
        "hipotesis": "Sintetizar ejemplos de la minoritaria (SMOTE) mejora la PR-AUC frente a no remuestrear o a costo-sensible.",
        "diseno": DISENO_COMUN + " SMOTE solo sobre el TRAIN de cada fold (imblearn.Pipeline); un test verifica que VALID conserva su prevalencia. Tolerancia de PR-AUC fijada de antemano = 0.005.",
        "metrica": "PR-AUC en VALID (principal para la minoritaria, independiente del umbral).",
        "tabla": [
            ["Estrategia", "PR-AUC (VALID)", "ROC-AUC (VALID)"],
            ["sin_remuestreo (elegida)", "0.9330", "0.9556"],
            ["costo_sensible", "0.9331", "0.9556"],
            ["smote (SMOTENC)", "0.9327", "0.9551"],
        ],
        "resultado": "Las tres estrategias difieren en < 0.001 de PR-AUC (dentro de la tolerancia). SMOTE no supera a la base ni a la costo-sensible, y costaba ~20 min vs ~30 s.",
        "decision": "NO SE ADOPTA SMOTE. Se elige la estrategia más simple dentro de la tolerancia (sin_remuestreo). Mostrar con números que el aumento de datos no aporta ES el entregable del experimento.",
        "fuente": "docs/fase-3/experimento_aumento_datos.md; models/clasificacion_v1.meta.json",
    },
    {
        "num": 3,
        "titulo": "Mejor objetivo de regresión en almacén: fórmula vs demanda futura (Fase 2e)",
        "objetivo": "Evitar que el modelo prediga una identidad trivial (dias_de_cobertura = stock/demanda).",
        "hipotesis": "Cambiar el objetivo a la demanda futura (demanda_dia) da una tarea con señal real y aprendible.",
        "diseno": DISENO_COMUN + " Anti-fuga: la media de demanda y la cobertura contienen el consumo del día → se usan solo con retraso o se excluyen.",
        "metrica": "R² y WAPE sobre la demo (semilla 42).",
        "tabla": [
            ["Objetivo", "¿Aprende?", "R²", "WAPE %"],
            ["dias_de_cobertura (antes)", "No (≈ fórmula)", "—", "—"],
            ["demanda_dia (ahora)", "Sí", "0.84", "16.4"],
        ],
        "resultado": "Con demanda_dia el modelo aprende señal real (R²=0.84, no 1.0), y los KPIs de inventario (cobertura, punto de reposición, stock de seguridad) se derivan del pronóstico.",
        "decision": "SE ADOPTA demanda_dia como objetivo de almacén (mayor valor de negocio). Bloque indicadores_inventario en /v2/almacen.",
        "fuente": "docs/reporte_mejoras_modelos.md (Fase 2)",
    },
    {
        "num": 4,
        "titulo": "Clustering honesto de proveedores (fin de la circularidad, Fase 3c)",
        "objetivo": "Evitar auto-engaño: antes los proveedores se fabricaban en 3 cajas fijas y el modelo 'descubría' esas 3 cajas.",
        "hipotesis": "Generando proveedores desde rangos continuos con solape, los grupos emergen de los datos y k lo decide el modelo (mejor silueta).",
        "diseno": "Datos sintéticos con arquetipos continuos (no cajas). k por mejor silueta en compras; k=3 fijo en almacén por interpretación ABC de negocio.",
        "metrica": "Silueta (−1..1, mayor = grupos más separados) + interpretación de cada grupo.",
        "tabla": [
            ["Clustering", "Antes", "Ahora", "Lectura"],
            ["Compras (proveedores)", "k=3, silueta 0.586", "k=2, silueta 0.383", "Más realista; solape"],
            ["Almacén (SKU, ABC)", "k=2 auto", "k=3 fijo, silueta 0.406", "Interpretación A/B/C"],
        ],
        "resultado": "La silueta BAJA es la prueba de que los datos son más realistas (continuo, no fronteras duras). La segmentación sigue siendo accionable para priorizar.",
        "decision": "SE ADOPTA el clustering desde continuo (k automático en compras) y k=3 A/B/C en almacén. Se documenta la silueta real sin inflarla.",
        "fuente": "docs/reporte_mejoras_modelos.md (Fase 3)",
    },
    {
        "num": 5,
        "titulo": "Evaluación offline 3×3: los 9 modelos vs baseline (Fase 4, ADR-0025)",
        "objetivo": "Demostrar con números que cada uno de los 9 modelos (3 dominios × 3 tareas) aporta, no solo que corre.",
        "hipotesis": "Cada regresión gana a su baseline; cada clasificación supera al azar (prevalencia); cada clustering da grupos interpretables.",
        "diseno": DISENO_COMUN + " Datasets grandes (8 tiendas, un año; 20 proveedores). Reproducible con scripts/evaluar_modelos.py.",
        "metrica": "Regresión: WAPE vs baseline. Clasificación: PR-AUC/ROC-AUC/F1 vs prevalencia. Clustering: k + silueta.",
        "tabla": [
            ["Dominio · tarea", "Métrica modelo", "Referencia", "Veredicto"],
            ["Ventas · regresión (WAPE)", "10.3 %", "baseline 20.6 %", "✅ 50.8 % mejor"],
            ["Compras · regresión (WAPE)", "8.5 %", "baseline 13.5 %", "✅ 37.0 % mejor"],
            ["Almacén · regresión (WAPE)", "16.1 %", "baseline 22.4 %", "✅ 28.3 % mejor"],
            ["Ventas · demanda_alta (F1 / PR-AUC)", "0.905 / 0.972", "azar 0.371", "✅"],
            ["Compras · entrega_con_retraso (F1 / PR-AUC)", "0.667 / 0.602", "azar 0.231", "✅"],
            ["Almacén · riesgo_quiebre (recall / PR-AUC)", "0.821 / 0.666", "azar 0.026", "✅ (evento raro)"],
            ["Ventas · clustering (k / silueta)", "3 / 0.331", "—", "grupos por volumen"],
            ["Compras · clustering (k / silueta)", "2 / 0.445", "—", "velocidad vs costo"],
            ["Almacén · clustering (k / silueta)", "3 / 0.414", "—", "ABC por demanda"],
        ],
        "resultado": "9/9 modelos aportan: las 3 regresiones ganan al baseline (28–51 %); las 3 clasificaciones superan de largo al azar; los 3 clusterings dan grupos accionables. Punto flojo declarado: riesgo_quiebre (evento raro → precisión baja, recall alto).",
        "decision": "SE VALIDA el rediseño 3×3. Además se arregló el umbral de 'entrega con retraso' (recall ~0.04 → 0.85).",
        "fuente": "docs/reporte_mejoras_modelos.md (Fase 4); scripts/evaluar_modelos.py",
    },
]

FIGURAS = (
    "Figuras de apoyo en figures/: 11_balance_clases_demanda.png (desbalance), "
    "18_segmentacion_tiendas_kmeans.png (clustering), 19_silueta_k_tiendas.png (silueta vs k), "
    "distribuciones y estacionalidad del EDA."
)


def _tabla_docx(doc, filas: list[list[str]]) -> None:
    """Inserta una tabla de resultados con cabecera azul oscuro."""
    tabla = doc.add_table(rows=0, cols=len(filas[0]))
    tabla.style = "Table Grid"
    cab = tabla.add_row().cells
    for celda, txt in zip(cab, filas[0]):
        est.texto(celda, txt, negrita=True, blanco=True)
        est.sombrear(celda, est.AZUL_OSCURO)
    for fila in filas[1:]:
        celdas = tabla.add_row().cells
        for celda, valor in zip(celdas, fila):
            est.texto(celda, str(valor))


def construir_docx(destino: Path) -> None:
    doc = est.nuevo_documento()
    est.portada(
        doc,
        "PRUEBAS DOCUMENTADAS DE LA EXPERIMENTACIÓN",
        [
            "Tipo: Experimentos de modelado (ML) documentados",
            "Diseño: validación temporal, semilla 42, sin fuga de datos",
            f"Total de Experimentos: {len(EXPERIMENTOS)}",
        ],
    )
    est.tabla_indice(
        doc,
        "Índice de Experimentos",
        ["N°", "Experimento", "Decisión"],
        [[e["num"], e["titulo"], "Adoptado" if "SE ADOPTA" in e["decision"] or "SE VALIDA" in e["decision"] else "No adoptado"]
         for e in EXPERIMENTOS],
    )

    for e in EXPERIMENTOS:
        tabla = est.nueva_tabla(doc)
        est.fila_titulo(tabla, f"Experimento {e['num']} — {e['titulo']}")
        est.fila_kv(tabla, "Objetivo", e["objetivo"])
        est.fila_kv(tabla, "Hipótesis", e["hipotesis"])
        est.fila_kv(tabla, "Diseño (leak-safe)", e["diseno"])
        est.fila_kv(tabla, "Métrica", e["metrica"])
        doc.add_paragraph()
        _tabla_docx(doc, e["tabla"])
        tabla2 = est.nueva_tabla(doc)
        est.fila_kv(tabla2, "Resultado", e["resultado"])
        est.fila_kv(tabla2, "Decisión", e["decision"], fondo_valor=est.VERDE_OK)
        est.fila_kv(tabla2, "Fuente (trazabilidad)", e["fuente"])
        doc.add_paragraph()
        if e["num"] != EXPERIMENTOS[-1]["num"]:
            doc.add_page_break()

    p = doc.add_paragraph()
    p.add_run("Evidencia gráfica. ").bold = True
    p.add_run(FIGURAS + " Salidas de las corridas en final/evidencias/pruebas/experimentacion/.")
    doc.save(str(destino))


def construir_md(destino: Path) -> None:
    L: list[str] = [
        "# Pruebas Documentadas de la Experimentación",
        "",
        f"**{est.SISTEMA}**",
        "",
        "- **Tipo:** Experimentos de modelado (ML) documentados",
        "- **Diseño:** validación temporal, selección en VALID, TEST una vez, sin fuga, semilla 42",
        f"- **Total de Experimentos:** {len(EXPERIMENTOS)}",
        f"- **{est.UNIVERSIDAD}**",
        "",
        "## Índice de Experimentos",
        "",
        "| N° | Experimento | Decisión |",
        "|----|-------------|----------|",
    ]
    for e in EXPERIMENTOS:
        dec = "Adoptado" if ("SE ADOPTA" in e["decision"] or "SE VALIDA" in e["decision"]) else "No adoptado"
        L.append(f"| {e['num']} | {e['titulo']} | {dec} |")
    L.append("")
    for e in EXPERIMENTOS:
        L.append(f"## Experimento {e['num']} — {e['titulo']}")
        L.append("")
        L.append(f"- **Objetivo:** {e['objetivo']}")
        L.append(f"- **Hipótesis:** {e['hipotesis']}")
        L.append(f"- **Diseño (leak-safe):** {e['diseno']}")
        L.append(f"- **Métrica:** {e['metrica']}")
        L.append("")
        cab = e["tabla"][0]
        L.append("| " + " | ".join(cab) + " |")
        L.append("|" + "|".join(["---"] * len(cab)) + "|")
        for fila in e["tabla"][1:]:
            L.append("| " + " | ".join(str(x) for x in fila) + " |")
        L.append("")
        L.append(f"- **Resultado:** {e['resultado']}")
        L.append(f"- **Decisión:** **{e['decision']}**")
        L.append(f"- **Fuente (trazabilidad):** {e['fuente']}")
        L.append("")
    L.append("---")
    L.append("")
    L.append(f"**Evidencia gráfica.** {FIGURAS}")
    L.append("")
    L.append("Salidas de las corridas en `final/evidencias/pruebas/experimentacion/`.")
    destino.write_text("\n".join(L), encoding="utf-8")


def main() -> None:
    final = Path(__file__).resolve().parent.parent / "final"
    construir_docx(final / "Pruebas de Experimentacion SPC.docx")
    construir_md(final / "Pruebas de Experimentacion SPC.md")
    print(f"OK  ->  {final / 'Pruebas de Experimentacion SPC.docx'}")
    print(f"OK  ->  {final / 'Pruebas de Experimentacion SPC.md'}")


if __name__ == "__main__":
    main()
