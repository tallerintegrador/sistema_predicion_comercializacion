"""Configuracion central del paquete `spc`.

Todo lo que antes eran constantes sueltas en `eda.py` (rutas, semilla, archivos
esperados, parametros de figuras) vive aqui en una dataclass tipada e inmutable.
La configuracion se inyecta al pipeline y los modulos la reciben como argumento,
de modo que las rutas se pueden sobreescribir desde la CLI sin tocar el codigo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

# Nombre logico -> archivo esperado en data/raw.
EXPECTED_FILES: dict[str, str] = {
    "train": "train.csv",
    "test": "test.csv",
    "stores": "stores.csv",
    "transactions": "transactions.csv",
    "oil": "oil.csv",
    "holidays_events": "holidays_events.csv",
    "sample_submission": "sample_submission.csv",
}


@dataclass(frozen=True)
class FigureStyle:
    """Parametros visuales compartidos por todas las figuras."""

    theme: str = "whitegrid"
    context: str = "notebook"
    dpi: int = 160
    figsize_default: tuple[float, float] = (9.0, 5.0)
    figsize_wide: tuple[float, float] = (13.0, 5.0)
    figsize_square: tuple[float, float] = (8.0, 6.0)
    # Paleta coherente por rol semantico (no un color por figura al azar).
    color_primary: str = "#2f6f8f"
    color_secondary: str = "#8a5a44"
    color_accent: str = "#4f8a5f"
    color_highlight: str = "#7a5c91"
    palette_qualitative: str = "tab10"
    cmap_diverging: str = "vlag"
    cmap_sequential: str = "YlGnBu"


@dataclass(frozen=True)
class Settings:
    """Rutas y parametros del pipeline. Inmutable y reproducible."""

    base_dir: Path = field(default_factory=Path.cwd)
    random_seed: int = 42
    style: FigureStyle = field(default_factory=FigureStyle)
    expected_files: dict[str, str] = field(default_factory=lambda: dict(EXPECTED_FILES))

    # --- Rutas derivadas (todas relativas a base_dir) ---
    @property
    def raw_dir(self) -> Path:
        return self.base_dir / "data" / "raw"

    @property
    def processed_dir(self) -> Path:
        return self.base_dir / "data" / "processed"

    @property
    def figures_dir(self) -> Path:
        return self.base_dir / "figures"

    @property
    def report_path(self) -> Path:
        return self.base_dir / "reporte_eda.md"

    @property
    def notebook_path(self) -> Path:
        return self.base_dir / "notebooks" / "eda.ipynb"

    def ensure_dirs(self) -> None:
        """Crea las carpetas de salida si no existen."""
        for directory in (self.processed_dir, self.figures_dir, self.notebook_path.parent):
            directory.mkdir(parents=True, exist_ok=True)
