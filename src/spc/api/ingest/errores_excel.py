"""Errores del canal Excel compartidos por la API.

Vive aparte del lector para que quien solo necesita la excepción (el manejador de
errores y el canal Excel agnóstico ``/auto``) no arrastre el lector completo.
"""

from __future__ import annotations


class ArchivoDemasiadoGrande(Exception):
    """El ``.xlsx`` subido supera el tope de tamaño (``SPC_EXCEL_MAX_BYTES``).

    La capa API lo traduce a HTTP 413. Es un límite plano de protección.
    """
