"""Servicio de **predicción agnóstica auto-entrenada** (ADR-0023).

Orquesta los tres dominios sobre el contrato agnóstico (`schema` + `rows`): traduce el
esquema declarado a `EspecEsquema`, **entrena el algoritmo ganador al vuelo** (o reusa
el cacheado si la data no cambió), pronostica/clasifica y aplica la política de stock.

No conoce HTTP (la API mapea). No conoce el algoritmo (lo elige `spc.models.automl`).
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from spc import config
from spc.api.schemas.agnostico import (
    AutoInventoryRequest,
    AutoPurchasesRequest,
    AutoSalesRequest,
    SchemaSpec,
)
from spc.features.generico import EspecEsquema
from spc.models import automl
from spc.service import politica
from spc.service.cache_agnostico import CacheModelosAgnosticos, firma_datos, firma_esquema
from spc.service.errores import SolicitudInvalida
from spc.utils.logging import get_logger

log = get_logger("service.agnostico")


# ===========================================================================
# Esquema declarado → EspecEsquema + DataFrame validado
# ===========================================================================
def construir_spec(schema: SchemaSpec, *, objetivo: str | None = None) -> EspecEsquema:
    """Traduce el ``SchemaSpec`` del contrato al ``EspecEsquema`` del motor genérico."""
    num_futuro = tuple(
        f.name for f in schema.features if f.type == "numeric" and f.known_future
    )
    num_pasado = tuple(
        f.name for f in schema.features if f.type == "numeric" and not f.known_future
    )
    cats = tuple(f.name for f in schema.features if f.type == "categorical")
    return EspecEsquema(
        objetivo=objetivo or schema.target,
        col_fecha=schema.date,
        cols_serie=tuple(schema.series_keys),
        num_conocidas_futuro=num_futuro,
        num_solo_pasado=num_pasado,
        cats_extra=cats,
    )


def _columnas_declaradas(schema: SchemaSpec) -> list[str]:
    cols = [schema.target, *schema.series_keys, *(f.name for f in schema.features)]
    if schema.date:
        cols.append(schema.date)
    return cols


def a_dataframe(rows: list[dict[str, Any]], schema: SchemaSpec) -> pd.DataFrame:
    """Construye el DataFrame validando que las columnas declaradas existan y coercionando tipos."""
    df = pd.DataFrame(rows)
    faltan = [c for c in _columnas_declaradas(schema) if c not in df.columns]
    if faltan:
        raise SolicitudInvalida(
            f"El esquema declara columnas ausentes en los datos: {', '.join(sorted(set(faltan)))}."
        )
    # Objetivo numérico (las ventas/etiqueta deben ser número).
    df[schema.target] = pd.to_numeric(df[schema.target], errors="coerce").astype("float64")
    if df[schema.target].isna().all():
        raise SolicitudInvalida(f"La columna objetivo '{schema.target}' no es numérica.")
    # Fecha a datetime (orden temporal honesto).
    if schema.date:
        df[schema.date] = pd.to_datetime(df[schema.date], errors="coerce")
        if df[schema.date].isna().any():
            raise SolicitudInvalida(f"La columna de fecha '{schema.date}' tiene valores no parseables.")
    # Numéricas a número; categóricas/series a texto.
    for f in schema.features:
        if f.type == "numeric":
            df[f.name] = pd.to_numeric(df[f.name], errors="coerce")
        else:
            df[f.name] = df[f.name].astype("string").astype("object")
    for k in schema.series_keys:
        df[k] = df[k].astype("string").astype("object")
    return df


# ===========================================================================
# Entrenar-o-reusar (caché)
# ===========================================================================
def _info(res_winner: str, trained_rows: int, metrics: dict, sig_esquema: str,
          candidates: dict | None = None, reused: bool = False) -> dict[str, Any]:
    return {
        "winner_algorithm": res_winner,
        "trained_rows": trained_rows,
        "honest_metrics": {k: round(float(v), 4) for k, v in (metrics or {}).items()
                           if v is not None and np.isfinite(v)},
        "candidates": candidates,
        "reused_cached_model": reused,
        "schema_signature": sig_esquema,
    }


def _resolver_regresion(
    df: pd.DataFrame, spec: EspecEsquema, schema_dict: dict, rows: list[dict],
    client_id: str, cache: CacheModelosAgnosticos | None, seed: int,
) -> tuple[Any, dict[str, Any]]:
    sig_e = firma_esquema("sales", schema_dict)
    sig_d = firma_datos(rows)
    if cache is not None:
        cacheado = cache.obtener(client_id, "sales", sig_e, sig_d)
        if cacheado is not None:
            predictor, info = cacheado
            return predictor, {**info, "reused_cached_model": True, "schema_signature": sig_e}
    res = automl.entrenar_regresion(df, spec, seed=seed)
    info = _info(res.ganador, res.n_filas, res.metricas_test, sig_e, candidates=res.candidatos)
    if cache is not None:
        cache.guardar(client_id, "sales", sig_e, sig_d, res.predictor, info)
    return res.predictor, info


# ===========================================================================
# Esqueleto futuro genérico (horizonte por serie, calendario/known-future fijados)
# ===========================================================================
def _esqueleto_futuro(
    df: pd.DataFrame, spec: EspecEsquema, horizonte: int,
    futuro: list[dict[str, Any]] | None,
) -> tuple[pd.DataFrame, pd.Timestamp, pd.Timestamp]:
    """Añade ``horizonte`` días futuros por serie (objetivo=0, known-future fijadas)."""
    fecha = spec.col_fecha
    ultima = pd.Timestamp(df[fecha].max())
    inicio, fin = ultima + pd.Timedelta(days=1), ultima + pd.Timedelta(days=horizonte)
    fechas_fut = pd.date_range(inicio, fin, freq="D")

    serie_cols = list(spec.cols_serie)
    series = df[serie_cols].drop_duplicates() if serie_cols else pd.DataFrame({"_u": [0]})

    # Índice de valores futuros conocidos provistos por el cliente (por serie+fecha).
    fut_idx: dict[tuple, dict] = {}
    if futuro:
        for r in futuro:
            try:
                f = pd.Timestamp(pd.to_datetime(r[fecha]))
            except Exception:  # noqa: BLE001
                continue
            clave = (*(str(r.get(k)) for k in serie_cols), f.normalize())
            fut_idx[clave] = r

    # Último valor categórico/extra por serie (se arrastra a futuro).
    cats_arrastre = list(spec.cats_extra)
    ultimos: dict[tuple, dict] = {}
    if serie_cols:
        for keys, g in df.groupby(serie_cols, observed=True):
            keys_t = keys if isinstance(keys, tuple) else (keys,)
            ultimos[tuple(str(k) for k in keys_t)] = g.iloc[-1].to_dict()
    else:
        ultimos[()] = df.iloc[-1].to_dict()

    filas: list[dict[str, Any]] = []
    for _, s in series.iterrows():
        clave_serie = tuple(str(s[k]) for k in serie_cols) if serie_cols else ()
        ult = ultimos.get(clave_serie, {})
        for f in fechas_fut:
            fila: dict[str, Any] = {fecha: f}
            for k in serie_cols:
                fila[k] = s[k]
            fila[spec.objetivo] = 0.0
            prov = fut_idx.get((*clave_serie, f.normalize()), {})
            for col in spec.num_conocidas_futuro:
                val = prov.get(col)
                fila[col] = float(val) if val is not None else 0.0
            for col in spec.num_solo_pasado:
                fila[col] = np.nan
            for col in cats_arrastre:
                fila[col] = prov.get(col, ult.get(col))
            filas.append(fila)

    futuro_df = pd.DataFrame(filas)
    completo = pd.concat([df, futuro_df[df.columns.intersection(futuro_df.columns)]], ignore_index=True)
    return completo, inicio, fin


def _agregar_granularidad(pred: pd.DataFrame, spec: EspecEsquema, granularidad: str) -> pd.DataFrame:
    """Agrega el pronóstico diario a week/month (suma); day lo deja igual."""
    if granularidad == "day":
        return pred
    fechas = pd.to_datetime(pred[spec.col_fecha])
    periodo = (fechas.dt.to_period("W") if granularidad == "week" else fechas.dt.to_period("M")).dt.start_time
    serie_cols = list(spec.cols_serie)
    g = pred.assign(**{spec.col_fecha: periodo}).groupby(
        serie_cols + [spec.col_fecha], observed=True, as_index=False
    )["prediccion"].sum()
    return g


# ===========================================================================
# Dominio SALES
# ===========================================================================
def pronosticar_ventas(
    req: AutoSalesRequest, *, client_id: str = "default",
    cache: CacheModelosAgnosticos | None = None, seed: int = 42,
) -> dict[str, Any]:
    schema = req.schema_spec
    spec = construir_spec(schema)
    if not spec.es_temporal:
        raise SolicitudInvalida("El pronóstico de ventas requiere declarar 'date' en el esquema.")
    df = a_dataframe(req.rows, schema)
    predictor, info = _resolver_regresion(
        df, spec, schema.model_dump(by_alias=True), req.rows, client_id, cache, seed
    )

    completo, inicio, fin = _esqueleto_futuro(df, spec, req.horizon, req.future)
    pred = predictor.pronosticar_horizonte(completo, inicio, fin)
    pred = _agregar_granularidad(pred, spec, req.granularity)
    serie_cols = list(spec.cols_serie)
    pred = pred.sort_values(serie_cols + [spec.col_fecha]).reset_index(drop=True)

    forecast = []
    for _, row in pred.iterrows():
        item = {k: str(row[k]) for k in serie_cols}
        item["date"] = pd.Timestamp(row[spec.col_fecha]).date().isoformat()
        item["forecast_demand"] = round(float(row["prediccion"]), 2)
        forecast.append(item)

    return {
        "field": "sales",
        "training": info,
        "forecast": forecast,
        "metadata": {
            "target": schema.target,
            "granularity": req.granularity,
            "horizon": req.horizon,
            "series_keys": serie_cols,
        },
    }


# ===========================================================================
# Dominio INVENTORY (clasificación + política)
# ===========================================================================
def _clave_item(item: dict[str, Any], serie_cols: list[str]) -> tuple[str, ...]:
    faltan = [k for k in serie_cols if k not in item]
    if faltan:
        raise SolicitudInvalida(
            f"Un item de inventario/compras no trae las claves de serie: {', '.join(faltan)}."
        )
    return tuple(str(item[k]) for k in serie_cols)


def _marcar_demanda_alta(df: pd.DataFrame, spec: EspecEsquema, cuantil: float) -> pd.DataFrame:
    """Etiqueta binaria por serie: objetivo > P{cuantil} de su propia serie."""
    out = df.copy()
    serie_cols = list(spec.cols_serie)
    if serie_cols:
        pq = out.groupby(serie_cols, observed=True)[spec.objetivo].transform(
            lambda s: s.quantile(cuantil)
        )
    else:
        pq = out[spec.objetivo].quantile(cuantil)
    out["_demanda_alta"] = (out[spec.objetivo].to_numpy() > np.asarray(pq)).astype("int8")
    return out


def _segmentos_volumen(df: pd.DataFrame, spec: EspecEsquema) -> dict[tuple[str, ...], int]:
    """Segmento de volumen por serie (terciles de la media del objetivo). Agnóstico: sin clustering retail."""
    serie_cols = list(spec.cols_serie)
    if not serie_cols:
        return {(): 0}
    medias = df.groupby(serie_cols, observed=True)[spec.objetivo].mean()
    if medias.empty:
        return {}
    try:
        seg = pd.qcut(medias.rank(method="first"), q=min(3, medias.nunique()), labels=False, duplicates="drop")
    except ValueError:
        seg = pd.Series(0, index=medias.index)
    return {
        (tuple(str(x) for x in (k if isinstance(k, tuple) else (k,)))): int(v)
        for k, v in seg.items()
    }


def alertas_inventario(
    req: AutoInventoryRequest, *, client_id: str = "default",
    cache: CacheModelosAgnosticos | None = None, seed: int = 42,
) -> dict[str, Any]:
    schema = req.schema_spec
    spec = construir_spec(schema)
    if not spec.es_temporal:
        raise SolicitudInvalida("El inventario requiere declarar 'date' en el esquema.")
    df = a_dataframe(req.rows, schema)
    serie_cols = list(spec.cols_serie)

    # Etiqueta derivada + esquema de clasificación (el objetivo de demanda pasa a solo-pasado).
    df_lab = _marcar_demanda_alta(df, spec, req.high_demand_quantile)
    spec_clf = EspecEsquema(
        objetivo="_demanda_alta", col_fecha=spec.col_fecha, cols_serie=spec.cols_serie,
        num_conocidas_futuro=spec.num_conocidas_futuro,
        num_solo_pasado=(*spec.num_solo_pasado, spec.objetivo),
        cats_extra=spec.cats_extra,
    )
    schema_clf_dict = {**schema.model_dump(by_alias=True), "_derivado": "demanda_alta",
                       "cuantil": req.high_demand_quantile}
    sig_e = firma_esquema("inventory", schema_clf_dict)
    sig_d = firma_datos(req.rows)
    predictor = info = None
    if cache is not None:
        cacheado = cache.obtener(client_id, "inventory", sig_e, sig_d)
        if cacheado is not None:
            predictor, info = cacheado[0], {**cacheado[1], "reused_cached_model": True, "schema_signature": sig_e}
    if predictor is None:
        res = automl.entrenar_clasificacion(df_lab, spec_clf, seed=seed)
        predictor = res.predictor
        info = _info(res.ganador, res.n_filas, res.metricas_test, sig_e)
        info["threshold_probability"] = round(res.umbral, 4)
        if cache is not None:
            cache.guardar(client_id, "inventory", sig_e, sig_d, predictor, info)

    # Régimen actual por serie: última fila clasificada.
    pred = predictor.predecir(df_lab)
    base = df_lab[serie_cols].copy() if serie_cols else pd.DataFrame(index=df_lab.index)
    base["_clase"] = pred["clase"].to_numpy()
    base["_prob"] = pred["probabilidad"].to_numpy()
    if serie_cols:
        ultimas = base.groupby(serie_cols, observed=True).tail(1)
        clases = {
            tuple(str(r[k]) for k in serie_cols): (int(r["_clase"]), float(r["_prob"]))
            for _, r in ultimas.iterrows()
        }
    else:
        r = base.iloc[-1]
        clases = {(): (int(r["_clase"]), float(r["_prob"]))}

    # Proxy de demanda reciente (μ/σ) por serie.
    ventana = config.inventory_demand_window()
    demanda: dict[tuple, tuple[float, float]] = {}
    grupos = df.groupby(serie_cols, observed=True) if serie_cols else [((), df)]
    for keys, g in grupos:
        clave = tuple(str(x) for x in (keys if isinstance(keys, tuple) else (keys,))) if serie_cols else ()
        v = g.sort_values(spec.col_fecha)[spec.objetivo].to_numpy("float64")[-ventana:]
        media = float(np.mean(v)) if len(v) else 0.0
        std = float(np.std(v, ddof=1)) if len(v) >= 2 else float("nan")
        demanda[clave] = (media, std)

    segmentos = _segmentos_volumen(df, spec)
    seg_alto = max(segmentos.values()) if segmentos else 0

    metodo = config.inventory_safety_method()
    lead_default = config.inventory_lead_time_default()
    z_base, z_alto = config.inventory_z_base(), config.inventory_z_high_volume()
    factor_fb, factor_cob = config.inventory_safety_fallback_factor(), config.inventory_coverage_factor()

    disponibles = set(clases)
    alerts: list[dict[str, Any]] = []
    for it in req.items:
        clave = _clave_item(it, serie_cols)
        if clave not in disponibles:
            raise SolicitudInvalida(
                f"No hay histórico para la serie {dict(zip(serie_cols, clave, strict=False))}; no se puede evaluar."
            )
        stock_actual = float(it.get("current_stock", 0.0))
        lead = int(it["lead_time_days"]) if it.get("lead_time_days") else lead_default
        clase, prob = clases[clave]
        media, std = demanda.get(clave, (0.0, float("nan")))
        segmento = segmentos.get(clave, 0)
        demanda_lead = media * lead
        z = z_alto if segmento == seg_alto and seg_alto > 0 else z_base
        ss = politica.stock_seguridad(
            metodo, demanda_lead=demanda_lead, lead=lead, factor_cobertura=factor_cob,
            z=z, sigma_diaria=std, factor_fallback=factor_fb,
        )
        recomendado = demanda_lead + ss
        alerta = {k: str(it[k]) for k in serie_cols}
        alerta.update({
            "demand_class": "high" if clase == 1 else "low",
            "high_demand_probability": round(prob, 4),
            "stockout_risk": bool(stock_actual < recomendado),
            "recommended_stock": round(recomendado, 2),
            "safety_stock": round(ss, 2),
            "volume_segment": int(segmento),
        })
        alerts.append(alerta)

    pct = int(round(req.high_demand_quantile * 100))
    return {
        "field": "inventory",
        "training": info,
        "alerts": alerts,
        "metadata": {
            "threshold": f"high_demand = {schema.target} > P{pct} of its own series",
            "probability_threshold": info.get("threshold_probability"),
            "series_keys": serie_cols,
        },
    }


# ===========================================================================
# Dominio PURCHASES (reposición sobre el pronóstico genérico)
# ===========================================================================
def reponer_compras(
    req: AutoPurchasesRequest, *, client_id: str = "default",
    cache: CacheModelosAgnosticos | None = None, seed: int = 42,
) -> dict[str, Any]:
    schema = req.schema_spec
    spec = construir_spec(schema)
    if not spec.es_temporal:
        raise SolicitudInvalida("Las compras requieren declarar 'date' en el esquema.")
    df = a_dataframe(req.rows, schema)
    serie_cols = list(spec.cols_serie)

    for it in req.items:
        for campo in ("lead_time_days", "target_coverage_days"):
            if it.get(campo) is None:
                raise SolicitudInvalida(f"Cada item de compras requiere '{campo}'.")

    predictor, info = _resolver_regresion(
        df, spec, schema.model_dump(by_alias=True), req.rows, client_id, cache, seed
    )

    horizonte_max = max(int(p["lead_time_days"]) + int(p["target_coverage_days"]) for p in req.items)
    completo, inicio, fin = _esqueleto_futuro(df, spec, horizonte_max, None)
    pred = predictor.pronosticar_horizonte(completo, inicio, fin)
    pred = pred.sort_values(serie_cols + [spec.col_fecha]).reset_index(drop=True)

    metodo = config.purchases_safety_method()
    factor = config.purchases_safety_factor()
    z = config.inventory_z_base()

    if serie_cols:
        por_serie = {tuple(str(x) for x in (k if isinstance(k, tuple) else (k,))): g
                     for k, g in pred.groupby(serie_cols, observed=True)}
    else:
        por_serie = {(): pred}

    recomendacion: list[dict[str, Any]] = []
    for it in req.items:
        clave = _clave_item(it, serie_cols)
        serie = por_serie.get(clave)
        if serie is None:
            raise SolicitudInvalida(
                f"No hay histórico para la serie {dict(zip(serie_cols, clave, strict=False))}; no se puede pronosticar."
            )
        lead = int(it["lead_time_days"])
        cobertura = int(it["target_coverage_days"])
        stock_actual = float(it.get("current_stock", 0.0))
        diaria = serie.sort_values(spec.col_fecha)["prediccion"].to_numpy("float64")
        demanda_lead = float(diaria[:lead].sum())
        demanda_horizonte = float(diaria[: lead + cobertura].sum())
        sigma = float(np.std(diaria[:lead], ddof=1)) if lead >= 2 else float("nan")
        ss = politica.stock_seguridad(
            metodo, demanda_lead=demanda_lead, lead=lead, factor_cobertura=factor,
            z=z, sigma_diaria=sigma, factor_fallback=factor,
        )
        punto_reorden = demanda_lead + ss
        cantidad = max(0.0, demanda_horizonte + ss - stock_actual)
        rec = {k: str(it[k]) for k in serie_cols}
        rec.update({
            "expected_demand_horizon": round(demanda_horizonte, 2),
            "reorder_point": round(punto_reorden, 2),
            "replenishment_quantity": round(cantidad, 2),
            "justification": "forecast_demand(lead + coverage) + safety_stock - current_stock",
        })
        recomendacion.append(rec)

    return {
        "field": "purchases",
        "training": info,
        "recommendation": recomendacion,
        "metadata": {"policy": metodo, "series_keys": serie_cols},
    }
