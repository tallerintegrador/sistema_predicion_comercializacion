"""Generador de datos sintéticos **multi-país** para los 3 ejemplos ``/auto/*`` (ADR-0023).

Mundo: cadena minorista presente en 4 países (Perú, Bolivia, España, México). Series =
``almacen × sku``. El objetivo ``unidades_vendidas`` se construye con correlaciones
**reales** contra ~40 features declaradas, para que el AutoML aprenda señal y no ruido
(una columna sin correlación es ruido y EMPEORA la métrica). Todo es leak-safe:

- Las **conocidas a futuro** (precio, promo, calendario, país, moneda, tipo de cambio,
  atributos de producto, flete/combustible/confiabilidad) afectan la demanda del día y
  se conocen de antemano → entran tal cual + rezagos.
- Las **solo-pasado** (tráfico, transacciones, ventas online, devoluciones, recepciones,
  stock, cobertura, rotación, mermas, pedidos pendientes, lead time real) se derivan de la
  demanda y de una **simulación de inventario** por serie → solo sus rezagos son features
  (el motor nunca ve su valor del período a predecir).

Demuestra agnosticismo de verdad: estacionalidad por **hemisferio** (verano dic-feb en el
sur, jun-ago en el norte), feriados y día de pago locales, moneda y FX por país. Semilla 42.

Uso:
    venv\\Scripts\\python examples\\api\\generar_auto_retail.py
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import numpy as np

rng = np.random.default_rng(42)

OUT = Path(__file__).resolve().parent

INICIO = date(2024, 1, 1)
DIAS = 150          # ~5 meses: rezagos hasta 28 + estacionalidad semanal estable
HORIZON = 14        # días futuros con drivers planificados (bloque `future`)


# ===========================================================================
# Catálogo de países (hemisferio, moneda, tipo de cambio ref, combustible ref)
# ===========================================================================
PAISES = {
    "Peru":    {"hemisferio": "sur",   "moneda": "PEN", "fx_ref": 3.75, "fuel_ref": 4.40,
                "online_base": 0.14},
    "Bolivia": {"hemisferio": "sur",   "moneda": "BOB", "fx_ref": 6.96, "fuel_ref": 3.74,
                "online_base": 0.08},
    "Espana":  {"hemisferio": "norte", "moneda": "EUR", "fx_ref": 0.92, "fuel_ref": 1.65,
                "online_base": 0.30},
    "Mexico":  {"hemisferio": "norte", "moneda": "MXN", "fx_ref": 17.1, "fuel_ref": 24.5,
                "online_base": 0.22},
}

# Feriados nacionales 2024 por país (fecha -> nombre de la festividad local).
FERIADOS_PAIS = {
    "Peru": {
        date(2024, 1, 1): "ano_nuevo", date(2024, 3, 28): "jueves_santo",
        date(2024, 3, 29): "viernes_santo", date(2024, 5, 1): "dia_trabajo",
        date(2024, 6, 7): "batalla_arica", date(2024, 6, 29): "san_pedro_san_pablo",
    },
    "Bolivia": {
        date(2024, 1, 1): "ano_nuevo", date(2024, 1, 22): "estado_plurinacional",
        date(2024, 2, 12): "carnaval", date(2024, 2, 13): "carnaval",
        date(2024, 3, 29): "viernes_santo", date(2024, 5, 1): "dia_trabajo",
    },
    "Espana": {
        date(2024, 1, 1): "ano_nuevo", date(2024, 1, 6): "reyes",
        date(2024, 3, 29): "viernes_santo", date(2024, 5, 1): "dia_trabajo",
        date(2024, 5, 2): "comunidad_madrid",
    },
    "Mexico": {
        date(2024, 1, 1): "ano_nuevo", date(2024, 2, 5): "dia_constitucion",
        date(2024, 3, 18): "natalicio_juarez", date(2024, 5, 1): "dia_trabajo",
        date(2024, 5, 5): "batalla_puebla",
    },
}

# ===========================================================================
# Catálogo de almacenes (2 por país): segmento, tamaño relativo, clima base
# ===========================================================================
ALMACENES = {
    "lima_norte": {"pais": "Peru", "segmento_almacen": "urbano", "mult": 1.30,
                   "trafico_base": 260, "temp_base": 20.0, "temp_amp": 5.0},
    "arequipa":   {"pais": "Peru", "segmento_almacen": "turistico", "mult": 0.85,
                   "trafico_base": 150, "temp_base": 16.0, "temp_amp": 6.0},
    "la_paz":     {"pais": "Bolivia", "segmento_almacen": "urbano", "mult": 1.00,
                   "trafico_base": 200, "temp_base": 12.0, "temp_amp": 4.0},
    "santa_cruz": {"pais": "Bolivia", "segmento_almacen": "residencial", "mult": 1.10,
                   "trafico_base": 210, "temp_base": 25.0, "temp_amp": 5.0},
    "madrid":     {"pais": "Espana", "segmento_almacen": "urbano", "mult": 1.40,
                   "trafico_base": 300, "temp_base": 15.0, "temp_amp": 12.0},
    "barcelona":  {"pais": "Espana", "segmento_almacen": "turistico", "mult": 1.25,
                   "trafico_base": 280, "temp_base": 17.0, "temp_amp": 9.0},
    "cdmx":       {"pais": "Mexico", "segmento_almacen": "urbano", "mult": 1.35,
                   "trafico_base": 320, "temp_base": 18.0, "temp_amp": 7.0},
    "monterrey":  {"pais": "Mexico", "segmento_almacen": "residencial", "mult": 1.15,
                   "trafico_base": 240, "temp_base": 24.0, "temp_amp": 10.0},
}

# ===========================================================================
# Catálogo de SKUs: categoría, proveedor, precio ref, elasticidad, nivel base,
# sensibilidades estacionales + atributos de producto (conocidos a futuro, estáticos)
# ===========================================================================
SKUS = {
    "ARROZ-5KG": {
        "categoria": "abarrotes", "proveedor": "Molinos del Norte", "precio_ref": 24.90,
        "elas": 0.6, "base": 40, "feriado": 1.35, "verano": 0.00, "temp": 0.000,
        "perecedero": 0, "vida_util_dias": 540, "marca": "DonArroz",
        "unidad_medida": "saco", "peso_kg": 5.0, "importado": 0.10, "escolar": 0.10},
    "LECHE-1L": {
        "categoria": "lacteos", "proveedor": "Gloria SA", "precio_ref": 4.50,
        "elas": 0.5, "base": 70, "feriado": 1.20, "verano": 0.05, "temp": 0.004,
        "perecedero": 1, "vida_util_dias": 7, "marca": "Gloria",
        "unidad_medida": "litro", "peso_kg": 1.0, "importado": 0.00, "escolar": 0.18},
    "GASEOSA-3L": {
        "categoria": "bebidas", "proveedor": "Embotelladora Sur", "precio_ref": 9.90,
        "elas": 1.8, "base": 55, "feriado": 1.15, "verano": 0.25, "temp": 0.022,
        "perecedero": 0, "vida_util_dias": 180, "marca": "ColaSur",
        "unidad_medida": "botella", "peso_kg": 3.0, "importado": 0.05, "escolar": 0.00},
    "DETERGENTE-2KG": {
        "categoria": "limpieza", "proveedor": "Alicorp", "precio_ref": 18.50,
        "elas": 1.0, "base": 32, "feriado": 1.10, "verano": 0.00, "temp": 0.000,
        "perecedero": 0, "vida_util_dias": 730, "marca": "Bolivar",
        "unidad_medida": "bolsa", "peso_kg": 2.0, "importado": 0.20, "escolar": 0.05},
    "ACEITE-1L": {
        "categoria": "abarrotes", "proveedor": "Alicorp", "precio_ref": 11.20,
        "elas": 0.9, "base": 36, "feriado": 1.25, "verano": 0.00, "temp": 0.000,
        "perecedero": 0, "vida_util_dias": 365, "marca": "Primor",
        "unidad_medida": "botella", "peso_kg": 0.92, "importado": 0.30, "escolar": 0.00},
}

CLIMAS = ["soleado", "nublado", "lluvia"]
EVENTOS = ["ninguno", "feria", "partido", "concierto"]

# Proveedor: lead nominal, lote mínimo, costo unitario, flete base, confiabilidad [0,1].
PROVEEDOR_OPS = {
    "Molinos del Norte": {"lead": 5, "moq": 50, "costo": 19.50, "flete": 1.80, "conf": 0.88},
    "Gloria SA":         {"lead": 2, "moq": 120, "costo": 3.40, "flete": 0.60, "conf": 0.95},
    "Embotelladora Sur": {"lead": 3, "moq": 80, "costo": 7.20, "flete": 1.10, "conf": 0.90},
    "Alicorp":           {"lead": 4, "moq": 60, "costo": 14.10, "flete": 1.40, "conf": 0.92},
}


# ===========================================================================
# Helpers de calendario / país (conocidos a futuro)
# ===========================================================================
def temperatura(ainfo: dict, f: date) -> float:
    """Temperatura estacional según el **hemisferio** del país (conocida a futuro)."""
    doy = f.timetuple().tm_yday
    pico = 15 if PAISES[ainfo["pais"]]["hemisferio"] == "sur" else 196  # verano sur≈ene, norte≈jul
    base = ainfo["temp_base"] + ainfo["temp_amp"] * np.cos(2 * np.pi * (doy - pico) / 365.0)
    return round(float(base + rng.normal(0, 1.2)), 1)


def es_feriado(pais: str, f: date) -> int:
    return 1 if f in FERIADOS_PAIS[pais] else 0


def festividad_local(pais: str, f: date) -> str:
    return FERIADOS_PAIS[pais].get(f, "ninguna")


def vispera(pais: str, f: date) -> int:
    return 1 if (f + timedelta(days=1)) in FERIADOS_PAIS[pais] else 0


def dia_pago(pais: str, f: date) -> int:
    """Día de pago local: quincena/fin de mes (España solo fin de mes)."""
    fin_mes = (f + timedelta(days=1)).day == 1
    if pais == "Espana":
        return 1 if fin_mes else 0
    return 1 if (f.day == 15 or fin_mes) else 0


def inicio_clases(pais: str, f: date) -> int:
    """Vuelta al cole: marzo en el sur, fin agosto/inicio septiembre en el norte."""
    hemis = PAISES[pais]["hemisferio"]
    if hemis == "sur":
        return 1 if (f.month == 3 and f.day <= 14) else 0
    return 1 if (f.month == 8 and f.day >= 25) or (f.month == 9 and f.day <= 10) else 0


def temporada(pais: str, f: date) -> str:
    """Temporada comercial alta/media/baja según hemisferio."""
    hemis = PAISES[pais]["hemisferio"]
    verano = {12, 1, 2} if hemis == "sur" else {6, 7, 8}
    invierno = {6, 7, 8} if hemis == "sur" else {12, 1, 2}
    if f.month in verano or f.month == 12:
        return "alta"
    if f.month in invierno:
        return "baja"
    return "media"


def fx_diario(pais: str, n: int) -> list[float]:
    """Tipo de cambio USD por día: paseo aleatorio suave alrededor de la referencia."""
    ref = PAISES[pais]["fx_ref"]
    pasos = rng.normal(0, ref * 0.004, size=n).cumsum()
    return [round(float(ref + p), 4) for p in pasos]


def fuel_diario(pais: str, n: int) -> list[float]:
    """Precio de combustible por día: tendencia lenta + ruido (conocido a futuro)."""
    ref = PAISES[pais]["fuel_ref"]
    tend = np.linspace(0, ref * 0.05, n)
    return [round(float(ref + tend[i] + rng.normal(0, ref * 0.01)), 3) for i in range(n)]


def clima_factor(sku_info: dict, clima: str) -> float:
    if sku_info["categoria"] == "bebidas":
        return {"soleado": 1.22, "nublado": 1.0, "lluvia": 0.82}[clima]
    return {"soleado": 1.05, "nublado": 1.0, "lluvia": 0.96}[clima]


def evento_factor(sku_info: dict, evento: str) -> float:
    if evento == "ninguno":
        return 1.0
    if sku_info["categoria"] in ("bebidas", "abarrotes"):
        return {"feria": 1.45, "partido": 1.55, "concierto": 1.35}[evento]
    return {"feria": 1.15, "partido": 1.10, "concierto": 1.10}[evento]


# ===========================================================================
# Modelo de demanda: producto de factores (mismo modelo en train y future)
# ===========================================================================
def _factores_demanda(sinfo, ainfo, pais, f, *, promo, descuento, campaña, clima, evento,
                      competidor, temp, precio, precio_comp, traf_rel, fx, fx_ref,
                      fuel, fuel_ref, conf, flete, flete_ref) -> float:
    dow = f.weekday()
    dow_f = (1.20 if sinfo["categoria"] == "bebidas" else 1.10) if dow >= 5 else (0.9 if dow == 0 else 1.0)
    mes_f = 1.0 + sinfo["verano"] * np.sin(2 * np.pi * f.timetuple().tm_yday / 365.0 + np.pi / 2)
    precio_f = (precio / sinfo["precio_ref"]) ** (-sinfo["elas"])
    comp_precio_f = (precio / precio_comp) ** (-0.8)          # más barato que el rival → vendo más
    promo_disp = 1.12 if promo else 1.0
    fer = sinfo["feriado"] if es_feriado(pais, f) else 1.0
    visp = 1.15 if vispera(pais, f) else 1.0                  # acaparamiento víspera de feriado
    camp = 1.18 if campaña else 1.0
    cf = clima_factor(sinfo, clima)
    temp_f = 1.0 + sinfo["temp"] * (temp - 20.0)             # calor empuja bebidas/lácteos
    ev = evento_factor(sinfo, evento)
    comp = 0.85 if competidor else 1.0
    # --- Drivers macro/país (conocidos a futuro) ---
    fx_f = (fx / fx_ref) ** (-0.5 * sinfo["importado"])      # moneda débil → cae lo importado
    fuel_f = (fuel / fuel_ref) ** (-0.05)                    # combustible caro → leve freno
    pago_f = 1.10 if dia_pago(pais, f) else 1.0             # quincena/fin de mes → repunte
    escolar_f = 1.0 + sinfo["escolar"] * (1.0 if inicio_clases(pais, f) else 0.0)
    temp_com = {"alta": 1.06, "media": 1.0, "baja": 0.95}[temporada(pais, f)]
    # --- Logística/proveedor ---
    conf_f = 0.85 + 0.15 * conf                              # proveedor confiable → menos quiebres
    flete_f = (flete / flete_ref) ** (-0.03)                # flete caro → leve presión de precio
    return (dow_f * mes_f * precio_f * comp_precio_f * promo_disp * fer * visp * camp * cf
            * temp_f * ev * comp * fx_f * fuel_f * pago_f * escolar_f * temp_com
            * conf_f * flete_f * traf_rel)


# ===========================================================================
# Generación de filas (histórico) + bloque future
# ===========================================================================
def generar():
    fechas = [INICIO + timedelta(days=i) for i in range(DIAS)]
    fechas_fut = [INICIO + timedelta(days=DIAS + i) for i in range(HORIZON)]
    rows, future = [], []

    for almacen, ainfo in ALMACENES.items():
        pais = ainfo["pais"]
        pinfo = PAISES[pais]
        fx_ref, fuel_ref = pinfo["fx_ref"], pinfo["fuel_ref"]
        fx_dia = fx_diario(pais, DIAS)
        fuel_dia = fuel_diario(pais, DIAS)
        fx_fut = fx_diario(pais, HORIZON)
        fuel_fut = fuel_diario(pais, HORIZON)

        clima_dia = list(rng.choice(CLIMAS, size=DIAS, p=[0.45, 0.35, 0.20]))
        evento_dia = list(rng.choice(EVENTOS, size=DIAS, p=[0.88, 0.05, 0.04, 0.03]))
        campaña_dia = (rng.random(DIAS) < 0.10).astype(int)
        temp_dia = [temperatura(ainfo, f) for f in fechas]
        trafico_dia, transacciones_dia = [], []
        for i, f in enumerate(fechas):
            dow = f.weekday()
            dow_f = 1.25 if dow >= 5 else (0.9 if dow == 0 else 1.0)
            cf = 1.10 if clima_dia[i] == "soleado" else (0.9 if clima_dia[i] == "lluvia" else 1.0)
            t = ainfo["trafico_base"] * dow_f * cf * rng.lognormal(0, 0.08)
            trafico_dia.append(int(round(t)))
            transacciones_dia.append(int(round(t * rng.uniform(0.55, 0.68))))

        # Plan futuro de tienda (conocido a futuro): clima pronosticado, campaña, temp.
        clima_fut = list(rng.choice(CLIMAS, size=HORIZON, p=[0.45, 0.35, 0.20]))
        campaña_fut = (rng.random(HORIZON) < 0.12).astype(int)
        temp_fut = [temperatura(ainfo, f) for f in fechas_fut]

        for sku, sinfo in SKUS.items():
            ops = PROVEEDOR_OPS[sinfo["proveedor"]]
            conf, flete, flete_ref = ops["conf"], ops["flete"], ops["flete"]
            base = sinfo["base"] * ainfo["mult"]
            tendencia = rng.uniform(0.0003, 0.0010)          # leve crecimiento diario por serie

            # Promo: rachas por serie (~15% de días).
            en_promo = np.zeros(DIAS, dtype=int)
            descuento = np.zeros(DIAS)
            i = 0
            while i < DIAS:
                if rng.random() < 0.05:
                    dur = int(rng.integers(3, 8))
                    desc = int(rng.choice([10, 15, 20, 25, 30]))
                    for j in range(i, min(i + dur, DIAS)):
                        en_promo[j], descuento[j] = 1, desc
                    i += dur
                else:
                    i += 1
            competidor_promo = (rng.random(DIAS) < 0.12).astype(int)
            precio_comp_dia = [round(sinfo["precio_ref"] * rng.uniform(0.90, 1.12), 2) for _ in range(DIAS)]

            # --- Simulación de inventario por serie (genera las solo-pasado coherentes) ---
            lead = ops["lead"]
            media_aprox = base * 1.05
            stock = media_aprox * rng.uniform(3.0, 5.0)      # arranque de stock
            reorden = media_aprox * lead
            online_share = pinfo["online_base"] * rng.uniform(0.8, 1.2)
            ret_rate = 0.05 if sinfo["perecedero"] else 0.025
            spoil_rate = 0.03 if sinfo["perecedero"] else 0.0
            dem_prev = media_aprox

            for i, f in enumerate(fechas):
                precio = round(sinfo["precio_ref"] * (1 - descuento[i] / 100.0), 2)
                traf_rel = trafico_dia[i] / ainfo["trafico_base"]
                factor = _factores_demanda(
                    sinfo, ainfo, pais, f, promo=en_promo[i], descuento=descuento[i],
                    campaña=campaña_dia[i], clima=clima_dia[i], evento=evento_dia[i],
                    competidor=competidor_promo[i], temp=temp_dia[i], precio=precio,
                    precio_comp=precio_comp_dia[i], traf_rel=traf_rel,
                    fx=fx_dia[i], fx_ref=fx_ref, fuel=fuel_dia[i], fuel_ref=fuel_ref,
                    conf=conf, flete=flete, flete_ref=flete_ref,
                )
                demanda = base * (1 + tendencia * i) * factor * rng.lognormal(0, 0.12)
                quiebre = 1 if rng.random() < 0.04 else 0
                if quiebre:
                    demanda *= rng.uniform(0.40, 0.65)
                demanda = float(max(0, round(demanda)))

                # Inventario: stock al inicio del día, ventas atendidas, pendientes, mermas...
                stock_inicial = stock
                atendida = min(demanda, stock)
                pendientes = max(0.0, demanda - stock)
                stock -= atendida
                mermas = round(stock * spoil_rate) if sinfo["perecedero"] else 0
                stock -= mermas
                devoluciones = round(dem_prev * ret_rate)
                stock += devoluciones
                recepciones = 0
                if stock < reorden:                          # reposición cuando baja del punto
                    recepciones = int(round(reorden * 1.5 + ops["moq"]))
                    stock += recepciones
                dias_cobertura = round(stock / max(media_aprox, 1.0), 2)
                rotacion = round(atendida / max(stock_inicial, 1.0), 3)
                ventas_online = round(demanda * online_share * rng.uniform(0.85, 1.15))
                lead_real = int(round(lead + rng.normal(0, 1) + (1 if quiebre else 0)))
                dem_prev = demanda

                rows.append({
                    "fecha": f.isoformat(), "almacen": almacen, "sku": sku,
                    "unidades_vendidas": demanda,
                    # --- conocidas a futuro: comerciales ---
                    "precio": precio, "en_promo": int(en_promo[i]),
                    "descuento_pct": float(descuento[i]),
                    "es_feriado": es_feriado(pais, f), "vispera_feriado": vispera(pais, f),
                    "campaña_mkt": int(campaña_dia[i]), "temperatura": temp_dia[i],
                    "clima": clima_dia[i], "evento_cercano": evento_dia[i],
                    "categoria": sinfo["categoria"],
                    "segmento_almacen": ainfo["segmento_almacen"],
                    "proveedor": sinfo["proveedor"],
                    # --- conocidas a futuro: macro/país ---
                    "pais": pais, "moneda": pinfo["moneda"],
                    "tipo_cambio_usd": fx_dia[i],
                    "festividad_local": festividad_local(pais, f),
                    "temporada": temporada(pais, f),
                    "dia_pago_local": dia_pago(pais, f),
                    "inicio_clases": inicio_clases(pais, f),
                    # --- conocidas a futuro: atributos de producto ---
                    "perecedero": sinfo["perecedero"],
                    "vida_util_dias": sinfo["vida_util_dias"],
                    "marca": sinfo["marca"], "unidad_medida": sinfo["unidad_medida"],
                    "peso_kg": sinfo["peso_kg"],
                    # --- conocidas a futuro: logística ---
                    "costo_flete": flete, "precio_combustible": fuel_dia[i],
                    "confiabilidad_proveedor": conf,
                    # --- solo pasado: tienda/competencia ---
                    "trafico_tienda": trafico_dia[i], "transacciones": transacciones_dia[i],
                    "competidor_promo": int(competidor_promo[i]),
                    "precio_competidor": precio_comp_dia[i],
                    "quiebre_stock_prev": quiebre,
                    # --- solo pasado: inventario/almacén ---
                    "ventas_online": int(ventas_online), "devoluciones": int(devoluciones),
                    "recepciones": int(recepciones), "stock_inicial_dia": round(stock_inicial, 1),
                    "dias_cobertura": dias_cobertura, "rotacion_inventario": rotacion,
                    "pedidos_pendientes": int(pendientes), "lead_time_real": max(1, lead_real),
                })

            # --- Plan futuro por serie: SOLO features conocidas a futuro + categóricas ---
            for k, f in enumerate(fechas_fut):
                promo_f = 1 if 2 <= k <= 6 else 0
                desc_f = 20.0 if promo_f else 0.0
                precio_f = round(sinfo["precio_ref"] * (1 - desc_f / 100.0), 2)
                future.append({
                    "fecha": f.isoformat(), "almacen": almacen, "sku": sku,
                    "precio": precio_f, "en_promo": promo_f, "descuento_pct": desc_f,
                    "es_feriado": es_feriado(pais, f), "vispera_feriado": vispera(pais, f),
                    "campaña_mkt": int(campaña_fut[k]), "temperatura": temp_fut[k],
                    "clima": clima_fut[k], "evento_cercano": "ninguno",
                    "categoria": sinfo["categoria"],
                    "segmento_almacen": ainfo["segmento_almacen"],
                    "proveedor": sinfo["proveedor"],
                    "pais": pais, "moneda": pinfo["moneda"], "tipo_cambio_usd": fx_fut[k],
                    "festividad_local": festividad_local(pais, f),
                    "temporada": temporada(pais, f), "dia_pago_local": dia_pago(pais, f),
                    "inicio_clases": inicio_clases(pais, f),
                    "perecedero": sinfo["perecedero"], "vida_util_dias": sinfo["vida_util_dias"],
                    "marca": sinfo["marca"], "unidad_medida": sinfo["unidad_medida"],
                    "peso_kg": sinfo["peso_kg"],
                    "costo_flete": flete, "precio_combustible": fuel_fut[k],
                    "confiabilidad_proveedor": conf,
                })
    return rows, future


# ===========================================================================
# Esquema declarado (≈40 features, agnóstico al rubro)
# ===========================================================================
def _f(name: str, type_: str, known_future: bool) -> dict:
    return {"name": name, "type": type_, "known_future": known_future}


FEATURES = [
    # Comerciales (conocidas a futuro)
    _f("precio", "numeric", True), _f("en_promo", "numeric", True),
    _f("descuento_pct", "numeric", True), _f("es_feriado", "numeric", True),
    _f("vispera_feriado", "numeric", True), _f("campaña_mkt", "numeric", True),
    _f("temperatura", "numeric", True), _f("clima", "categorical", True),
    _f("evento_cercano", "categorical", True), _f("categoria", "categorical", True),
    _f("segmento_almacen", "categorical", True), _f("proveedor", "categorical", True),
    # Macro/país (conocidas a futuro)
    _f("pais", "categorical", True), _f("moneda", "categorical", True),
    _f("tipo_cambio_usd", "numeric", True), _f("festividad_local", "categorical", True),
    _f("temporada", "categorical", True), _f("dia_pago_local", "numeric", True),
    _f("inicio_clases", "numeric", True),
    # Atributos de producto (conocidas a futuro, estáticas por SKU)
    _f("perecedero", "numeric", True), _f("vida_util_dias", "numeric", True),
    _f("marca", "categorical", True), _f("unidad_medida", "categorical", True),
    _f("peso_kg", "numeric", True),
    # Logística (conocidas a futuro)
    _f("costo_flete", "numeric", True), _f("precio_combustible", "numeric", True),
    _f("confiabilidad_proveedor", "numeric", True),
    # Tienda/competencia (solo pasado)
    _f("trafico_tienda", "numeric", False), _f("transacciones", "numeric", False),
    _f("competidor_promo", "numeric", False), _f("precio_competidor", "numeric", False),
    _f("quiebre_stock_prev", "numeric", False),
    # Inventario/almacén (solo pasado)
    _f("ventas_online", "numeric", False), _f("devoluciones", "numeric", False),
    _f("recepciones", "numeric", False), _f("stock_inicial_dia", "numeric", False),
    _f("dias_cobertura", "numeric", False), _f("rotacion_inventario", "numeric", False),
    _f("pedidos_pendientes", "numeric", False), _f("lead_time_real", "numeric", False),
]

SCHEMA = {
    "target": "unidades_vendidas", "date": "fecha",
    "series_keys": ["almacen", "sku"], "features": FEATURES,
}


def items(*, con_cobertura: bool):
    """Estado/parametros de inventario por serie (claves de serie + campos de política)."""
    out = []
    for almacen, ainfo in ALMACENES.items():
        for sku, sinfo in SKUS.items():
            ops = PROVEEDOR_OPS[sinfo["proveedor"]]
            stock = int(round(sinfo["base"] * ainfo["mult"] * rng.uniform(2.5, 5.0)))
            it = {"almacen": almacen, "sku": sku, "current_stock": stock,
                  "lead_time_days": ops["lead"], "proveedor": sinfo["proveedor"],
                  "moq": ops["moq"], "costo_unitario": ops["costo"]}
            if con_cobertura:
                it["target_coverage_days"] = 14
            out.append(it)
    return out


def main():
    rows, future = generar()
    n_series = len(ALMACENES) * len(SKUS)
    print(f"filas: {len(rows)} | future: {len(future)} | series: {n_series} "
          f"| paises: {len(PAISES)} | features: {len(FEATURES)}")

    sales = {"schema": SCHEMA, "horizon": HORIZON, "granularity": "day", "rows": rows, "future": future}
    inventory = {"schema": SCHEMA, "rows": rows, "items": items(con_cobertura=False),
                 "high_demand_quantile": 0.75}
    purchases = {"schema": SCHEMA, "rows": rows, "items": items(con_cobertura=True)}

    for nombre, obj in [("auto_sales_request", sales),
                        ("auto_inventory_request", inventory),
                        ("auto_purchases_request", purchases)]:
        p = OUT / f"{nombre}.json"
        p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"escrito: {p.name} ({p.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
