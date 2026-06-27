"""Generador de ejemplos **multi-dominio** para el motor agnóstico ``/auto/*`` (ADR-0023).

Demuestra que el motor NO sabe de rubros: cada dominio declara su propio esquema
(target, fecha, claves de serie y ~6-9 features con su ``known_future``) y trae el
mismo contrato de petición ``/auto/forecast`` (``schema`` + ``horizon`` +
``granularity`` + ``rows`` + ``future``).

Cada objetivo se construye con **correlaciones reales** contra sus features (no ruido)
y respeta la fuga: las *conocidas a futuro* (precio, promo, calendario, clima
pronosticado, temperatura, etc.) entran tal cual y van en el bloque ``future``; las
*solo-pasado* (tráfico, cancelaciones, devoluciones…) solo existen en el histórico.

A diferencia del retail de ``generar_auto_retail.py`` (8 MB, 40 series), aquí cada
dominio es **pequeño** (~KB, 3-6 series, 90 días, horizonte 14): rápido de leer y de
pegar en Swagger. Reproducible (semilla 42).

Uso:
    venv\\Scripts\\python examples\\api\\generar_auto_dominios.py
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import numpy as np

rng = np.random.default_rng(42)

OUT = Path(__file__).resolve().parent.parent / "auto_dominios"

INICIO = date(2024, 1, 1)
DIAS = 90            # ~3 meses: histórico estable con estacionalidad semanal
HORIZON = 14        # días futuros con drivers planificados (bloque `future`)
SIGMA = 0.10        # ruido irreducible (lognormal) que fija el piso de WAPE

DOW = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]

# Feriados Perú dentro del rango ene-mar 2024 (conocidos a futuro).
FERIADOS = {
    date(2024, 1, 1): "ano_nuevo",
    date(2024, 3, 28): "jueves_santo",
    date(2024, 3, 29): "viernes_santo",
}


def fechas(n: int, desde: date = INICIO) -> list[date]:
    return [desde + timedelta(days=i) for i in range(n)]


def es_feriado(f: date) -> int:
    return 1 if f in FERIADOS else 0


def festividad(f: date) -> str:
    return FERIADOS.get(f, "ninguna")


def dia_habil(f: date) -> int:
    return 1 if f.weekday() < 5 and not es_feriado(f) else 0


def finde(f: date) -> int:
    return 1 if f.weekday() >= 5 else 0


def temp_verano(f: date, base: float, amp: float) -> float:
    """Verano sur ≈ enero: pico al inicio del rango. Conocida a futuro."""
    doy = f.timetuple().tm_yday
    val = base + amp * np.cos(2 * np.pi * (doy - 15) / 365.0) + rng.normal(0, 1.0)
    return round(float(val), 1)


def _f(name: str, type_: str, known_future: bool) -> dict:
    return {"name": name, "type": type_, "known_future": known_future}


def _envolver(schema: dict, rows: list[dict], future: list[dict]) -> dict:
    return {"schema": schema, "horizon": HORIZON, "granularity": "day",
            "rows": rows, "future": future}


def _ruido() -> float:
    return float(rng.lognormal(0, SIGMA))


def _items(obj: dict, ops: dict, *, cobertura: bool) -> list[dict]:
    """Estado/política de 'inventario' por serie, derivado del histórico.

    Agnóstico al rubro: agrupa ``rows`` por las claves de serie, toma la **media del
    objetivo** como nivel de demanda y fija un ``current_stock`` equivalente a unos
    días de cobertura. Para ``purchases`` añade ``target_coverage_days``.
    """
    s = obj["schema"]
    keys = s["series_keys"]
    tgt = s["target"]
    acc: dict[tuple, list[float]] = {}
    for r in obj["rows"]:
        acc.setdefault(tuple(r[k] for k in keys), []).append(r[tgt])
    out = []
    for clave, vals in acc.items():
        media = sum(vals) / len(vals)
        it = {keys[i]: clave[i] for i in range(len(keys))}
        it["current_stock"] = int(round(media * ops["stock_dias"] * rng.uniform(0.8, 1.2)))
        it["lead_time_days"] = ops["lead"]
        if cobertura:
            it["target_coverage_days"] = ops["cover"]
        out.append(it)
    return out


# ===========================================================================
# 1) CLÍNICA — pacientes atendidos por sede × especialidad
# ===========================================================================
def clinica() -> dict:
    sedes = {"trujillo_centro": 1.30, "trujillo_oeste": 0.90}
    espec = {
        "medicina_general": {"base": 95, "gripe": 0.45, "finde": 0.55},
        "pediatria":        {"base": 60, "gripe": 0.60, "finde": 0.50},
        "cardiologia":      {"base": 28, "gripe": 0.05, "finde": 0.20},
    }
    schema = {
        "target": "pacientes_atendidos", "date": "fecha",
        "series_keys": ["sede", "especialidad"],
        "features": [
            _f("dia_semana", "categorical", True), _f("es_feriado", "numeric", True),
            _f("temporada_gripe", "numeric", True), _f("campaña_salud", "numeric", True),
            _f("temperatura", "numeric", True),
            _f("ausentismo_prev", "numeric", False), _f("derivaciones_prev", "numeric", False),
        ],
    }
    fs = fechas(DIAS)
    ff = fechas(HORIZON, INICIO + timedelta(days=DIAS))
    # Índice de temporada de gripe: alto en invierno sur (jun-ago); ene-mar bajo-medio.
    gripe = {f: round(0.5 + 0.5 * np.cos(2 * np.pi * (f.timetuple().tm_yday - 196) / 365.0), 2)
             for f in fs + ff}
    camp = {f: int(rng.random() < 0.08) for f in fs}
    camp_fut = {f: int(rng.random() < 0.10) for f in ff}
    rows, future = [], []
    for sede, smult in sedes.items():
        for esp, info in espec.items():
            prev_dem = info["base"] * smult
            for f in fs:
                dow = f.weekday()
                dow_f = info["finde"] if dow >= 5 else (0.9 if dow == 0 else 1.0)
                temp = temp_verano(f, 22.0, 4.0)
                gf = 1.0 + info["gripe"] * gripe[f]
                fer = 0.25 if es_feriado(f) else 1.0
                cf = 1.12 if camp[f] else 1.0
                dem = info["base"] * smult * dow_f * gf * fer * cf * _ruido()
                dem = float(max(0, round(dem)))
                rows.append({
                    "fecha": f.isoformat(), "sede": sede, "especialidad": esp,
                    "pacientes_atendidos": dem,
                    "dia_semana": DOW[dow], "es_feriado": es_feriado(f),
                    "temporada_gripe": gripe[f], "campaña_salud": camp[f],
                    "temperatura": temp,
                    "ausentismo_prev": round(prev_dem * rng.uniform(0.05, 0.12)),
                    "derivaciones_prev": round(prev_dem * rng.uniform(0.02, 0.06)),
                })
                prev_dem = dem
            for f in ff:
                future.append({
                    "fecha": f.isoformat(), "sede": sede, "especialidad": esp,
                    "dia_semana": DOW[f.weekday()], "es_feriado": es_feriado(f),
                    "temporada_gripe": gripe[f], "campaña_salud": camp_fut[f],
                    "temperatura": temp_verano(f, 22.0, 4.0),
                })
    return _envolver(schema, rows, future)


# ===========================================================================
# 2) RESTAURANTE — platos vendidos por local × plato
# ===========================================================================
def restaurante() -> dict:
    locales = {"centro": 1.20, "mall": 1.00}
    platos = {
        "ceviche":      {"precio": 32.0, "elas": 1.6, "base": 70, "soleado": 1.25, "finde": 1.40},
        "lomo_saltado": {"precio": 28.0, "elas": 1.1, "base": 90, "soleado": 1.02, "finde": 1.30},
        "menu_dia":     {"precio": 16.0, "elas": 0.7, "base": 140, "soleado": 1.00, "finde": 0.80},
    }
    schema = {
        "target": "platos_vendidos", "date": "fecha",
        "series_keys": ["local", "plato"],
        "features": [
            _f("precio", "numeric", True), _f("en_promo", "numeric", True),
            _f("descuento_pct", "numeric", True), _f("finde", "numeric", True),
            _f("es_feriado", "numeric", True), _f("clima", "categorical", True),
            _f("evento_cercano", "categorical", True), _f("temperatura", "numeric", True),
            _f("reservas_prev", "numeric", False), _f("delivery_prev", "numeric", False),
        ],
    }
    climas = ["soleado", "nublado", "lluvia"]
    eventos = ["ninguno", "feria_gastronomica", "partido", "concierto"]
    fs = fechas(DIAS)
    ff = fechas(HORIZON, INICIO + timedelta(days=DIAS))
    clima_d = {f: rng.choice(climas, p=[0.5, 0.3, 0.2]) for f in fs}
    evento_d = {f: rng.choice(eventos, p=[0.85, 0.07, 0.05, 0.03]) for f in fs}
    clima_f = {f: rng.choice(climas, p=[0.5, 0.3, 0.2]) for f in ff}
    rows, future = [], []
    for local, lmult in locales.items():
        for plato, info in platos.items():
            # Promo en rachas (~12% de días).
            promo = np.zeros(DIAS, dtype=int)
            desc = np.zeros(DIAS)
            i = 0
            while i < DIAS:
                if rng.random() < 0.04:
                    dur = int(rng.integers(2, 5))
                    d = int(rng.choice([10, 15, 20]))
                    for j in range(i, min(i + dur, DIAS)):
                        promo[j], desc[j] = 1, d
                    i += dur
                else:
                    i += 1
            prev = info["base"] * lmult
            for k, f in enumerate(fs):
                precio = round(info["precio"] * (1 - desc[k] / 100.0), 2)
                precio_f = (precio / info["precio"]) ** (-info["elas"])
                cl = clima_d[f]
                cf = {"soleado": info["soleado"], "nublado": 1.0, "lluvia": 0.88}[cl]
                ev = {"ninguno": 1.0, "feria_gastronomica": 1.5, "partido": 1.25,
                      "concierto": 1.2}[evento_d[f]]
                ff_ = info["finde"] if finde(f) else 1.0
                fer = 1.20 if es_feriado(f) else 1.0
                temp = temp_verano(f, 24.0, 3.0)
                dem = info["base"] * lmult * precio_f * cf * ev * ff_ * fer * _ruido()
                dem = float(max(0, round(dem)))
                rows.append({
                    "fecha": f.isoformat(), "local": local, "plato": plato,
                    "platos_vendidos": dem,
                    "precio": precio, "en_promo": int(promo[k]), "descuento_pct": float(desc[k]),
                    "finde": finde(f), "es_feriado": es_feriado(f), "clima": str(cl),
                    "evento_cercano": str(evento_d[f]), "temperatura": temp,
                    "reservas_prev": round(prev * rng.uniform(0.10, 0.25)),
                    "delivery_prev": round(prev * rng.uniform(0.15, 0.35)),
                })
                prev = dem
            for f in ff:
                promo_f = 1 if 3 <= (f - ff[0]).days <= 6 else 0
                d = 15.0 if promo_f else 0.0
                future.append({
                    "fecha": f.isoformat(), "local": local, "plato": plato,
                    "precio": round(info["precio"] * (1 - d / 100.0), 2),
                    "en_promo": promo_f, "descuento_pct": d,
                    "finde": finde(f), "es_feriado": es_feriado(f),
                    "clima": str(clima_f[f]), "evento_cercano": "ninguno",
                    "temperatura": temp_verano(f, 24.0, 3.0),
                })
    return _envolver(schema, rows, future)


# ===========================================================================
# 3) ENERGÍA — demanda kWh por subestación
# ===========================================================================
def energia() -> dict:
    subes = {"norte": 1.10, "sur": 0.95, "centro": 1.35}
    schema = {
        "target": "demanda_kwh", "date": "fecha",
        "series_keys": ["subestacion"],
        "features": [
            _f("temperatura", "numeric", True), _f("dia_habil", "numeric", True),
            _f("es_feriado", "numeric", True), _f("festividad_local", "categorical", True),
            _f("dia_semana", "categorical", True),
            _f("perdidas_tecnicas_prev", "numeric", False),
        ],
    }
    fs = fechas(DIAS)
    ff = fechas(HORIZON, INICIO + timedelta(days=DIAS))
    base = 42000.0
    rows, future = [], []
    for sub, mult in subes.items():
        prev = base * mult
        for f in fs:
            temp = temp_verano(f, 23.0, 6.0)
            # U: aire acondicionado con calor, calefacción con frío (mínimo ~20°C).
            clima_f = 1.0 + 0.010 * (temp - 20.0) ** 2 / 10.0
            hab = 1.10 if dia_habil(f) else 0.85
            fer = 0.80 if es_feriado(f) else 1.0
            dem = base * mult * clima_f * hab * fer * _ruido()
            dem = float(round(dem))
            rows.append({
                "fecha": f.isoformat(), "subestacion": sub, "demanda_kwh": dem,
                "temperatura": temp, "dia_habil": dia_habil(f), "es_feriado": es_feriado(f),
                "festividad_local": festividad(f), "dia_semana": DOW[f.weekday()],
                "perdidas_tecnicas_prev": round(prev * rng.uniform(0.04, 0.08)),
            })
            prev = dem
        for f in ff:
            future.append({
                "fecha": f.isoformat(), "subestacion": sub,
                "temperatura": temp_verano(f, 23.0, 6.0), "dia_habil": dia_habil(f),
                "es_feriado": es_feriado(f), "festividad_local": festividad(f),
                "dia_semana": DOW[f.weekday()],
            })
    return _envolver(schema, rows, future)


# ===========================================================================
# 4) ECOMMERCE — pedidos por categoría × canal
# ===========================================================================
def ecommerce() -> dict:
    cats = {
        "moda":  {"base": 220, "elas": 1.4, "campaña": 0.40},
        "hogar": {"base": 160, "elas": 0.9, "campaña": 0.25},
        "tech":  {"base": 130, "elas": 1.7, "campaña": 0.55},
    }
    canales = {"web": 1.0, "app": 0.85}
    schema = {
        "target": "pedidos", "date": "fecha",
        "series_keys": ["categoria", "canal"],
        "features": [
            _f("indice_precio", "numeric", True), _f("descuento_pct", "numeric", True),
            _f("campaña", "numeric", True), _f("envio_gratis", "numeric", True),
            _f("es_feriado", "numeric", True), _f("dia_pago", "numeric", True),
            _f("evento_comercial", "categorical", True),
            _f("trafico_web_prev", "numeric", False), _f("devoluciones_prev", "numeric", False),
        ],
    }
    eventos = ["ninguno", "cyber_wow", "black_friday"]
    fs = fechas(DIAS)
    ff = fechas(HORIZON, INICIO + timedelta(days=DIAS))
    # Evento comercial: una ventana de cyber a mediados del histórico.
    ev_d = {f: "ninguno" for f in fs}
    for f in fs:
        if date(2024, 2, 12) <= f <= date(2024, 2, 15):
            ev_d[f] = "cyber_wow"
    rows, future = [], []
    for cat, info in cats.items():
        for canal, cmult in canales.items():
            # Descuento/envío gratis en rachas.
            desc = np.zeros(DIAS)
            envio = np.zeros(DIAS, dtype=int)
            camp = np.zeros(DIAS, dtype=int)
            i = 0
            while i < DIAS:
                if rng.random() < 0.05:
                    dur = int(rng.integers(2, 6))
                    d = int(rng.choice([10, 20, 30]))
                    for j in range(i, min(i + dur, DIAS)):
                        desc[j], envio[j], camp[j] = d, int(rng.random() < 0.6), 1
                    i += dur
                else:
                    i += 1
            prev = info["base"] * cmult
            for k, f in enumerate(fs):
                idx = round(1 - desc[k] / 100.0, 3)
                precio_f = idx ** (-info["elas"])
                ev_f = {"ninguno": 1.0, "cyber_wow": 1.9, "black_friday": 2.3}[ev_d[f]]
                camp_f = 1.0 + info["campaña"] * camp[k]
                envio_f = 1.10 if envio[k] else 1.0
                pago_f = 1.12 if (f.day == 15 or (f + timedelta(days=1)).day == 1) else 1.0
                fer = 1.05 if es_feriado(f) else 1.0
                dem = info["base"] * cmult * precio_f * ev_f * camp_f * envio_f * pago_f * fer * _ruido()
                dem = float(max(0, round(dem)))
                rows.append({
                    "fecha": f.isoformat(), "categoria": cat, "canal": canal, "pedidos": dem,
                    "indice_precio": idx, "descuento_pct": float(desc[k]),
                    "campaña": int(camp[k]), "envio_gratis": int(envio[k]),
                    "es_feriado": es_feriado(f),
                    "dia_pago": 1 if (f.day == 15 or (f + timedelta(days=1)).day == 1) else 0,
                    "evento_comercial": ev_d[f],
                    "trafico_web_prev": round(prev * rng.uniform(8, 14)),
                    "devoluciones_prev": round(prev * rng.uniform(0.04, 0.10)),
                })
                prev = dem
            for f in ff:
                promo_f = 1 if 4 <= (f - ff[0]).days <= 8 else 0
                d = 20.0 if promo_f else 0.0
                future.append({
                    "fecha": f.isoformat(), "categoria": cat, "canal": canal,
                    "indice_precio": round(1 - d / 100.0, 3), "descuento_pct": d,
                    "campaña": promo_f, "envio_gratis": promo_f,
                    "es_feriado": es_feriado(f),
                    "dia_pago": 1 if (f.day == 15 or (f + timedelta(days=1)).day == 1) else 0,
                    "evento_comercial": "ninguno",
                })
    return _envolver(schema, rows, future)


# ===========================================================================
# 5) MOVILIDAD — viajes por ruta
# ===========================================================================
def movilidad() -> dict:
    rutas = {"centro_norte": 1.10, "centro_sur": 1.00, "aeropuerto": 0.70}
    schema = {
        "target": "viajes", "date": "fecha",
        "series_keys": ["ruta"],
        "features": [
            _f("clima", "categorical", True), _f("es_feriado", "numeric", True),
            _f("finde", "numeric", True), _f("evento_cercano", "categorical", True),
            _f("precio_combustible", "numeric", True), _f("tarifa_base", "numeric", True),
            _f("cancelaciones_prev", "numeric", False), _f("tiempo_espera_prev", "numeric", False),
        ],
    }
    climas = ["soleado", "nublado", "lluvia"]
    eventos = ["ninguno", "concierto", "partido", "feria"]
    fs = fechas(DIAS)
    ff = fechas(HORIZON, INICIO + timedelta(days=DIAS))
    clima_d = {f: rng.choice(climas, p=[0.5, 0.3, 0.2]) for f in fs}
    clima_f = {f: rng.choice(climas, p=[0.5, 0.3, 0.2]) for f in ff}
    evento_d = {f: rng.choice(eventos, p=[0.85, 0.06, 0.05, 0.04]) for f in fs}
    # Combustible: tendencia lenta + ruido (conocido a futuro).
    fuel = {f: round(16.5 + 0.02 * i + rng.normal(0, 0.15), 3) for i, f in enumerate(fs + ff)}
    base = 1400.0
    rows, future = [], []
    for ruta, mult in rutas.items():
        finde_f = 1.30 if ruta != "aeropuerto" else 0.85  # ocio vs negocio
        prev = base * mult
        for f in fs:
            cl = clima_d[f]
            cf = {"soleado": 0.97, "nublado": 1.0, "lluvia": 1.20}[cl]  # lluvia empuja taxi
            ev = {"ninguno": 1.0, "concierto": 1.4, "partido": 1.3, "feria": 1.2}[evento_d[f]]
            ff_ = finde_f if finde(f) else 1.0
            fer = 0.90 if es_feriado(f) else 1.0
            tarifa = round(7.5 * (fuel[f] / 16.5), 2)
            fuel_f = (fuel[f] / 16.5) ** (-0.10)
            dem = base * mult * cf * ev * ff_ * fer * fuel_f * _ruido()
            dem = float(max(0, round(dem)))
            rows.append({
                "fecha": f.isoformat(), "ruta": ruta, "viajes": dem,
                "clima": str(cl), "es_feriado": es_feriado(f), "finde": finde(f),
                "evento_cercano": str(evento_d[f]), "precio_combustible": fuel[f],
                "tarifa_base": tarifa,
                "cancelaciones_prev": round(prev * rng.uniform(0.03, 0.08)),
                "tiempo_espera_prev": round(rng.uniform(3, 12), 1),
            })
            prev = dem
        for f in ff:
            tarifa = round(7.5 * (fuel[f] / 16.5), 2)
            future.append({
                "fecha": f.isoformat(), "ruta": ruta,
                "clima": str(clima_f[f]), "es_feriado": es_feriado(f), "finde": finde(f),
                "evento_cercano": "ninguno", "precio_combustible": fuel[f],
                "tarifa_base": tarifa,
            })
    return _envolver(schema, rows, future)


# ===========================================================================
# README por dominio
# ===========================================================================
def readme(nombre: str, sales: dict, ops: dict, desc: str) -> str:
    s = sales["schema"]
    feats = ", ".join(f"`{x['name']}`{'·fut' if x['known_future'] else '·pas'}"
                      for x in s["features"])
    n_series = len({tuple(r[k] for k in s["series_keys"]) for r in sales["rows"]})
    return (
        f"# {nombre} — ejemplo agnóstico `/auto/*`\n\n"
        f"{desc}\n\n"
        f"- **Objetivo (`target`)**: `{s['target']}`\n"
        f"- **Fecha (`date`)**: `{s['date']}`\n"
        f"- **Claves de serie**: {', '.join(f'`{k}`' for k in s['series_keys'])} "
        f"→ {n_series} series\n"
        f"- **Horizonte**: {sales['horizon']} días · **Granularidad**: {sales['granularity']}\n"
        f"- **Histórico**: {len(sales['rows'])} filas · **Futuro**: {len(sales['future'])} filas\n"
        f"- **Features** (·fut = conocida a futuro, ·pas = solo pasado): {feats}\n\n"
        f"Los tres comparten `schema` + `rows`; cambia solo el endpoint y su bloque extra.\n\n"
        f"| Endpoint | Archivo | Extra |\n"
        f"|---|---|---|\n"
        f"| `POST /auto/forecast` | `sales_request.json` | `horizon`, `future` |\n"
        f"| `POST /auto/inventory` | `inventory_request.json` | `items` (`current_stock`, "
        f"`lead_time_days`={ops['lead']}), `high_demand_quantile`={ops['quantile']} |\n"
        f"| `POST /auto/purchases` | `purchases_request.json` | `items` (+ "
        f"`target_coverage_days`={ops['cover']}) |\n\n"
        f"## Uso\n\n"
        f"```bash\n"
        f"curl -X POST http://localhost:8000/auto/forecast \\\n"
        f"  -H \"Content-Type: application/json\" \\\n"
        f"  -d @examples/auto_dominios/{nombre}/sales_request.json\n"
        f"```\n\n"
        f"El motor entrena-y-predice en una sola llamada: declara el esquema, manda el "
        f"histórico en `rows` y (ventas) el plan de drivers en `future`. No sabe que esto "
        f"es {nombre}; solo ve columnas. En `inventory`/`purchases`, `items` lleva el estado "
        f"por serie (stock actual derivado de la demanda media del histórico).\n"
    )


DOMINIOS = {
    "clinica": (clinica, "Atenciones diarias en una clínica: estacionalidad de gripe en "
                "invierno, caída en feriados y fines de semana, campañas de salud."),
    "restaurante": (restaurante, "Platos vendidos por local y carta: elasticidad de precio, "
                    "promos en racha, clima (sol empuja ceviche), eventos y findes."),
    "energia": (energia, "Demanda eléctrica por subestación: curva en U con la temperatura "
                "(frío/calor suben consumo), día hábil vs feriado."),
    "ecommerce": (ecommerce, "Pedidos por categoría y canal: descuentos, campañas, envío "
                  "gratis, día de pago y un pico de evento comercial (cyber)."),
    "movilidad": (movilidad, "Viajes por ruta: lluvia y eventos empujan demanda, ocio en "
                  "findes vs ruta de aeropuerto, sensibilidad al combustible."),
}

# Parámetros de 'inventario' por rubro: lead time, días de cobertura objetivo, stock
# actual en días de demanda media, cuantil de demanda alta.
OPS = {
    "clinica":     {"lead": 2, "cover": 7,  "stock_dias": 3.0, "quantile": 0.75},
    "restaurante": {"lead": 1, "cover": 3,  "stock_dias": 1.5, "quantile": 0.75},
    "energia":     {"lead": 1, "cover": 2,  "stock_dias": 1.0, "quantile": 0.80},
    "ecommerce":   {"lead": 3, "cover": 10, "stock_dias": 5.0, "quantile": 0.75},
    "movilidad":   {"lead": 1, "cover": 3,  "stock_dias": 2.0, "quantile": 0.75},
}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    total = 0
    indice = ["# Ejemplos multi-dominio — motor agnóstico `/auto/*`\n",
              "Cada subcarpeta es un rubro distinto con su **propio esquema**. Mismo motor, "
              "cero configuración por rubro (ADR-0023). Cada rubro trae los **3 endpoints** "
              "(`sales`, `inventory`, `purchases`) compartiendo `schema` + `rows`. Generado "
              "por `examples/api/generar_auto_dominios.py` (semilla 42).\n",
              "| Dominio | Objetivo | Series | Descripción |",
              "|---|---|---|---|"]
    for nombre, (fn, desc) in DOMINIOS.items():
        sales = fn()
        ops = OPS[nombre]
        inventory = {"schema": sales["schema"], "rows": sales["rows"],
                     "items": _items(sales, ops, cobertura=False),
                     "high_demand_quantile": ops["quantile"]}
        purchases = {"schema": sales["schema"], "rows": sales["rows"],
                     "items": _items(sales, ops, cobertura=True)}
        carpeta = OUT / nombre
        carpeta.mkdir(parents=True, exist_ok=True)
        kb = 0
        for arch, obj in [("sales_request", sales), ("inventory_request", inventory),
                          ("purchases_request", purchases)]:
            p = carpeta / f"{arch}.json"
            p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
            kb += p.stat().st_size // 1024
        (carpeta / "README.md").write_text(readme(nombre, sales, ops, desc), encoding="utf-8")
        s = sales["schema"]
        n_series = len({tuple(r[k] for k in s["series_keys"]) for r in sales["rows"]})
        total += kb
        print(f"  {nombre:12s} target={s['target']:20s} series={n_series} "
              f"filas={len(sales['rows'])} (3 archivos, {kb} KB)")
        indice.append(f"| [`{nombre}`]({nombre}/) | `{s['target']}` | {n_series} | {desc} |")
    (OUT / "README.md").write_text("\n".join(indice) + "\n", encoding="utf-8")
    print(f"Total: {len(DOMINIOS)} dominios × 3 endpoints, {total} KB en {OUT}")


if __name__ == "__main__":
    main()
