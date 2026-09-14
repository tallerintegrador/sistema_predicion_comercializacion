"""Flujo 11 — Errores de carga: el sistema los explica sin romperse.

Dos casos desde la interfaz: un archivo con extensión no admitida (lo rechaza el propio
frontend) y un ``.xlsx`` corrupto (lo rechaza el backend con un error controlado que la app
muestra en el panel de error, sin pantalla en blanco).
"""

from __future__ import annotations

import ayudas as ay
from ayudas import ADMIN_ID, ADMIN_PASS


def test_archivo_no_admitido_y_excel_corrupto(contexto: dict, excel_corrupto, tmp_path) -> None:
    nav, srv, log = contexto["nav"], contexto["srv"], contexto["log"]

    ay.sesion_admin(nav, srv.web, ADMIN_ID, ADMIN_PASS)
    ay.ir_a_seccion(nav, "sales")
    ay.esperar(nav, ay.tid("btn-subir"))

    # --- Extensión no admitida ---
    texto = tmp_path / "datos.txt"
    texto.write_text("no es una plantilla", encoding="utf-8")
    ay.subir_archivo(nav, texto)
    aviso = ay.esperar(nav, ay.tid("aviso-carga")).text
    log.paso(f"Archivo .txt rechazado por la interfaz: «{aviso}»")
    assert ".xlsx" in aviso

    # --- Excel corrupto ---
    ay.subir_archivo(nav, excel_corrupto)
    panel = ay.esperar(nav, ay.tid("error-panel"), t=60).text
    log.paso(f"Excel corrupto: error controlado del servidor · {panel.splitlines()[0]}")
    assert panel.strip(), "El panel de error llegó vacío"
    assert "500" not in panel, f"El error debería ser controlado, no 500: {panel}"

    ay.esperar(nav, ay.tid("sidebar-nav"))
    log.paso("La aplicación sigue operativa tras los errores (sin pantalla en blanco)")
