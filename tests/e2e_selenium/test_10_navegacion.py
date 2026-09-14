"""Flujo 10 — Recorrido del administrador por todas las secciones y «Acerca del sistema».

Comprueba que ninguna sección queda en blanco ni deja errores en la consola del navegador.
"""

from __future__ import annotations

import ayudas as ay
from ayudas import ADMIN_ID, ADMIN_PASS


def test_recorrido_por_todas_las_secciones(contexto: dict) -> None:
    nav, srv, log = contexto["nav"], contexto["srv"], contexto["log"]

    ay.sesion_admin(nav, srv.web, ADMIN_ID, ADMIN_PASS)
    secciones = ay.secciones_visibles(nav)
    log.paso(f"El administrador ve todas las secciones: {secciones}")
    assert {"home", "sales", "purchases", "inventory", "users", "about"} <= set(secciones)

    for seccion in secciones:
        ay.ir_a_seccion(nav, seccion)
        ay.esperar(nav, ay.tid("sidebar-nav"))
        cuerpo = nav.find_element("tag name", "main").text
        assert cuerpo.strip(), f"La sección «{seccion}» quedó en blanco"
        log.paso(f"Sección «{seccion}» carga contenido ({len(cuerpo)} caracteres)")

    ay.ir_a_seccion(nav, "about")
    acerca = ay.esperar(nav, ay.tid("pagina-acerca")).text
    log.paso("«Acerca del sistema» explica cómo funciona y su exactitud")
    assert "scikit-learn" in acerca or "modelo" in acerca.lower()

    errores = [e for e in nav.get_log("browser") if e.get("level") == "SEVERE"]
    # Los 4xx esperados de los flujos de error también quedan en consola: se descartan.
    reales = [e for e in errores if "Failed to load resource" not in e.get("message", "")]
    log.paso(f"Consola del navegador sin errores de la aplicación ({len(reales)} severos)")
    assert not reales, reales
