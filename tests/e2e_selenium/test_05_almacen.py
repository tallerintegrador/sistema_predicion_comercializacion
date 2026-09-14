"""Flujo 5 — Módulo Almacén: reposición y clasificación ABC desde el Excel del negocio."""

from __future__ import annotations

import ayudas as ay
from ayudas import ADMIN_ID, ADMIN_PASS, DATOS


def test_analisis_de_almacen_desde_excel(contexto: dict) -> None:
    nav, srv, log = contexto["nav"], contexto["srv"], contexto["log"]

    ay.sesion_admin(nav, srv.web, ADMIN_ID, ADMIN_PASS)
    ay.ir_a_seccion(nav, "inventory")
    ay.esperar(nav, ay.tid("btn-subir"))
    log.paso("Módulo Almacén abierto")

    archivo = DATOS / "almacen.xlsx"
    tarjetas = ay.analizar(nav, archivo)
    log.paso(f"Se sube {archivo.name} y llegan {len(tarjetas)} análisis de almacén")
    assert len(tarjetas) == 10

    # El módulo agrupa por tipo: al menos una segmentación (clasificación ABC) debe existir.
    segmentos = [t for t in tarjetas if t.get_attribute("data-tipo") == "clustering"]
    log.paso(f"Se generaron {len(segmentos)} segmentaciones (agrupación de productos)")
    assert segmentos, "El módulo Almacén debe incluir al menos una segmentación"

    srv.esperar_en_log("POST /v3/almacen/archivo")
