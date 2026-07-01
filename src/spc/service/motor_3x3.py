"""Motor **3×3 por dominio**: entrena los tres modelos *en el momento* y responde.

Una sola llamada por dominio (ventas/compras/almacén) sobre su **formato único**:
construye el DataFrame, **entrena al vuelo** (sklearn liviano) los tres modelos
—regresión, clasificación y clustering— y devuelve los tres bloques en la misma
respuesta. Es la pieza que cumple lo que pidió el docente: modelos ligeros que corren
en el backend al recibir la petición.

Reutiliza la maquinaria del motor agnóstico:
- ``spc.models.automl.entrenar_regresion(..., usar_zoo_liviano=True)`` + ``_esqueleto_futuro``.
- ``spc.models.zoo_liviano.entrenar_clasificacion_liviana`` / ``entrenar_clustering``.
- ``spc.service.dominios`` (specs leak-safe, derivación de etiqueta, perfil de entidad).

No conoce HTTP (la API mapea). No conoce el algoritmo (lo elige el zoo liviano).
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from spc.models import automl, zoo_liviano
from spc.service import dominios
from spc.service.agnostico import _esqueleto_futuro
from spc.service.errores import SolicitudInvalida
from spc.synthetic import comun
from spc.synthetic.esquemas import esquema_de
from spc.utils.logging import get_logger

log = get_logger("service.motor_3x3")

HORIZON_DEFAULT = 14
HORIZON_MAX = 90
# Mínimo de entidades para un clustering con sentido (si no, terciles de volumen).
MIN_ENTIDADES_CLUSTER = 3


# ===========================================================================
# Construcción del DataFrame desde las filas del cliente
# ===========================================================================
def construir_dataframe(rows: list[dict[str, Any]], dominio: str) -> pd.DataFrame:
    """Valida y tipa las filas recibidas según el esquema del dominio."""
    esquema = esquema_de(dominio)
    if not rows:
        raise SolicitudInvalida("No se recibieron filas de datos.")
    df = pd.DataFrame(rows)
    faltan = [c for c in esquema.orden if c not in df.columns]
    if faltan:
        raise SolicitudInvalida(
            f"Faltan columnas del formato de '{dominio}': {', '.join(faltan)}."
        )
    df = df[esquema.orden].copy()  # orden canónico, descarta extras
    for col in esquema.columnas:
        if col.tipo == "date":
            df[col.nombre] = pd.to_datetime(df[col.nombre], errors="coerce")
            if df[col.nombre].isna().any():
                raise SolicitudInvalida(f"La columna '{col.nombre}' tiene fechas no parseables.")
        elif col.tipo in ("int", "float"):
            df[col.nombre] = pd.to_numeric(df[col.nombre], errors="coerce")
        else:
            df[col.nombre] = df[col.nombre].astype("string").astype("object")
    return df


# ===========================================================================
# Bloque REGRESIÓN
# ===========================================================================
def _futuro_calendario(
    df: pd.DataFrame, cfg: dominios.ConfigDominio, horizon: int
) -> list[dict[str, Any]] | None:
    """Filas futuras con el **calendario correcto** y las numéricas conocidas arrastradas.

    Solo para los dominios con calendario (`fecha`). Recalcula ``es_fin_de_semana`` y
    ``dias_a_proximo_feriado`` desde las fechas futuras (no las deja en 0 como el
    esqueleto genérico) y arrastra el último valor de las demás conocidas-a-futuro.
    """
    spec = cfg.spec_regresion
    fecha = spec.col_fecha
    if fecha is None:
        return None
    serie_cols = list(spec.cols_serie)
    ultima = pd.Timestamp(df[fecha].max())
    fechas_fut = [(ultima + pd.Timedelta(days=i)).date() for i in range(1, horizon + 1)]
    finde = comun.es_fin_de_semana(fechas_fut)
    dias_fer = comun.dias_a_proximo_feriado(fechas_fut)

    # Último valor de cada conocida-a-futuro por serie (arrastre).
    ultimos = df.sort_values(fecha).groupby(serie_cols, observed=True).tail(1)
    futuro: list[dict[str, Any]] = []
    for _, ult in ultimos.iterrows():
        for i, f in enumerate(fechas_fut):
            fila: dict[str, Any] = {fecha: pd.Timestamp(f)}
            for k in serie_cols:
                fila[k] = ult[k]
            for col in spec.num_conocidas_futuro:
                if col == "es_fin_de_semana":
                    fila[col] = int(finde[i])
                elif col == "dias_a_proximo_feriado":
                    fila[col] = int(dias_fer[i])
                elif col in ("en_promocion", "descuento_pct"):
                    fila[col] = 0  # sin promoción planificada por defecto
                else:
                    fila[col] = ult[col]  # arrastra precio/política
            futuro.append(fila)
    return futuro


def _bloque_regresion(df: pd.DataFrame, cfg: dominios.ConfigDominio, horizon: int, seed: int) -> dict[str, Any]:
    spec = cfg.spec_regresion
    try:
        res = automl.entrenar_regresion(df, spec, seed=seed, usar_zoo_liviano=True)
    except ValueError as exc:
        raise SolicitudInvalida(f"No se pudo entrenar la regresión: {exc}") from exc

    serie_cols = list(spec.cols_serie)
    pronostico: list[dict[str, Any]] = []
    futuro = _futuro_calendario(df, cfg, horizon)
    col_fecha = spec.col_fecha
    if spec.es_temporal and futuro and col_fecha is not None:
        completo, inicio, fin = _esqueleto_futuro(df, spec, horizon, futuro)
        pred = res.predictor.pronosticar_horizonte(completo, inicio, fin)
        pred = pred.sort_values([*serie_cols, col_fecha]).reset_index(drop=True)
        for _, row in pred.iterrows():
            item: dict[str, Any] = {k: str(row[k]) for k in serie_cols}
            item["fecha"] = pd.Timestamp(row[col_fecha]).date().isoformat()
            item["prediccion"] = round(float(row["prediccion"]), 2)
            pronostico.append(item)

    return {
        "objetivo": spec.objetivo,
        "modelo_ganador": res.ganador,
        "n_filas_entrenamiento": res.n_filas,
        "metricas_honestas": {k: round(float(v), 4) for k, v in res.metricas_test.items()},
        "candidatos": res.candidatos,
        "horizonte": horizon if pronostico else 0,
        "prediccion": pronostico,
    }


# ===========================================================================
# Bloque CLASIFICACIÓN
# ===========================================================================
def _bloque_clasificacion(df: pd.DataFrame, cfg: dominios.ConfigDominio, seed: int) -> dict[str, Any]:
    df_lab = cfg.derivar_etiqueta(df)
    spec = cfg.spec_clasificacion
    serie_cols = list(spec.cols_serie)
    try:
        res = zoo_liviano.entrenar_clasificacion_liviana(df_lab, spec, seed=seed)
    except ValueError as exc:
        raise SolicitudInvalida(f"No se pudo entrenar la clasificación: {exc}") from exc

    # Estado actual por serie: clase/probabilidad de la última fila de cada serie.
    pred = res.predictor.predecir(df_lab)
    base = df_lab[serie_cols].copy()
    base["_clase"] = pred["clase"].to_numpy()
    base["_prob"] = pred["probabilidad"].to_numpy()
    ultimas = base.groupby(serie_cols, observed=True).tail(1)

    alertas: list[dict[str, Any]] = []
    for _, r in ultimas.iterrows():
        item: dict[str, Any] = {k: str(r[k]) for k in serie_cols}
        item["clase"] = int(r["_clase"])
        item["probabilidad"] = round(float(r["_prob"]), 4)
        alertas.append(item)

    return {
        "etiqueta": cfg.etiqueta,
        "definicion": esquema_de(cfg.dominio).derivacion_etiqueta,
        "modelo_ganador": res.ganador,
        "umbral": round(res.umbral, 4),
        "prevalencia": round(res.prevalencia, 4),
        "metricas_honestas": {k: round(float(v), 4) for k, v in res.metricas_test.items()},
        "alertas": alertas,
    }


# ===========================================================================
# Bloque CLUSTERING
# ===========================================================================
def _segmentos_terciles(perfil: pd.DataFrame, clave: str, columna_volumen: str) -> dict[str, Any]:
    """Fallback cuando hay muy pocas entidades para KMeans: terciles de volumen."""
    vol = perfil[columna_volumen]
    try:
        seg = pd.qcut(vol.rank(method="first"), q=min(3, vol.nunique()), labels=False, duplicates="drop")
    except ValueError:
        seg = pd.Series(0, index=vol.index)
    seg = seg.fillna(0).astype("int64")
    nombres = {0: "volumen bajo", 1: "volumen medio", 2: "volumen alto"}
    segmentos = [
        {clave: str(idx), "segmento": int(s), "etiqueta": nombres.get(int(s), f"segmento {s}")}
        for idx, s in seg.items()
    ]
    return {
        "algoritmo": "terciles_de_volumen (fallback: pocas entidades)",
        "k": int(seg.nunique()),
        "silueta": None,
        "segmentos": segmentos,
    }


def _bloque_clustering(df: pd.DataFrame, cfg: dominios.ConfigDominio, seed: int) -> dict[str, Any]:
    perfil = cfg.perfil_entidades(df)
    cols = list(cfg.columnas_clustering)
    if len(perfil) < MIN_ENTIDADES_CLUSTER:
        return _segmentos_terciles(perfil, cfg.clave_entidad, cfg.columna_volumen)

    res = zoo_liviano.entrenar_clustering(
        perfil, cfg.clave_entidad, cols, cfg.columna_volumen, seed=seed, k_fijo=cfg.k_fijo,
        estilo_etiqueta=cfg.estilo_etiqueta, columna_etiqueta=cfg.columna_etiqueta,
    )
    segmentos = [
        {cfg.clave_entidad: str(r[cfg.clave_entidad]), "segmento": int(r["segmento"]), "etiqueta": str(r["etiqueta"])}
        for _, r in res.asignacion.iterrows()
    ]
    return {
        "algoritmo": "KMeans (escalado + silueta)",
        "entidad": cfg.clave_entidad,
        "k": res.k,
        "silueta": round(res.silueta, 4),
        "curva_silueta": res.curva_silueta,
        "segmentos": segmentos,
    }


# ===========================================================================
# Indicadores de inventario derivados (ALMACÉN) — se MUESTRAN, no se predicen
# ===========================================================================
Z_SERVICIO = 1.65  # ~95 % de nivel de servicio para el stock de seguridad


def _indicadores_inventario(
    df: pd.DataFrame, pronostico: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """KPIs de inventario **derivados del pronóstico de demanda** (ADR-0025 e).

    Con ``demanda_dia`` como objetivo, ``dias_de_cobertura``, el punto de reposición y el
    stock de seguridad dejan de **predecirse** y se **calculan** por serie (tienda×sku) a
    partir de la demanda prevista, el stock actual conocido y el tiempo de reposición:

    - ``stock_seguridad = z · σ(demanda histórica) · √(tiempo_reposicion)`` (z≈1.65 → ~95 %)
    - ``punto_reposicion = demanda_prevista · tiempo_reposicion + stock_seguridad``
    - ``dias_cobertura_proyectada = stock_actual / demanda_prevista``
    - ``alerta_reposicion = stock_actual ≤ punto_reposicion``
    """
    if not pronostico:
        return []
    serie = ["id_tienda", "sku"]
    pred = pd.DataFrame(pronostico)
    pred["prediccion"] = pd.to_numeric(pred["prediccion"], errors="coerce")
    dem_prev = pred.groupby(serie)["prediccion"].mean()

    ult = df.sort_values("fecha").groupby(serie, observed=True).tail(1).set_index(serie)
    sigma = df.groupby(serie, observed=True)["demanda_dia"].std().fillna(0.0)

    indicadores: list[dict[str, Any]] = []
    for clave, d_prev in dem_prev.items():
        d_prev = float(d_prev)
        stock = float(ult.loc[clave, "stock_actual"])
        lead = float(ult.loc[clave, "tiempo_reposicion_dias"])
        ss = Z_SERVICIO * float(sigma.loc[clave]) * (lead**0.5)
        rop = d_prev * lead + ss
        cobertura = round(stock / d_prev, 1) if d_prev > 0 else None
        indicadores.append({
            "id_tienda": str(clave[0]), "sku": str(clave[1]),
            "demanda_diaria_prevista": round(d_prev, 2),
            "stock_actual": round(stock, 2),
            "stock_seguridad": round(ss, 2),
            "punto_reposicion": round(rop, 2),
            "dias_cobertura_proyectada": cobertura,
            "alerta_reposicion": bool(stock <= rop),
        })
    return indicadores


# ===========================================================================
# Orquestación: los tres modelos en una respuesta
# ===========================================================================
def analizar(
    dominio: str, rows: list[dict[str, Any]], *, horizon: int = HORIZON_DEFAULT, seed: int = 42
) -> dict[str, Any]:
    """Entrena y ejecuta los **tres modelos** del dominio sobre ``rows`` (en el momento)."""
    cfg = dominios.config_de(dominio)
    horizon = max(1, min(int(horizon), HORIZON_MAX))
    df = construir_dataframe(rows, dominio)

    regresion = _bloque_regresion(df, cfg, horizon, seed)
    clasificacion = _bloque_clasificacion(df, cfg, seed)
    clustering = _bloque_clustering(df, cfg, seed)

    resultado: dict[str, Any] = {
        "dominio": dominio,
        "formato": esquema_de(dominio).grano,
        "n_filas": int(len(df)),
        "regresion": regresion,
        "clasificacion": clasificacion,
        "clustering": clustering,
        "nota": "Modelos sklearn entrenados en el momento sobre los datos enviados (sin artefactos congelados).",
    }
    # ALMACÉN: los KPIs clásicos (cobertura, punto de reposición, stock de seguridad) se
    # MUESTRAN derivados del pronóstico de demanda, aunque ya no sean el objetivo (ADR-0025 e).
    if dominio == "almacen":
        resultado["indicadores_inventario"] = _indicadores_inventario(df, regresion["prediccion"])
    return resultado


def analizar_demo(dominio: str, *, horizon: int = HORIZON_DEFAULT, seed: int = 42) -> dict[str, Any]:
    """Igual que :func:`analizar` pero sobre los **datos sintéticos** del propio sistema."""
    from spc.synthetic import generar_dominio

    rows: list[dict[str, Any]] = [
        {str(k): v for k, v in fila.items()}
        for fila in generar_dominio(dominio, seed=seed).to_dict(orient="records")
    ]
    return analizar(dominio, rows, horizon=horizon, seed=seed)
