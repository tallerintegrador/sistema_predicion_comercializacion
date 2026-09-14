"""Flujo 8 — Ingreso del usuario creado: onboarding, permisos aplicados y datos aislados.

Comprueba en el navegador que el rol sin ``action:users_manage`` **no ve** la sección de
administración (ni escribiendo la ruta a mano) y que su corpus arranca vacío: el historial
del administrador no se filtra a la cuenta nueva.
"""

from __future__ import annotations

import ayudas as ay
from ayudas import DATOS
from test_07_usuarios_roles import PASSWORD, USUARIO

NEGOCIO = "Botica Farmasalud"


def test_usuario_nuevo_onboarding_permisos_y_corpus_propio(contexto: dict) -> None:
    nav, srv, log = contexto["nav"], contexto["srv"], contexto["log"]

    ay.abrir(nav, srv.web)
    if not ay.en_login(nav):
        ay.logout(nav)
    ay.login(nav, srv.web, USUARIO, PASSWORD)
    log.paso(f"Ingreso como «{USUARIO}» (primer ingreso: pide configurar el negocio)")

    ay.completar_onboarding(nav, NEGOCIO)
    log.paso(f"Onboarding completado para «{NEGOCIO}» (sector, tamaño, región y moneda)")

    secciones = ay.secciones_visibles(nav)
    log.paso(f"Secciones visibles para su rol: {secciones}")
    assert "users" not in secciones, "Un rol sin administración no debe ver «Usuarios y permisos»"
    assert {"sales", "purchases", "inventory"} <= set(secciones)

    # Ruta escrita a mano: la app redirige a una sección permitida (no hay puerta trasera).
    ay.abrir(nav, srv.web, "/users")
    ay.esperar(nav, ay.tid("sidebar-nav"))
    assert not ay.existe(nav, ay.tid("tabla-usuarios")), "La ruta /users quedó accesible sin permiso"
    log.paso("Escribir /users a mano no da acceso: la app redirige a su sección permitida")

    # Corpus propio: el historial de esta cuenta arranca vacío pese a los análisis del admin.
    ay.ir_a_seccion(nav, "sales")
    ay.esperar(nav, ay.tid("historial-v3"))
    assert ay.existe(nav, ay.tid("historial-vacio")), "El historial del administrador se filtró"
    log.paso("El historial de la cuenta nueva está vacío: los datos de cada cliente son suyos")

    tarjetas = ay.analizar(nav, DATOS / "ventas.xlsx")
    log.paso(f"La cuenta nueva genera su propio pronóstico: {len(tarjetas)} análisis")
    assert len(tarjetas) == 10
