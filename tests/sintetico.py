"""Builders de datos sintéticos compartidos por los tests.

Viven fuera de ``conftest.py`` (módulo de nombre único ``sintetico``) para poder
importarse desde varios conftests sin colisión de nombres. Producen frames con el
**esquema del dataset analítico integrado**, sin depender de los CSV de `data/raw`.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def construir_analitico_sintetico(
    n_series: int = 4, n_dias: int = 140, seed: int = 7
) -> pd.DataFrame:
    """Frame con el esquema del dataset analitico y estructura **aprendible**.

    Las ventas siguen un AR(1) fuerte mas un efecto de promocion y ruido pequeno.
    Asi un modelo que use el rezago t-1 + promocion supera con holgura al baseline
    naive estacional (t-7), permitiendo testear el criterio "supera al baseline".
    """
    rng = np.random.default_rng(seed)
    fechas = pd.date_range("2016-02-01", periods=n_dias, freq="D")
    tipos = ["A", "B", "C", "D", "E"]
    ciudades = ["Quito", "Guayaquil"]
    estados = ["Pichincha", "Guayas"]
    familias = ["BEVERAGES", "GROCERY"]
    frames = []
    for i in range(n_series):
        promo = rng.integers(0, 6, n_dias)
        sales = np.zeros(n_dias)
        prev = rng.uniform(20, 60)
        for t in range(n_dias):
            valor = 0.85 * prev + 8.0 * promo[t] + rng.normal(0, 3)
            sales[t] = max(0.0, valor)
            prev = sales[t]
        frames.append(
            pd.DataFrame(
                {
                    "date": fechas,
                    "store_nbr": np.int16(i + 1),
                    "family": familias[i % len(familias)],
                    "sales": sales.astype("float32"),
                    "onpromotion": promo.astype("int16"),
                    "transactions_filled": (sales * 2 + rng.normal(0, 5, n_dias)).clip(0).astype("int32"),
                    "dcoilwtico": np.float32(50.0),
                    "type": tipos[i % len(tipos)],
                    "city": ciudades[i % len(ciudades)],
                    "state": estados[i % len(estados)],
                    "cluster": np.int16(i % 3 + 1),
                }
            )
        )
    df = pd.concat(frames, ignore_index=True)
    df = _decorar_calendario(df)
    return df


def _decorar_calendario(df: pd.DataFrame) -> pd.DataFrame:
    """Anade las columnas de calendario/feriados que espera el dataset analitico."""
    df["year"] = df["date"].dt.year.astype("int16")
    df["month"] = df["date"].dt.month.astype("int8")
    df["day"] = df["date"].dt.day.astype("int8")
    df["dayofweek"] = df["date"].dt.dayofweek.astype("int8")
    df["is_weekend"] = df["dayofweek"] >= 5
    df["is_month_end"] = df["date"].dt.is_month_end
    df["is_payday"] = (df["day"] == 15) | df["is_month_end"]
    for c in ("holiday_national", "holiday_regional", "holiday_local", "holiday_event_count"):
        df[c] = np.int16(0)
    df["holiday_any"] = False
    df["family"] = df["family"].astype("category")
    return df


def construir_analitico_clasificacion(
    n_dias: int = 170, n_stores: int = 4, seed: int = 11
) -> pd.DataFrame:
    """Dataset analitico sintetico para los tests de **clasificacion** (2b).

    - Familias **normales** (AR(1) + efecto promocion): la etiqueta
      ``demanda_alta = sales > P75(familia)`` queda **desbalanceada (~25 % pos)** y
      es **aprendible** desde los rezagos/promocion (un booster supera al dummy).
    - Una familia **degenerada** (`BOOKS`): ventas casi siempre 0 (P75 train = 0),
      de modo que la etiqueta se vuelve "vendio algo" -> el motor la **excluye** y el
      test verifica esa deteccion.
    """
    rng = np.random.default_rng(seed)
    fechas = pd.date_range("2016-02-01", periods=n_dias, freq="D")
    normales = ["BEVERAGES", "GROCERY", "MEATS"]
    tipos = ["A", "B", "C", "D"]
    ciudades = ["Quito", "Guayaquil"]
    estados = ["Pichincha", "Guayas"]
    frames = []
    for s in range(n_stores):
        for fam in normales:
            promo = rng.integers(0, 6, n_dias)
            sales = np.zeros(n_dias)
            prev = rng.uniform(20, 60)
            for t in range(n_dias):
                valor = 0.85 * prev + 9.0 * promo[t] + rng.normal(0, 4)
                sales[t] = max(0.0, valor)
                prev = sales[t]
            frames.append(
                pd.DataFrame(
                    {
                        "date": fechas,
                        "store_nbr": np.int16(s + 1),
                        "family": fam,
                        "sales": sales.astype("float32"),
                        "onpromotion": promo.astype("int16"),
                        "transactions_filled": (sales * 2 + rng.normal(0, 5, n_dias)).clip(0).astype("int32"),
                        "dcoilwtico": np.float32(50.0),
                        "type": tipos[s % len(tipos)],
                        "city": ciudades[s % len(ciudades)],
                        "state": estados[s % len(estados)],
                        "cluster": np.int16(s % 3 + 1),
                    }
                )
            )
        # Familia degenerada: ventas casi siempre 0 -> P75 train = 0.
        promo = rng.integers(0, 2, n_dias)
        sales = np.where(rng.random(n_dias) < 0.10, rng.integers(1, 3, n_dias), 0).astype("float32")
        frames.append(
            pd.DataFrame(
                {
                    "date": fechas,
                    "store_nbr": np.int16(s + 1),
                    "family": "BOOKS",
                    "sales": sales,
                    "onpromotion": promo.astype("int16"),
                    "transactions_filled": np.int32(0),
                    "dcoilwtico": np.float32(50.0),
                    "type": tipos[s % len(tipos)],
                    "city": ciudades[s % len(ciudades)],
                    "state": estados[s % len(estados)],
                    "cluster": np.int16(s % 3 + 1),
                }
            )
        )
    df = pd.concat(frames, ignore_index=True)
    return _decorar_calendario(df)


def construir_analitico_clustering(n_dias: int = 60, seed: int = 21) -> pd.DataFrame:
    """Dataset analitico sintetico para los tests de **clustering** (2c).

    Estructura **separable a proposito** para que KMeans recupere segmentos claros:

    - **Tiendas (16):** dos grupos. `store_nbr` 1..8 = alto volumen (venta y
      transacciones altas, mas promo); 9..16 = bajo volumen e intermitente.
    - **Familias (6):** 4 **continuas** (venta alta, pocos ceros) + 2 **intermitentes**
      (`BOOKS`, `BABY CARE`: casi siempre 0).
    """
    rng = np.random.default_rng(seed)
    fechas = pd.date_range("2016-03-01", periods=n_dias, freq="D")
    continuas = {"BEVERAGES": 1.0, "GROCERY": 1.4, "PRODUCE": 0.7, "CLEANING": 0.5}
    intermitentes = ["BOOKS", "BABY CARE"]
    familias = list(continuas) + intermitentes
    frames = []
    for s in range(1, 17):
        alto = s <= 8
        nivel = rng.uniform(400, 700) if alto else rng.uniform(20, 80)
        trans = rng.uniform(2000, 3500) if alto else rng.uniform(150, 600)
        promo_lambda = 4 if alto else 1
        for fam in familias:
            if fam in intermitentes:
                sales = np.where(
                    rng.random(n_dias) < 0.15, rng.integers(1, 4, n_dias), 0
                ).astype("float64")
                promo = rng.integers(0, 2, n_dias)
            else:
                base = nivel * continuas[fam]
                promo = rng.poisson(promo_lambda, n_dias)
                sales = np.maximum(
                    0.0, base + 6.0 * promo + rng.normal(0, base * 0.15, n_dias)
                )
            transacciones = np.clip(trans + rng.normal(0, trans * 0.1, n_dias), 0, None)
            frames.append(
                pd.DataFrame(
                    {
                        "date": fechas,
                        "store_nbr": np.int16(s),
                        "family": fam,
                        "sales": sales.astype("float32"),
                        "onpromotion": np.asarray(promo).astype("int16"),
                        "transactions_filled": transacciones.astype("int32"),
                        "dcoilwtico": np.float32(50.0),
                        "type": "A" if alto else "C",
                        "city": "Quito" if alto else "Guayaquil",
                        "state": "Pichincha" if alto else "Guayas",
                        "cluster": np.int16(1 if alto else 2),
                    }
                )
            )
    df = pd.concat(frames, ignore_index=True)
    df = _decorar_calendario(df)
    # Etiqueta demanda_alta = sales > P75 de su familia (como en la integracion real).
    p75 = df.groupby("family", observed=True)["sales"].transform(lambda x: x.quantile(0.75))
    df["demanda_alta"] = (df["sales"].to_numpy() > p75.to_numpy()).astype("int8")
    return df
