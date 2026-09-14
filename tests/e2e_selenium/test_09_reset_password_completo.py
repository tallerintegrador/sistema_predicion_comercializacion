"""Flujo 9 — Restablecimiento de contraseña de punta a punta.

Solicita el enlace desde el login, lo recupera del **log del backend** (sin SMTP configurado
el enlace se registra en modo desarrollo, que es lo que hace el sistema en la corrida),
abre ``/reset?token=…`` en el navegador, fija una contraseña nueva y entra con ella. Al
final comprueba que el enlace es de un solo uso.
"""

from __future__ import annotations

import re

import ayudas as ay
from selenium.webdriver.common.by import By
from test_07_usuarios_roles import CORREO, USUARIO

NUEVA = "clave-nueva-e2e"
PATRON_ENLACE = re.compile(r"(http://\S+/reset\?token=[\w.\-]+)")


def _ultimo_enlace(log_backend: str) -> str:
    """Extrae del log del backend el último enlace de restablecimiento emitido."""
    enlaces = PATRON_ENLACE.findall(log_backend)
    assert enlaces, "El backend no registró ningún enlace de restablecimiento"
    return enlaces[-1]


def test_restablecer_contrasena_con_el_enlace(contexto: dict) -> None:
    nav, srv, log = contexto["nav"], contexto["srv"], contexto["log"]

    ay.abrir(nav, srv.web)
    if not ay.en_login(nav):
        ay.logout(nav)

    ay.click(nav, ay.tid("login-forgot"))
    ay.escribir(nav, (By.ID, "reset_email"), CORREO)
    ay.click(nav, ay.tid("forgot-submit"))
    ay.esperar(nav, ay.tid("forgot-ok"))
    log.paso(f"Se solicita el enlace de restablecimiento para {CORREO}")

    enlace = _ultimo_enlace(srv.esperar_en_log("/reset?token="))
    log.paso(f"El backend emitió el enlace de un solo uso: {enlace[:60]}…", captura=False)

    nav.get(enlace)
    ay.escribir(nav, (By.ID, "new_password"), NUEVA)
    ay.escribir(nav, (By.ID, "confirm_password"), NUEVA)
    ay.click(nav, ay.tid("reset-submit"))
    ay.esperar(nav, ay.tid("reset-ok"))
    log.paso("Se fija la nueva contraseña desde el enlace del correo")

    # El enlace no sirve dos veces (queda ligado a la contraseña anterior).
    nav.get(enlace)
    ay.escribir(nav, (By.ID, "new_password"), "otra-clave-mas")
    ay.escribir(nav, (By.ID, "confirm_password"), "otra-clave-mas")
    ay.click(nav, ay.tid("reset-submit"))
    aviso = ay.esperar(nav, (By.CSS_SELECTOR, "p[role='alert']")).text
    log.paso(f"Reutilizar el enlace se rechaza: «{aviso[:70]}…»")
    assert not ay.existe(nav, ay.tid("reset-ok")), "El enlace se pudo reutilizar"

    ay.abrir(nav, srv.web)
    ay.login(nav, srv.web, USUARIO, NUEVA)
    ay.esperar(nav, ay.tid("sidebar-nav"))
    log.paso(f"«{USUARIO}» entra con la contraseña nueva")
    assert ay.usuario_actual(nav) == USUARIO
