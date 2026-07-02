"""Datos de ejemplo **ricos** por rubro (PYME peruana) para el contrato 3×3.

Genera, para **5 rubros** peruanos, los tres archivos (ventas, compras, almacén) en Excel
y JSON, **conformes al diccionario de variables** de cada dominio, listos para subir a
``/v2`` y demostrar el sistema con datos que se sienten reales.

Cómo: reutiliza el motor sintético realista (estacionalidad, promociones, fines de semana,
feriados peruanos, Yape/Plin) y le pone **identidad de rubro** — nombres reales de
productos, locales y proveedores, y **precios en soles** apropiados—, **sin cambiar las
columnas** (el formato exige las mismas). Reproducible con semilla 42.

Uso::

    python scripts/generar_ejemplos_peru.py                 # -> datos_ejemplo_peru/
    python scripts/generar_ejemplos_peru.py -o docs/demo_peru
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

SEED = 42
N_DIAS = 120
N_ORDENES = 24

# Cada rubro: (nombre, categoría, precio de venta en soles) por producto + locales y
# proveedores con nombres reconocibles del contexto peruano.
RUBROS: dict[str, dict] = {
    "bodega": {
        "titulo": "Bodega / Minimarket",
        "tiendas": ["Bodega San Martín (SJL)", "Minimarket La Esquina (Comas)"],
        "proveedores": [
            "Distribuidora Alicorp", "Gloria S.A.", "Backus Depósito", "Molitalia",
            "Comercial Andina", "Distribuidora Norte", "Mayorista Central", "Proveedor La Victoria",
        ],
        "productos": [
            ("Arroz Costeño 5kg", "Abarrotes", 22.0), ("Aceite Primor 1L", "Abarrotes", 9.5),
            ("Azúcar Rubia 1kg", "Abarrotes", 4.5), ("Fideos Don Vittorio 500g", "Abarrotes", 3.8),
            ("Leche Gloria tarro", "Lácteos", 4.2), ("Atún Florida lata", "Abarrotes", 5.5),
            ("Inca Kola 1.5L", "Bebidas", 7.0), ("Agua San Luis 2.5L", "Bebidas", 5.0),
            ("Detergente Bolívar 1kg", "Limpieza", 12.0), ("Papel higiénico Suave x4", "Limpieza", 6.5),
            ("Galletas Soda Field", "Snacks", 2.5), ("Shampoo Head&Shoulders", "Cuidado personal", 18.0),
        ],
    },
    "botica": {
        "titulo": "Botica / Farmacia",
        "tiendas": ["Botica Salud Total (Miraflores)", "Farmacia Vida (SJL)"],
        "proveedores": [
            "Química Suiza", "Droguería Inkafarma", "Perufarma", "BSN Medical",
            "Farmindustria", "Medifarma", "Distribuidora Sur", "Genéricos Perú",
        ],
        "productos": [
            ("Paracetamol 500mg x10", "Medicamentos", 3.5), ("Ibuprofeno 400mg x10", "Medicamentos", 5.0),
            ("Alcohol 96° 250ml", "Cuidado", 4.0), ("Mascarilla KN95", "Cuidado", 1.5),
            ("Vitamina C x30", "Suplementos", 15.0), ("Pañal Babysec M x30", "Bebé", 32.0),
            ("Gel antibacterial 250ml", "Cuidado", 6.0), ("Ambroxol jarabe", "Medicamentos", 12.0),
            ("Curitas x20", "Cuidado", 4.5), ("Suero fisiológico", "Medicamentos", 3.0),
            ("Protector solar 50 SPF", "Cuidado", 35.0), ("Termómetro digital", "Equipos", 22.0),
        ],
    },
    "ferreteria": {
        "titulo": "Ferretería",
        "tiendas": ["Ferretería El Constructor (Ate)", "Ferretería Los Andes (VMT)"],
        "proveedores": [
            "Cementos Pacasmayo", "Aceros Arequipa", "CPP Pinturas", "Distribuidora Eléctrica",
            "Pavco Perú", "Ferretería Mayorista", "Importadora Sur", "Comercial Ferretera",
        ],
        "productos": [
            ("Cemento Sol 42.5kg", "Construcción", 28.0), ("Fierro 1/2\" varilla", "Construcción", 32.0),
            ("Pintura Látex 1gal", "Pinturas", 45.0), ("Foco LED 9W", "Eléctrico", 8.0),
            ("Cable THW 14 (m)", "Eléctrico", 2.5), ("Tubo PVC 1/2\" (m)", "Gasfitería", 6.0),
            ("Clavos 2\" (kg)", "Ferretería", 7.0), ("Cinta aislante", "Eléctrico", 3.0),
            ("Brocha 3\"", "Pinturas", 9.0), ("Silicona transparente", "Ferretería", 12.0),
            ("Candado 40mm", "Seguridad", 18.0), ("Guantes de trabajo", "Seguridad", 10.0),
        ],
    },
    "panaderia": {
        "titulo": "Panadería / Pastelería",
        "tiendas": ["Panadería La Espiga (Surco)", "Pastelería Dulce Hogar (SJL)"],
        "proveedores": [
            "Molino Santa Rosa", "Gloria (lácteos)", "Avícola San Fernando", "Azucarera Andina",
            "Levaduras Fleischmann", "Insumos Pasteleros", "Distribuidora Norte", "Proveedor Central",
        ],
        "productos": [
            ("Pan francés (unidad)", "Panadería", 0.3), ("Pan de molde", "Panadería", 6.5),
            ("Keke de vainilla", "Pastelería", 12.0), ("Empanada de pollo", "Pastelería", 3.5),
            ("Torta chocolate (porción)", "Pastelería", 8.0), ("Alfajor", "Pastelería", 2.0),
            ("Croissant", "Panadería", 2.5), ("Pan integral", "Panadería", 5.0),
            ("Galleta de avena", "Pastelería", 1.5), ("Bizcocho", "Pastelería", 4.0),
            ("Chancay", "Panadería", 0.5), ("Pastel de manzana", "Pastelería", 9.0),
        ],
    },
    "veterinaria": {
        "titulo": "Veterinaria / Pet shop",
        "tiendas": ["Pet Shop Huellitas (Miraflores)", "Veterinaria Amigos (SJL)"],
        "proveedores": [
            "Rinti S.A.", "Mars Petcare", "Distribuidora Veterinaria", "Bayer Animal Health",
            "Importadora Pet", "Distribuidora Sur", "Agroveterinaria", "Proveedor Central",
        ],
        "productos": [
            ("Alimento perro Ricocan 8kg", "Alimento", 65.0), ("Alimento gato Whiskas 3kg", "Alimento", 42.0),
            ("Correa perro", "Accesorios", 25.0), ("Shampoo mascota", "Higiene", 18.0),
            ("Antipulgas pipeta", "Salud", 22.0), ("Arena para gato 5kg", "Higiene", 15.0),
            ("Juguete mordedor", "Accesorios", 12.0), ("Snack perro", "Alimento", 8.0),
            ("Plato doble", "Accesorios", 20.0), ("Vitaminas mascota", "Salud", 28.0),
            ("Collar antipulgas", "Salud", 30.0), ("Cama para mascota", "Accesorios", 55.0),
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


def construir(dominio: str, rubro: dict) -> pd.DataFrame:
    n_p = len(rubro["productos"])
    mapa_sku, mapa_cat, mapa_precio, mapa_tienda, mapa_prov = _mapas(rubro)

    if dominio == "compras":
        df = generar_dominio("compras", seed=SEED, n_proveedores=len(rubro["proveedores"]),
                             n_productos=n_p, n_ordenes_por_serie=N_ORDENES)
    else:
        df = generar_dominio(dominio, seed=SEED, n_tiendas=len(rubro["tiendas"]),
                             n_productos=n_p, n_dias=N_DIAS)
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
    else:  # almacen — sin precio, solo identidad
        df["id_tienda"] = df["id_tienda"].map(mapa_tienda)

    df["sku"] = df["_sku"].map(mapa_sku)
    df = df.drop(columns="_sku")
    df = df[esquema_de(dominio).orden]  # orden canónico
    validar_conforme(df, dominio)
    return df


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Genera datos de ejemplo por rubro (PYME peruana).")
    parser.add_argument("-o", "--out", default="datos_ejemplo_peru", help="Carpeta de salida.")
    args = parser.parse_args(argv)
    out = Path(args.out)

    for slug, rubro in RUBROS.items():
        carpeta = out / slug
        carpeta.mkdir(parents=True, exist_ok=True)
        print(f"\n== {rubro['titulo']}  ->  {carpeta}")
        for dominio in ("ventas", "compras", "almacen"):
            df = construir(dominio, rubro)
            filas = onboarding._filas_jsonables(df, dominio)
            (carpeta / f"{dominio}.json").write_text(
                json.dumps({"rows": filas, "horizon": 14}, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            (carpeta / f"{dominio}.xlsx").write_bytes(dominios_excel.generar_excel(dominio, filas))
            print(f"   [ok] {dominio}.xlsx / {dominio}.json  ({len(df):>5d} filas)")

    print(f"\nListo. Sube cualquiera en la interfaz (paso 3) o con POST /v2/{{dominio}}/excel.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
