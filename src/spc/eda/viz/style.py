"""Estilo visual compartido y utilidades de guardado de figuras.

Centraliza tema, paleta, tamanos y dpi para que todas las figuras se vean
consistentes, en vez de un color hardcodeado por grafico como antes. Tambien
fuerza una fuente con soporte de acentos en espanol.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # backend sin ventana: pensado para generar PNG en batch.

import matplotlib.pyplot as plt  # noqa: E402
import seaborn as sns  # noqa: E402
from matplotlib.container import BarContainer  # noqa: E402

from spc.config import FigureStyle  # noqa: E402


def apply_theme(style: FigureStyle) -> None:
    """Aplica el tema de seaborn y ajustes globales de matplotlib."""
    sns.set_theme(style=style.theme, context=style.context)
    plt.rcParams.update(
        {
            "axes.titleweight": "semibold",
            "axes.titlesize": 13,
            "figure.autolayout": False,
            "savefig.dpi": style.dpi,
            "font.family": "DejaVu Sans",  # tiene acentos completos
        }
    )


def save_figure(path: Path, dpi: int) -> str:
    """Guarda la figura actual con layout ajustado y la cierra. Devuelve la ruta POSIX."""
    path.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(path, dpi=dpi, bbox_inches="tight")
    plt.close()
    return str(path).replace("\\", "/")


def value_labels(ax: plt.Axes, *, horizontal: bool = False, fmt: str = "{:,.0f}") -> None:
    """Anota el valor encima/al lado de cada barra de un grafico de barras."""
    for container in ax.containers:
        if not isinstance(container, BarContainer):
            continue
        # Se leen los valores de los rectangulos (tipado preciso) en vez de
        # `datavalues`, cuyo stub en matplotlib es impreciso.
        values = [p.get_width() if horizontal else p.get_height() for p in container.patches]
        labels = [fmt.format(v).replace(",", " ") for v in values]
        ax.bar_label(container, labels=labels, padding=3, fontsize=8, label_type="edge")
    if horizontal:
        ax.margins(x=0.12)
    else:
        ax.margins(y=0.12)
