"""Test de **portabilidad** del artefacto serializado (Fase 2a).

El artefacto debe poder cargarse y predecir desde un **proceso limpio** que no
aliasa ``__main__`` (la capa de servicio/API hace ``cargar_artefacto`` sin
importar antes nada especial). El bug que esto previene: si el entrenamiento se
ejecuta con ``regresion.py`` como ``__main__``, las clases ``PredictorRegresion``
/ ``ModeloEnsemble`` quedan pickleadas bajo ``__main__`` y la carga falla con
``AttributeError: module '__main__' has no attribute 'PredictorRegresion'``.

El test entrena un modelo pequeno via **import** (dentro de pytest el modulo es
``spc.models.regresion``, no ``__main__``), lo serializa, y lo carga en un
**subproceso** que solo conoce ``spc.utils.serializacion``. Pasa si las clases se
resuelven a ``spc.models.regresion`` (artefacto portable) y falla si quedaron bajo
``__main__``.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

from spc.config import Settings
from spc.models.clasificacion import (
    PredictorClasificacion,
)
from spc.models.clasificacion import (
    entrenar_y_comparar as entrenar_clasificacion,
)
from spc.models.clasificacion import serializar_artefacto as serializar_clasificacion
from spc.models.clustering import (
    CONFIGS,
    PerfiladorClustering,
)
from spc.models.clustering import entrenar_tarea as entrenar_clustering_tarea
from spc.models.clustering import serializar_artefactos as serializar_clustering
from spc.models.regresion import (
    ModeloEnsemble,
    PredictorRegresion,
    entrenar_y_comparar,
    serializar_artefacto,
)

SRC = str(Path(__file__).resolve().parent.parent / "src")


def test_clases_serializadas_no_viven_en_main():
    """Las clases del artefacto se resuelven a su modulo, no ``__main__``."""
    assert PredictorRegresion.__module__ == "spc.models.regresion"
    assert ModeloEnsemble.__module__ == "spc.models.regresion"
    assert PredictorClasificacion.__module__ == "spc.models.clasificacion"
    assert PerfiladorClustering.__module__ == "spc.models.clustering"


def test_artefacto_carga_en_proceso_limpio_y_predice(analitico_sintetico, tmp_path):
    """Serializa el artefacto y lo carga/predice en un **subproceso limpio**.

    El subproceso NO importa ``spc.models.regresion`` por adelantado: solo llama a
    ``cargar_artefacto`` (joblib auto-importa el modulo que el pickle referencia).
    Si el pickle apuntara a ``__main__``, fallaria; con el artefacto portable pasa.
    """
    settings = Settings(base_dir=tmp_path)
    res = entrenar_y_comparar(
        analitico_sintetico, settings, max_train_rows=None, con_cv=False
    )
    ruta_art, _ = serializar_artefacto(res, settings)
    assert ruta_art.exists()

    # El historico para predecir se pasa por disco (parquet) al subproceso.
    ruta_hist = tmp_path / "historico.pkl"
    analitico_sintetico.to_pickle(ruta_hist)

    codigo = textwrap.dedent(
        f"""
        import sys
        sys.path.insert(0, {SRC!r})
        import pandas as pd
        from spc.utils.serializacion import cargar_artefacto
        predictor, meta = cargar_artefacto(r{str(ruta_art)!r})
        hist = pd.read_pickle(r{str(ruta_hist)!r})
        pred = predictor.predecir(hist)
        assert len(pred) == len(hist), "longitud de prediccion inesperada"
        assert (pred >= 0).all(), "predicciones negativas"
        # Tipo resuelto al modulo correcto (no __main__).
        assert type(predictor).__module__ == "spc.models.regresion"
        print("OK", len(pred), meta.get("modelo"))
        """
    )
    proc = subprocess.run(
        [sys.executable, "-c", codigo],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, (
        f"carga en proceso limpio fallo:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    )
    assert proc.stdout.startswith("OK"), proc.stdout


def test_artefacto_clasificacion_carga_en_proceso_limpio(analitico_clasificacion, tmp_path):
    """El artefacto 2b se carga y predice (clase + probabilidad) en un subproceso limpio.

    El subproceso solo llama a ``cargar_artefacto``; joblib auto-importa
    ``spc.models.clasificacion`` desde el pickle. Si la clase viviera bajo
    ``__main__`` fallaria; con el artefacto portable pasa.
    """
    settings = Settings(base_dir=tmp_path)
    res = entrenar_clasificacion(
        analitico_clasificacion, settings, max_train_rows=None, con_cv=False, usar_gpu=False
    )
    ruta_art, _ = serializar_clasificacion(res, settings)
    assert ruta_art.exists()

    ruta_hist = tmp_path / "historico_clf.pkl"
    analitico_clasificacion.to_pickle(ruta_hist)

    codigo = textwrap.dedent(
        f"""
        import sys
        sys.path.insert(0, {SRC!r})
        import pandas as pd
        from spc.utils.serializacion import cargar_artefacto
        predictor, meta = cargar_artefacto(r{str(ruta_art)!r})
        hist = pd.read_pickle(r{str(ruta_hist)!r})
        out = predictor.predecir(hist)
        assert len(out) == len(hist), "longitud inesperada"
        prob = out["probabilidad_demanda_alta"].to_numpy()
        assert ((prob >= 0) & (prob <= 1)).all(), "probabilidad fuera de [0,1]"
        assert set(out["clase_demanda_alta"].unique()).issubset({{0, 1}}), "clase no binaria"
        assert type(predictor).__module__ == "spc.models.clasificacion"
        print("OK", len(out), meta.get("estrategia_desbalance"))
        """
    )
    proc = subprocess.run(
        [sys.executable, "-c", codigo],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, (
        f"carga 2b en proceso limpio fallo:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    )
    assert proc.stdout.startswith("OK"), proc.stdout


def test_artefacto_clustering_carga_en_proceso_limpio(analitico_clustering, tmp_path):
    """El artefacto 2c se carga y asigna segmento (clave + segmento + etiqueta) en un
    subproceso limpio.

    El subproceso solo llama a ``cargar_artefacto``; joblib auto-importa
    ``spc.models.clustering`` desde el pickle. Si ``PerfiladorClustering`` viviera bajo
    ``__main__`` fallaria; con el artefacto portable pasa. Verifica ademas que el scaler
    viaja DENTRO del pipeline (se asigna escalando una entidad nueva).
    """
    settings = Settings(base_dir=tmp_path)
    resultados = {
        "tiendas": entrenar_clustering_tarea(analitico_clustering, CONFIGS["tiendas"], seed=42)
    }
    rutas = serializar_clustering(resultados, settings)
    ruta_art, _ = rutas["tiendas"]
    assert ruta_art.exists()

    ruta_hist = tmp_path / "historico_clust.pkl"
    analitico_clustering.to_pickle(ruta_hist)

    codigo = textwrap.dedent(
        f"""
        import sys
        sys.path.insert(0, {SRC!r})
        import pandas as pd
        from spc.utils.serializacion import cargar_artefacto
        perfilador, meta = cargar_artefacto(r{str(ruta_art)!r})
        hist = pd.read_pickle(r{str(ruta_hist)!r})
        # Entidad nueva: el historico de una sola tienda.
        una = hist[hist["store_nbr"] == 1].copy()
        salida = perfilador.perfilar(una)
        assert len(salida) == 1, "se esperaba una sola entidad"
        assert list(salida.columns) == ["store_nbr", "segmento", "etiqueta_narrativa"]
        seg = int(salida["segmento"].iloc[0])
        assert 0 <= seg < perfilador.k, "segmento fuera de rango"
        assert salida["etiqueta_narrativa"].iloc[0].strip(), "etiqueta vacia"
        assert type(perfilador).__module__ == "spc.models.clustering"
        print("OK", perfilador.k, meta.get("silueta"))
        """
    )
    proc = subprocess.run(
        [sys.executable, "-c", codigo],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, (
        f"carga 2c en proceso limpio fallo:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    )
    assert proc.stdout.startswith("OK"), proc.stdout
