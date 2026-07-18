"""Organiza metadatos y genera un manifiesto sin mover los datasets existentes."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

EVIDENCIAS = (
    "evidencia_candidatos.csv",
    "evidencia_smote_reconstruccion.csv",
    "evidencia_metricas_modelos.csv",
    "evidencia_aceptacion_consolidada.csv",
    "detalle_remuestreo_backend.json",
    "metadatos_reconstruccion.json",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as archivo:
        for bloque in iter(lambda: archivo.read(1024 * 1024), b""):
            digest.update(bloque)
    return digest.hexdigest()


def _leer_seleccion(raiz: Path) -> list[dict[str, str]]:
    path = raiz / "evidencia_smote_reconstruccion.csv"
    with path.open(encoding="utf-8", newline="") as archivo:
        return list(csv.DictReader(archivo))


def _parametros(seleccion: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "semilla": 42,
        "particion_temporal": {"train": 0.70, "valid": 0.15, "test": 0.15},
        "remuestreo_backend": {
            "aplicar_en": "train",
            "sampling_strategy": "auto (50/50)",
            "seleccion": "PR-AUC en validación; empate absoluto <= 0.005 favorece simplicidad",
            "umbral": "seleccionado únicamente en validación",
        },
        "reconstruccion_archivos": {
            fila["dominio"]: {
                "retencion_minoria": float(fila["retencion_minoria"]),
                "k_neighbors": int(fila["k_neighbors"]),
                "filas_crudo": int(fila["filas_crudo"]),
                "filas_reconstruidas": int(fila["filas_reconstruidas"]),
                "sinteticas_agregadas": int(fila["sinteticas_agregadas"]),
            }
            for fila in seleccion
        },
    }


def organizar(raiz: Path) -> None:
    raiz = raiz.resolve()
    if not (raiz / "crudo").is_dir() or not (raiz / "reconstruido").is_dir():
        raise ValueError(f"No parece una reconstrucción válida: {raiz}")

    evidencia = raiz / "evidencia"
    documentacion = raiz / "documentacion"
    config = raiz / "config"
    for carpeta in (evidencia, documentacion, config, raiz / "notebooks", raiz / "qa_excel"):
        carpeta.mkdir(parents=True, exist_ok=True)

    for nombre in EVIDENCIAS:
        origen = raiz / nombre
        if origen.exists():
            shutil.copy2(origen, evidencia / nombre)
    metodologia = raiz / "METODOLOGIA_RECONSTRUCCION.md"
    if metodologia.exists():
        shutil.copy2(metodologia, documentacion / metodologia.name)

    seleccion = _leer_seleccion(raiz)
    parametros = _parametros(seleccion)
    (config / "parametros_smotenc.json").write_text(
        json.dumps(parametros, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )

    filas_por_etapa = {
        (fila["dominio"], "crudo"): int(fila["filas_crudo"]) for fila in seleccion
    }
    filas_por_etapa.update(
        {(fila["dominio"], "reconstruido"): int(fila["filas_reconstruidas"]) for fila in seleccion}
    )
    manifiesto: list[dict[str, Any]] = []
    for etapa, patron in (("crudo", "*_crudo.*"), ("reconstruido", "*_smotenc.*")):
        for path in sorted((raiz / etapa).glob(patron)):
            dominio = path.stem.split("_")[0]
            manifiesto.append(
                {
                    "dominio": dominio,
                    "etapa": etapa,
                    "formato": path.suffix.lstrip("."),
                    "ruta": path.relative_to(raiz).as_posix(),
                    "filas": filas_por_etapa[(dominio, etapa)],
                    "bytes": path.stat().st_size,
                    "sha256": _sha256(path),
                }
            )

    campos = ["dominio", "etapa", "formato", "ruta", "filas", "bytes", "sha256"]
    with (evidencia / "manifiesto_datasets.csv").open("w", encoding="utf-8", newline="") as archivo:
        writer = csv.DictWriter(archivo, fieldnames=campos, lineterminator="\n")
        writer.writeheader()
        writer.writerows(manifiesto)
    (evidencia / "manifiesto_datasets.json").write_text(
        json.dumps({"archivos": manifiesto}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Organización actualizada: {raiz}")
    print(f"Datasets registrados: {len(manifiesto)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--raiz",
        type=Path,
        default=Path("pyme_hibrida/reconstruccion_smote"),
    )
    args = parser.parse_args()
    organizar(args.raiz)


if __name__ == "__main__":
    main()
