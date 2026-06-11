"""Entry point CLI para el modulo de modelado (usado por spc-models)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from spc.config import Settings


def cli(argv: list[str] | None = None) -> None:
    """Punto de entrada de linea de comandos para entrenar modelos y mostrar metricas."""
    parser = argparse.ArgumentParser(
        description="Entrena modelos y muestra metricas (regresion, clasificacion, clustering)."
    )
    parser.add_argument(
        "--base-dir", type=Path, default=None,
        help="Raiz del proyecto (contiene data/raw)."
    )
    parser.add_argument(
        "--sample-frac", type=float, default=0.3,
        help="Fraccion del dataset para entrenar (default: 0.3)."
    )
    parser.add_argument(
        "--test-days", type=int, default=30,
        help="Dias finales usados como test (default: 30)."
    )
    parser.add_argument(
        "--full", action="store_true",
        help="Usar 100%% del dataset (lento pero preciso)."
    )
    args = parser.parse_args(argv)

    settings = Settings(base_dir=args.base_dir) if args.base_dir else Settings()
    sample_frac = 1.0 if args.full else args.sample_frac

    # Import here to avoid slow imports at CLI parse time
    from spc.modeling.regression import train_regression_models
    from spc.modeling.classification_model import train_classification_models
    from spc.modeling.clustering_eval import evaluate_clustering
    from spc.features.integration import build_analytic_dataset
    from spc.analysis.clustering import clustering_features
    from spc.io.loaders import load_data

    print("Cargando datos...")
    data = load_data(settings)
    analytic, _, _ = build_analytic_dataset(data, settings)

    print("Entrenando modelos de REGRESION...")
    reg = train_regression_models(analytic, settings, sample_frac=sample_frac, test_days=args.test_days)
    print("Entrenando modelos de CLASIFICACION...")
    clf = train_classification_models(analytic, settings, sample_frac=sample_frac, test_days=args.test_days)
    print("Evaluando CLUSTERING...")
    store_f, family_f = clustering_features(analytic, settings)
    clust = evaluate_clustering(store_f, family_f, settings)

    print("\n" + "=" * 70)
    print("  METRICAS DE REGRESION")
    print("=" * 70)
    print(reg["metrics"].to_string())

    print("\n" + "=" * 70)
    print("  METRICAS DE CLASIFICACION")
    print("=" * 70)
    print(clf["metrics"].to_string())

    print("\n" + "=" * 70)
    print("  METRICAS DE CLUSTERING")
    print("=" * 70)
    print(clust["metrics"].to_string())

    # Guardar CSVs
    reg["metrics"].to_csv(settings.processed_dir / "metricas_regresion.csv")
    clf["metrics"].to_csv(settings.processed_dir / "metricas_clasificacion.csv")
    clust["metrics"].to_csv(settings.processed_dir / "metricas_clustering.csv")
    print(f"\nMetricas guardadas en {settings.processed_dir}")


if __name__ == "__main__":
    cli()
