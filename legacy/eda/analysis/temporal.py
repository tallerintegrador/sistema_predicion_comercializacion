"""Analisis temporal y de calendario (tarea F del enunciado).

Incluye estacionalidad anual (year-over-year) y un **indice estacional mensual**
que corrige el sesgo de la version anterior: promediar la venta diaria por mes a lo
largo de todos los anios mezclaba tendencia con estacionalidad (los meses Sep-Dic no
tienen datos de 2017, el anio de mayor nivel, mientras Ene-Ago si). El indice
normaliza cada mes contra la media diaria de SU anio antes de promediar entre anios.
"""

from __future__ import annotations

import pandas as pd

from spc.config import Settings
from spc.data.loaders import write_csv


def seasonal_month_index(daily: pd.DataFrame) -> pd.DataFrame:
    """Indice estacional mensual robusto a la tendencia.

    Para cada anio: indice_mes = media_diaria_mes / media_diaria_anual. Luego se
    promedia el indice entre anios. Un valor > 1 indica un mes por encima del nivel
    tipico de su anio; < 1, por debajo. Asi la estacionalidad no se contamina con el
    crecimiento year-over-year ni con la cobertura parcial de 2017.
    """
    year_mean = daily.groupby("year", observed=True)["sales_total"].mean().rename("media_anual")
    year_month = (
        daily.groupby(["year", "month"], observed=True)["sales_total"]
        .mean()
        .reset_index(name="venta_media_diaria")
        .merge(year_mean, on="year")
    )
    year_month["indice"] = year_month["venta_media_diaria"] / year_month["media_anual"]
    index = (
        year_month.groupby("month", observed=True)["indice"]
        .agg(indice_estacional="mean", anios_observados="size")
        .reset_index()
    )
    return index


def temporal_analysis(
    train: pd.DataFrame, holidays: pd.DataFrame, settings: Settings
) -> dict[str, pd.DataFrame]:
    """Serie diaria, estacionalidad (anual/mensual/dia), efectos de calendario y promos."""
    daily = train.groupby("date", observed=True)["sales"].sum().reset_index(name="sales_total")
    daily["year"] = daily["date"].dt.year
    daily["month"] = daily["date"].dt.month
    daily["dayofweek"] = daily["date"].dt.dayofweek
    daily["is_month_end"] = daily["date"].dt.is_month_end
    daily["is_payday"] = daily["date"].dt.day.eq(15) | daily["is_month_end"]
    write_csv(daily, settings.processed_dir / "ventas_diarias.csv")

    monthly = (
        daily.assign(periodo=daily["date"].dt.to_period("M").astype(str))
        .groupby("periodo", observed=True)["sales_total"]
        .sum()
        .reset_index()
    )
    # Indice estacional mensual (corrige el sesgo de tendencia).
    month_index = seasonal_month_index(daily)
    write_csv(month_index, settings.processed_dir / "indice_estacional_mes.csv")

    dow = (
        daily.groupby("dayofweek", observed=True)["sales_total"]
        .mean()
        .reset_index(name="venta_media_diaria")
    )
    payday = (
        daily.groupby("is_payday", observed=True)["sales_total"]
        .agg(dias="size", venta_media_diaria="mean", venta_mediana_diaria="median")
        .reset_index()
    )

    # --- Estacionalidad anual (year-over-year) ---
    yearly = (
        daily.groupby("year", observed=True)["sales_total"]
        .agg(dias_observados="size", ventas_total="sum", venta_media_diaria="mean")
        .reset_index()
    )
    yearly["anio_completo"] = yearly["dias_observados"] >= 360
    yearly["yoy_media_diaria_pct"] = yearly["venta_media_diaria"].pct_change() * 100
    write_csv(yearly, settings.processed_dir / "ventas_anuales.csv")

    # Perfil mensual por anio: matriz year x month con venta media diaria.
    year_month = (
        daily.groupby(["year", "month"], observed=True)["sales_total"]
        .mean()
        .reset_index(name="venta_media_diaria")
    )
    write_csv(year_month, settings.processed_dir / "estacionalidad_anual_mes.csv")

    # --- Efecto de feriado/evento activo (cualquier alcance, a nivel diario nacional) ---
    active_holidays = holidays.loc[~holidays["transferred"]].copy()
    event_days = active_holidays[["date"]].drop_duplicates().assign(tiene_evento_activo=True)
    holiday_effect = daily.merge(event_days, on="date", how="left")
    holiday_effect["tiene_evento_activo"] = holiday_effect["tiene_evento_activo"].fillna(False)
    holiday_summary = (
        holiday_effect.groupby("tiene_evento_activo", observed=True)["sales_total"]
        .agg(dias="size", venta_media_diaria="mean", venta_mediana_diaria="median")
        .reset_index()
    )

    # --- Efecto por TIPO de feriado/evento nacional ---
    nat = active_holidays.loc[active_holidays["locale"].astype(str).eq("National")]
    nat_type = nat[["date", "type"]].astype({"type": str}).drop_duplicates()
    by_type = daily.merge(nat_type, on="date", how="inner")
    type_effect = (
        by_type.groupby("type", observed=True)["sales_total"]
        .agg(dias="size", venta_media_diaria="mean", venta_mediana_diaria="median")
        .reset_index()
    )
    baseline_dates = set(daily["date"]) - set(nat_type["date"])
    baseline = daily.loc[daily["date"].isin(baseline_dates), "sales_total"]
    type_effect = pd.concat(
        [
            pd.DataFrame(
                [
                    {
                        "type": "Sin feriado nacional",
                        "dias": int(baseline.shape[0]),
                        "venta_media_diaria": float(baseline.mean()),
                        "venta_mediana_diaria": float(baseline.median()),
                    }
                ]
            ),
            type_effect,
        ],
        ignore_index=True,
    ).sort_values("venta_media_diaria", ascending=False)
    write_csv(type_effect, settings.processed_dir / "efecto_tipo_feriado.csv")

    # --- Penetracion de promociones en el tiempo (mensual) ---
    promo_month = (
        train.assign(
            periodo=train["date"].dt.to_period("M").astype(str), en_promo=train["onpromotion"] > 0
        )
        .groupby("periodo", observed=True)
        .agg(
            filas=("en_promo", "size"),
            pct_en_promo=("en_promo", "mean"),
            promo_media=("onpromotion", "mean"),
        )
        .reset_index()
    )
    promo_month["pct_en_promo"] = promo_month["pct_en_promo"] * 100
    write_csv(promo_month, settings.processed_dir / "penetracion_promo_mensual.csv")

    top_days = daily.nlargest(10, "sales_total")[["date", "sales_total"]].copy()
    top_days["date"] = top_days["date"].dt.strftime("%Y-%m-%d")

    write_csv(monthly, settings.processed_dir / "ventas_mensuales.csv")
    write_csv(dow, settings.processed_dir / "estacionalidad_dia_semana.csv")
    write_csv(payday, settings.processed_dir / "efecto_quincena.csv")
    write_csv(holiday_summary, settings.processed_dir / "efecto_eventos.csv")
    write_csv(top_days, settings.processed_dir / "dias_pico_ventas.csv")
    return {
        "daily": daily,
        "monthly": monthly,
        "month_index": month_index,
        "dow": dow,
        "payday": payday,
        "yearly": yearly,
        "year_month": year_month,
        "holiday_summary": holiday_summary,
        "type_effect": type_effect,
        "promo_month": promo_month,
        "top_days": top_days,
    }
