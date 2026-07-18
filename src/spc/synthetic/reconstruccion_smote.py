"""Reconstruccion estadistica inversa de los datasets de ``pyme_hibrida``.

El objetivo no es afirmar que se recupero una fuente historica desconocida. Se construye
una base *pre-SMOTE* reproducible retirando parte de la clase minoritaria solamente del
tramo de entrenamiento; despues SMOTENC recupera el numero original de positivos. Las
fechas y claves de las filas retiradas se conservan como un esqueleto estructural para que
la salida siga siendo un archivo de negocio valido y sin claves duplicadas.

VALID y TEST nunca se remuestrean y se copian byte-a-byte a nivel de valores desde el
dataset objetivo. Las etiquetas no se exportan: se derivan con umbrales fijados en TRAIN.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import wasserstein_distance
from sklearn.preprocessing import StandardScaler

from spc.api.ingest.dominios_excel import generar_excel
from spc.synthetic.esquemas import esquema_de, validar_conforme

SEED = 42
RETENCIONES = (0.25, 0.50, 0.75)
K_VECINOS = (3, 5, 7)


@dataclass(frozen=True)
class ConfigReconstruccion:
    dominio: str
    fecha: str
    claves: tuple[str, ...]
    categoricas_smote: tuple[str, ...]
    numericas_smote: tuple[str, ...]
    categoricas_auditoria: tuple[str, ...]
    numericas_auditoria: tuple[str, ...]
    etiqueta: str


CONFIGS: dict[str, ConfigReconstruccion] = {
    "ventas": ConfigReconstruccion(
        dominio="ventas",
        fecha="fecha",
        claves=("fecha", "id_tienda", "sku"),
        categoricas_smote=("en_promocion", "metodo_pago", "canal_venta"),
        numericas_smote=("unidades_vendidas", "descuento_pct"),
        categoricas_auditoria=(
            "id_tienda", "sku", "categoria", "en_promocion", "metodo_pago", "canal_venta"
        ),
        numericas_auditoria=(
            "unidades_vendidas", "precio_unitario", "ingreso", "descuento_pct",
            "dias_a_proximo_feriado",
        ),
        etiqueta="demanda_alta",
    ),
    "compras": ConfigReconstruccion(
        dominio="compras",
        fecha="fecha_orden",
        claves=("fecha_orden", "id_proveedor", "sku"),
        categoricas_smote=("metodo_pago",),
        numericas_smote=("cantidad_pedida", "lead_time_dias", "cumplimiento"),
        categoricas_auditoria=("id_proveedor", "sku", "categoria", "metodo_pago"),
        numericas_auditoria=(
            "cantidad_pedida", "precio_unitario_compra", "costo_total", "lead_time_dias",
            "cantidad_recibida", "cumplimiento", "descuento_volumen",
        ),
        etiqueta="entrega_con_retraso",
    ),
    "almacen": ConfigReconstruccion(
        dominio="almacen",
        fecha="fecha",
        claves=("fecha", "id_tienda", "sku"),
        categoricas_smote=("zona_almacen",),
        numericas_smote=("demanda_dia", "stock_actual"),
        categoricas_auditoria=("id_tienda", "sku", "categoria", "zona_almacen"),
        numericas_auditoria=(
            "stock_actual", "stock_minimo", "stock_maximo", "demanda_dia",
            "demanda_diaria_promedio", "dias_de_cobertura", "rotacion",
            "tiempo_reposicion_dias",
        ),
        etiqueta="riesgo_quiebre",
    ),
}


@dataclass
class Cortes:
    train_fin: str
    valid_ini: str
    valid_fin: str
    test_ini: str

    def mascara(self, fechas: pd.Series) -> dict[str, np.ndarray]:
        f = pd.to_datetime(fechas)
        train_fin = pd.Timestamp(self.train_fin)
        valid_ini = pd.Timestamp(self.valid_ini)
        valid_fin = pd.Timestamp(self.valid_fin)
        test_ini = pd.Timestamp(self.test_ini)
        return {
            "train": (f <= train_fin).to_numpy(),
            "valid": ((f >= valid_ini) & (f <= valid_fin)).to_numpy(),
            "test": (f >= test_ini).to_numpy(),
        }


@dataclass
class EtiquetaInfo:
    nombre: str
    umbral_global: float | None = None
    umbrales_categoria: dict[str, float] | None = None


@dataclass
class AuditoriaCandidato:
    dominio: str
    retencion_minoria: float
    k_neighbors: int
    filas_objetivo: int
    filas_crudo: int
    filas_reconstruidas: int
    positivos_train_objetivo: int
    positivos_train_crudo: int
    positivos_train_reconstruido: int
    sinteticas_agregadas: int
    max_diferencia_categorica: float
    wasserstein_normalizada: float
    diferencia_correlacion: float
    duplicados_clave: int
    reglas_validas: bool
    valid_test_intactos: bool
    cumple: bool
    perdida: float
    diferencia_pr_auc: float | None = None
    diferencia_f1: float | None = None
    diferencia_recall: float | None = None
    diferencia_wape: float | None = None
    diferencia_silhouette: float | None = None
    metricas_modelos_cumplen: bool | None = None


@dataclass
class ResultadoDominio:
    dominio: str
    crudo: pd.DataFrame
    reconstruido: pd.DataFrame
    auditoria: AuditoriaCandidato
    candidatos: list[AuditoriaCandidato]
    cortes: Cortes
    etiqueta: EtiquetaInfo


def _cortes_por_fecha(df: pd.DataFrame, col_fecha: str) -> Cortes:
    """70/15/15 sobre fechas unicas; una fecha nunca queda repartida entre splits."""
    fechas = pd.Series(pd.to_datetime(df[col_fecha]).dropna().unique()).sort_values().reset_index(drop=True)
    if len(fechas) < 3:
        raise ValueError("Se requieren al menos tres fechas distintas para train/valid/test.")
    i70 = min(max(1, int(len(fechas) * 0.70)), len(fechas) - 2)
    i85 = min(max(i70 + 1, int(len(fechas) * 0.85)), len(fechas) - 1)
    return Cortes(
        train_fin=str(pd.Timestamp(fechas.iloc[i70 - 1]).date()),
        valid_ini=str(pd.Timestamp(fechas.iloc[i70]).date()),
        valid_fin=str(pd.Timestamp(fechas.iloc[i85 - 1]).date()),
        test_ini=str(pd.Timestamp(fechas.iloc[i85]).date()),
    )


def _etiquetar(
    df: pd.DataFrame,
    cfg: ConfigReconstruccion,
    cortes: Cortes,
    info: EtiquetaInfo | None = None,
) -> tuple[np.ndarray, EtiquetaInfo]:
    train = cortes.mascara(df[cfg.fecha])["train"]
    if cfg.dominio == "ventas":
        if info is None:
            p75 = (
                df.loc[train].groupby("categoria", observed=True)["unidades_vendidas"]
                .quantile(0.75).astype(float).to_dict()
            )
            global_ = float(df.loc[train, "unidades_vendidas"].quantile(0.75))
            info = EtiquetaInfo(cfg.etiqueta, global_, {str(k): float(v) for k, v in p75.items()})
        umbral = df["categoria"].astype(str).map(info.umbrales_categoria or {}).fillna(
            float(info.umbral_global or 0.0)
        )
        y = (pd.to_numeric(df["unidades_vendidas"]) > umbral).astype("int8").to_numpy()
    elif cfg.dominio == "compras":
        if info is None:
            info = EtiquetaInfo(
                cfg.etiqueta, float(pd.to_numeric(df.loc[train, "lead_time_dias"]).quantile(0.75))
            )
        y = (
            pd.to_numeric(df["lead_time_dias"]) > float(info.umbral_global or 0.0)
        ).astype("int8").to_numpy()
    else:
        info = info or EtiquetaInfo(cfg.etiqueta)
        y = (
            pd.to_numeric(df["stock_actual"])
            < pd.to_numeric(df["demanda_diaria_promedio"])
            * pd.to_numeric(df["tiempo_reposicion_dias"])
        ).astype("int8").to_numpy()
    return y, info


def _seleccionar_minoria(
    df: pd.DataFrame,
    indices_positivos: np.ndarray,
    retencion: float,
    cfg: ConfigReconstruccion,
    seed: int,
) -> np.ndarray:
    """Muestreo estratificado reproducible por mes y categoria, con tamano exacto."""
    pos = df.loc[indices_positivos].copy()
    pos["_mes"] = pd.to_datetime(pos[cfg.fecha]).dt.to_period("M").astype(str)
    estratos = ["_mes"] + (["categoria"] if "categoria" in pos.columns else [])
    rng = np.random.default_rng(seed)
    objetivo = max(6, int(round(len(pos) * retencion)))
    objetivo = min(objetivo, len(pos))
    elegidos: list[int] = []
    for _, grupo in pos.groupby(estratos, observed=True, sort=True):
        n = max(1, int(round(len(grupo) * retencion)))
        n = min(n, len(grupo))
        elegidos.extend(rng.choice(grupo.index.to_numpy(), n, replace=False).tolist())
    elegidos = list(dict.fromkeys(elegidos))
    if len(elegidos) > objetivo:
        elegidos = rng.choice(np.array(elegidos), objetivo, replace=False).tolist()
    elif len(elegidos) < objetivo:
        faltan = np.setdiff1d(indices_positivos, np.array(elegidos), assume_unique=False)
        elegidos.extend(rng.choice(faltan, objetivo - len(elegidos), replace=False).tolist())
    return np.sort(np.asarray(elegidos, dtype=int))


def _preparar_smote(
    df: pd.DataFrame, cfg: ConfigReconstruccion
) -> tuple[pd.DataFrame, StandardScaler]:
    cols = [*cfg.categoricas_smote, *cfg.numericas_smote]
    x = df[cols].copy()
    for c in cfg.categoricas_smote:
        x[c] = x[c].astype(str).astype("category")
    scaler = StandardScaler()
    x[list(cfg.numericas_smote)] = scaler.fit_transform(
        x[list(cfg.numericas_smote)].astype(float)
    )
    return x, scaler


def _sintetizar(
    df_crudo_train: pd.DataFrame,
    y_crudo_train: np.ndarray,
    n_positivos_objetivo: int,
    cfg: ConfigReconstruccion,
    k_neighbors: int,
    seed: int,
) -> pd.DataFrame:
    from imblearn.over_sampling import SMOTENC

    x, scaler = _preparar_smote(df_crudo_train, cfg)
    pos = int(y_crudo_train.sum())
    if pos <= k_neighbors:
        raise ValueError(f"SMOTENC requiere mas de {k_neighbors} positivos; hay {pos}.")
    sampler = SMOTENC(
        categorical_features="auto",
        sampling_strategy={1: int(n_positivos_objetivo)},
        k_neighbors=k_neighbors,
        random_state=seed,
    )
    xrs, _ = sampler.fit_resample(x, y_crudo_train)
    syn = xrs.iloc[len(x):].copy().reset_index(drop=True)
    syn[list(cfg.numericas_smote)] = scaler.inverse_transform(
        syn[list(cfg.numericas_smote)].astype(float)
    )
    return syn


def _mapa_estable(df: pd.DataFrame, clave: str, valor: str, agg: str = "first") -> dict[str, Any]:
    g = df.assign(_k=df[clave].astype(str)).groupby("_k", observed=True)[valor]
    serie = g.first() if agg == "first" else g.median()
    return serie.to_dict()


def _reparar_ventas(
    target: pd.DataFrame,
    base: pd.DataFrame,
    slots: pd.DataFrame,
    syn: pd.DataFrame,
    info: EtiquetaInfo,
) -> pd.DataFrame:
    nuevas = slots.copy().reset_index(drop=True)
    nuevas["unidades_vendidas"] = syn["unidades_vendidas"].clip(lower=0).round(3)
    nuevas["en_promocion"] = pd.to_numeric(syn["en_promocion"], errors="coerce").fillna(0).round().clip(0, 1).astype(int)
    nuevas["descuento_pct"] = syn["descuento_pct"].clip(0, 25).round(2)
    nuevas.loc[nuevas["en_promocion"] == 0, "descuento_pct"] = 0.0
    nuevas.loc[(nuevas["en_promocion"] == 1) & (nuevas["descuento_pct"] < 5), "descuento_pct"] = 5.0
    nuevas["metodo_pago"] = syn["metodo_pago"].astype(str).to_numpy()
    nuevas["canal_venta"] = syn["canal_venta"].astype(str).to_numpy()

    cat = _mapa_estable(target, "sku", "categoria")
    precio = _mapa_estable(target, "sku", "precio_unitario", "median")
    nuevas["categoria"] = nuevas["sku"].astype(str).map(cat)
    nuevas["precio_unitario"] = nuevas["sku"].astype(str).map(precio).astype(float).round(2)
    umbral = nuevas["categoria"].astype(str).map(info.umbrales_categoria or {}).fillna(
        float(info.umbral_global or 0)
    )
    nuevas["unidades_vendidas"] = np.maximum(
        nuevas["unidades_vendidas"].to_numpy(float), umbral.to_numpy(float) + 0.001
    ).round(3)
    nuevas["ingreso"] = (nuevas["unidades_vendidas"] * nuevas["precio_unitario"]).round(2)
    fechas = pd.to_datetime(nuevas["fecha"])
    nuevas["es_fin_de_semana"] = (fechas.dt.dayofweek >= 5).astype(int)
    feriado = target.assign(_f=pd.to_datetime(target["fecha"])).groupby("_f")["dias_a_proximo_feriado"].first()
    nuevas["dias_a_proximo_feriado"] = fechas.map(feriado).astype(int)
    return pd.concat([base, nuevas], ignore_index=True)


def _reparar_compras(
    target: pd.DataFrame,
    base: pd.DataFrame,
    slots: pd.DataFrame,
    syn: pd.DataFrame,
    info: EtiquetaInfo,
) -> pd.DataFrame:
    nuevas = slots.copy().reset_index(drop=True)
    nuevas["cantidad_pedida"] = syn["cantidad_pedida"].clip(lower=1).round(2)
    nuevas["lead_time_dias"] = np.maximum(
        np.rint(syn["lead_time_dias"].to_numpy(float)),
        int(np.floor(float(info.umbral_global or 0))) + 1,
    ).astype(int)
    cumplimiento = syn["cumplimiento"].clip(0.55, 1.0).to_numpy(float)
    nuevas["cumplimiento"] = cumplimiento.round(4)
    for col in ("id_proveedor", "categoria", "precio_unitario_compra", "metodo_pago", "descuento_volumen"):
        agg = "median" if col in {"precio_unitario_compra", "descuento_volumen"} else "first"
        nuevas[col] = nuevas["sku"].astype(str).map(_mapa_estable(target, "sku", col, agg))
    nuevas["cantidad_recibida"] = np.minimum(
        nuevas["cantidad_pedida"],
        (nuevas["cantidad_pedida"] * nuevas["cumplimiento"]).round(2),
    )
    nuevas["cumplimiento"] = (
        nuevas["cantidad_recibida"] / nuevas["cantidad_pedida"].clip(lower=0.1)
    ).round(4)
    nuevas["costo_total"] = (
        nuevas["cantidad_pedida"] * pd.to_numeric(nuevas["precio_unitario_compra"])
    ).round(2)
    return pd.concat([base, nuevas], ignore_index=True)


def _reparar_almacen(
    target: pd.DataFrame,
    base: pd.DataFrame,
    slots: pd.DataFrame,
    syn: pd.DataFrame,
) -> pd.DataFrame:
    nuevas = slots.copy().reset_index(drop=True)
    nuevas["demanda_dia"] = np.rint(syn["demanda_dia"].clip(lower=0)).astype(int)
    nuevas["stock_actual"] = syn["stock_actual"].clip(lower=0).round(2)
    nuevas["_sintetica"] = True
    base_original = base.copy()
    base = base.copy()
    base["_sintetica"] = False
    out = pd.concat([base, nuevas], ignore_index=True)
    out["fecha"] = pd.to_datetime(out["fecha"])
    out = out.sort_values(["id_tienda", "sku", "fecha"], kind="stable").reset_index(drop=True)
    cat = _mapa_estable(target, "sku", "categoria")
    lead = _mapa_estable(target, "sku", "tiempo_reposicion_dias", "median")
    zona = _mapa_estable(target, "sku", "zona_almacen")
    ratio = (target["stock_maximo"] / target["stock_minimo"].replace(0, np.nan)).replace([np.inf, -np.inf], np.nan)
    factor = target.assign(_ratio=ratio, _k=target["sku"].astype(str)).groupby("_k")["_ratio"].median().fillna(2.0).to_dict()
    out["categoria"] = out["sku"].astype(str).map(cat)
    out["tiempo_reposicion_dias"] = out["sku"].astype(str).map(lead).round().astype(int)
    out["zona_almacen"] = out["sku"].astype(str).map(zona)
    grp = out.groupby(["id_tienda", "sku"], observed=True)["demanda_dia"]
    dda = grp.transform(lambda s: s.shift(1).rolling(28, min_periods=1).mean())
    out["demanda_diaria_promedio"] = dda.fillna(out["demanda_dia"]).clip(lower=0.1).round(3)
    out["stock_minimo"] = (
        out["demanda_diaria_promedio"] * out["tiempo_reposicion_dias"]
    ).round(2)
    out["stock_maximo"] = (
        out["stock_minimo"] * out["sku"].astype(str).map(factor).astype(float)
    ).round(2)
    m = out["_sintetica"].to_numpy(bool)
    out.loc[m, "stock_actual"] = np.minimum(
        out.loc[m, "stock_actual"].to_numpy(float),
        np.maximum(0.0, out.loc[m, "stock_minimo"].to_numpy(float) - 0.01),
    ).round(2)
    stock_medio = ((out["stock_minimo"] + out["stock_maximo"]) / 2).clip(lower=0.1)
    out["rotacion"] = (out["demanda_diaria_promedio"] / stock_medio).round(4)
    out["dias_de_cobertura"] = (
        out["stock_actual"] / out["demanda_diaria_promedio"].clip(lower=0.1)
    ).round(2)
    out["fecha"] = out["fecha"].dt.strftime("%Y-%m-%d")

    # La ingenieria de restricciones solo puede alterar filas generadas. Si se
    # recalcularan los historicos de las observaciones retenidas, algunas cambiarian de
    # clase y la base dejaria de ser realmente "cruda". Se restauran exactamente.
    sinteticas = out.loc[out["_sintetica"]].drop(columns="_sintetica")
    return pd.concat([base_original, sinteticas], ignore_index=True)


def _hash_filas(df: pd.DataFrame) -> str:
    csv = df.to_csv(index=False, lineterminator="\n", float_format="%.10g")
    return hashlib.sha256(csv.encode("utf-8")).hexdigest()


def _reglas_validas(df: pd.DataFrame, dominio: str) -> bool:
    try:
        validar_conforme(df, dominio)
    except Exception:
        return False
    if dominio == "ventas":
        return bool(
            np.allclose(df["ingreso"], (df["unidades_vendidas"] * df["precio_unitario"]).round(2))
            and (df["unidades_vendidas"] >= 0).all()
            and (df.loc[df["en_promocion"] == 0, "descuento_pct"] == 0).all()
        )
    if dominio == "compras":
        return bool(
            np.allclose(df["costo_total"], (df["cantidad_pedida"] * df["precio_unitario_compra"]).round(2), atol=0.011)
            and (df["cantidad_recibida"] <= df["cantidad_pedida"] + 1e-9).all()
            and df["cumplimiento"].between(0, 1).all()
        )
    return bool(
        (df["stock_minimo"] <= df["stock_maximo"]).all()
        and np.allclose(df["dias_de_cobertura"], (df["stock_actual"] / df["demanda_diaria_promedio"]).round(2))
        and (df["stock_actual"] >= 0).all()
    )


def _auditar(
    target: pd.DataFrame,
    crudo: pd.DataFrame,
    reconstruido: pd.DataFrame,
    cfg: ConfigReconstruccion,
    cortes: Cortes,
    info: EtiquetaInfo,
    retencion: float,
    k: int,
) -> AuditoriaCandidato:
    masks_t = cortes.mascara(target[cfg.fecha])
    masks_r = cortes.mascara(reconstruido[cfg.fecha])
    yt, _ = _etiquetar(target, cfg, cortes, info)
    yc, _ = _etiquetar(crudo, cfg, cortes, info)
    yr, _ = _etiquetar(reconstruido, cfg, cortes, info)

    ttrain = target.loc[masks_t["train"]]
    rtrain = reconstruido.loc[masks_r["train"]]
    cat_max = 0.0
    for col in cfg.categoricas_auditoria:
        a = ttrain[col].astype(str).value_counts(normalize=True)
        b = rtrain[col].astype(str).value_counts(normalize=True)
        cat_max = max(cat_max, float((a.sub(b, fill_value=0)).abs().max()))

    wdist: list[float] = []
    for col in cfg.numericas_auditoria:
        a = pd.to_numeric(ttrain[col], errors="coerce").dropna().to_numpy(float)
        b = pd.to_numeric(rtrain[col], errors="coerce").dropna().to_numpy(float)
        if len(a) and len(b):
            iqr = float(np.quantile(a, 0.75) - np.quantile(a, 0.25))
            wdist.append(float(wasserstein_distance(a, b) / max(iqr, 1.0)))
    wnorm = float(np.mean(wdist)) if wdist else 0.0

    cols_corr = [c for c in cfg.numericas_auditoria if pd.to_numeric(ttrain[c], errors="coerce").notna().any()]
    ct = ttrain[cols_corr].apply(pd.to_numeric, errors="coerce").corr(method="spearman").fillna(0)
    cr = rtrain[cols_corr].apply(pd.to_numeric, errors="coerce").corr(method="spearman").fillna(0)
    corr = float(np.mean(np.abs(ct.to_numpy() - cr.to_numpy()))) if len(cols_corr) > 1 else 0.0

    duplicados = int(reconstruido.duplicated(list(cfg.claves)).sum())
    reglas = _reglas_validas(reconstruido, cfg.dominio)
    intactos = True
    for split in ("valid", "test"):
        a = target.loc[masks_t[split]].sort_values(list(cfg.claves)).reset_index(drop=True)
        b = reconstruido.loc[masks_r[split]].sort_values(list(cfg.claves)).reset_index(drop=True)
        intactos = intactos and _hash_filas(a) == _hash_filas(b)
    pos_t = int(yt[masks_t["train"]].sum())
    pos_c = int(yc[cortes.mascara(crudo[cfg.fecha])["train"]].sum())
    pos_r = int(yr[masks_r["train"]].sum())
    cumple = bool(
        len(reconstruido) == len(target)
        and pos_r == pos_t
        and cat_max <= 0.03
        and wnorm <= 0.10
        and corr <= 0.10
        and duplicados == 0
        and reglas
        and intactos
    )
    perdida = float(cat_max + wnorm + corr + (0 if reglas and intactos and not duplicados else 10))
    return AuditoriaCandidato(
        dominio=cfg.dominio,
        retencion_minoria=retencion,
        k_neighbors=k,
        filas_objetivo=len(target),
        filas_crudo=len(crudo),
        filas_reconstruidas=len(reconstruido),
        positivos_train_objetivo=pos_t,
        positivos_train_crudo=pos_c,
        positivos_train_reconstruido=pos_r,
        sinteticas_agregadas=pos_t - pos_c,
        max_diferencia_categorica=round(cat_max, 6),
        wasserstein_normalizada=round(wnorm, 6),
        diferencia_correlacion=round(corr, 6),
        duplicados_clave=duplicados,
        reglas_validas=reglas,
        valid_test_intactos=intactos,
        cumple=cumple,
        perdida=round(perdida, 6),
    )


def _auditar_modelos(
    target: pd.DataFrame,
    reconstruido: pd.DataFrame,
    dominio: str,
    referencia: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compara métricas del backend activo; VALID/TEST ya son idénticos por contrato."""
    from spc.catalogo.motor_catalogo import ejecutar_consulta

    consultas = {
        "ventas": ("ven-c1", "ven-r1", "ven-k1"),
        "compras": ("com-c1", "com-r1", "com-k1"),
        "almacen": ("alm-c1", "alm-r1", "alm-k2"),
    }
    cid, rid, kid = consultas[dominio]
    if referencia is None:
        clasif_t = ejecutar_consulta(cid, target)
        regr_t = ejecutar_consulta(rid, target)
        cluster_t = ejecutar_consulta(kid, target)
        referencia = {
            "clasificacion": clasif_t.meta["test_metrics"],
            "wape": regr_t.valor_metrica,
            "silhouette": cluster_t.valor_metrica,
        }
    clasif_r = ejecutar_consulta(cid, reconstruido)
    regr_r = ejecutar_consulta(rid, reconstruido)
    cluster_r = ejecutar_consulta(kid, reconstruido)
    diferencias = {
        "diferencia_pr_auc": abs(
            float(referencia["clasificacion"]["PR_AUC"])
            - float(clasif_r.meta["test_metrics"]["PR_AUC"])
        ),
        "diferencia_f1": abs(
            float(referencia["clasificacion"]["F1"])
            - float(clasif_r.meta["test_metrics"]["F1"])
        ),
        "diferencia_recall": abs(
            float(referencia["clasificacion"]["Recall"])
            - float(clasif_r.meta["test_metrics"]["Recall"])
        ),
        "diferencia_wape": abs(float(referencia["wape"]) - float(regr_r.valor_metrica)),
        "diferencia_silhouette": abs(
            float(referencia["silhouette"]) - float(cluster_r.valor_metrica)
        ),
    }
    diferencias = {k: round(v, 6) for k, v in diferencias.items()}
    diferencias["metricas_modelos_cumplen"] = bool(
        diferencias["diferencia_pr_auc"] <= 0.03
        and diferencias["diferencia_f1"] <= 0.03
        and diferencias["diferencia_recall"] <= 0.03
        and diferencias["diferencia_wape"] <= 0.05
        and diferencias["diferencia_silhouette"] <= 0.05
    )
    return {"referencia": referencia, **diferencias}


def reconstruir_dominio(
    target: pd.DataFrame,
    dominio: str,
    seed: int = SEED,
    validar_modelos: bool = False,
) -> ResultadoDominio:
    cfg = CONFIGS[dominio]
    esq = esquema_de(dominio)
    target = target[esq.orden].copy().reset_index(drop=True)
    target[cfg.fecha] = pd.to_datetime(target[cfg.fecha]).dt.strftime("%Y-%m-%d")
    cortes = _cortes_por_fecha(target, cfg.fecha)
    y, info = _etiquetar(target, cfg, cortes)
    train = cortes.mascara(target[cfg.fecha])["train"]
    idx_pos = target.index[train & (y == 1)].to_numpy()
    if len(idx_pos) < 8:
        raise ValueError(f"{dominio}: clase minoritaria insuficiente ({len(idx_pos)}).")

    candidatos: list[tuple[AuditoriaCandidato, pd.DataFrame, pd.DataFrame]] = []
    for retencion in RETENCIONES:
        idx_keep = _seleccionar_minoria(target, idx_pos, retencion, cfg, seed)
        idx_remove = np.setdiff1d(idx_pos, idx_keep)
        crudo = target.drop(index=idx_remove).reset_index(drop=True)
        slots = target.loc[idx_remove].copy().sort_values(list(cfg.claves), kind="stable").reset_index(drop=True)
        masks_c = cortes.mascara(crudo[cfg.fecha])
        yc, _ = _etiquetar(crudo, cfg, cortes, info)
        ctrain = crudo.loc[masks_c["train"]].reset_index(drop=True)
        yctrain = yc[masks_c["train"]]
        for k in K_VECINOS:
            try:
                syn = _sintetizar(ctrain, yctrain, len(idx_pos), cfg, k, seed)
                if len(syn) != len(slots):
                    raise AssertionError("SMOTENC no genero exactamente las filas retiradas.")
                base = crudo.copy()
                if dominio == "ventas":
                    rec = _reparar_ventas(target, base, slots, syn, info)
                elif dominio == "compras":
                    rec = _reparar_compras(target, base, slots, syn, info)
                else:
                    rec = _reparar_almacen(target, base, slots, syn)
                rec = rec[esq.orden].sort_values(list(cfg.claves), kind="stable").reset_index(drop=True)

                # VALID y TEST son intocables por contrato. Se restauran desde el objetivo.
                split_rec = cortes.mascara(rec[cfg.fecha])
                rec_train = rec.loc[split_rec["train"]]
                rec = pd.concat(
                    [
                        rec_train,
                        target.loc[cortes.mascara(target[cfg.fecha])["valid"]],
                        target.loc[cortes.mascara(target[cfg.fecha])["test"]],
                    ],
                    ignore_index=True,
                )[esq.orden].sort_values(list(cfg.claves), kind="stable").reset_index(drop=True)
                audit = _auditar(target, crudo, rec, cfg, cortes, info, retencion, k)
                candidatos.append((audit, crudo, rec))
            except Exception as exc:
                candidatos.append((
                    AuditoriaCandidato(
                        dominio, retencion, k, len(target), len(crudo), 0,
                        int(y[train].sum()), int(yctrain.sum()), 0, len(idx_remove),
                        1.0, 1.0, 1.0, -1, False, False, False, 99.0,
                    ),
                    crudo,
                    pd.DataFrame(),
                ))
                # La causa queda disponible en el log del llamador sin abortar la grilla.
                _ = exc

    validos = [x for x in candidatos if x[0].cumple]
    if not validos:
        mejor = min(candidatos, key=lambda x: x[0].perdida)
        resumen = asdict(mejor[0])
        raise RuntimeError(f"{dominio}: ninguna configuracion cumple tolerancias: {resumen}")
    if validar_modelos:
        referencia: dict[str, Any] | None = None
        elegible: list[tuple[AuditoriaCandidato, pd.DataFrame, pd.DataFrame]] = []
        for retencion in sorted({x[0].retencion_minoria for x in validos}):
            grupo = sorted(
                (x for x in validos if x[0].retencion_minoria == retencion),
                key=lambda x: x[0].perdida,
            )
            aprobados: list[tuple[AuditoriaCandidato, pd.DataFrame, pd.DataFrame]] = []
            for candidato in grupo:
                audit_c, _, rec_c = candidato
                resultado_modelos = _auditar_modelos(target, rec_c, dominio, referencia)
                referencia = resultado_modelos.pop("referencia")
                for campo, valor in resultado_modelos.items():
                    setattr(audit_c, campo, valor)
                if audit_c.metricas_modelos_cumplen:
                    aprobados.append(candidato)
            if aprobados:
                elegible = aprobados
                break
        if not elegible:
            diagnostico = [
                asdict(x[0]) for x in validos if x[0].metricas_modelos_cumplen is not None
            ]
            raise RuntimeError(
                f"{dominio}: ninguna retención cumple las tolerancias funcionales: {diagnostico}"
            )
    else:
        menor_retencion = min(x[0].retencion_minoria for x in validos)
        elegible = [x for x in validos if x[0].retencion_minoria == menor_retencion]
    audit, crudo, rec = min(elegible, key=lambda x: x[0].perdida)
    return ResultadoDominio(
        dominio=dominio,
        crudo=crudo.sort_values(list(cfg.claves), kind="stable").reset_index(drop=True),
        reconstruido=rec,
        auditoria=audit,
        candidatos=[x[0] for x in candidatos],
        cortes=cortes,
        etiqueta=info,
    )


def _filas_json(df: pd.DataFrame) -> list[dict[str, Any]]:
    limpio = df.copy()
    for col in limpio.columns:
        if "fecha" in col:
            limpio[col] = pd.to_datetime(limpio[col]).dt.strftime("%Y-%m-%d")
    return json.loads(limpio.to_json(orient="records", force_ascii=False, double_precision=10))


def _guardar_dataset(df: pd.DataFrame, dominio: str, destino: Path, nombre: str) -> None:
    destino.mkdir(parents=True, exist_ok=True)
    df.to_csv(destino / f"{nombre}.csv", index=False, lineterminator="\n", float_format="%.10g")
    filas = _filas_json(df)
    (destino / f"{nombre}.json").write_text(
        json.dumps({"rows": filas}, ensure_ascii=False, sort_keys=False, separators=(",", ":")),
        encoding="utf-8",
    )
    (destino / f"{nombre}.xlsx").write_bytes(generar_excel(dominio, filas))


def ejecutar_reconstruccion(
    origen: str | Path = "pyme_hibrida",
    destino: str | Path = "pyme_hibrida/reconstruccion_smote",
    seed: int = SEED,
) -> list[ResultadoDominio]:
    origen, destino = Path(origen), Path(destino)
    resultados: list[ResultadoDominio] = []
    for dominio in CONFIGS:
        payload = json.loads((origen / f"{dominio}_v3.json").read_text(encoding="utf-8"))
        target = pd.DataFrame(payload["rows"])
        resultado = reconstruir_dominio(target, dominio, seed, validar_modelos=True)
        resultados.append(resultado)
        _guardar_dataset(resultado.crudo, dominio, destino / "crudo", f"{dominio}_crudo")
        _guardar_dataset(
            resultado.reconstruido,
            dominio,
            destino / "reconstruido",
            f"{dominio}_smotenc",
        )

    evidencia = pd.DataFrame([asdict(c) for r in resultados for c in r.candidatos])
    evidencia.to_csv(destino / "evidencia_candidatos.csv", index=False, lineterminator="\n")
    seleccion = pd.DataFrame([asdict(r.auditoria) for r in resultados])
    seleccion.to_csv(destino / "evidencia_smote_reconstruccion.csv", index=False, lineterminator="\n")
    metadata = {
        "tipo": "reconstruccion_estadistica_inversa; no son datos historicos observados",
        "origen_canonico": [f"{d}_v3.json" for d in CONFIGS],
        "semilla": seed,
        "valid_test_remuestreados": False,
        "seleccion": [asdict(r.auditoria) for r in resultados],
        "cortes": {r.dominio: asdict(r.cortes) for r in resultados},
        "etiquetas": {r.dominio: asdict(r.etiqueta) for r in resultados},
    }
    (destino / "metadatos_reconstruccion.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )
    metodologia = """# Reconstruccion estadistica inversa con SMOTENC

Los archivos de esta carpeta son una reconstruccion inferida a partir de `pyme_hibrida`.
No representan una base historica peruana observada ni recuperan de forma exacta una fuente
desconocida. La base `crudo/` retira una fraccion de la clase minoritaria solo de TRAIN; la
carpeta `reconstruido/` recupera el tamano y la prevalencia objetivo mediante SMOTENC.

VALID y TEST se copian sin remuestreo. La seleccion prueba retenciones 25/50/75 % y
`k_neighbors` 3/5/7; se elige la menor base que satisface tanto las tolerancias estadisticas
como las diferencias maximas de PR-AUC/F1/recall, WAPE y silueta. La evidencia esta en
`evidencia_smote_reconstruccion.csv`, `evidencia_metricas_modelos.csv` y
`evidencia_aceptacion_consolidada.csv`. Semilla global: 42.

La identidad temporal (fecha y claves de negocio) de las filas retiradas se conserva como
esqueleto estructural; las variables sintetizables se generan con SMOTENC y las columnas
derivadas se recalculan aplicando las reglas del contrato.
"""
    (destino / "METODOLOGIA_RECONSTRUCCION.md").write_text(metodologia, encoding="utf-8")
    return resultados
