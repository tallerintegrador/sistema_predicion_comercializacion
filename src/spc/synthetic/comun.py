"""Vocabulario y utilidades **compartidas** por los generadores sintéticos.

Centraliza lo que los tres dominios reusan: el universo de productos/categorías, los
medios de pago/canales, el calendario de feriados (PYME, contexto peruano) y los
ayudantes deterministas (RNG sembrado, banderas de calendario, días al próximo
feriado). Todo deriva de una **semilla** para que la generación sea reproducible.
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Universo de productos (genérico para una PYME de retail)
# ---------------------------------------------------------------------------
# (sku, categoría). Mismo catálogo en los tres dominios para que un cliente pueda
# cruzar ventas/compras/almacén por `sku`.
CATALOGO: tuple[tuple[str, str], ...] = (
    ("SKU-001", "Bebidas"),
    ("SKU-002", "Abarrotes"),
    ("SKU-003", "Lacteos"),
    ("SKU-004", "Limpieza"),
    ("SKU-005", "Snacks"),
    ("SKU-006", "Cuidado personal"),
    ("SKU-007", "Bebidas"),
    ("SKU-008", "Abarrotes"),
)

METODOS_PAGO: tuple[str, ...] = ("efectivo", "tarjeta", "transferencia", "yape_plin")
CANALES_VENTA: tuple[str, ...] = ("tienda", "online")
CONDICIONES_PAGO: tuple[str, ...] = ("contado", "credito_15", "credito_30")
ZONAS_ALMACEN: tuple[str, ...] = ("A", "B", "C")

# Feriados representativos de una PYME peruana (mes, día). La señal predictiva es la
# CERCANÍA (`dias_a_proximo_feriado`), no una bandera binaria (que el docente descartó).
FERIADOS_MD: tuple[tuple[int, int], ...] = (
    (1, 1),    # Año Nuevo
    (5, 1),    # Día del Trabajo
    (6, 29),   # San Pedro y San Pablo
    (7, 28),   # Fiestas Patrias
    (7, 29),
    (8, 30),   # Santa Rosa de Lima
    (10, 8),   # Combate de Angamos
    (11, 1),   # Todos los Santos
    (12, 8),   # Inmaculada Concepción
    (12, 25),  # Navidad
)


def rng_de(seed: int, *etiquetas: int) -> np.random.Generator:
    """Generador determinista derivado de la semilla global y unas etiquetas enteras.

    Mismas etiquetas → misma secuencia, así cada serie ``(tienda, sku)`` o
    ``(proveedor, sku)`` es independiente pero reproducible.
    """
    return np.random.default_rng([seed, *etiquetas])


def entre(rng: np.random.Generator, lo: float, hi: float) -> float:
    """Un float uniforme en ``[lo, hi]`` (azúcar para los rangos de patrón)."""
    return float(rng.uniform(lo, hi))


def fechas_dia(inicio: date, n_dias: int) -> list[date]:
    """Lista de ``n_dias`` fechas consecutivas desde ``inicio`` (inclusive)."""
    return [inicio + timedelta(days=i) for i in range(n_dias)]


def es_fin_de_semana(fechas: list[date]) -> np.ndarray:
    """Bandera 0/1 por fecha: 1 si es sábado/domingo (corrige el 0/1/2/3)."""
    return np.array([1 if f.weekday() >= 5 else 0 for f in fechas], dtype="int64")


def _feriados_de_anios(anios: set[int]) -> list[date]:
    """Materializa las fechas de feriado para los años dados (ordenadas)."""
    fechas = [date(a, m, d) for a in sorted(anios) for (m, d) in FERIADOS_MD]
    return sorted(fechas)


def dias_a_proximo_feriado(fechas: list[date]) -> np.ndarray:
    """Días (≥0) hasta el próximo feriado para cada fecha (reemplaza la bandera feriado).

    Considera los feriados del año de la fecha y del siguiente, de modo que diciembre
    "ve" Año Nuevo. Es la variable de calendario con señal que el docente pidió en vez
    de la bandera binaria que no aportaba.
    """
    if not fechas:
        return np.array([], dtype="int64")
    anios = {f.year for f in fechas} | {f.year + 1 for f in fechas}
    feriados = _feriados_de_anios(anios)
    fer_ord = np.array([f.toordinal() for f in feriados])
    salida = np.empty(len(fechas), dtype="int64")
    for i, f in enumerate(fechas):
        o = f.toordinal()
        futuros = fer_ord[fer_ord >= o]
        salida[i] = int(futuros[0] - o) if futuros.size else 0
    return salida


def factor_estacional_semanal(fechas: list[date], amplitud: float) -> np.ndarray:
    """Multiplicador por día de la semana (repunte de fin de semana en retail)."""
    # Lun..Dom: leve caída entre semana, alza viernes-domingo.
    base = np.array([0.00, -0.05, -0.03, 0.02, 0.12, 0.28, 0.18])
    dow = np.array([f.weekday() for f in fechas])
    return 1.0 + amplitud * base[dow]


def factor_estacional_anual(fechas: list[date], amplitud: float, fase: float) -> np.ndarray:
    """Multiplicador estacional anual (onda senoidal sobre el día del año)."""
    doy = np.array([f.timetuple().tm_yday for f in fechas], dtype="float64")
    return 1.0 + amplitud * np.sin(2 * np.pi * doy / 365.25 + fase)


def productos(n: int) -> tuple[tuple[str, str], ...]:
    """Primeros ``n`` (sku, categoría) del catálogo (recicla si se piden de más)."""
    if n <= len(CATALOGO):
        return CATALOGO[:n]
    veces = (n // len(CATALOGO)) + 1
    return (CATALOGO * veces)[:n]


def manifiesto_fila(dominio: str, df: pd.DataFrame, seed: int) -> dict[str, object]:
    """Fila de metadatos del dataset para el MANIFIESTO (deja claro que es sintético)."""
    return {
        "dominio": dominio,
        "archivo": f"{dominio}_sintetico.csv",
        "filas": len(df),
        "columnas": df.shape[1],
        "sintetico": True,
        "semilla": seed,
    }
