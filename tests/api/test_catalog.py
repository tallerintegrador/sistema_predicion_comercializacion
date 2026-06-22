"""Tests del **catálogo de predicciones** — ``GET /catalog`` (solo lectura).

Anclan la **honestidad** del catálogo: responde 200, lista exactamente los tres
dominios implementados, declara la versión del contrato (alineada con el encabezado
del documento) y —lo central— sus salidas declaradas **coinciden con las que la API
realmente produce**. La prueba de consistencia falla si el catálogo afirma un campo
que la API no entrega (o si la API entrega un campo que el catálogo no declara),
cubriendo también los dos campos de metadata recién declarados (``policy`` y
``probability_threshold``).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from spc.api.catalog import CONTRACT_VERSION

DOMINIOS_ESPERADOS = {"sales", "purchases", "inventory"}


def _payloads(historico: list[dict]) -> dict[str, tuple[str, dict]]:
    """Petición válida por dominio (ruta + cuerpo) para verificar consistencia."""
    return {
        "sales": (
            "/sales",
            {"granularity": "day", "horizon": 5, "history": historico},
        ),
        "purchases": (
            "/purchases",
            {
                "history": historico,
                "replenishment_params": [
                    {
                        "store_id": "1",
                        "product_id": "BEVERAGES",
                        "current_stock": 900,
                        "lead_time_days": 3,
                        "target_coverage_days": 7,
                    }
                ],
            },
        ),
        "inventory": (
            "/inventory",
            {
                "history": historico,
                "inventory_status": [
                    {
                        "store_id": "1",
                        "product_id": "BEVERAGES",
                        "current_stock": 300,
                        "lead_time_days": 3,
                    }
                ],
            },
        ),
    }


def _grupos(dominio_cat: dict) -> dict[str, dict]:
    """Indexa los grupos de salida (root/items/metadata) de un dominio del catálogo."""
    return {g["group"]: g for g in dominio_cat["outputs"]}


def test_catalog_responde_200(client):
    """El endpoint de solo lectura responde 200 sin depender del motor."""
    r = client.get("/catalog")
    assert r.status_code == 200, r.text


def test_catalog_lista_exactamente_los_tres_dominios(client):
    """Lista exactamente los tres dominios implementados, ni más ni menos."""
    cat = client.get("/catalog").json()
    dominios = {d["domain"] for d in cat["domains"]}
    assert dominios == DOMINIOS_ESPERADOS


def test_catalog_declara_la_version_del_contrato(client):
    """Expone la versión del contrato vigente desde la única constante del código."""
    cat = client.get("/catalog").json()
    assert cat["contract_version"] == CONTRACT_VERSION == "1.0.1"


def test_catalog_version_alineada_con_encabezado_del_doc():
    """La constante del código coincide con el encabezado de docs/contrato_datos.md."""
    doc = Path(__file__).resolve().parents[2] / "docs" / "contrato_datos.md"
    texto = doc.read_text(encoding="utf-8")
    m = re.search(r"Versi[oó]n:\s*`(\d+\.\d+\.\d+)`", texto)
    assert m, "no se encontró la versión en el encabezado del contrato"
    assert m.group(1) == CONTRACT_VERSION


def test_catalog_solo_sales_expone_model(client):
    """Honestidad del campo ``model``: solo SALES lo expone; PURCHASES/INVENTORY no."""
    cat = client.get("/catalog").json()
    has_model = {d["domain"]: d["has_model"] for d in cat["domains"]}
    assert has_model == {"sales": True, "purchases": False, "inventory": False}


def test_catalog_etiqueta_canales_y_modos_con_honestidad(client):
    """JSON/Excel, en línea/lote y ajuste por cliente disponibles hoy (ADR-0013)."""
    cat = client.get("/catalog").json()
    canales = {c["name"]: c["status"] for c in cat["channels"]}
    modos = {m["name"]: m["status"] for m in cat["modes"]}
    assert canales["json"] == "available" and canales["excel"] == "available"
    assert modos["online"] == "available" and modos["batch"] == "available"
    # El ajuste por cliente bajo demanda ya es funcional y validado (opt-in, ADR-0013).
    assert modos["client_adjustment"] == "available"
    desc = next(m["description"] for m in cat["modes"] if m["name"] == "client_adjustment").lower()
    # Honestidad: opt-in, validado vs congelado, "no mejora" se reporta.
    assert "opt-in" in desc and "congelado" in desc


@pytest.mark.parametrize("dominio", sorted(DOMINIOS_ESPERADOS))
def test_catalog_consistente_con_la_api(client, historico_contrato, dominio):
    """Ancla de honestidad: lo declarado en el catálogo == lo que la API entrega.

    Falla si la API produce un campo no declarado (drift) o si el catálogo declara
    como **requerido** un campo que la respuesta real no incluye.
    """
    dom = next(d for d in client.get("/catalog").json()["domains"] if d["domain"] == dominio)
    grupos = _grupos(dom)
    contenedor = grupos["items"]["container"]  # forecast / recommendation / alerts

    ruta, payload = _payloads(historico_contrato)[dominio]
    r = client.post(ruta, json=payload)
    assert r.status_code == 200, r.text
    cuerpo = r.json()

    # --- Nivel raíz: campos escalares + el contenedor de ítems + metadata ---
    nombres_raiz = {f["name"] for f in grupos["root"]["fields"]}
    req_raiz = {f["name"] for f in grupos["root"]["fields"] if f["required"]}
    declarado_top = nombres_raiz | {contenedor, "metadata"}
    actual_top = set(cuerpo.keys())
    assert actual_top <= declarado_top, f"raíz: campos no declarados {actual_top - declarado_top}"
    assert req_raiz <= actual_top, f"raíz: faltan requeridos {req_raiz - actual_top}"
    assert contenedor in cuerpo and "metadata" in cuerpo

    # --- Ítems de la lista ---
    nombres_item = {f["name"] for f in grupos["items"]["fields"]}
    req_item = {f["name"] for f in grupos["items"]["fields"] if f["required"]}
    assert cuerpo[contenedor], "la lista de ítems vino vacía"
    actual_item = set(cuerpo[contenedor][0].keys())
    assert actual_item <= nombres_item, f"ítem: campos no declarados {actual_item - nombres_item}"
    assert req_item <= actual_item, f"ítem: faltan requeridos {req_item - actual_item}"

    # --- Metadata ---
    nombres_meta = {f["name"] for f in grupos["metadata"]["fields"]}
    req_meta = {f["name"] for f in grupos["metadata"]["fields"] if f["required"]}
    actual_meta = set(cuerpo["metadata"].keys())
    assert actual_meta <= nombres_meta, f"metadata: campos no declarados {actual_meta - nombres_meta}"
    assert req_meta <= actual_meta, f"metadata: faltan requeridos {req_meta - actual_meta}"


def test_catalog_cubre_metadata_policy_y_probability_threshold(client, historico_contrato):
    """Los dos campos de metadata recién declarados quedan cubiertos por el catálogo.

    ``purchases.metadata.policy`` es requerido (siempre presente) y
    ``inventory.metadata.probability_threshold`` es opcional (leído del meta); el
    artefacto de prueba expone ``umbral``, así que aquí llega como número real.
    """
    por_dominio = {d["domain"]: d for d in client.get("/catalog").json()["domains"]}

    meta_compras = {f["name"]: f for f in _grupos(por_dominio["purchases"])["metadata"]["fields"]}
    assert "policy" in meta_compras and meta_compras["policy"]["required"]
    ruta, payload = _payloads(historico_contrato)["purchases"]
    assert client.post(ruta, json=payload).json()["metadata"]["policy"] == "coverage_days"

    meta_inv = {f["name"]: f for f in _grupos(por_dominio["inventory"])["metadata"]["fields"]}
    assert "probability_threshold" in meta_inv
    assert not meta_inv["probability_threshold"]["required"]  # opcional (puede ser null)
    ruta, payload = _payloads(historico_contrato)["inventory"]
    valor = client.post(ruta, json=payload).json()["metadata"]["probability_threshold"]
    assert isinstance(valor, (int, float))


def test_catalog_declara_politica_configurable(client):
    """Tras ADR-0010, las constantes de política se documentan como CONFIGURABLES en notes."""
    por_dominio = {d["domain"]: d for d in client.get("/catalog").json()["domains"]}
    notes_compras = " ".join(por_dominio["purchases"]["notes"]).lower()
    notes_inv = " ".join(por_dominio["inventory"]["notes"]).lower()
    # PURCHASES: método + factor configurables, referenciando el ADR.
    assert "configurable" in notes_compras and "adr-0010" in notes_compras
    assert "spc_purchases_safety_method" in notes_compras
    # INVENTORY: constantes + método configurables, referenciando el ADR.
    assert "configurable" in notes_inv and "adr-0010" in notes_inv
    assert "spc_inventory_safety_method" in notes_inv


def test_catalog_coincide_con_openapi(client):
    """Swagger ↔ catálogo: lo que el catálogo declara existe de verdad en el OpenAPI.

    - Cada ``endpoint`` de dominio (``POST /sales`` …) es un path real del OpenAPI.
    - Canal ``excel`` "available" ⇒ existen ``POST /{dominio}/excel`` y ``GET /{dominio}/template``.
    - Modo ``batch`` "available" ⇒ existen los endpoints de consulta de trabajos.
    Así el catálogo no puede prometer un canal/modo que la API no expone.
    """
    cat = client.get("/catalog").json()
    paths = client.get("/openapi.json").json()["paths"]

    for dom in cat["domains"]:
        metodo, ruta = dom["endpoint"].split()
        assert ruta in paths, f"{ruta} declarado en /catalog no está en el OpenAPI"
        assert metodo.lower() in paths[ruta], f"{dom['endpoint']} no figura como método en {ruta}"

    canales = {c["name"]: c["status"] for c in cat["channels"]}
    if canales.get("excel") == "available":
        for dom in cat["domains"]:
            base = dom["endpoint"].split()[1]  # "/sales"
            assert f"{base}/excel" in paths, f"falta el endpoint Excel de {base}"
            assert f"{base}/template" in paths, f"falta la plantilla de {base}"

    modos = {m["name"]: m["status"] for m in cat["modes"]}
    if modos.get("batch") == "available":
        assert "/jobs/{job_id}" in paths
        assert "/jobs/{job_id}/result" in paths
    if modos.get("client_adjustment") == "available":
        # El ajuste por cliente (ADR-0013) expone disparo + estado + resultado + switch.
        assert "/training/sales/excel" in paths
        assert "/training/jobs/{job_id}" in paths
        assert "/training/jobs/{job_id}/result" in paths
        assert "/training/sales/serving" in paths


def _query_options_sales(client) -> dict:
    """Atajo: el bloque ``query_options`` del dominio SALES tal como lo entrega la API."""
    sales = next(d for d in client.get("/catalog").json()["domains"] if d["domain"] == "sales")
    assert "query_options" in sales, "SALES debe exponer query_options"
    return sales["query_options"]


def test_catalog_query_options_solo_en_sales(client):
    """Solo SALES expone ``query_options`` hoy; con ``exclude_none`` los demás lo omiten."""
    por_dominio = {d["domain"]: d for d in client.get("/catalog").json()["domains"]}
    assert "query_options" in por_dominio["sales"]
    assert "query_options" not in por_dominio["purchases"]
    assert "query_options" not in por_dominio["inventory"]


def test_catalog_query_options_granularidades_calzan_con_el_contrato(client):
    """Anti-desync: las granularidades del catálogo == el Literal ``Granularidad`` del contrato."""
    import typing

    from spc.api.schemas.ventas import Granularidad

    qo = _query_options_sales(client)
    nombres = [g["name"] for g in qo["granularities"]]
    assert nombres == list(typing.get_args(Granularidad))
    # Etiqueta en español, no vacía y distinta del valor en inglés (Día/Semana/Mes).
    for g in qo["granularities"]:
        assert g["label"] and g["label"] != g["name"]


def test_catalog_query_options_horizonte_calza_con_las_restricciones(client):
    """Anti-desync: min/max del horizonte == restricciones (gt/le) de ``VentasRequest``."""
    import annotated_types

    from spc.api.schemas.ventas import VentasRequest

    qo = _query_options_sales(client)
    meta = VentasRequest.model_fields["horizon"].metadata
    gt = next((m.gt for m in meta if isinstance(m, annotated_types.Gt)), None)
    le = next((m.le for m in meta if isinstance(m, annotated_types.Le)), None)
    assert gt is not None and le is not None
    assert qo["horizon"]["min"] == int(gt) + 1 == 1
    assert qo["horizon"]["max"] == int(le) == 365
    assert qo["horizon"]["min"] <= qo["horizon"]["default"] <= qo["horizon"]["max"]


def test_catalog_query_options_dimensiones_existen_en_el_contrato(client):
    """Anti-desync: cada dimensión (R2) es una columna real del bloque ``history``."""
    from spc.api.schemas.comunes import HistoricoItem

    qo = _query_options_sales(client)
    columnas = set(HistoricoItem.model_fields)
    nombres = [d["name"] for d in qo["dimensions"]]
    assert nombres, "se esperaba al menos una dimensión de desglose"
    assert set(nombres) <= columnas, f"dimensiones ausentes en history: {set(nombres) - columnas}"
    for d in qo["dimensions"]:
        assert d["label"], "cada dimensión debe traer etiqueta en español"


def test_catalog_query_options_tipologias_coherentes(client):
    """Tipologías (R1) con etiqueta y descripción; si alguna requiere dimensión, hay dimensiones."""
    qo = _query_options_sales(client)
    assert qo["typologies"], "se esperaba al menos una tipología"
    for t in qo["typologies"]:
        assert t["label"] and t["description"]
    if any(t["requires_dimension"] for t in qo["typologies"]):
        assert qo["dimensions"], "una tipología requiere dimensión pero no hay dimensiones disponibles"


def test_catalog_input_tables_presentes_en_los_tres_dominios(client):
    """Cada dominio expone ``input_tables`` con, al menos, la tabla ``history``."""
    for dom in client.get("/catalog").json()["domains"]:
        nombres = {t["name"] for t in dom["input_tables"]}
        assert "history" in nombres, f"{dom['domain']} no expone la tabla history"


@pytest.mark.parametrize(
    "dominio,esperado",
    [
        ("sales", {"history"}),
        ("purchases", {"history", "replenishment_params"}),
        ("inventory", {"history", "inventory_status"}),
    ],
)
def test_catalog_input_tables_calzan_con_los_request(client, dominio, esperado):
    """Anti-desync: las tablas de entrada == los bloques tipo lista de cada request.

    Verifica, columna por columna, que (a) cada columna existe de verdad en el esquema
    nested y (b) no se omite ningún campo OBLIGATORIO; además exige etiqueta en español
    no vacía y distinta del nombre canónico (traducción real, sin tecnicismos).
    """
    from spc.api.schemas.almacen import AlmacenRequest
    from spc.api.schemas.compras import ComprasRequest
    from spc.api.schemas.ventas import VentasRequest

    requests = {"sales": VentasRequest, "purchases": ComprasRequest, "inventory": AlmacenRequest}
    modelo = requests[dominio]

    dom = next(d for d in client.get("/catalog").json()["domains"] if d["domain"] == dominio)
    tablas = {t["name"]: t for t in dom["input_tables"]}
    assert set(tablas) == esperado, f"{dominio}: tablas {set(tablas)} != {esperado}"

    for nombre, tabla in tablas.items():
        # El modelo del ítem es el tipo dentro de ``list[...]`` del campo del request.
        import typing

        item_model = typing.get_args(modelo.model_fields[nombre].annotation)[0]
        campos = item_model.model_fields
        nombres_cat = {c["name"] for c in tabla["columns"]}
        # (a) sin columnas fantasma; (b) sin omitir obligatorios.
        assert nombres_cat <= set(campos), f"{dominio}.{nombre}: columnas inexistentes"
        requeridos = {n for n, i in campos.items() if i.is_required()}
        assert requeridos <= nombres_cat, f"{dominio}.{nombre}: faltan obligatorios {requeridos - nombres_cat}"
        # (c) traducción real: etiqueta en español, no vacía y != nombre canónico.
        for col in tabla["columns"]:
            assert col["label"] and col["label"] != col["name"], f"columna sin traducir: {col}"


def _columna(dom: dict, tabla: str, columna: str) -> dict | None:
    """Devuelve la columna ``columna`` de la tabla ``tabla`` del dominio, o None."""
    t = next((t for t in dom["input_tables"] if t["name"] == tabla), None)
    if t is None:
        return None
    return next((c for c in t["columns"] if c["name"] == columna), None)


def test_catalog_defaults_de_columnas_salen_de_la_politica(client):
    """Los defaults editables (lead time / cobertura) se leen de la política, no son literales.

    Anti-desync: el valor declarado en el catálogo coincide con el accesor de ``spc.config``
    (las variables de entorno de la política, ADR-0010), de modo que si cambia la política,
    cambia el prellenado de la UI con ella.
    """
    from spc.config import inventory_lead_time_default, purchases_target_coverage_days

    por_dominio = {d["domain"]: d for d in client.get("/catalog").json()["domains"]}

    # COMPRAS: lead_time_days y target_coverage_days traen default desde la política.
    lead = _columna(por_dominio["purchases"], "replenishment_params", "lead_time_days")
    cobertura = _columna(por_dominio["purchases"], "replenishment_params", "target_coverage_days")
    assert lead is not None and cobertura is not None
    assert lead["default"] == inventory_lead_time_default()
    assert cobertura["default"] == purchases_target_coverage_days()

    # ALMACÉN: el lead time (opcional) comparte el mismo default de política.
    lead_inv = _columna(por_dominio["inventory"], "inventory_status", "lead_time_days")
    assert lead_inv is not None and lead_inv["default"] == inventory_lead_time_default()


def test_catalog_defaults_son_columnas_reales_y_no_huerfanos(client):
    """Cada clave de ``_field_defaults`` es una columna real de algún esquema de entrada.

    Evita defaults huérfanos: si el contrato renombra/elimina un campo con default, la prueba
    avisa. Además, los campos sin default lo omiten en la respuesta (``exclude_none``).
    """
    from spc.api.catalog import _field_defaults
    from spc.api.schemas.almacen import EstadoInventarioItem
    from spc.api.schemas.comunes import HistoricoItem
    from spc.api.schemas.compras import ParametroReposicion

    columnas_contrato = (
        set(HistoricoItem.model_fields)
        | set(ParametroReposicion.model_fields)
        | set(EstadoInventarioItem.model_fields)
    )
    claves = set(_field_defaults())
    assert claves, "se esperaba al menos un default editable"
    assert claves <= columnas_contrato, f"defaults huérfanos: {claves - columnas_contrato}"

    # Un campo sin default (p. ej. current_stock) no incluye la clave 'default' en la respuesta.
    por_dominio = {d["domain"]: d for d in client.get("/catalog").json()["domains"]}
    stock = _columna(por_dominio["purchases"], "replenishment_params", "current_stock")
    assert stock is not None and "default" not in stock


def test_catalog_pending_solo_lista_el_cuantil_model_adjacent(client):
    """`pending_policy` ya no lista constantes de política (resueltas); solo el P75 pendiente.

    PURCHASES no tiene pendientes; INVENTORY lista el cuantil de demanda alta (P75) como
    item model-adjacent que la metadata del artefacto aún no expone.
    """
    por_dominio = {d["domain"]: d for d in client.get("/catalog").json()["domains"]}
    assert por_dominio["purchases"]["pending_policy"] == []
    pend_inv = " ".join(por_dominio["inventory"]["pending_policy"]).lower()
    assert "p75" in pend_inv and "model-adjacent" in pend_inv
