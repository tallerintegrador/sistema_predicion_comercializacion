"""Aptitud para clasificacion: objetivo `demanda_alta` y desbalance (tarea J)."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from spc.config import Settings
from spc.io.loaders import write_csv


def classification_analysis(analytic: pd.DataFrame, settings: Settings) -> dict[str, Any]:
    """Mide el desbalance del objetivo por familia y, como contraste, con umbral global."""
    # Objetivo principal: umbral P75 dentro de cada familia (evita sesgo de escala).
    classes = (
        analytic["demanda_alta"]
        .value_counts(dropna=False)
        .rename_axis("demanda_alta")
        .reset_index(name="filas")
    )
    classes["pct"] = classes["filas"] / len(analytic) * 100
    classes["demanda_alta"] = classes["demanda_alta"].map({False: "No", True: "Si"})
    write_csv(classes, settings.processed_dir / "clasificacion_demanda_alta.csv")

    # Alternativa: umbral P75 GLOBAL (ignora familia) para comparar desbalance.
    p75_global = float(analytic["sales"].quantile(0.75))
    alta_global = analytic["sales"] > p75_global
    classes_global = (
        alta_global.value_counts(dropna=False)
        .rename_axis("demanda_alta_global")
        .reset_index(name="filas")
    )
    classes_global["pct"] = classes_global["filas"] / len(analytic) * 100
    classes_global["demanda_alta_global"] = classes_global["demanda_alta_global"].map(
        {False: "No", True: "Si"}
    )
    write_csv(classes_global, settings.processed_dir / "clasificacion_umbral_global.csv")

    si = int(analytic["demanda_alta"].sum())
    no = int((~analytic["demanda_alta"]).sum())
    ratio = no / si if si else np.nan
    return {
        "classes": classes,
        "classes_global": classes_global,
        "p75_global": p75_global,
        "ratio_desbalance": ratio,
    }
