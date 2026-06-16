"""Script para entrenar modelos y mostrar metricas de los 3 modulos.

Ejecuta modelos de regresion, clasificacion y clustering, y muestra una tabla
comparativa de metricas (MAPE, WAPE, RMSE, R2, Accuracy, F1, Silhouette, etc.)
para cada modulo.

Uso:
    python scripts/run_models.py
    python scripts/run_models.py --sample-frac 0.1   # mas rapido
    python scripts/run_models.py --full               # sin muestreo (lento)
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Agregar src/ al path para imports directos
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pandas as pd

from spc.config import Settings
from spc.data.integration import build_analytic_dataset
from spc.data.loaders import load_data
from spc.eda.analysis.clustering import clustering_features
from spc.models.clasificacion import train_classification_models
from spc.models.clustering import evaluate_clustering
from spc.models.regresion import train_regression_models


def _separator(title: str) -> str:
    """Genera separador visual para la consola."""
    return f"\n{'='*70}\n  {title}\n{'='*70}"


def run_all_models(settings: Settings, sample_frac: float = 0.3, test_days: int = 30) -> None:
    """Carga datos, entrena modelos para los 3 modulos y muestra metricas."""
    print("Cargando datos...")
    data = load_data(settings)

    print("Construyendo dataset analitico integrado...")
    analytic, _, _ = build_analytic_dataset(data, settings)
    print(f"  Dataset analitico: {len(analytic):,} filas x {analytic.shape[1]} columnas")

    # -------------------------------------------------------------------------
    # MODULO 1: REGRESION (predecir ventas)
    # -------------------------------------------------------------------------
    print(_separator("MODULO 1: REGRESION — Prediccion de Ventas (sales)"))
    print(f"  Muestreo: {sample_frac*100:.0f}% | Test: ultimos {test_days} dias")
    t0 = time.time()

    reg_results = train_regression_models(
        analytic, settings, sample_frac=sample_frac, test_days=test_days
    )

    print(f"  Entrenamiento completado en {time.time()-t0:.1f}s")
    print(f"  Filas train: {reg_results['n_train']:,} | Filas test: {reg_results['n_test']:,}")
    print(f"  Features usadas: {len(reg_results['features_used'])}")
    print()
    print("  METRICAS DE REGRESION:")
    print("  " + "-" * 66)
    _print_df(reg_results["metrics"], float_format="{:.4f}")

    # -------------------------------------------------------------------------
    # MODULO 2: CLASIFICACION (predecir demanda alta)
    # -------------------------------------------------------------------------
    print(_separator("MODULO 2: CLASIFICACION — Prediccion de Demanda Alta"))
    print(f"  Muestreo: {sample_frac*100:.0f}% | Test: ultimos {test_days} dias")
    t0 = time.time()

    clf_results = train_classification_models(
        analytic, settings, sample_frac=sample_frac, test_days=test_days
    )

    print(f"  Entrenamiento completado en {time.time()-t0:.1f}s")
    print(f"  Filas train: {clf_results['n_train']:,} | Filas test: {clf_results['n_test']:,}")
    print(f"  Features usadas: {len(clf_results['features_used'])}")
    print()
    print("  METRICAS DE CLASIFICACION:")
    print("  " + "-" * 66)
    _print_df(clf_results["metrics"], float_format="{:.4f}")

    # -------------------------------------------------------------------------
    # MODULO 3: CLUSTERING (segmentacion de tiendas y familias)
    # -------------------------------------------------------------------------
    print(_separator("MODULO 3: CLUSTERING — Segmentacion"))
    t0 = time.time()

    store_features, family_features = clustering_features(analytic, settings)
    clust_results = evaluate_clustering(store_features, family_features, settings)

    print(f"  Evaluacion completada en {time.time()-t0:.1f}s")
    print()
    print("  METRICAS DE CLUSTERING:")
    print("  " + "-" * 66)
    _print_df(clust_results["metrics"], float_format="{:.4f}")

    # -------------------------------------------------------------------------
    # RESUMEN CONSOLIDADO
    # -------------------------------------------------------------------------
    print(_separator("RESUMEN CONSOLIDADO DE METRICAS"))
    _print_summary(reg_results, clf_results, clust_results)

    # Guardar metricas a CSV
    _save_metrics(reg_results, clf_results, clust_results, settings)


def _print_df(df: pd.DataFrame, float_format: str = "{:.4f}") -> None:
    """Imprime un DataFrame formateado."""
    formatted = df.copy()
    for col in formatted.columns:
        if formatted[col].dtype in ("float64", "float32"):
            formatted[col] = formatted[col].apply(lambda x: float_format.format(x))
    print()
    print(formatted.to_string())
    print()


def _print_summary(reg: dict, clf: dict, clust: dict) -> None:
    """Imprime un resumen compacto de los mejores modelos por modulo."""
    print()
    # Mejor modelo de regresion (menor WAPE)
    reg_df = reg["metrics"]
    best_reg = reg_df["WAPE"].astype(float).idxmin()
    print(f"  Mejor modelo REGRESION (menor WAPE): {best_reg}")
    print(f"    MAPE={reg_df.loc[best_reg, 'MAPE']:.2f}%  "
          f"WAPE={reg_df.loc[best_reg, 'WAPE']:.2f}%  "
          f"RMSE={reg_df.loc[best_reg, 'RMSE']:.2f}  "
          f"MAE={reg_df.loc[best_reg, 'MAE']:.2f}  "
          f"R2={reg_df.loc[best_reg, 'R2']:.4f}")
    print()

    # Mejor modelo de clasificacion (mayor F1)
    clf_df = clf["metrics"]
    best_clf = clf_df["F1"].astype(float).idxmax()
    print(f"  Mejor modelo CLASIFICACION (mayor F1): {best_clf}")
    print(f"    Accuracy={clf_df.loc[best_clf, 'Accuracy']:.4f}  "
          f"Precision={clf_df.loc[best_clf, 'Precision']:.4f}  "
          f"Recall={clf_df.loc[best_clf, 'Recall']:.4f}  "
          f"F1={clf_df.loc[best_clf, 'F1']:.4f}  "
          f"AUC-ROC={clf_df.loc[best_clf, 'AUC-ROC']:.4f}")
    print()

    # Clustering
    clust_df = clust["metrics"]
    best_clust = clust_df["Silhouette"].astype(float).idxmax()
    print(f"  Mejor CLUSTERING (mayor Silhouette): {best_clust}")
    print(f"    Silhouette={clust_df.loc[best_clust, 'Silhouette']:.4f}  "
          f"Calinski-Harabasz={clust_df.loc[best_clust, 'Calinski-Harabasz']:.2f}  "
          f"Davies-Bouldin={clust_df.loc[best_clust, 'Davies-Bouldin']:.4f}")
    print()


def _save_metrics(reg: dict, clf: dict, clust: dict, settings: Settings) -> None:
    """Guarda las metricas en CSV para consulta posterior."""
    out_dir = settings.processed_dir
    reg["metrics"].to_csv(out_dir / "metricas_regresion.csv")
    clf["metrics"].to_csv(out_dir / "metricas_clasificacion.csv")
    clust["metrics"].to_csv(out_dir / "metricas_clustering.csv")
    print(f"  Metricas guardadas en: {out_dir}")
    print("    - metricas_regresion.csv")
    print("    - metricas_clasificacion.csv")
    print("    - metricas_clustering.csv")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Entrena modelos y muestra metricas de los 3 modulos (regresion, clasificacion, clustering)."
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
    args = parser.parse_args()

    settings = Settings(base_dir=args.base_dir) if args.base_dir else Settings()
    sample_frac = 1.0 if args.full else args.sample_frac

    print("=" * 70)
    print("  SISTEMA PREDICTIVO DE COMERCIALIZACION — METRICAS DE MODELOS")
    print("=" * 70)
    print()

    run_all_models(settings, sample_frac=sample_frac, test_days=args.test_days)


if __name__ == "__main__":
    main()
