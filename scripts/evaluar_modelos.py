"""Evaluación OFFLINE de los 9 modelos 3×3 vs. baselines — Fase 4 (ADR-0025).

Va **separado del endpoint en vivo**: aquí el tiempo NO importa, así que se usan datasets
**grandes** (8 tiendas, historial largo) y **validación temporal** (entrenar con el pasado,
evaluar con el futuro), sin fuga de datos. El objetivo es demostrar con números que cada
modelo **aporta** sobre un pronóstico ingenuo (baseline), no solo que "corre".

Qué mide, por dominio (ventas/compras/almacén):
- **Regresión**: WAPE y MAE del modelo COMPARADOS con baselines ingenuos —"predecir el
  último valor" (rezago 1) y "el mismo día de la semana pasada" (rezago 7, solo diarios)—.
  Backtest de un paso, leak-safe (features solo del pasado).
- **Clasificación**: precisión, recall, F1, PR-AUC y ROC-AUC en el umbral de operación del
  camino 3×3, frente al azar (la prevalencia).
- **Clustering**: silueta + interpretación de cada grupo (su centro y tamaño).

Uso::

    python scripts/evaluar_modelos.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_RAIZ = Path(__file__).resolve().parent.parent
if str(_RAIZ / "src") not in sys.path:
    sys.path.insert(0, str(_RAIZ / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.compose import ColumnTransformer  # noqa: E402
from sklearn.ensemble import HistGradientBoostingRegressor  # noqa: E402
from sklearn.impute import SimpleImputer  # noqa: E402
from sklearn.pipeline import Pipeline  # noqa: E402
from sklearn.preprocessing import OneHotEncoder  # noqa: E402

from spc.features.generico import columnas_lag_objetivo, construir_features  # noqa: E402
from spc.models.automl import cortes_adaptativos  # noqa: E402
from spc.models.zoo_liviano import (  # noqa: E402
    entrenar_clasificacion_liviana,
    entrenar_clustering,
)
from spc.service import dominios  # noqa: E402
from spc.synthetic import generar_dominio  # noqa: E402

SEED = 42

# Datasets GRANDES (offline): 8 tiendas y un año de historia; compras con muchos proveedores.
DATOS: dict[str, dict[str, int]] = {
    "ventas": dict(n_tiendas=8, n_productos=40, n_dias=365),
    "almacen": dict(n_tiendas=8, n_productos=40, n_dias=365),
    "compras": dict(n_proveedores=20, n_productos=20, n_ordenes_por_serie=52),
}


def _wape(actual: np.ndarray, pred: np.ndarray) -> float:
    actual = np.asarray(actual, dtype="float64")
    pred = np.asarray(pred, dtype="float64")
    denom = float(np.sum(np.abs(actual)))
    return float(np.sum(np.abs(actual - pred)) / denom) if denom else float("nan")


def _mae(actual: np.ndarray, pred: np.ndarray) -> float:
    return float(np.mean(np.abs(np.asarray(actual, "float64") - np.asarray(pred, "float64"))))


def backtest_regresion(dominio: str, df: pd.DataFrame) -> dict:
    """Backtest temporal de UN PASO: entrena con el pasado, evalúa el futuro; modelo vs baseline."""
    spec = dominios.config_de(dominio).spec_regresion
    obj = spec.objetivo
    df_feat, features, cats = construir_features(df, spec)
    lag_cols = columnas_lag_objetivo(features)
    df_feat = df_feat.dropna(subset=lag_cols).copy()  # descarta el calentamiento
    warm = [c for c in features if c.startswith(("tgt_", "feat_", "featkf_"))]
    df_feat[warm] = df_feat[warm].fillna(0.0)

    fechas = pd.to_datetime(df_feat[spec.col_fecha])
    cortes = cortes_adaptativos(fechas)
    m_tr = (fechas < cortes.test_ini).to_numpy()   # pasado = todo antes de TEST
    m_te = (fechas >= cortes.test_ini).to_numpy()   # futuro = TEST

    num = [f for f in features if f not in cats]
    pre = ColumnTransformer([
        ("cat", OneHotEncoder(handle_unknown="ignore"), cats),
        ("num", SimpleImputer(strategy="median"), num),
    ])
    modelo = Pipeline([
        ("pre", pre),
        ("gb", HistGradientBoostingRegressor(max_iter=300, learning_rate=0.06, random_state=SEED)),
    ])
    modelo.fit(df_feat.loc[m_tr, features], df_feat.loc[m_tr, obj].to_numpy())
    yte = df_feat.loc[m_te, obj].to_numpy()
    pred = modelo.predict(df_feat.loc[m_te, features])

    out = {
        "objetivo": obj,
        "n_test": int(m_te.sum()),
        "WAPE_modelo": _wape(yte, pred),
        "MAE_modelo": _mae(yte, pred),
        "WAPE_ultimo_valor": _wape(yte, df_feat.loc[m_te, "tgt_lag_1"].to_numpy()),
        "MAE_ultimo_valor": _mae(yte, df_feat.loc[m_te, "tgt_lag_1"].to_numpy()),
    }
    if "tgt_lag_7" in df_feat.columns:  # baseline "misma jornada de la semana pasada"
        b7 = df_feat.loc[m_te, "tgt_lag_7"].to_numpy()
        out["WAPE_semana_pasada"] = _wape(yte, b7)
        out["MAE_semana_pasada"] = _mae(yte, b7)
    return out


def eval_clasificacion(dominio: str, df: pd.DataFrame) -> dict:
    """Clasificación con la maquinaria 3×3 (umbral de operación fijado en validación)."""
    cfg = dominios.config_de(dominio)
    dfl = cfg.derivar_etiqueta(df)
    res = entrenar_clasificacion_liviana(dfl, cfg.spec_clasificacion, seed=SEED)
    met = {k: float(v) for k, v in res.metricas_test.items()}
    return {
        "etiqueta": cfg.etiqueta,
        "prevalencia": float(res.prevalencia),
        "umbral": float(res.umbral),
        "ganador": res.ganador,
        **met,
    }


def eval_clustering(dominio: str, df: pd.DataFrame) -> dict:
    """Clustering con el k del dominio (almacén k=3 A/B/C; ventas/compras automático)."""
    cfg = dominios.config_de(dominio)
    perfil = cfg.perfil_entidades(df)
    res = entrenar_clustering(
        perfil, cfg.clave_entidad, list(cfg.columnas_clustering), cfg.columna_volumen,
        seed=SEED, k_fijo=cfg.k_fijo,
        estilo_etiqueta=cfg.estilo_etiqueta, columna_etiqueta=cfg.columna_etiqueta,
    )
    cz = res.clusterizador
    grupos = [
        {
            "segmento": seg,
            "etiqueta": cz.etiquetas[seg],
            "n": cz.n_por_segmento.get(seg, 0),
            "centro": cz.centroides.get(seg, {}),
        }
        for seg in sorted(cz.etiquetas)
    ]
    return {
        "entidad": cfg.clave_entidad,
        "k": res.k,
        "silueta": res.silueta,
        "curva_silueta": res.curva_silueta,
        "grupos": grupos,
    }


def _mejora(wape_modelo: float, wape_base: float) -> str:
    if not np.isfinite(wape_modelo) or not np.isfinite(wape_base) or wape_base == 0:
        return "s/d"
    delta = (wape_base - wape_modelo) / wape_base * 100.0
    signo = "MEJORA" if wape_modelo < wape_base else "PEOR"
    return f"{signo} {delta:+.1f}% vs baseline"


def main() -> int:
    print(f"== Evaluación offline de los 9 modelos (semilla {SEED}) ==\n", flush=True)
    for dominio, params in DATOS.items():
        df = generar_dominio(dominio, seed=SEED, **params)
        print(f"### {dominio.upper()}  (filas={len(df)}, params={params})", flush=True)

        r = backtest_regresion(dominio, df)
        linea = (f"  REGRESION[{r['objetivo']}] n_test={r['n_test']}  "
                 f"WAPE modelo={r['WAPE_modelo']:.3f} | ultimo_valor={r['WAPE_ultimo_valor']:.3f}")
        if "WAPE_semana_pasada" in r:
            linea += f" | semana_pasada={r['WAPE_semana_pasada']:.3f}"
        print(linea, flush=True)
        print(f"    -> {_mejora(r['WAPE_modelo'], r['WAPE_ultimo_valor'])}"
              f"  (MAE modelo={r['MAE_modelo']:.2f} vs ultimo_valor={r['MAE_ultimo_valor']:.2f})", flush=True)

        c = eval_clasificacion(dominio, df)
        print(f"  CLASIFICACION[{c['etiqueta']}] prevalencia={c['prevalencia']:.3f} umbral={c['umbral']:.3f} "
              f"ganador={c['ganador']}", flush=True)
        print(f"    -> precision={c.get('Precision', float('nan')):.3f} recall={c.get('Recall', float('nan')):.3f} "
              f"F1={c.get('F1', float('nan')):.3f} PR_AUC={c.get('PR_AUC', float('nan')):.3f} "
              f"ROC_AUC={c.get('ROC_AUC', float('nan')):.3f}", flush=True)

        k = eval_clustering(dominio, df)
        print(f"  CLUSTERING[{k['entidad']}] k={k['k']} silueta={k['silueta']:.3f} curva={k['curva_silueta']}", flush=True)
        for g in k["grupos"]:
            centro = {kk: round(vv, 2) for kk, vv in g["centro"].items()}
            print(f"    grupo {g['segmento']} '{g['etiqueta']}' (n={g['n']}): {centro}", flush=True)
        print("", flush=True)

    print("LISTO_EVAL", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
