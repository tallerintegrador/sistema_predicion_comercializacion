"""Datos de ejemplo **ricos** (~10.000 filas por módulo) para 2 rubros de PYME peruana.

Genera, para 2 rubros (minimarket y ferretería), los tres archivos (ventas, compras,
almacén) en Excel y JSON, **conformes al esquema v3** (columnas de la plantilla del
catálogo), listos para subir a la app (/v3/{modulo}) y probar el ML con datos que se
sienten reales.

Reutiliza el motor sintético realista (``spc.synthetic``): estacionalidad semanal,
promociones, fines de semana, feriados peruanos, Yape/Plin, perfiles de proveedor, etc.,
y le pone **identidad de rubro** (nombres reales de productos/locales/proveedores y precios
en soles) **sin cambiar las columnas**. Reproducible con ``--seed`` (default 2025).

Tamaños (≈10.080 filas cada uno):
- Ventas / Almacén: 6 tiendas × 16 productos × 105 días.
- Compras: 10 proveedores × 16 productos × 63 órdenes (una orden por semana).

Más entidades a propósito (6 tiendas, 16 SKUs, 10 proveedores) para que el **clustering**
tenga con qué agrupar. Las zonas de almacén son A/B/C (fijas del dominio: un almacén tiene
pocas zonas).

Uso::

    ./venv/Scripts/python.exe scripts/generar_ricos_10k.py            # -> ejemplos/datos_ricos_10k/
    ./venv/Scripts/python.exe scripts/generar_ricos_10k.py --seed 7 -o ejemplos/mis_datos
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_RAIZ = Path(__file__).resolve().parent.parent
if str(_RAIZ / "src") not in sys.path:
    sys.path.insert(0, str(_RAIZ / "src"))

import pandas as pd  # noqa: E402

from spc.api.ingest import dominios_excel  # noqa: E402
from spc.service import onboarding  # noqa: E402
from spc.synthetic import generar_dominio  # noqa: E402
from spc.synthetic.esquemas import esquema_de, validar_conforme  # noqa: E402

# --- Tamaños para ~10.000 filas por módulo ---
N_TIENDAS = 6
N_PRODUCTOS = 16
N_DIAS = 105           # ventas/almacén: 6 × 16 × 105 = 10.080 filas
N_PROVEEDORES = 10
N_ORDENES = 63         # compras: 10 × 16 × 63 = 10.080 filas
DIAS_ENTRE_ORDENES = 7  # una orden por semana (≈15 meses de historia)

# ---------------------------------------------------------------------------
# 2 rubros ricos. Cada producto: (nombre, categoría, precio de venta en soles).
# ---------------------------------------------------------------------------
RUBROS: dict[str, dict] = {
    "minimarket_mi_barrio": {
        "titulo": "Minimarket / Bodega «Mi Barrio»",
        "tiendas": [
            "Bodega San Martín (SJL)", "Minimarket La Esquina (Comas)",
            "Bodega Doña Rosa (VMT)", "Market El Ahorro (Ate)",
            "Minimarket Los Olivos", "Bodega La Molina Central",
        ],
        "proveedores": [
            "Distribuidora Alicorp", "Gloria S.A.", "Backus Depósito", "Molitalia",
            "Comercial Andina", "Distribuidora Norte", "Mayorista Central",
            "Proveedor La Victoria", "Nestlé Perú", "P&G Distribuidora",
        ],
        "productos": [
            ("Arroz Costeño 5kg", "Abarrotes", 22.0), ("Aceite Primor 1L", "Abarrotes", 9.5),
            ("Azúcar Rubia 1kg", "Abarrotes", 4.5), ("Fideos Don Vittorio 500g", "Abarrotes", 3.8),
            ("Atún Florida lata", "Abarrotes", 5.5), ("Leche Gloria tarro", "Lácteos", 4.2),
            ("Yogurt Gloria 1L", "Lácteos", 7.5), ("Queso Bonlé 500g", "Lácteos", 16.0),
            ("Inca Kola 1.5L", "Bebidas", 7.0), ("Agua San Luis 2.5L", "Bebidas", 5.0),
            ("Cerveza Pilsen 650ml", "Bebidas", 6.5), ("Detergente Bolívar 1kg", "Limpieza", 12.0),
            ("Papel higiénico Suave x4", "Limpieza", 6.5), ("Galletas Soda Field", "Snacks", 2.5),
            ("Chocolate Sublime", "Snacks", 1.5), ("Shampoo Head&Shoulders", "Cuidado personal", 18.0),
        ],
    },
    "ferreteria_construperu": {
        "titulo": "Ferretería «ConstruPerú»",
        "tiendas": [
            "Ferretería El Constructor (Ate)", "Ferretería Los Andes (VMT)",
            "Ferretería Maestro Pérez (SJL)", "Ferretería La Unión (Comas)",
            "Ferretería El Martillo (Callao)", "Ferretería Central (Lima)",
        ],
        "proveedores": [
            "Cementos Pacasmayo", "Aceros Arequipa", "CPP Pinturas", "Distribuidora Eléctrica",
            "Pavco Perú", "Ferretería Mayorista", "Importadora Sur", "Comercial Ferretera",
            "Sodimac Distribución", "Promart Mayorista",
        ],
        "productos": [
            ("Cemento Sol 42.5kg", "Construcción", 28.0), ("Fierro 1/2\" varilla", "Construcción", 32.0),
            ("Ladrillo King Kong", "Construcción", 0.9), ("Pintura Látex 1gal", "Pinturas", 45.0),
            ("Esmalte Sintético 1/4gal", "Pinturas", 22.0), ("Foco LED 9W", "Eléctrico", 8.0),
            ("Cable THW 14 (m)", "Eléctrico", 2.5), ("Interruptor simple", "Eléctrico", 6.0),
            ("Tubo PVC 1/2\" (m)", "Gasfitería", 6.0), ("Llave de paso 1/2\"", "Gasfitería", 14.0),
            ("Clavos 2\" (kg)", "Ferretería", 7.0), ("Cinta aislante", "Ferretería", 3.0),
            ("Brocha 3\"", "Pinturas", 9.0), ("Silicona transparente", "Ferretería", 12.0),
            ("Candado 40mm", "Seguridad", 18.0), ("Guantes de trabajo", "Seguridad", 10.0),
        ],
    },
}


def _mapas(rubro: dict):
    productos = rubro["productos"]
    mapa_sku = {f"SKU-{i:03d}": p[0] for i, p in enumerate(productos, start=1)}
    mapa_cat = {f"SKU-{i:03d}": p[1] for i, p in enumerate(productos, start=1)}
    mapa_precio = {f"SKU-{i:03d}": p[2] for i, p in enumerate(productos, start=1)}
    mapa_tienda = {f"T{t:02d}": nombre for t, nombre in enumerate(rubro["tiendas"], start=1)}
    mapa_prov = {f"PROV-{p:02d}": nombre for p, nombre in enumerate(rubro["proveedores"], start=1)}
    return mapa_sku, mapa_cat, mapa_precio, mapa_tienda, mapa_prov


def _escalar_precio(df: pd.DataFrame, col: str, objetivo: pd.Series) -> pd.Series:
    """Reescala una columna de precio para que su media por SKU sea el objetivo (en soles)."""
    media = df.groupby("_sku")[col].transform("mean").replace(0, 1.0)
    return (df[col] / media * objetivo).round(2)


def construir(dominio: str, rubro: dict, seed: int) -> pd.DataFrame:
    n_p = len(rubro["productos"])
    mapa_sku, mapa_cat, mapa_precio, mapa_tienda, mapa_prov = _mapas(rubro)

    if dominio == "compras":
        df = generar_dominio(
            "compras", seed=seed, n_proveedores=len(rubro["proveedores"]),
            n_productos=n_p, n_ordenes_por_serie=N_ORDENES, dias_entre_ordenes=DIAS_ENTRE_ORDENES,
        )
    else:
        df = generar_dominio(
            dominio, seed=seed, n_tiendas=N_TIENDAS, n_productos=n_p, n_dias=N_DIAS,
        )
    df = df.copy()
    df["_sku"] = df["sku"]
    df["categoria"] = df["sku"].map(mapa_cat)

    if dominio == "ventas":
        objetivo = df["_sku"].map(mapa_precio)
        df["precio_unitario"] = _escalar_precio(df, "precio_unitario", objetivo)
        df["ingreso"] = (df["unidades_vendidas"] * df["precio_unitario"]).round(2)
        df["id_tienda"] = df["id_tienda"].map(mapa_tienda)
    elif dominio == "compras":
        objetivo = df["_sku"].map(mapa_precio) * 0.6  # el costo de compra ~60 % del precio de venta
        df["precio_unitario_compra"] = _escalar_precio(df, "precio_unitario_compra", objetivo)
        df["costo_total"] = (df["cantidad_pedida"] * df["precio_unitario_compra"]).round(2)
        df["id_proveedor"] = df["id_proveedor"].map(mapa_prov)
    else:  # almacen — sin precio, solo identidad de nombres
        df["id_tienda"] = df["id_tienda"].map(mapa_tienda)

    df["sku"] = df["_sku"].map(mapa_sku)
    df = df.drop(columns="_sku")
    df = df[esquema_de(dominio).orden]  # orden canónico de columnas
    validar_conforme(df, dominio)
    return df


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Genera datos ricos (~10k filas) por rubro (PYME peruana), esquema v3.")
    parser.add_argument("-o", "--out", default="ejemplos/datos_ricos_10k", help="Carpeta de salida.")
    parser.add_argument("--seed", type=int, default=2025, help="Semilla global (default: 2025).")
    args = parser.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass

    out = Path(args.out)
    for slug, rubro in RUBROS.items():
        carpeta = out / slug
        carpeta.mkdir(parents=True, exist_ok=True)
        print(f"\n== {rubro['titulo']}  ->  {carpeta}")
        for dominio in ("ventas", "compras", "almacen"):
            df = construir(dominio, rubro, args.seed)
            filas = onboarding._filas_jsonables(df, dominio)
            (carpeta / f"{dominio}.json").write_text(
                json.dumps(filas, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            (carpeta / f"{dominio}.xlsx").write_bytes(dominios_excel.generar_excel(dominio, filas))
            print(f"   [ok] {dominio}.xlsx / {dominio}.json  ({len(df):>6d} filas)")

    print(f"\nListo. Sube cualquiera en la app (Paso 3) o con POST /v3/{{modulo}}/archivo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
