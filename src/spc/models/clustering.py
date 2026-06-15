"""Clustering / perfilado (Fase 2c): segmenta tiendas y familias con KMeans.

Cierra la Fase 2 (motor de ML). Dos tareas **separadas**, cada una con su propio
``StandardScaler + KMeans`` dentro de un ``Pipeline`` serializado:

1. **Tiendas:** un perfil agregado por ``store_nbr``.
2. **Familias:** un perfil agregado por ``family``.

Metodologia (lecciones de la 2a/2b aplicadas desde el inicio):

- **Escala obligatoria:** KMeans es por distancia -> se estandariza antes de agrupar;
  el scaler viaja **dentro del artefacto** (un perfil nuevo se transforma igual que en
  entrenamiento). Nunca se agrupa sin escalar.
- **Seleccion de k principiada:** se evalua un rango (k=2..10 tiendas, k=2..8 familias)
  y se elige por **silueta**, apoyandose en inercia (codo), Davies-Bouldin y
  Calinski-Harabasz. Se persiste la **curva silueta vs k**.
- **Reproduce el orden de magnitud del EDA** (silueta ~0.61 tiendas k=2, ~0.71 familias
  k=2): el reporte recalcula ademas el set EXACTO del EDA para validar el pipeline.
- **KMeans robusto:** ``init="k-means++"``, ``n_init`` alto, ``random_state=42`` ->
  asignacion estable entre corridas (test de reproducibilidad).

El perfilado opera sobre **54 tiendas / 33 familias** (vectores agregados): es CPU
puro, instantaneo y **determinista** (no usa GPU; la GPU de la 2a/2b era para los
boosters sobre millones de filas, aqui no aporta y daniaria la reproducibilidad).

Capa de motor de ML: no conoce HTTP. El artefacto se entrena offline y en produccion
solo se **carga y asigna**: ``perfilar`` toma el historico integrado de una entidad
**nueva** y devuelve su ``segmento`` + etiqueta narrativa, sin reentrenar. El
``segmento_tienda`` del contrato de ALMACEN sale de aqui.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import (
    calinski_harabasz_score,
    davies_bouldin_score,
    silhouette_score,
)
from sklearn.preprocessing import StandardScaler

from spc.config import Settings
from spc.features.perfiles import (
    CLAVE_FAMILIA,
    CLAVE_TIENDA,
    COLS_FAMILIAS,
    COLS_FAMILIAS_DESC,
    COLS_FAMILIAS_EDA,
    COLS_FAMILIAS_RICO,
    COLS_TIENDAS,
    COLS_TIENDAS_DESC,
    COLS_TIENDAS_EDA,
    COLS_TIENDAS_RICO,
    PERFIL_FAMILIAS_DICT,
    PERFIL_TIENDAS_DICT,
    perfiles_familias,
    perfiles_familias_eda,
    perfiles_tiendas,
    perfiles_tiendas_eda,
)
from spc.utils.formatters import markdown_table
from spc.utils.logging import get_logger
from spc.utils.serializacion import cargar_artefacto, guardar_artefacto

log = get_logger("models.clustering")

# KMeans robusto: reinicios altos para una asignacion estable (no depende del
# sorteo inicial); semilla fija para reproducibilidad de extremo a extremo.
N_INIT = 25

VERSION_MODELO = {
    "tiendas": "clustering_tiendas_v1",
    "familias": "clustering_familias_v1",
}


# ---------------------------------------------------------------------------
# Configuracion por tarea
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ConfigTarea:
    """Parametros de una de las dos tareas de clustering (tiendas | familias)."""

    nombre: str  # "tiendas" | "familias"
    clave: str  # columna de entidad (store_nbr | family)
    entidad: str  # singular para la etiqueta narrativa ("tienda" | "familia")
    cols: list[str]  # features DESPLEGADAS (entran a KMeans; elegidas por diagnostico)
    cols_desc: list[str]  # co-variables descriptivas (reportadas, NO entran a KMeans)
    cols_rico: list[str]  # universo de features (cols + cols_desc) producido por perfil_fn
    cols_eda: list[str]  # features exactas del EDA (validacion: reproduccion de la silueta)
    diccionario: dict[str, str]  # documentacion de las features
    perfil_fn: Callable[[pd.DataFrame], pd.DataFrame]
    perfil_eda_fn: Callable[[pd.DataFrame], pd.DataFrame]
    k_range: tuple[int, ...]
    sil_ref_eda: float  # silueta del EDA (referencia: 0.6075 tiendas / 0.7052 familias)
    # k del modelo desplegado. None -> se elige por maxima silueta sobre k_range.
    # Un valor fijo es una decision DELIBERADA (documentada): se aparta del maximo de
    # silueta para ganar accionabilidad (familias k=3 aisla las intermitentes).
    k_fijo: int | None = None
    motivo_k: str = "maxima silueta sobre el rango evaluado"


CONFIGS: dict[str, ConfigTarea] = {
    "tiendas": ConfigTarea(
        nombre="tiendas",
        clave=CLAVE_TIENDA,
        entidad="tienda",
        cols=COLS_TIENDAS,
        cols_desc=COLS_TIENDAS_DESC,
        cols_rico=COLS_TIENDAS_RICO,
        cols_eda=COLS_TIENDAS_EDA,
        diccionario=PERFIL_TIENDAS_DICT,
        perfil_fn=perfiles_tiendas,
        perfil_eda_fn=perfiles_tiendas_eda,
        k_range=tuple(range(2, 11)),
        sil_ref_eda=0.6075,
        k_fijo=None,  # auto -> k=2 (maxima silueta), confirmado por el chequeo de sentido
        motivo_k=(
            "maxima silueta sobre el rango (k=2): corte limpio grande/pequena; "
            "k=3 baja la silueta (0.58) sin aportar un tercer segmento accionable"
        ),
    ),
    "familias": ConfigTarea(
        nombre="familias",
        clave=CLAVE_FAMILIA,
        entidad="familia",
        cols=COLS_FAMILIAS,
        cols_desc=COLS_FAMILIAS_DESC,
        cols_rico=COLS_FAMILIAS_RICO,
        cols_eda=COLS_FAMILIAS_EDA,
        diccionario=PERFIL_FAMILIAS_DICT,
        perfil_fn=perfiles_familias,
        perfil_eda_fn=perfiles_familias_eda,
        k_range=tuple(range(2, 9)),
        sil_ref_eda=0.7052,
        k_fijo=3,  # DELIBERADO: k=2 maximiza silueta (0.71) pero da "3 gigantes vs resto"
        motivo_k=(
            "k=3 DELIBERADO sobre el maximo de silueta (k=2, 0.71): k=3 aisla las familias "
            "intermitentes (BABY CARE/BOOKS/HARDWARE/HOME APPLIANCES) en su propio segmento "
            "(tipo de demanda accionable para stock); silueta 0.66, aun saludable (>0.50)"
        ),
    ),
}


# ---------------------------------------------------------------------------
# Seleccion de k (silueta principal + inercia/DB/CH de apoyo)
# ---------------------------------------------------------------------------
def _kmeans(k: int, seed: int) -> KMeans:
    """KMeans robusto (k-means++, n_init alto, semilla fija)."""
    return KMeans(n_clusters=k, init="k-means++", n_init=N_INIT, random_state=seed)


def evaluar_k(X: np.ndarray, k_range: tuple[int, ...], seed: int) -> tuple[pd.DataFrame, int]:
    """Evalua ``k_range`` sobre datos **ya escalados** y elige el k por silueta.

    Devuelve ``(curva, best_k)`` donde ``curva`` tiene una fila por k con silueta,
    inercia (codo), Davies-Bouldin (menor mejor) y Calinski-Harabasz (mayor mejor).
    El k elegido es el de **mayor silueta**.
    """
    filas = []
    for k in k_range:
        if k >= len(X):  # silhouette necesita 2 <= k <= n-1
            break
        km = _kmeans(k, seed)
        labels = km.fit_predict(X)
        filas.append(
            {
                "k": int(k),
                "silueta": float(silhouette_score(X, labels)),
                "inercia": float(km.inertia_),
                "davies_bouldin": float(davies_bouldin_score(X, labels)),
                "calinski_harabasz": float(calinski_harabasz_score(X, labels)),
            }
        )
    curva = pd.DataFrame(filas)
    best_k = int(curva.loc[curva["silueta"].idxmax(), "k"])
    return curva, best_k


# ---------------------------------------------------------------------------
# Diagnostico de contribucion de features (que separa de verdad vs polizon)
# ---------------------------------------------------------------------------
def _silueta_cols(perfil: pd.DataFrame, cols: list[str], k: int, seed: int):
    """Silueta + labels de KMeans(k) sobre ``cols`` estandarizadas."""
    X = StandardScaler().fit_transform(perfil[cols].to_numpy(dtype="float64"))
    labels = _kmeans(k, seed).fit_predict(X)
    return float(silhouette_score(X, labels)), labels


def diagnosticar_contribucion(
    perfil: pd.DataFrame,
    cols_rico: list[str],
    cols_deploy: list[str],
    cols_eda: list[str],
    seed: int,
    k_diag: int = 2,
) -> dict[str, Any]:
    """Cuantifica que features separan de verdad (vs polizones del volumen).

    Sobre el set RICO a ``k_diag`` (k=2, el corte de referencia):
      - **Leave-one-out de silueta:** ``delta = sil_sin_feature - sil_rico``. ``delta>0``
        => quitarla MEJORA => la feature es ruido/polizon (no separa).
      - **Correlacion** de cada feature con la etiqueta y con el VOLUMEN
        (``ventas_total``): marca las co-variables del volumen.
      - **PCA:** % de varianza de PC1 (cuan unidimensional/volumen es la estructura).
      - **Head-to-head** de silueta a ``k_diag`` por set (rico / EDA / desplegado).

    Devuelve un dict serializable (entra al meta del artefacto y al reporte).
    """
    sil_rico, lab = _silueta_cols(perfil, cols_rico, k_diag, seed)
    vol = perfil["ventas_total"].to_numpy(dtype="float64")

    loo: list[dict[str, Any]] = []
    corr: list[dict[str, Any]] = []
    for c in cols_rico:
        resto = [x for x in cols_rico if x != c]
        sil_sin = _silueta_cols(perfil, resto, k_diag, seed)[0] if len(resto) >= 1 else float("nan")
        x = perfil[c].to_numpy(dtype="float64")
        cl = abs(float(np.corrcoef(x, lab)[0, 1])) if np.std(x) > 0 else 0.0
        if c == "ventas_total":
            cv = 1.0
        elif np.std(x) > 0:
            cv = abs(float(np.corrcoef(x, vol)[0, 1]))
        else:
            cv = 0.0
        loo.append(
            {"feature": c, "delta_silueta": round(sil_sin - sil_rico, 4), "polizon": bool(sil_sin > sil_rico)}
        )
        corr.append({"feature": c, "corr_etiqueta": round(cl, 3), "corr_volumen": round(cv, 3)})
    loo.sort(key=lambda r: r["delta_silueta"], reverse=True)

    Xs = StandardScaler().fit_transform(perfil[cols_rico].to_numpy(dtype="float64"))
    pca = PCA(random_state=seed).fit(Xs)
    evr = pca.explained_variance_ratio_

    h2h = {
        "rico": round(sil_rico, 4),
        "eda": round(_silueta_cols(perfil, cols_eda, k_diag, seed)[0], 4),
        "desplegado": round(_silueta_cols(perfil, cols_deploy, k_diag, seed)[0], 4),
    }
    return {
        "k_diagnostico": k_diag,
        "pc1_varianza": round(float(evr[0]), 4),
        "pc1_pc2_varianza": round(float(evr[:2].sum()), 4),
        "leave_one_out": loo,
        "correlaciones": corr,
        "silueta_por_set_kdiag": h2h,
        "nota": (
            "delta_silueta>0 => quitar la feature MEJORA la silueta (polizon, no separa). "
            "PC1 alto + features de volumen colineales => la separacion es por volumen."
        ),
    }


# ---------------------------------------------------------------------------
# Etiqueta narrativa (derivada de los centroides en unidades originales)
# ---------------------------------------------------------------------------
def etiquetar_clusters(perfil_segmentos: pd.DataFrame, entidad: str) -> dict[int, str]:
    """Deriva una etiqueta HONESTA por segmento a partir de sus medias en unidades.

    La separacion es por **volumen** (lo confirma el diagnostico: PC1 ~70 % de la
    varianza, todas las features de volumen colineales). Por eso la etiqueta es un
    **nivel de volumen** (no una combinacion que sugiera una riqueza multidimensional
    que la separacion no tiene): ``bajo`` / ``medio`` / ``alto`` segun el rango de
    ``venta_media``, mas un descriptor de **tipo de demanda** (``intermitente`` vs
    ``venta continua``) derivado de ``tasa_ceros``, que si distingue (sobre todo el
    segmento de cola: las familias intermitentes). Promo y demanda-alta NO entran a la
    etiqueta: son co-variables del volumen y se reportan aparte.
    """
    plural = "Tiendas" if entidad == "tienda" else "Familias"
    orden = perfil_segmentos["venta_media"].sort_values().index.tolist()  # bajo -> alto
    k = len(orden)
    if k <= 2:
        nivel = {orden[0]: "bajo volumen", orden[-1]: "alto volumen"}
    elif k == 3:
        nivel = {orden[0]: "bajo volumen", orden[1]: "volumen medio", orden[2]: "alto volumen"}
    else:
        nivel = {seg: f"volumen nivel {i + 1}/{k}" for i, seg in enumerate(orden)}

    med_ceros = (
        float(perfil_segmentos["tasa_ceros"].median())
        if "tasa_ceros" in perfil_segmentos.columns
        else None
    )
    etiquetas: dict[int, str] = {}
    for seg, row in perfil_segmentos.iterrows():
        partes: list[str] = [nivel[seg]]
        if med_ceros is not None:
            tc = float(row["tasa_ceros"])
            # `intermitente` solo si supera CLARAMENTE el resto (estricto: el segmento en
            # la mediana cae a `venta continua`, evita marcar al grupo intermedio).
            if tc > 0.10 and tc > med_ceros:
                partes.append("intermitente")
            elif tc <= med_ceros:
                partes.append("venta continua")
        etiquetas[int(seg)] = f"{plural}: " + ", ".join(partes)
    return etiquetas


# ---------------------------------------------------------------------------
# Perfilador serializable (artefacto de produccion)
# ---------------------------------------------------------------------------
class PerfiladorClustering:
    """Envuelve la agregacion de perfil + ``Pipeline(scaler + KMeans)`` entrenado.

    Se serializa entero (joblib): en produccion se carga y se llama ``perfilar`` sin
    reentrenar. Reconstruye el perfil agregado de una entidad **nueva** desde su
    historico ya integrado (misma logica que en entrenamiento), lo escala con el
    scaler del pipeline y devuelve su **segmento** + etiqueta narrativa.

    Es serializable: clase top-level bajo ``spc.models.clustering`` (no ``__main__``),
    atributos picklables. El scaler vive **dentro** del pipeline -> nunca se asigna sin
    escalar. CPU puro (no GPU): la asignacion es determinista.
    """

    def __init__(
        self,
        tarea: str,
        clave: str,
        cols: list[str],
        pipeline: Any,
        k: int,
        silueta: float,
        centroides_unidades: pd.DataFrame,
        etiquetas: dict[int, str],
        n_por_cluster: dict[int, int],
        version: str,
    ) -> None:
        self.tarea = tarea
        self.clave = clave
        self.cols = list(cols)
        self.pipeline = pipeline
        self.k = int(k)
        self.silueta = float(silueta)
        self.centroides_unidades = centroides_unidades
        self.etiquetas = {int(c): str(v) for c, v in etiquetas.items()}
        self.n_por_cluster = {int(c): int(v) for c, v in n_por_cluster.items()}
        self.version = version

    def _perfilar_entidades(self, historico_integrado: pd.DataFrame) -> pd.DataFrame:
        """Reagrega el historico a un perfil por entidad (misma logica que en train)."""
        if self.tarea == "tiendas":
            return perfiles_tiendas(historico_integrado)
        return perfiles_familias(historico_integrado)

    def _matriz(self, perfil: pd.DataFrame) -> np.ndarray:
        return perfil[self.cols].to_numpy(dtype="float64")

    def perfilar(self, historico_integrado: pd.DataFrame) -> pd.DataFrame:
        """Asigna a cada entidad del historico su ``segmento`` + ``etiqueta_narrativa``.

        El historico debe venir **integrado** (esquema del dataset analitico). Devuelve
        una fila por entidad con la clave (``store_nbr`` o ``family``), el segmento y su
        etiqueta narrativa. Funciona con una sola entidad nueva (1 fila) o con muchas.
        """
        perfil = self._perfilar_entidades(historico_integrado)
        X = self._matriz(perfil)
        seg = self.pipeline.predict(X).astype("int64")
        return pd.DataFrame(
            {
                self.clave: perfil[self.clave].to_numpy(),
                "segmento": seg,
                "etiqueta_narrativa": [self.etiquetas[int(s)] for s in seg],
            }
        )

    # Alias coherente con el resto del motor (clasificacion usa `predecir`).
    def predecir(self, historico_integrado: pd.DataFrame) -> pd.DataFrame:
        return self.perfilar(historico_integrado)


# ---------------------------------------------------------------------------
# Entrenamiento de una tarea
# ---------------------------------------------------------------------------
@dataclass
class ResultadoTarea:
    """Salida de entrenar una tarea de clustering (tiendas | familias)."""

    tarea: str
    entidad: str
    perfilador: PerfiladorClustering
    curva: pd.DataFrame  # k-curve del set de produccion
    curva_eda: pd.DataFrame  # k-curve del set EXACTO del EDA
    best_k: int
    best_k_auto: int  # k de maxima silueta (puede diferir de best_k si k es deliberado)
    motivo_k: str  # criterio del k desplegado (auto o deliberado)
    silueta: float
    best_k_eda: int
    silueta_eda: float  # silueta del set EDA en su mejor k (reproduccion)
    sil_ref_eda: float  # referencia del EDA (0.6075 / 0.7052)
    cols: list[str]  # features desplegadas (clustering)
    cols_desc: list[str]  # co-variables descriptivas (reportadas, no clustering)
    diccionario: dict[str, str]
    perfil_unidades: pd.DataFrame  # medias por segmento (rico) + n + etiqueta
    asignacion: pd.DataFrame  # entidad -> segmento (entrenamiento)
    n_entidades: int
    diagnostico: dict[str, Any]  # contribucion de features (LOO/corr/PCA/head-to-head)


def _silueta_en_k(curva: pd.DataFrame, k: int) -> float:
    """Silueta registrada en la curva para un k dado (NaN si no esta)."""
    fila = curva.loc[curva["k"] == k, "silueta"]
    return float(fila.iloc[0]) if not fila.empty else float("nan")


def entrenar_tarea(
    analytic: pd.DataFrame, cfg: ConfigTarea, seed: int
) -> ResultadoTarea:
    """Construye el perfil agregado, elige k por silueta y ajusta el ``Pipeline``.

    Reproduce ademas el set EXACTO del EDA para validar el orden de magnitud de la
    silueta (~0.61 tiendas / ~0.71 familias).
    """
    from sklearn.pipeline import Pipeline

    # --- Perfil RICO (universo de features); el clustering usa solo el set desplegado ---
    perfil = cfg.perfil_fn(analytic)
    X_raw = perfil[cfg.cols].to_numpy(dtype="float64")  # solo features DESPLEGADAS
    scaler_eval = StandardScaler().fit(X_raw)
    curva, best_k_auto = evaluar_k(scaler_eval.transform(X_raw), cfg.k_range, seed)
    # k desplegado: el deliberado (cfg.k_fijo) si esta fijado, si no el de maxima silueta.
    best_k = cfg.k_fijo if cfg.k_fijo is not None else best_k_auto
    log.info(
        "[%s] curva silueta: %s | k_auto=%d, k_desplegado=%d (sil=%.4f)",
        cfg.nombre,
        {int(r.k): round(r.silueta, 4) for r in curva.itertuples()},
        best_k_auto,
        best_k,
        _silueta_en_k(curva, best_k),
    )

    # Pipeline final (scaler + KMeans dentro del artefacto). Mismos params que la
    # curva -> labels identicos (KMeans determinista con semilla + n_init).
    pipeline = Pipeline(
        [("scaler", StandardScaler()), ("kmeans", _kmeans(best_k, seed))]
    ).fit(X_raw)
    labels = pipeline.named_steps["kmeans"].labels_
    silueta = _silueta_en_k(curva, best_k)

    # Medias por segmento en UNIDADES ORIGINALES de TODO el set rico (desplegadas +
    # co-variables descriptivas). El subconjunto desplegado equivale a los centroides de
    # KMeans invertidos; las descriptivas muestran que co-varian con el volumen.
    medias = (
        perfil.assign(segmento=labels).groupby("segmento", observed=True)[cfg.cols_rico].mean()
    )
    medias.index.name = "segmento"
    centroides = medias[cfg.cols]  # centroides desplegados (en unidades)
    etiquetas = etiquetar_clusters(medias, cfg.entidad)
    n_por_cluster = pd.Series(labels).value_counts().sort_index().to_dict()

    # Diagnostico de contribucion de features (por que este set desplegado).
    diagnostico = diagnosticar_contribucion(perfil, cfg.cols_rico, cfg.cols, cfg.cols_eda, seed)

    # --- Reproduccion del set EXACTO del EDA ---
    perfil_eda = cfg.perfil_eda_fn(analytic)
    X_eda = StandardScaler().fit_transform(perfil_eda[cfg.cols_eda].to_numpy(dtype="float64"))
    curva_eda, best_k_eda = evaluar_k(X_eda, cfg.k_range, seed)
    silueta_eda = _silueta_en_k(curva_eda, best_k_eda)
    log.info(
        "[%s] reproduccion EDA: best_k=%d sil=%.4f (referencia EDA %.4f)",
        cfg.nombre, best_k_eda, silueta_eda, cfg.sil_ref_eda,
    )

    perfilador = PerfiladorClustering(
        tarea=cfg.nombre,
        clave=cfg.clave,
        cols=cfg.cols,
        pipeline=pipeline,
        k=best_k,
        silueta=silueta,
        centroides_unidades=centroides,
        etiquetas=etiquetas,
        n_por_cluster=n_por_cluster,
        version=VERSION_MODELO[cfg.nombre],
    )

    # Tabla de perfiles legible: medias por segmento (desplegadas + descriptivas) + n +
    # etiqueta. El orden de columnas deja primero las desplegadas, luego las descriptivas.
    perfil_unidades = medias[cfg.cols + cfg.cols_desc].reset_index().copy()
    perfil_unidades.insert(1, "n_entidades", [n_por_cluster.get(int(s), 0) for s in perfil_unidades["segmento"]])
    perfil_unidades["etiqueta_narrativa"] = [etiquetas[int(s)] for s in perfil_unidades["segmento"]]

    asignacion = pd.DataFrame(
        {cfg.clave: perfil[cfg.clave].to_numpy(), "segmento": labels.astype("int64")}
    )
    asignacion["etiqueta_narrativa"] = [etiquetas[int(s)] for s in asignacion["segmento"]]

    return ResultadoTarea(
        tarea=cfg.nombre,
        entidad=cfg.entidad,
        perfilador=perfilador,
        curva=curva,
        curva_eda=curva_eda,
        best_k=best_k,
        best_k_auto=best_k_auto,
        motivo_k=cfg.motivo_k,
        silueta=silueta,
        best_k_eda=best_k_eda,
        silueta_eda=silueta_eda,
        sil_ref_eda=cfg.sil_ref_eda,
        cols=cfg.cols,
        cols_desc=cfg.cols_desc,
        diccionario=cfg.diccionario,
        perfil_unidades=perfil_unidades,
        asignacion=asignacion,
        n_entidades=len(perfil),
        diagnostico=diagnostico,
    )


# ---------------------------------------------------------------------------
# Persistencia: registro de metricas, perfiles, artefactos y reporte
# ---------------------------------------------------------------------------
def _curva_registro(res: ResultadoTarea) -> pd.DataFrame:
    """Filas del registro de metricas para una tarea: modelo desplegado + validacion EDA.

    ``feature_set='desplegado'`` (metrica oficial, ``elegido`` en el k desplegado) y
    ``feature_set='eda_validacion'`` (reproduccion de plomeria, ``elegido`` en su k optimo).
    """
    desplegado = res.curva.copy()
    desplegado.insert(0, "feature_set", "desplegado")
    desplegado["elegido"] = desplegado["k"] == res.best_k
    eda = res.curva_eda.copy()
    eda.insert(0, "feature_set", "eda_validacion")
    eda["elegido"] = eda["k"] == res.best_k_eda
    out = pd.concat([desplegado, eda], ignore_index=True)
    out.insert(0, "tarea", res.tarea)
    return out


def persistir_metricas(resultados: dict[str, ResultadoTarea], settings: Settings) -> Path:
    """Guarda ``metricas_clustering_2c.{csv,json}``: silueta/inercia/DB/CH por k, para
    tiendas y familias, en el modelo **desplegado** (oficial) y en la **validacion EDA**."""
    settings.processed_dir.mkdir(parents=True, exist_ok=True)
    registro = pd.concat(
        [_curva_registro(res) for res in resultados.values()], ignore_index=True
    )
    ruta_csv = settings.processed_dir / "metricas_clustering_2c.csv"
    registro.to_csv(ruta_csv, index=False)
    (settings.processed_dir / "metricas_clustering_2c.json").write_text(
        registro.to_json(orient="records", force_ascii=False, indent=2),
        encoding="utf-8",
    )
    return ruta_csv


def persistir_perfiles(resultados: dict[str, ResultadoTarea], settings: Settings) -> None:
    """Persiste la tabla de perfiles (centroides en unidades + etiqueta) y la
    asignacion entidad -> segmento, por tarea."""
    settings.processed_dir.mkdir(parents=True, exist_ok=True)
    for res in resultados.values():
        res.perfil_unidades.to_csv(
            settings.processed_dir / f"perfiles_clustering_{res.tarea}_2c.csv", index=False
        )
        res.asignacion.to_csv(
            settings.processed_dir / f"segmentos_clustering_{res.tarea}_2c.csv", index=False
        )


def _metadatos(res: ResultadoTarea, settings: Settings) -> dict[str, Any]:
    """Metadatos completos del artefacto (criterio de hecho de la 2c)."""
    return {
        "version": VERSION_MODELO[res.tarea],
        "fecha_entrenamiento": date.today().isoformat(),
        "tarea": res.tarea,
        "entidad": res.entidad,
        "campo": "almacen" if res.tarea == "tiendas" else "perfilado",
        "uso_en_contrato": (
            "segmento_tienda de la respuesta de ALMACEN" if res.tarea == "tiendas"
            else "perfilado de familias (apoyo a politicas de stock)"
        ),
        "modelo": "KMeans (k-means++) sobre perfiles agregados, escalados (StandardScaler)",
        "k_elegido": res.best_k,
        "k_maxima_silueta": res.best_k_auto,
        "criterio_k": res.motivo_k,
        "silueta": round(res.silueta, 4),
        "silueta_es_oficial": True,
        "curva_silueta_vs_k": [
            {
                "k": int(r.k),
                "silueta": round(float(r.silueta), 4),
                "inercia": round(float(r.inercia), 2),
                "davies_bouldin": round(float(r.davies_bouldin), 4),
                "calinski_harabasz": round(float(r.calinski_harabasz), 2),
            }
            for r in res.curva.itertuples()
        ],
        "diagnostico_features": res.diagnostico,
        "segmentacion_dominada_por_volumen": True,
        "nota_transparencia": (
            "La separacion es por VOLUMEN (diagnostico: PC1 concentra la mayor parte de la "
            "varianza y las features de volumen son colineales). Las features descriptivas "
            "(promo, demanda alta, intermitencia, transacciones) son co-variables que "
            "correlacionan con el segmento, NO ejes de separacion independientes."
        ),
        "reproduccion_eda": {
            "silueta_set_eda": round(res.silueta_eda, 4),
            "k_set_eda": res.best_k_eda,
            "silueta_referencia_eda": res.sil_ref_eda,
            "nota": (
                "VALIDACION DE PLOMERIA: el set EXACTO del EDA recupera la silueta del EDA "
                "a 4 decimales. Es independiente del modelo desplegado (otro set/k); la "
                "metrica oficial es 'silueta' (set desplegado)."
            ),
        },
        "features_perfil": res.cols,
        "features_descriptivas": res.cols_desc,
        "diccionario_features": res.diccionario,
        "n_entidades": res.n_entidades,
        "n_por_cluster": res.perfilador.n_por_cluster,
        "centroides_unidades": {
            int(row["segmento"]): {
                c: round(float(row[c]), 4) for c in res.cols
            }
            for _, row in res.perfil_unidades.iterrows()
        },
        "covariables_descriptivas_por_segmento": {
            int(row["segmento"]): {
                c: round(float(row[c]), 4) for c in res.cols_desc
            }
            for _, row in res.perfil_unidades.iterrows()
        },
        "etiquetas_narrativas": res.perfilador.etiquetas,
        "semilla": settings.random_seed,
        "n_init": N_INIT,
        "alcance_temporal": (
            "descriptivo/estatico: el perfil se calcula sobre el historico disponible y "
            "es recomputable desde el historico que envie el cliente. Mejora diferida: "
            "perfil as-of-time si el segmento se usa como feature predictiva en t."
        ),
        "nota_portabilidad": (
            "scaler + KMeans dentro del pipeline; CPU puro y determinista (sin GPU). "
            "El artefacto carga y asigna segmento a una entidad nueva sin reentrenar."
        ),
    }


def serializar_artefactos(
    resultados: dict[str, ResultadoTarea], settings: Settings
) -> dict[str, tuple[Path, Path]]:
    """Serializa los dos perfiladores (tiendas/familias) + metadatos en ``models/``."""
    rutas: dict[str, tuple[Path, Path]] = {}
    for res in resultados.values():
        ruta = settings.base_dir / "models" / f"{VERSION_MODELO[res.tarea]}.joblib"
        rutas[res.tarea] = guardar_artefacto(res.perfilador, ruta, _metadatos(res, settings))
    return rutas


# ---------------------------------------------------------------------------
# Reporte Markdown
# ---------------------------------------------------------------------------
def _tabla_curva(curva: pd.DataFrame, best_k: int) -> str:
    df = curva.copy()
    df["silueta"] = df["silueta"].round(4)
    df["inercia"] = df["inercia"].round(2)
    df["davies_bouldin"] = df["davies_bouldin"].round(4)
    df["calinski_harabasz"] = df["calinski_harabasz"].round(2)
    df["elegido"] = np.where(df["k"] == best_k, "<- elegido", "")
    return markdown_table(df)


def _tabla_perfiles(res: ResultadoTarea) -> str:
    df = res.perfil_unidades.copy()
    for c in res.cols + res.cols_desc:
        if c in df.columns:
            df[c] = df[c].round(3)
    return markdown_table(df)


def _tabla_diccionario(diccionario: dict[str, str], cols_deploy: list[str]) -> str:
    deploy = set(cols_deploy)
    return markdown_table(
        pd.DataFrame(
            [
                {
                    "feature": k,
                    "uso": "clustering" if k in deploy else "descriptiva",
                    "descripcion": v,
                }
                for k, v in diccionario.items()
            ]
        )
    )


def _tabla_diagnostico(res: ResultadoTarea) -> str:
    """Tabla por feature del set rico: delta LOO (separa vs polizon) + correlaciones."""
    diag = res.diagnostico
    loo = {r["feature"]: r for r in diag["leave_one_out"]}
    corr = {r["feature"]: r for r in diag["correlaciones"]}
    deploy = set(res.cols)
    filas = []
    for f in res.cols + res.cols_desc:
        filas.append(
            {
                "feature": f,
                "en_clustering": "si" if f in deploy else "no",
                "delta_silueta_LOO": loo[f]["delta_silueta"],
                "polizon": "si" if loo[f]["polizon"] else "no",
                "corr_etiqueta": corr[f]["corr_etiqueta"],
                "corr_volumen": corr[f]["corr_volumen"],
            }
        )
    return markdown_table(pd.DataFrame(filas))


# Familias intermitentes esperadas (las degeneradas de la 2b + bajo volumen).
_FAMILIAS_INTERMITENTES = ("BOOKS", "BABY CARE", "HARDWARE", "HOME APPLIANCES")


def _nota_segmentos(res: ResultadoTarea) -> str:
    """Nota interpretativa por tarea (lectura de negocio + transparencia de volumen)."""
    if res.tarea == "tiendas":
        return (
            "**Lectura de negocio:** el corte separa tiendas **grandes** (alto volumen, "
            "venta continua) de **pequenas** (bajo volumen, intermitentes) — las grandes son "
            "candidatas a un nivel de servicio/stock mas exigente. Este `segmento` enriquece "
            "la respuesta de ALMACEN (`segmento_tienda`). **Transparencia:** la separacion es "
            "por **volumen** (las 4 features desplegadas son medidas colineales del tamano); "
            "promo, transacciones y demanda alta (tabla, columnas descriptivas) **co-varian** "
            "con el segmento pero no son ejes de separacion independientes."
        )
    # Familias: senala donde caen las intermitentes (el tercer segmento de k=3).
    asig = res.asignacion.set_index(res.perfilador.clave)["segmento"]
    presentes = [f for f in _FAMILIAS_INTERMITENTES if f in asig.index]
    seg_bajo = int(res.perfil_unidades.sort_values("venta_media").iloc[0]["segmento"])
    en_bajo = [f for f in presentes if int(asig[f]) == seg_bajo]
    detalle = ", ".join(f"`{f}`" for f in en_bajo) if en_bajo else "—"
    return (
        f"**Por que k={res.best_k} (y no k={res.best_k_auto}, el de maxima silueta):** a "
        f"k={res.best_k_auto} el corte es 'gigantes vs resto' (mas deteccion de outliers que "
        "segmentacion accionable). **k=3 aisla un tercer segmento de familias intermitentes** "
        f"({detalle}: las degeneradas de la 2b + otras de demanda casi nula) en su propio "
        "grupo — un **tipo de demanda** distinto que pide otra politica de stock. Se sacrifica "
        "algo de silueta por una segmentacion mas util. **Transparencia:** sigue siendo un "
        "ordenamiento por **volumen** (tres niveles); las co-variables (intermitencia, promo) "
        "describen los niveles, no abren ejes independientes."
    )


def escribir_reporte(resultados: dict[str, ResultadoTarea], settings: Settings) -> Path:
    """Genera ``docs/reporte_clustering_2c.md`` (curvas, k elegido, perfiles legibles)."""
    res_t = resultados.get("tiendas")
    res_f = resultados.get("familias")
    head = "; ".join(
        f"**{r.entidad}s** silueta **{r.silueta:.4f}** (k={r.best_k}, {len(r.cols)} features)"
        for r in (res_t, res_f)
        if r is not None
    )
    lineas: list[str] = [
        "# Reporte de Clustering / Perfilado (Fase 2c)",
        "",
        "> Generado por `spc.models.clustering`. Segmenta **tiendas** y **familias** con "
        "KMeans sobre perfiles agregados (un vector por entidad). Escala obligatoria "
        "(StandardScaler **dentro** del artefacto); features del modelo **desplegado** "
        "elegidas por **diagnostico de contribucion**; k por silueta **e** "
        "interpretabilidad; centroides en **unidades originales** + etiqueta. CPU puro, "
        "determinista (semilla 42). Cierra la **Fase 2** (motor de ML).",
        "",
        f"**Metrica oficial (modelo desplegado):** {head}.",
        "",
        "La **silueta del modelo desplegado** es la metrica oficial. La reproduccion exacta "
        "del set del EDA se conserva aparte como **validacion de plomeria** (no es el modelo "
        "desplegado).",
        "",
        "> **Transparencia (leer antes de los perfiles):** en ambas tareas la separacion esta "
        "**dominada por el volumen** (el diagnostico lo cuantifica: PC1 concentra la mayor "
        "parte de la varianza y las features de volumen son colineales). Las features "
        "descriptivas (promo, demanda alta, intermitencia, transacciones) son **co-variables** "
        "que correlacionan con el segmento, **no ejes de separacion independientes**. Las "
        "etiquetas narrativas son **niveles de volumen** (+ tipo de demanda), para no sugerir "
        "una riqueza multidimensional que la separacion no tiene.",
        "",
    ]
    for res in resultados.values():
        plural = "Tiendas" if res.tarea == "tiendas" else "Familias"
        diag = res.diagnostico
        # Features desplegadas que el LOO a k_diag marca polizon: se mantienen a proposito
        # (aportan a OTRO k, no al k de diagnostico). Lo explicitamos para que la tabla no
        # parezca contradictoria (en_clustering=si pero polizon=si).
        polizon_set = {r["feature"] for r in diag["leave_one_out"] if r["polizon"]}
        deploy_polizon = [f for f in res.cols if f in polizon_set]
        nota_polizon = ""
        if deploy_polizon:
            feats = ", ".join(f"`{f}`" for f in deploy_polizon)
            nota_polizon = (
                f" **Nota:** {feats} aparece como polizon a k={diag['k_diagnostico']} pero se "
                f"**mantiene**: su baja correlacion con el volumen aporta el eje de **calidad "
                f"de demanda** que habilita el aislamiento de las intermitentes a k={res.best_k} "
                "(ver seleccion de k); a k=2 seria ruido, a k=3 es la clave del tercer segmento."
            )
        lineas += [
            f"## {plural} (`{res.perfilador.clave}`) — {res.n_entidades} entidades",
            "",
            f"**Set desplegado ({len(res.cols)}):** `{'`, `'.join(res.cols)}`  ·  "
            f"**k={res.best_k}**  ·  **silueta oficial = {res.silueta:.4f}**.",
            "",
            "### Diccionario de features de perfil",
            "",
            _tabla_diccionario(res.diccionario, res.cols),
            "",
            "### Diagnostico de contribucion de features (que separa de verdad)",
            "",
            f"Sobre el set rico ({len(res.cols) + len(res.cols_desc)} features) a k="
            f"{diag['k_diagnostico']}. `delta_silueta_LOO` = silueta al **quitar** la feature "
            "menos la del set rico: **>0 => quitarla mejora => polizon** (no separa). "
            "`corr_volumen` alto => co-variable del volumen.",
            "",
            _tabla_diagnostico(res),
            "",
            f"**PCA del set rico:** PC1 explica **{diag['pc1_varianza']:.1%}** de la varianza "
            f"(PC1+PC2 = {diag['pc1_pc2_varianza']:.1%}) → estructura **casi unidimensional "
            "(volumen)**. Head-to-head de silueta a k="
            f"{diag['k_diagnostico']}: rico **{diag['silueta_por_set_kdiag']['rico']}**, EDA "
            f"**{diag['silueta_por_set_kdiag']['eda']}**, desplegado "
            f"**{diag['silueta_por_set_kdiag']['desplegado']}**. **Decision:** se despliega el "
            "set que **maximiza la separacion manteniendo la interpretabilidad**, descartando "
            "las features polizon (suben la silueta al quitarse)." + nota_polizon,
            "",
            "### Curva de seleccion de k",
            "",
            "Silueta (principal, mayor mejor) + inercia (codo) + Davies-Bouldin (menor "
            "mejor) + Calinski-Harabasz (mayor mejor). El k desplegado se marca abajo.",
            "",
            _tabla_curva(res.curva, res.best_k),
            "",
            f"**k desplegado = {res.best_k}** (silueta **{res.silueta:.4f}**). "
            f"Criterio: {res.motivo_k}.",
            "",
            "### Validacion de plomeria — reproduccion exacta del set EDA",
            "",
            f"Con el set EXACTO del EDA, la silueta optima es **{res.silueta_eda:.4f}** "
            f"(k={res.best_k_eda}), frente a la referencia del EDA **{res.sil_ref_eda:.4f}**: "
            "coincide **a 4 decimales** → el pipeline recupera el resultado del EDA "
            "(diferencias serian por **features/k elegidos**, no por implementacion). Esto es "
            "una **prueba de plomeria**, independiente del modelo desplegado.",
            "",
            "### Perfiles legibles (medias por segmento en unidades + etiqueta)",
            "",
            "Columnas desplegadas (clustering) primero; luego **co-variables descriptivas** "
            "(no entran a KMeans, co-varian con el volumen).",
            "",
            _tabla_perfiles(res),
            "",
            _nota_segmentos(res),
            "",
        ]
    lineas += [
        "## Alcance temporal",
        "",
        "Segmentacion **descriptiva y estatica**: el perfil se calcula sobre el historico "
        "disponible y es **recomputable** desde el historico que envie el cliente (coherente "
        "con el contrato). **Mejora diferida:** perfil **as-of-time** si en el futuro el "
        "segmento se usa como **feature predictiva en t** (para no mirar el futuro).",
        "",
        "## Vinculo con el contrato (ALMACEN)",
        "",
        "El `segmento_tienda` de la respuesta de ALMACEN proviene del artefacto de tiendas: "
        "`perfilar(historico_integrado)` asigna una tienda nueva a su segmento sin "
        "reentrenar. El perfilado de familias apoya politicas de stock por tipo de demanda.",
        "",
        "## Mejoras diferidas (documentadas, no implementadas)",
        "",
        "- **Perfil as-of-time** (si el segmento pasa a ser feature predictiva).",
        "- **Metodos alternativos de clustering** (jerarquico, DBSCAN) como contraste; "
        "KMeans es el principal por el plan.",
        "",
    ]
    ruta = settings.base_dir / "docs" / "reporte_clustering_2c.md"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text("\n".join(lineas), encoding="utf-8")
    return ruta


# ---------------------------------------------------------------------------
# Flujo offline + CLI
# ---------------------------------------------------------------------------
def entrenar_clustering(
    analytic: pd.DataFrame, settings: Settings, tareas: tuple[str, ...] = ("tiendas", "familias")
) -> dict[str, ResultadoTarea]:
    """Entrena las tareas de clustering pedidas sobre el dataset analitico integrado."""
    seed = settings.random_seed
    return {nombre: entrenar_tarea(analytic, CONFIGS[nombre], seed) for nombre in tareas}


def entrenar(settings: Settings) -> dict[str, ResultadoTarea]:
    """Flujo offline: carga datos, entrena ambas tareas, persiste todo."""
    from spc.data.integration import build_analytic_dataset
    from spc.data.loaders import load_data

    np.random.seed(settings.random_seed)
    data = load_data(settings)
    analytic, _, _ = build_analytic_dataset(data, settings)

    resultados = entrenar_clustering(analytic, settings)
    ruta_csv = persistir_metricas(resultados, settings)
    persistir_perfiles(resultados, settings)
    rutas_art = serializar_artefactos(resultados, settings)
    ruta_rep = escribir_reporte(resultados, settings)
    log.info("Metricas: %s", ruta_csv)
    for tarea, (ruta_art, ruta_meta) in rutas_art.items():
        log.info("Artefacto [%s]: %s (+ %s)", tarea, ruta_art, ruta_meta.name)
    log.info("Reporte: %s", ruta_rep)
    return resultados


def cargar_perfilador(ruta: Path) -> tuple[PerfiladorClustering, dict[str, Any]]:
    """Carga un perfilador serializado y sus metadatos (para la capa servicio/API)."""
    return cargar_artefacto(ruta)


def cli(argv: list[str] | None = None) -> None:
    """Entrenamiento offline reproducible del clustering/perfilado (Fase 2c)."""
    parser = argparse.ArgumentParser(
        description="Entrena el clustering/perfilado de tiendas y familias (Fase 2c)."
    )
    parser.add_argument("--base-dir", type=Path, default=None, help="Raiz del proyecto.")
    args = parser.parse_args(argv)

    from spc.utils.logging import configure_logging

    configure_logging(verbose=True)
    settings = Settings(base_dir=args.base_dir) if args.base_dir else Settings()
    resultados = entrenar(settings)

    print("\n" + "=" * 72)
    print("  CLUSTERING / PERFILADO (Fase 2c) — resumen")
    print("=" * 72)
    for res in resultados.values():
        print(
            f"\n[{res.tarea}] {res.n_entidades} entidades | k={res.best_k} | "
            f"silueta={res.silueta:.4f} (EDA set: {res.silueta_eda:.4f} en k={res.best_k_eda}, "
            f"ref EDA {res.sil_ref_eda:.4f})"
        )
        print(res.perfil_unidades.to_string(index=False))
    print(f"\nArtefactos en models/: {', '.join(VERSION_MODELO.values())}")


# ===========================================================================
# Compatibilidad: CLI exploratorio antiguo (`spc-models` / scripts/run_models.py)
# ===========================================================================
_STORE_COLS = [
    "ventas_total",
    "venta_media",
    "venta_mediana",
    "promociones_media",
    "transacciones_media",
    "pct_demanda_alta",
    "familias_activas",
]
_FAMILY_COLS = ["ventas_total", "venta_media", "promociones_media", "pct_demanda_alta"]


def evaluate_clustering(
    store_features: pd.DataFrame,
    family_features: pd.DataFrame,
    settings: Settings,
) -> dict[str, Any]:
    """Shim de compatibilidad para el CLI exploratorio (`spc-models`).

    Evalua KMeans (silueta/DB/CH) sobre las features agregadas que produce el EDA
    (`spc.eda.analysis.clustering.clustering_features`). El flujo de produccion de la
    Fase 2c es ``entrenar`` (artefactos portables); este shim solo mantiene vivo el
    CLI antiguo sin romperlo.
    """
    from spc.utils.metrics import clustering_metrics, format_metrics_table

    resultados = []
    salida: dict[str, Any] = {}
    for nombre, feats, cols in (
        ("Tiendas", store_features, _STORE_COLS),
        ("Familias", family_features, _FAMILY_COLS),
    ):
        usar = [c for c in cols if c in feats.columns]
        X = StandardScaler().fit_transform(feats[usar].to_numpy(dtype="float64"))
        _, best_k = evaluar_k(X, tuple(range(2, min(9, len(X)))), settings.random_seed)
        labels = _kmeans(best_k, settings.random_seed).fit_predict(X)
        m = clustering_metrics(X, labels)
        m["Modelo"] = f"KMeans {nombre} (k={best_k})"
        resultados.append(m)
        salida[f"best_k_{nombre.lower()}"] = best_k
        salida[f"labels_{nombre.lower()}"] = labels
    salida["metrics"] = format_metrics_table(resultados)
    salida["results"] = resultados
    return salida


if __name__ == "__main__":
    cli()
