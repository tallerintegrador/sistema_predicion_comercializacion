"""Flujo 6 — Historial de análisis: los resultados quedan guardados y se pueden reabrir.

Depende de los flujos 3-5 (los análisis que poblaron el historial del usuario administrador).
"""

from __future__ import annotations

import ayudas as ay
from ayudas import ADMIN_ID, ADMIN_PASS


def test_historial_lista_y_reabre_un_analisis(contexto: dict) -> None:
    nav, srv, log = contexto["nav"], contexto["srv"], contexto["log"]

    ay.sesion_admin(nav, srv.web, ADMIN_ID, ADMIN_PASS)
    ay.ir_a_seccion(nav, "sales")
    ay.esperar(nav, ay.tid("historial-v3"))

    filas = ay.esperar_todos(nav, ay.tid("historial-fila"))
    log.paso(f"El historial de Ventas lista {len(filas)} análisis guardados")
    assert filas, "El análisis del flujo 3 debería aparecer en el historial"

    ay.click(nav, ay.tid("historial-ver"))
    detalle = ay.esperar(nav, ay.tid("historial-detalle"), t=60).text
    log.paso("Se reabre un análisis del historial y se ven sus resultados guardados")
    assert detalle.strip(), "El detalle del análisis guardado llegó vacío"

    srv.esperar_en_log("GET /v3/ventas/historial")
