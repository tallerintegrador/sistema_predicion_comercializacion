"""Flujo 4 — Módulo Compras: análisis de abastecimiento desde el Excel del negocio.

Mismo recorrido del usuario en Compras: cantidad a pedir, tiempo de entrega, costo y
cumplimiento del proveedor salen de los 10 análisis automáticos del módulo.
"""

from __future__ import annotations

import ayudas as ay
from ayudas import ADMIN_ID, ADMIN_PASS, DATOS


def test_analisis_de_compras_desde_excel(contexto: dict) -> None:
    nav, srv, log = contexto["nav"], contexto["srv"], contexto["log"]

    ay.sesion_admin(nav, srv.web, ADMIN_ID, ADMIN_PASS)
    ay.ir_a_seccion(nav, "purchases")
    ay.esperar(nav, ay.tid("btn-subir"))
    log.paso("Módulo Compras abierto")

    archivo = DATOS / "compras.xlsx"
    tarjetas = ay.analizar(nav, archivo)
    log.paso(f"Se sube {archivo.name} y llegan {len(tarjetas)} análisis de compras")
    assert len(tarjetas) == 10

    preguntas = [t.text.splitlines()[1] for t in tarjetas if len(t.text.splitlines()) > 1]
    log.paso(f"Primera pregunta respondida: «{preguntas[0]}»")
    assert preguntas, "Las tarjetas no muestran la pregunta que responden"

    srv.esperar_en_log("POST /v3/compras/archivo")
