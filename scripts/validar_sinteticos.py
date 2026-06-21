"""Valida los Excels sintéticos **contra el sistema real**, archivo por archivo.

Para cada `.xlsx` generado por `scripts/generar_sinteticos.py` comprueba:

1. **Conformidad strict.** Lo pasa por el MISMO lector del canal Excel
   (``spc.api.ingest.lector.leer_peticion``): si el archivo no cumple el contrato,
   lanza ``ErrorExcel`` y se reporta como fallo.
2. **Modo en línea / lote.** Sube el archivo al endpoint real
   ``POST /{dominio}/excel`` con un ``TestClient`` y el **motor real** cargado desde
   ``models/``, y confirma el código HTTP: **200** (en línea) si
   ``len(history) <= SPC_ONLINE_MAX_ROWS`` (2000), **202** (lote) si lo supera.
3. **Tope de bytes.** Confirma que el archivo pesa menos de 25 MB.

Los archivos a propósito mal formados (``invalidos/``) deben ser **rechazados** con
**422**.

La persistencia del corpus se **desactiva** (``SPC_PERSIST_ENABLED=0``) para no tocar
``data/spc.db``. No modifica el sistema: solo lo invoca como cliente.

Uso::

    python scripts/validar_sinteticos.py --dir data/sinteticos
    python scripts/validar_sinteticos.py --dir data/sinteticos --models models
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path

# Desactiva la persistencia ANTES de importar/crear la app (se lee en el arranque).
os.environ.setdefault("SPC_PERSIST_ENABLED", "0")

_RAIZ = Path(__file__).resolve().parent.parent
if str(_RAIZ / "src") not in sys.path:
    sys.path.insert(0, str(_RAIZ / "src"))

from fastapi.testclient import TestClient  # noqa: E402

from spc.api.ingest import lector  # noqa: E402
from spc.api.main import crear_app  # noqa: E402
from spc.config import online_max_rows  # noqa: E402
from spc.service.artefactos import RegistroArtefactos  # noqa: E402

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MAX_BYTES = 25 * 1024 * 1024

# Prefijo del nombre de archivo -> dominio del contrato.
_PREFIJO_DOMINIO = {"ventas": "sales", "compras": "purchases", "inventario": "inventory"}


def _dominio_de(nombre: str) -> str | None:
    for prefijo, dominio in _PREFIJO_DOMINIO.items():
        if nombre.startswith(prefijo):
            return dominio
    return None


def _filas_y_strict(ruta: Path, dominio: str) -> tuple[int | None, str]:
    """Pasa el archivo por el lector strict. Devuelve (filas_history, estado)."""
    contenido = ruta.read_bytes()
    try:
        peticion = lector.leer_peticion(contenido, dominio)
    except lector.ErrorExcel as exc:
        n = len(exc.detalles)
        return None, f"RECHAZADO ({n} detalle{'s' if n != 1 else ''})"
    return len(peticion.history), "PASA"


def _subir(client: TestClient, dominio: str, ruta: Path) -> int:
    """Sube el .xlsx al endpoint real y devuelve el código HTTP."""
    with ruta.open("rb") as fh:
        r = client.post(f"/{dominio}/excel", files={"file": (ruta.name, fh, XLSX)})
    return r.status_code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Valida los Excels sintéticos contra el sistema.")
    parser.add_argument("--dir", default="data/synthetic", help="Carpeta con los .xlsx (default: data/synthetic).")
    parser.add_argument("--models", default="models", help="Carpeta de artefactos del motor.")
    args = parser.parse_args(argv)

    base = Path(args.dir)
    if not base.is_dir():
        print(f"No existe la carpeta {base}. Genera primero con generar_sinteticos.py.")
        return 2

    umbral = online_max_rows()
    print(f"Cargando motor real desde {args.models} ... (umbral en línea = {umbral} filas)")
    registro = RegistroArtefactos.cargar(Path(args.models))
    app = crear_app(registro=registro, cors_origins=["http://localhost:5173"])

    validos = sorted(p for p in base.glob("*.xlsx"))
    invalidos = sorted((base / "invalidos").glob("*.xlsx"))

    filas_tabla: list[dict[str, str]] = []
    todo_ok = True

    with TestClient(app) as client:
        # --- Archivos válidos: en línea primero, lote después (ascendente por filas) ---
        info: list[tuple[Path, str, int | None, str, float]] = []
        for ruta in validos:
            dominio = _dominio_de(ruta.name)
            if dominio is None:
                continue
            mb = ruta.stat().st_size / (1024 * 1024)
            filas, strict = _filas_y_strict(ruta, dominio)
            info.append((ruta, dominio, filas, strict, mb))

        # Ordena para que el primer job de lote en correr sea el más pequeño (cierre rápido).
        def _orden(t: tuple) -> tuple:
            filas = t[2] if t[2] is not None else 0
            es_lote = filas > umbral
            return (es_lote, filas)

        for ruta, dominio, filas, strict, mb in sorted(info, key=_orden):
            modo_esp = "lote" if (filas or 0) > umbral else "online"
            http_esp = 202 if modo_esp == "lote" else 200
            http_real = _subir(client, dominio, ruta)
            modo_real = {200: "online", 202: "lote"}.get(http_real, f"HTTP {http_real}")

            ok = (strict == "PASA" and http_real == http_esp and mb < MAX_BYTES / (1024 * 1024))
            todo_ok = todo_ok and ok
            filas_tabla.append({
                "archivo": ruta.name,
                "dominio": dominio,
                "filas_history": str(filas if filas is not None else "-"),
                "MB": f"{mb:.2f}",
                "modo_esperado": modo_esp,
                "strict": strict,
                "http_real": str(http_real),
                "modo_real": modo_real,
                "resultado": "OK" if ok else "FALLA",
            })

        # --- Archivos mal formados: deben ser rechazados con 422 ---
        inval_tabla: list[dict[str, str]] = []
        for ruta in invalidos:
            dominio = _dominio_de(ruta.name) or "sales"
            _, strict = _filas_y_strict(ruta, dominio)
            http_real = _subir(client, dominio, ruta)
            ok = (http_real == 422 and strict.startswith("RECHAZADO"))
            todo_ok = todo_ok and ok
            inval_tabla.append({
                "archivo": ruta.name,
                "http_real": str(http_real),
                "strict": strict,
                "resultado": "OK" if ok else "FALLA",
            })

        # Cancela los trabajos de lote en cola para que el cierre no espere de más.
        jobs = getattr(app.state, "jobs", None)
        if jobs is not None:
            jobs._executor.shutdown(wait=False, cancel_futures=True)

    # --- Reporte ---
    _imprimir_tabla(filas_tabla, umbral)
    if inval_tabla:
        _imprimir_invalidos(inval_tabla)

    csv_ruta = base / "resultados_validacion.csv"
    with csv_ruta.open("w", newline="", encoding="utf-8") as fh:
        campos = ["archivo", "dominio", "filas_history", "MB", "modo_esperado",
                  "strict", "http_real", "modo_real", "resultado"]
        w = csv.DictWriter(fh, fieldnames=campos)
        w.writeheader()
        w.writerows(filas_tabla)
        for fila in inval_tabla:
            w.writerow({
                "archivo": f"invalidos/{fila['archivo']}",
                "dominio": "sales",
                "filas_history": "-",
                "MB": "-",
                "modo_esperado": "rechazo(422)",
                "strict": fila["strict"],
                "http_real": fila["http_real"],
                "modo_real": "-",
                "resultado": fila["resultado"],
            })
    print(f"\nResultados escritos en {csv_ruta}")
    print("\n==> TODO OK" if todo_ok else "\n==> HAY FALLOS (revisa la tabla)")
    return 0 if todo_ok else 1


def _imprimir_tabla(filas: list[dict[str, str]], umbral: int) -> None:
    print(f"\n{'archivo':32s} {'dominio':10s} {'filas':>7s} {'MB':>6s} "
          f"{'esperado':9s} {'strict':24s} {'real':10s} {'res':5s}")
    print("-" * 112)
    for f in filas:
        print(f"{f['archivo']:32s} {f['dominio']:10s} {f['filas_history']:>7s} {f['MB']:>6s} "
              f"{f['modo_esperado']:9s} {f['strict']:24s} "
              f"{f['http_real'] + ' ' + f['modo_real']:10s} {f['resultado']:5s}")


def _imprimir_invalidos(filas: list[dict[str, str]]) -> None:
    print("\nArchivos MAL formados (se espera rechazo 422):")
    print(f"{'archivo':28s} {'http':>5s} {'strict':24s} {'res':5s}")
    print("-" * 66)
    for f in filas:
        print(f"{f['archivo']:28s} {f['http_real']:>5s} {f['strict']:24s} {f['resultado']:5s}")


if __name__ == "__main__":
    raise SystemExit(main())
