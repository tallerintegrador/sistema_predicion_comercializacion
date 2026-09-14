"""Flujo 3 — Módulo Ventas: subir el Excel del negocio y obtener los 10 análisis.

Reproduce lo que hace el usuario: entra a Ventas, sube su plantilla llena (Excel real de la
botica de ejemplo) y espera los 10 reportes (predicciones, alertas y segmentos), incluida la
retroalimentación de la carga y el detalle técnico de un reporte.
"""

from __future__ import annotations

import ayudas as ay
from ayudas import ADMIN_ID, ADMIN_PASS, DATOS


def test_analisis_de_ventas_desde_excel(contexto: dict) -> None:
    nav, srv, log = contexto["nav"], contexto["srv"], contexto["log"]

    ay.sesion_admin(nav, srv.web, ADMIN_ID, ADMIN_PASS)
    ay.ir_a_seccion(nav, "sales")
    ay.esperar(nav, ay.tid("btn-subir"))
    log.paso("Módulo Ventas abierto (3 pasos guiados + historial)")

    archivo = DATOS / "ventas.xlsx"
    tarjetas = ay.analizar(nav, archivo)
    log.paso(f"Se sube {archivo.name} y el sistema entrena y devuelve {len(tarjetas)} análisis")
    assert len(tarjetas) == 10, f"Se esperaban 10 reportes, llegaron {len(tarjetas)}"

    validacion = ay.esperar(nav, ay.tid("validacion-carga")).text
    log.paso(f"Retroalimentación de la carga: {validacion.splitlines()[0]}")
    assert "columnas reconocidas" in validacion

    tipos = {t.get_attribute("data-tipo") for t in tarjetas}
    log.paso(f"Los tres tipos de análisis están presentes: {sorted(tipos)}")
    assert tipos == {"regression", "classification", "clustering"}

    detalle = ay.abrir_detalle_tecnico(nav)
    log.paso("Se abre el detalle técnico de un reporte (modelo y métrica)")
    assert detalle.strip(), "El detalle técnico llegó vacío"

    srv.esperar_en_log("POST /v3/ventas/archivo")
