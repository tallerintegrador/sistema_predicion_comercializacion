"""Flujo 1 — Ingreso al sistema y cierre de sesión (navegador real).

Recorre la pantalla de login como lo haría una persona: credenciales incorrectas (mensaje
genérico, sin revelar si el usuario existe), credenciales correctas del administrador de
demostración y cierre de sesión.
"""

from __future__ import annotations

import ayudas as ay
from ayudas import ADMIN_ID, ADMIN_PASS


def test_login_y_logout(contexto: dict) -> None:
    nav, srv, log = contexto["nav"], contexto["srv"], contexto["log"]

    ay.abrir(nav, srv.web)
    log.paso("Se abre la aplicación en el navegador: pantalla de ingreso")
    assert ay.en_login(nav), "La aplicación debería abrir en la pantalla de ingreso"

    # --- Credenciales incorrectas ---
    ay.login(nav, srv.web, ADMIN_ID, "clave-incorrecta")
    error = ay.esperar(nav, ay.tid("login-error")).text
    log.paso(f"Ingreso con contraseña incorrecta rechazado: «{error}»")
    assert "incorrect" in error.lower(), error
    assert ay.en_login(nav), "Tras el rechazo se debe seguir en el login"

    # --- Credenciales correctas ---
    ay.login(nav, srv.web, ADMIN_ID, ADMIN_PASS)
    ay.esperar(nav, ay.tid("sidebar-nav"))
    log.paso(f"Ingreso correcto como administrador {ADMIN_ID}: se muestra el panel")
    assert ay.usuario_actual(nav) == ADMIN_ID

    # El panel de administrador muestra a qué servidor está hablando el frontend:
    # confirma que la corrida usa la API temporal de la prueba y no otra instancia.
    badge = nav.find_element("xpath", "//*[contains(text(), 'Servidor:')]").text
    log.paso(f"El panel apunta al backend de la prueba: {badge}")
    assert srv.api in badge, f"El frontend habla con otro backend: {badge}"

    # --- Cierre de sesión ---
    ay.logout(nav)
    log.paso("Cierre de sesión: vuelve la pantalla de ingreso")
    assert ay.en_login(nav)

    # Evidencia del lado del servidor: el login quedó registrado en el log de uvicorn.
    srv.esperar_en_log("POST /auth/login")
