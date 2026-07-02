"""Orquestacion del pipeline de EDA (equivalente al antiguo `eda.main`).

`run_pipeline` ejecuta todo el flujo A-J en orden y devuelve un resumen. `cli`
expone el mismo flujo por linea de comandos (entry point ``spc-eda``).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np

from spc.config import Settings
from spc.data.integration import build_analytic_dataset
from spc.data.loaders import check_files, load_data
from spc.eda.analysis.classification import classification_analysis
from spc.eda.analysis.clustering import clustering_features, run_kmeans_segmentation
from spc.eda.analysis.correlation import correlation_analysis
from spc.eda.analysis.relational import relational_analysis
from spc.eda.analysis.target import analyze_sales
from spc.eda.analysis.temporal import temporal_analysis
from spc.eda.analysis.univariate import analyze_univariate
from spc.eda.quality.checks import build_observations, quality_checks
from spc.eda.quality.profiling import build_profiles
from spc.eda.reporting.notebook import create_notebook
from spc.eda.reporting.report import generate_report
from spc.eda.viz.figures import FigureContext, build_all_figures
from spc.utils.logging import configure_logging, get_logger

log = get_logger("pipeline")

# Columnas usadas en la segmentacion KMeans (se conservan del script original).
_STORE_SEG_COLS = [
    "ventas_total",
    "venta_media",
    "venta_mediana",
    "promociones_media",
    "transacciones_media",
    "pct_demanda_alta",
    "familias_activas",
]
_FAMILY_SEG_COLS = ["ventas_total", "venta_media", "promociones_media", "pct_demanda_alta"]


def run_pipeline(
    settings: Settings | None = None,
    *,
    make_notebook: bool = True,
    verbose: bool = False,
) -> dict[str, Any]:
    """Ejecuta el EDA completo: carga, calidad, analisis, figuras, reporte y notebook."""
    configure_logging(verbose)
    settings = settings or Settings()
    np.random.seed(settings.random_seed)
    settings.ensure_dirs()

    log.info("Iniciando pipeline EDA (base=%s)", settings.base_dir)
    file_check = check_files(settings)
    data = load_data(settings)

    profiles, missing = build_profiles(data, settings)
    quality = quality_checks(data, settings)
    observations = build_observations(profiles, missing, quality)

    sales = analyze_sales(data["train"], settings)
    univariate = analyze_univariate(data, settings)
    temporal = temporal_analysis(data["train"], data["holidays_events"], settings)

    analytic, integration, catalog = build_analytic_dataset(data, settings)
    relational = relational_analysis(analytic, settings)
    corr, signal = correlation_analysis(analytic, settings)
    classification = classification_analysis(analytic, settings)

    store_features, family_features = clustering_features(analytic, settings)
    store_seg = run_kmeans_segmentation(
        store_features, _STORE_SEG_COLS, range(2, 9), "tiendas", settings
    )
    family_seg = run_kmeans_segmentation(
        family_features, _FAMILY_SEG_COLS, range(2, 7), "familias", settings
    )

    ctx = FigureContext(
        train=data["train"],
        sales=sales,
        temporal=temporal,
        relational=relational,
        corr=corr,
        classes=classification["classes"],
        analytic=analytic,
        store_seg=store_seg,
        seed=settings.random_seed,
    )
    figures = build_all_figures(ctx, settings)

    generate_report(
        file_check=file_check,
        profiles=profiles,
        missing=missing,
        observations=observations,
        quality=quality,
        sales_analysis=sales,
        univariate=univariate,
        temporal=temporal,
        integration=integration,
        catalog=catalog,
        relational=relational,
        corr=corr,
        signal=signal,
        classification=classification,
        store_features=store_features,
        family_features=family_features,
        store_seg=store_seg,
        family_seg=family_seg,
        figures=figures,
        settings=settings,
    )
    if make_notebook:
        create_notebook(settings)

    summary = {
        "archivos": file_check.to_dict(orient="records"),
        "perfil": profiles.to_dict(orient="records"),
        "calidad": quality,
        "integracion": integration,
        "clasificacion_ratio": classification["ratio_desbalance"],
        "clustering_tiendas_k": store_seg["best_k"],
        "clustering_tiendas_silueta": store_seg["best_sil"],
        "clustering_familias_k": family_seg["best_k"],
        "n_figuras": len(figures),
        "reporte": str(settings.report_path),
        "notebook": str(settings.notebook_path) if make_notebook else None,
    }
    log.info("Pipeline completo: %d figuras, reporte en %s", len(figures), settings.report_path)
    return summary


def cli(argv: list[str] | None = None) -> None:
    """Punto de entrada de linea de comandos."""
    parser = argparse.ArgumentParser(
        description="Ejecuta el EDA del Sistema Predictivo de Comercializacion."
    )
    parser.add_argument(
        "--base-dir",
        type=Path,
        default=None,
        help="Raiz del proyecto (contiene data/raw). Por defecto: directorio actual.",
    )
    parser.add_argument("--no-notebook", action="store_true", help="No regenerar el notebook.")
    parser.add_argument("-v", "--verbose", action="store_true", help="Logging en nivel DEBUG.")
    args = parser.parse_args(argv)

    settings = Settings(base_dir=args.base_dir) if args.base_dir else Settings()
    summary = run_pipeline(settings, make_notebook=not args.no_notebook, verbose=args.verbose)
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    cli()
