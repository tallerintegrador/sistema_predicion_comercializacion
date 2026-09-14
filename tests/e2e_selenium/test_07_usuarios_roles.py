"""Flujo 7 — Administración: crear un rol con permisos y darle de alta un usuario.

El rol ``e2e_rol`` recibe los tres módulos y la acción de predecir, pero **no** la
administración de usuarios: el flujo 8 comprueba que ese límite se aplica de verdad.
"""

from __future__ import annotations

import ayudas as ay
from ayudas import ADMIN_ID, ADMIN_PASS

ROL = "e2e_rol"
USUARIO = "e2e_test"
PASSWORD = "e2e12345"
CORREO = "e2e.test@ejemplo.com"
PERMISOS = ["module:sales", "module:purchases", "module:inventory", "action:forecast"]


def test_crear_rol_y_usuario(contexto: dict) -> None:
    nav, srv, log = contexto["nav"], contexto["srv"], contexto["log"]

    ay.sesion_admin(nav, srv.web, ADMIN_ID, ADMIN_PASS)
    ay.ir_a_seccion(nav, "users")
    ay.esperar(nav, ay.tid("tabla-roles"))
    log.paso("Sección «Usuarios y permisos» abierta (solo visible para el administrador)")

    # --- Rol ---
    ay.click(nav, ay.tid("abrir-crear-rol"))
    ay.escribir(nav, ay.tid("rol-nombre"), ROL)
    ay.escribir(nav, ay.tid("rol-descripcion"), "Rol de la prueba E2E (sin administración)")
    for permiso in PERMISOS:
        ay.click(nav, ay.tid(f"permiso-{permiso}"))
    ay.click(nav, ay.tid("btn-crear-rol"))
    log.paso(f"Se crea el rol «{ROL}» con {len(PERMISOS)} permisos (sin administrar usuarios)")

    ay.abrir(nav, srv.web, "/users")  # recarga la vista para leer el estado ya persistido
    ay.esperar(nav, ay.tid(f"fila-rol-{ROL}"))
    log.paso(f"El rol «{ROL}» aparece en la tabla de roles")

    # --- Usuario ---
    ay.click(nav, ay.tid("abrir-crear-usuario"))
    ay.escribir(nav, ay.tid("usuario-id"), USUARIO)
    ay.escribir(nav, ay.tid("usuario-password"), PASSWORD)
    ay.escribir(nav, ay.tid("usuario-email"), CORREO)
    ay.elegir(nav, ay.tid("usuario-rol"), texto=ROL)
    ay.click(nav, ay.tid("btn-crear-usuario"))
    log.paso(f"Se crea el usuario «{USUARIO}» con el rol «{ROL}» y correo de contacto")

    ay.abrir(nav, srv.web, "/users")
    fila = ay.esperar(nav, ay.tid(f"fila-usuario-{USUARIO}")).text
    log.paso(f"El usuario aparece en la tabla: {fila.splitlines()[0]} · {CORREO}")
    assert CORREO in fila
    assert "Activo" in fila

    srv.esperar_en_log("POST /roles")
    srv.esperar_en_log("POST /users")
