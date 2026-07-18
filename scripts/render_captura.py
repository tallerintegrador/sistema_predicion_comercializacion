"""Renderiza texto de terminal a una imagen PNG estilo consola (evidencia de pruebas).

Convierte la salida de pytest (o cualquier log) en una captura PNG legible, con fondo oscuro
y tipografía monoespaciada, para adjuntar como evidencia en los documentos de prueba. Si
Pillow no está instalado, el llamador debe caer a guardar solo el ``.txt``.

Uso programático:
    from render_captura import render_png
    render_png(texto, destino_png, titulo="pytest tests/")
"""

from __future__ import annotations

from pathlib import Path

FONDO = (30, 30, 30)
TEXTO = (220, 220, 220)
VERDE = (120, 200, 120)
ROJO = (220, 120, 120)
TITULO_BG = (45, 55, 75)
MARGEN = 16
INTERLINEA = 4


def _fuente(tam: int = 14):
    from PIL import ImageFont

    for nombre in ("consola.ttf", "DejaVuSansMono.ttf", "cour.ttf", "Consolas.ttf"):
        try:
            return ImageFont.truetype(nombre, tam)
        except Exception:
            continue
    return ImageFont.load_default()


def _color_linea(linea: str) -> tuple[int, int, int]:
    baja = linea.lower()
    if "passed" in baja or "PASSED" in linea or linea.strip().endswith("ok"):
        return VERDE
    if "failed" in baja or "error" in baja:
        return ROJO
    return TEXTO


def render_png(texto: str, destino: Path, *, titulo: str = "", max_lineas: int = 60) -> Path:
    """Renderiza ``texto`` (recortado a ``max_lineas``) a un PNG en ``destino``."""
    from PIL import Image, ImageDraw

    lineas = texto.replace("\r\n", "\n").split("\n")
    if len(lineas) > max_lineas:
        lineas = ["… (recortado; log completo en el .txt) …", ""] + lineas[-(max_lineas - 2):]

    fuente = _fuente(14)
    fuente_tit = _fuente(15)

    # Medir con una imagen scratch.
    scratch = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    alto_linea = (scratch.textbbox((0, 0), "Ag", font=fuente)[3]) + INTERLINEA
    ancho = max([scratch.textbbox((0, 0), ln or " ", font=fuente)[2] for ln in lineas] + [400])
    ancho = min(ancho, 1600) + 2 * MARGEN
    alto_tit = (alto_linea + 8) if titulo else 0
    alto = 2 * MARGEN + alto_tit + alto_linea * len(lineas)

    img = Image.new("RGB", (ancho, alto), FONDO)
    draw = ImageDraw.Draw(img)
    y = MARGEN
    if titulo:
        draw.rectangle([0, 0, ancho, alto_tit + MARGEN // 2], fill=TITULO_BG)
        draw.text((MARGEN, MARGEN // 2), titulo, font=fuente_tit, fill=(230, 230, 240))
        y = alto_tit + MARGEN
    for ln in lineas:
        draw.text((MARGEN, y), ln, font=fuente, fill=_color_linea(ln))
        y += alto_linea

    destino.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(destino))
    return destino
