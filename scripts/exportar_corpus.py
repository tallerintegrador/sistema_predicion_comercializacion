"""Exporta el corpus acumulado (Fase A MEJORADO, ADR-0011) listo para reentrenar.

El servicio guarda cada ``history`` que sube el cliente en la tabla ``observations``
de la base SQLite del corpus (``SPC_DB_PATH``). Este script lee ese corpus —el dataset
que **crece con cada uso**— y lo exporta en el **esquema analítico** que consume el
motor, reutilizando ``adaptador.historico_a_analitico`` (la MISMA traducción
contrato→motor que usa la predicción). Así el archivo exportado encaja con el flujo de
features de ``spc.models.regresion`` / ``train_regresion.py`` para el reentrenamiento en
GPU ("entrenar más y más").

Esto es el **puente manual** de mejora; el reentrenamiento en sí (GPU, validación
rigurosa) sigue siendo un paso aparte y deliberado (ADR-0009/0011). El modelo en
producción se mantiene **congelado** hasta que un nuevo artefacto validado lo reemplace.

Uso:
    python scripts/exportar_corpus.py --out data/corpus.parquet
    python scripts/exportar_corpus.py --out data/corpus_acme.csv --client-id acme
    python scripts/exportar_corpus.py --out data/crudo.csv --raw   # tabla observations tal cual
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

import pandas as pd

# Permite ejecutar el script sin instalar el paquete (añade src/ al path).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from spc.config import db_path  # noqa: E402
from spc.service import adaptador, corpus  # noqa: E402

# Identidad de una observación (igual que el índice UNIQUE del repositorio, ADR-0011).
_CLAVE_SERIE = ("client_id", "date", "store_id", "product_id")


def _deduplicar(obs: pd.DataFrame) -> pd.DataFrame:
    """Quita observaciones duplicadas por (``client_id``, ``date``, ``store_id``, ``product_id``).

    El corpus ya se acumula **idempotente** en la base (índice UNIQUE + ``INSERT OR
    IGNORE``), pero se deduplica también aquí como **red de seguridad**: cubre bases
    previas creadas sin el índice y el modo ``--raw``. Es **imprescindible antes de
    reentrenar**: filas repetidas sesgarían el modelo. Política: se conserva la primera
    aparición (coincide con la del repositorio).
    """
    columnas = [c for c in _CLAVE_SERIE if c in obs.columns]
    return obs.drop_duplicates(subset=columnas, keep="first").reset_index(drop=True)


def _leer_observations(db: Path, client_id: str | None, *, dedup: bool) -> pd.DataFrame:
    """Lee la tabla ``observations`` (opcionalmente filtrada por ``client_id``).

    Reutiliza ``spc.service.corpus`` (la **misma regla de dedup** que el entrenamiento
    por cliente, ADR-0013): por defecto deduplica por serie-día quedándose con la
    observación más reciente.
    """
    if not db.exists():
        raise SystemExit(f"No existe la base de corpus: {db}")
    con = sqlite3.connect(str(db))
    try:
        return corpus.leer_observaciones(con, client_id, dedup=dedup)
    finally:
        con.close()


def _escribir(df: pd.DataFrame, out: Path) -> None:
    """Escribe el frame a Parquet o CSV según la extensión de ``out``."""
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.suffix.lower() == ".parquet":
        df.to_parquet(out, index=False)
    else:
        df.to_csv(out, index=False)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Exporta el corpus acumulado del SPC.")
    parser.add_argument("--out", required=True, type=Path, help="Archivo destino (.parquet o .csv).")
    parser.add_argument(
        "--db", type=Path, default=None, help="Ruta de la base SQLite (default: SPC_DB_PATH)."
    )
    parser.add_argument(
        "--client-id", default=None, help="Exporta solo el corpus de este cliente."
    )
    parser.add_argument(
        "--raw",
        action="store_true",
        help="Exporta la tabla observations tal cual (sin traducir al esquema analítico).",
    )
    parser.add_argument(
        "--no-dedup",
        action="store_true",
        help="No deduplicar por serie-día (por defecto se conserva la observación más reciente).",
    )
    args = parser.parse_args(argv)

    db = args.db or db_path()
    # ``--raw`` vuelca la tabla tal cual (sin dedup); el export analítico deduplica por
    # defecto (la misma regla que el entrenamiento por cliente; --no-dedup lo desactiva).
    dedup = not (args.raw or args.no_dedup)
    obs = _leer_observations(db, args.client_id, dedup=dedup)
    if obs.empty:
        print(f"Corpus vacío (db={db}, client_id={args.client_id}). Nada que exportar.")
        return 1

    # Deduplicación obligatoria antes de exportar/entrenar (red de seguridad; ADR-0011).
    n_leidas = len(obs)
    obs = _deduplicar(obs)

    # ``--raw``: la tabla observations tal cual (ya deduplicada). Por defecto, el MISMO
    # traductor contrato→motor que la predicción, para que el archivo encaje con
    # construir_features (spc.models.regresion) en el reentrenamiento.
    salida = obs if args.raw else adaptador.historico_a_analitico(_a_contrato(obs))

    _escribir(salida, args.out)
    quitadas = n_leidas - len(obs)
    print(
        f"Exportadas {len(salida)} filas a {args.out} "
        f"({len(obs)} observaciones únicas; {quitadas} duplicadas descartadas; db={db})."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
