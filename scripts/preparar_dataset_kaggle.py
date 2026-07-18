"""Construye un paquete plano, documentado y verificable para publicar en Kaggle."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import zipfile
from pathlib import Path
from typing import Any

import pandas as pd

RAIZ_PROYECTO = Path(__file__).resolve().parent.parent
if str(RAIZ_PROYECTO / "src") not in sys.path:
    sys.path.insert(0, str(RAIZ_PROYECTO / "src"))

from spc.synthetic.esquemas import esquema_de, validar_conforme  # noqa: E402

DOMINIOS = ("ventas", "compras", "almacen")
CLAVES = {
    "ventas": ["fecha", "id_tienda", "sku"],
    "compras": ["fecha_orden", "id_proveedor", "sku"],
    "almacen": ["fecha", "id_tienda", "sku"],
}
FECHAS = {"ventas": "fecha", "compras": "fecha_orden", "almacen": "fecha"}
ARCHIVOS_CSV = {
    f"raw_{d}.csv": ("crudo", f"{d}_crudo.csv", d, "crudo") for d in DOMINIOS
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as archivo:
        for bloque in iter(lambda: archivo.read(1024 * 1024), b""):
            digest.update(bloque)
    return digest.hexdigest()


def _perfil_csv(path: Path, dominio: str, etapa: str) -> dict[str, Any]:
    df = pd.read_csv(path)
    validar_conforme(df, dominio)
    duplicados = int(df.duplicated(CLAVES[dominio]).sum())
    if duplicados:
        raise ValueError(f"{path.name}: {duplicados} claves de negocio duplicadas")
    nulos = int(df.isna().sum().sum())
    if nulos:
        raise ValueError(f"{path.name}: {nulos} valores nulos")
    fechas = pd.to_datetime(df[FECHAS[dominio]], format="%Y-%m-%d", errors="raise")
    pii = {
        c
        for c in df.columns
        if any(token in c.lower() for token in ("nombre", "email", "telefono", "direccion", "dni"))
    }
    if pii:
        raise ValueError(f"{path.name}: revisar posibles columnas personales {sorted(pii)}")
    return {
        "archivo": path.name,
        "dominio": dominio,
        "etapa": etapa,
        "filas": int(len(df)),
        "columnas": int(len(df.columns)),
        "fecha_min": str(fechas.min().date()),
        "fecha_max": str(fechas.max().date()),
        "valores_nulos": nulos,
        "duplicados_clave": duplicados,
        "columnas_posible_pii": sorted(pii),
    }


def _diccionario_datos() -> str:
    lineas = [
        "# Diccionario de datos",
        "",
        "Las etiquetas de clasificación no se almacenan: se derivan durante el experimento.",
        "",
    ]
    for dominio in DOMINIOS:
        esquema = esquema_de(dominio)
        lineas.extend(
            [
                f"## {dominio.capitalize()}",
                "",
                f"Grano: {esquema.grano}.",
                "",
                "| Columna | Tipo | Rol | Descripción | Fórmula |",
                "|---|---|---|---|---|",
            ]
        )
        for col in esquema.columnas:
            descripcion = col.descripcion.replace("|", "\\|")
            formula = (col.formula or "—").replace("|", "\\|")
            lineas.append(
                f"| `{col.nombre}` | {col.tipo} | {col.rol} | {descripcion} | {formula} |"
            )
        lineas.extend(
            [
                "",
                f"Objetivo de regresión: `{esquema.objetivo_regresion}`.",
                f"Etiqueta derivada: `{esquema.etiqueta_clasificacion}` — {esquema.derivacion_etiqueta}.",
                "",
            ]
        )
    return "\n".join(lineas)


def _readme(perfiles: list[dict[str, Any]]) -> str:
    filas = "\n".join(
        f"| `{p['archivo']}` | {p['dominio']} | {p['etapa']} | {p['filas']:,} | {p['columnas']} |"
        for p in perfiles
    )
    return f"""# PYME híbrida retail — dataset crudo

Dataset crudo educativo para proyectos de ventas, compras e inventario. Cada persona puede
aplicar su propia limpieza, ingeniería de variables, estrategia de remuestreo y modelos.

> **Advertencia de procedencia:** no son datos históricos observados ni una recuperación
> exacta de una fuente desconocida. Conservan el perfil estadístico híbrido/Favorita del
> proyecto y constituyen una reconstrucción inferida.

## Archivos

| Archivo | Dominio | Etapa | Filas | Columnas |
|---|---|---|---:|---:|
{filas}

Además se incluyen el diccionario de datos, el perfil de calidad y los hashes SHA-256.

## Posibles usos

- Pronóstico de demanda y cantidades de compra.
- Clasificación de riesgos o eventos poco frecuentes.
- Segmentación de productos, tiendas y proveedores.
- Investigación de técnicas para datos desbalanceados.
- Comparación de SMOTE, SMOTENC, ponderación de clases u otros métodos.

## Uso responsable

Si el proyecto usa remuestreo, debe aplicarlo sólo sobre TRAIN. VALID y TEST deben quedar
sin remuestreo para evitar fuga de información y una evaluación artificialmente optimista.

Consulta `PROVENANCE_AND_LIMITATIONS.md` y `LICENSE_REVIEW_REQUIRED.md` antes de publicar.
"""


def _procedencia() -> str:
    return """# Procedencia y limitaciones

- La base `raw_*` fue inferida estadísticamente desde los datasets objetivo de
  `pyme_hibrida`.
- No se incluyen archivos remuestreados, etiquetas precalculadas ni resultados de modelos.
- Cada usuario es responsable de definir sus particiones y su procesamiento experimental.
- La equivalencia es estadística y funcional, no fila por fila.
- Los datos mantienen una huella híbrida/Favorita; no representan operaciones observadas
  de una PYME peruana.
- Los identificadores son claves de tienda, proveedor y SKU; no se incluyen nombres,
  correos, teléfonos, direcciones ni documentos personales.

## Revisión obligatoria antes de publicación pública

El proyecto tiene relación estadística y estructural con Corporación Favorita. Debe
confirmarse que las reglas y derechos aplicables a la fuente permiten redistribuir esta
transformación. Hasta completar esa revisión, el paquete debe subirse como **privado**.
"""


def _instrucciones_subida() -> str:
    return """# Subida a Kaggle

1. Edita `dataset-metadata.json`:
   - reemplaza `YOUR_KAGGLE_USERNAME`;
   - confirma el título y slug;
   - sustituye `other` por la licencia autorizada, si corresponde.
2. Revisa `LICENSE_REVIEW_REQUIRED.md`.
3. Instala y autentica la CLI oficial:

```powershell
pip install kaggle
kaggle auth login
```

4. Crea primero el dataset como privado, desde esta carpeta:

```powershell
kaggle datasets create -p .
```

No añadas `--public` hasta verificar en Kaggle la vista previa, los archivos y la licencia.
Para una versión posterior:

```powershell
kaggle datasets version -p . -m "Descripción de los cambios"
```
"""


def _zip_determinista(carpeta: Path, destino: Path) -> None:
    with zipfile.ZipFile(destino, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in sorted(p for p in carpeta.iterdir() if p.is_file()):
            info = zipfile.ZipInfo(path.name, date_time=(2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, path.read_bytes(), compresslevel=9)


def preparar(origen: Path, salida: Path) -> tuple[Path, Path]:
    origen = origen.resolve()
    salida = salida.resolve()
    salida.mkdir(parents=True, exist_ok=True)

    permitidos = set(ARCHIVOS_CSV) | {
        "dataset-metadata.json",
        "README.md",
        "DATA_DICTIONARY.md",
        "DATA_PROFILE.json",
        "PROVENANCE_AND_LIMITATIONS.md",
        "LICENSE_REVIEW_REQUIRED.md",
        "UPLOAD_INSTRUCTIONS.md",
        "SHA256SUMS.txt",
    }
    inesperados = {p.name for p in salida.iterdir()} - permitidos
    if inesperados:
        raise ValueError(f"La salida contiene archivos no administrados: {sorted(inesperados)}")

    perfiles: list[dict[str, Any]] = []
    for destino_nombre, (carpeta, origen_nombre, dominio, etapa) in ARCHIVOS_CSV.items():
        fuente = origen / carpeta / origen_nombre
        destino = salida / destino_nombre
        shutil.copyfile(fuente, destino)
        perfiles.append(_perfil_csv(destino, dominio, etapa))

    metadata = {
        "title": "PYME Hybrid Retail Raw Dataset",
        "id": "YOUR_KAGGLE_USERNAME/pyme-hibrida-retail-raw",
        "licenses": [{"name": "other"}],
        "keywords": [
            "retail",
            "demand-forecasting",
            "inventory",
            "time-series",
            "synthetic-data",
        ],
    }
    (salida / "dataset-metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (salida / "README.md").write_text(_readme(perfiles), encoding="utf-8")
    (salida / "DATA_DICTIONARY.md").write_text(_diccionario_datos(), encoding="utf-8")
    (salida / "DATA_PROFILE.json").write_text(
        json.dumps({"archivos": perfiles}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (salida / "PROVENANCE_AND_LIMITATIONS.md").write_text(_procedencia(), encoding="utf-8")
    (salida / "LICENSE_REVIEW_REQUIRED.md").write_text(
        "# Licencia pendiente de revisión\n\n"
        "No publiques este paquete como público hasta confirmar los derechos de redistribución "
        "aplicables a la huella Favorita y elegir una licencia compatible.\n",
        encoding="utf-8",
    )
    (salida / "UPLOAD_INSTRUCTIONS.md").write_text(_instrucciones_subida(), encoding="utf-8")

    archivos_hash = sorted(p for p in salida.iterdir() if p.is_file() and p.name != "SHA256SUMS.txt")
    checksums = "\n".join(f"{_sha256(p)}  {p.name}" for p in archivos_hash) + "\n"
    (salida / "SHA256SUMS.txt").write_text(checksums, encoding="ascii")

    zip_path = salida.parent / f"{salida.name}.zip"
    _zip_determinista(salida, zip_path)
    return salida, zip_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--origen",
        type=Path,
        default=Path("pyme_hibrida/reconstruccion_smote"),
    )
    parser.add_argument(
        "--salida",
        type=Path,
        default=Path("dist/kaggle/pyme-hibrida-retail-raw"),
    )
    args = parser.parse_args()
    carpeta, zip_path = preparar(args.origen, args.salida)
    print(f"Paquete Kaggle: {carpeta}")
    print(f"ZIP: {zip_path}")


if __name__ == "__main__":
    main()
