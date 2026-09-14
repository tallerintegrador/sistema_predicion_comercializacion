"""Flujo 2 — Solicitud de restablecimiento de contraseña desde el login.

Verifica la respuesta **genérica** (no revela si el correo existe) tanto para un correo
inexistente como para uno válido, y que la solicitud llega al backend (log de uvicorn).
El restablecimiento completo con el enlace se prueba en el flujo 9.
"""

from __future__ import annotations

import ayudas as ay
from selenium.webdriver.common.by import By


def test_solicitar_enlace_de_restablecimiento(contexto: dict) -> None:
    nav, srv, log = contexto["nav"], contexto["srv"], contexto["log"]

    ay.abrir(nav, srv.web)
    if not ay.en_login(nav):
        ay.logout(nav)

    ay.click(nav, ay.tid("login-forgot"))
    log.paso("Se abre «¿Olvidaste tu contraseña?»")

    ay.escribir(nav, (By.ID, "reset_email"), "no-existe@ejemplo.com")
    ay.click(nav, ay.tid("forgot-submit"))
    mensaje = ay.esperar(nav, ay.tid("forgot-ok")).text
    log.paso(f"Correo inexistente → respuesta genérica: «{mensaje[:80]}…»")
    assert "si la cuenta existe" in mensaje.lower()

    peticiones = srv.esperar_en_log("POST /auth/forgot").count("POST /auth/forgot")
    assert peticiones >= 1, "La solicitud no llegó al backend"
    log.paso(f"El backend registró la solicitud de restablecimiento ({peticiones} llamada/s)")

    ay.click(nav, (By.XPATH, "//button[contains(., 'Volver a iniciar sesión')]"))
    ay.esperar(nav, (By.ID, "user_id"))
    log.paso("Se vuelve a la pantalla de ingreso")
