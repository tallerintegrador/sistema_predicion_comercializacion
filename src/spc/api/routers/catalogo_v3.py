"""Router de la API v3 del catálogo: endpoint principal.

Expone:
- POST /v3/{modulo} → ejecuta automáticamente 10 consultas, devuelve 10 reportes + tendencia
- GET /v3/catalogo → lista informativa de 30 consultas
- GET /v3/{modulo}/plantilla → plantilla Excel única por módulo
- GET /v3/{modulo}/demo → datos de ejemplo para demostración
"""

from __future__ import annotations

import io
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any

import pandas as pd
from fastapi import APIRouter, Depends, Query, HTTPException, File, UploadFile
from fastapi.responses import FileResponse

from spc.api.dependencies import (
    obtener_client_id,
    obtener_corpus_opcional,
    obtener_modelos_opcional,
)
from spc.api.schemas.catalogo_v3 import (
    ModuleResponse,
    QueryReport,
    ColumnUsed,
    RegressionSummary,
    DatasetInfo,
    TechnicalDetail,
    ComparisonRow,
    TrendAnalysis,
    TrendSummary,
    TrendBreakdown,
    SeriesPoint,
    CatalogResponse,
    QueryInfo,
    ModuleAnalysisRequest,
    PrediccionHistorialItem,
    HistorialResponse,
    PrediccionDetalle,
)
from spc.catalogo.config import (
    obtener_catalogo,
    obtener_descripciones,
    obtener_etiquetas,
    obtener_modulo,
)
from spc.catalogo.motor_catalogo import ejecutar_consulta, calcular_tendencia
from spc.catalogo.plantillas import generar_plantilla_excel, generar_plantilla_json
from spc.service.errores import SolicitudInvalida
from spc.service.repositorio_modelos import RepositorioModelos
from spc.utils.logging import get_logger

log = get_logger("api.catalogo_v3")

router = APIRouter(prefix="/v3", tags=["Catálogo"])

ClientIdDep = Annotated[str, Depends(obtener_client_id)]
ModelosOpcDep = Annotated[RepositorioModelos | None, Depends(obtener_modelos_opcional)]

# Tope de filas de predicción a guardar por reporte (el historial es un resumen, no un dump).
_MAX_FILAS_HISTORIAL = 500

# El motor usa tipos internos en español; el contrato los expone en inglés (ADR-0028).
_TIPO_EN = {"regresion": "regression", "clasificacion": "classification", "clustering": "clustering"}


# ==============================================================================
# GET /v3/catalogo — Lista de 30 consultas
# ==============================================================================
@router.get("/catalogo", summary="Catálogo completo de 30 consultas predefinidas")
def listar_catalogo() -> CatalogResponse:
    """Lista todas las 30 consultas disponibles (informativo, no entrena)."""
    catalogo = obtener_catalogo()
    consultas: list[QueryInfo] = []

    for modulo_config in catalogo.values():
        for consulta in modulo_config.consultas.values():
            consultas.append(
                QueryInfo(
                    id=consulta.id,
                    module=consulta.modulo,
                    type=_TIPO_EN.get(consulta.tipo, consulta.tipo),
                    question=consulta.pregunta,
                    description=consulta.descripcion,
                )
            )

    return CatalogResponse(
        total_queries=len(consultas),
        queries=sorted(consultas, key=lambda c: (c.module, c.id)),
        column_labels=obtener_etiquetas(),
    )


# ==============================================================================
# GET /v3/{modulo}/plantilla — Plantilla Excel por módulo
# ==============================================================================
@router.get(
    "/{modulo}/plantilla",
    summary="Plantilla para {modulo} (Excel o JSON)",
    responses={200: {"content": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {}}}},
)
def descargar_plantilla(modulo: str, formato: str = "excel") -> FileResponse:
    """Descarga la plantilla del módulo con instrucciones y filas de ejemplo.

    - ``formato=excel`` (por defecto): hoja de instrucciones + hoja de datos de ejemplo.
    - ``formato=json``: objeto ``{"rows": [...]}`` con filas de ejemplo, listo para llenar.
    """
    # Validar módulo
    try:
        obtener_modulo(modulo)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Módulo inexistente: {modulo}. Use ventas, compras o almacen.",
        )

    formato = (formato or "excel").lower()
    try:
        if formato == "json":
            contenido = generar_plantilla_json(modulo)
            with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
                tmp.write(contenido)
                path_temp = tmp.name
            return FileResponse(
                path=path_temp,
                filename=f"plantilla_v3_{modulo}.json",
                media_type="application/json",
            )

        contenido_excel = generar_plantilla_excel(modulo)
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
            tmp.write(contenido_excel)
            path_temp = tmp.name
        return FileResponse(
            path=path_temp,
            filename=f"plantilla_v3_{modulo}.xlsx",
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    except Exception as e:
        log.error(f"Error generando plantilla {modulo} ({formato}): {e}")
        raise HTTPException(status_code=500, detail="Error generando plantilla")


# ==============================================================================
# Función auxiliar: ejecutar análisis completo
# ==============================================================================
def _columnas_usadas(consulta: Any) -> list[ColumnUsed]:
    """Columnas en que se basa la consulta, con rol e interpretación para el popup ⓘ.

    Deriva de la config del catálogo (fuente única): objetivo, columnas_entrada y la
    dimensión de agrupación (cols_serie o entidad_cluster en clustering). Deduplica por
    nombre dando prioridad al objetivo. Etiquetas y descripciones salen del mismo YAML.
    """
    etiquetas = obtener_etiquetas()
    descripciones = obtener_descripciones()

    # (nombre, rol) en orden de prioridad; el primer rol gana en el dedup.
    candidatas: list[tuple[str, str]] = []
    if consulta.objetivo:
        candidatas.append((consulta.objetivo, "objetivo"))
    for col in consulta.columnas_entrada:
        candidatas.append((col, "feature"))
    dimensiones = list(consulta.cols_serie)
    if consulta.entidad_cluster:
        dimensiones.append(consulta.entidad_cluster)
    for col in dimensiones:
        candidatas.append((col, "dimension"))

    columnas: list[ColumnUsed] = []
    vistas: set[str] = set()
    for nombre, rol in candidatas:
        if nombre in vistas:
            continue
        vistas.add(nombre)
        columnas.append(
            ColumnUsed(
                name=nombre,
                label=etiquetas.get(nombre, nombre.replace("_", " ")),
                role=rol,
                description=descripciones.get(nombre, ""),
            )
        )
    return columnas


def _reporte_degradado(consulta: Any, modulo: str, mensaje: str) -> QueryReport:
    """Reporte de respaldo cuando una consulta falla de forma inesperada.

    Garantiza que el fallo de UNA consulta no tumbe el módulo completo (nunca un 500):
    devuelve un reporte válido, vacío y con un aviso claro en lenguaje de negocio.
    """
    metrica = {"regresion": "wape", "clasificacion": "pr_auc", "clustering": "silhouette"}.get(
        consulta.tipo, "wape"
    )
    return QueryReport(
        query_id=consulta.id,
        module=modulo,
        type=_TIPO_EN.get(consulta.tipo, consulta.tipo),
        question=consulta.pregunta,
        description=consulta.descripcion,
        unit="",
        result={"predictions": []},
        warning=f"No se pudo completar este análisis: {mensaje}",
        columns_used=_columnas_usadas(consulta),
        technical_detail=TechnicalDetail(
            winner_model="—",
            metric=metrica,
            metric_value=0.0,
            quality="limitada",
            comparison_table=[],
            trained_at=datetime.now(timezone.utc),
        ),
    )


def _puntos(serie: list[dict[str, Any]]) -> list[SeriesPoint]:
    return [SeriesPoint(date=p["date"], value=p["value"]) for p in serie]


def _tendencia_schema(modulo: str, df: pd.DataFrame) -> TrendAnalysis:
    """Adapta la tendencia calculada por el MOTOR al esquema del contrato (inglés).

    La lógica (tendencia, estacionalidad, resumen, desglose) vive en
    ``spc.catalogo.motor_catalogo``; aquí solo se envuelve en el esquema Pydantic.
    """
    t = calcular_tendencia(modulo, df)
    return TrendAnalysis(
        unit=t.unidad,
        method=t.metodo,
        horizon=t.horizonte,
        history=_puntos(t.historico),
        forecast=_puntos(t.pronostico),
        summary=TrendSummary(**t.resumen) if t.resumen else None,
        breakdowns=[
            TrendBreakdown(label=d["label"], history=_puntos(d["historico"]), forecast=_puntos(d["pronostico"]))
            for d in t.desgloses
        ],
    )


def _ejecutar_analisis_interno(
    modulo: str, df: pd.DataFrame, dataset_info: DatasetInfo | None = None
) -> ModuleResponse:
    """Ejecuta las 10 consultas sobre un DataFrame.

    Auxiliar compartido por POST /v3/{modulo} y GET /v3/{modulo}/demo. Cada consulta se
    ejecuta de forma aislada: si una falla, se degrada con aviso y las demás continúan.
    """
    modulo_config = obtener_modulo(modulo)

    # Ejecutar las 10 consultas en orden
    reportes: list[QueryReport] = []
    por_tipo = modulo_config.consultas_por_tipo()

    # Orden: regresión, clasificación, clustering
    for consulta in por_tipo["regresion"] + por_tipo["clasificacion"] + por_tipo["clustering"]:
        try:
            log.info(f"  Ejecutando {consulta.id}: {consulta.pregunta}")
            resultado = ejecutar_consulta(consulta.id, df)

            # Convertir a QueryReport (contrato en inglés)
            reporte = QueryReport(
                query_id=resultado.consulta_id,
                module=modulo,
                type=_TIPO_EN.get(resultado.tipo, resultado.tipo),
                question=resultado.pregunta,
                description=consulta.descripcion,
                unit=resultado.unidad,
                result={
                    "predictions": resultado.predicciones,  # Filas con predicciones/alertas/segmentos
                    "unit": resultado.unidad,
                    **resultado.meta,  # axes (clustering), classes (multiclase), etc.
                },
                summary=RegressionSummary(**resultado.resumen) if resultado.resumen else None,
                warning=resultado.advertencia,
                columns_used=_columnas_usadas(consulta),
                technical_detail=TechnicalDetail(
                    winner_model=resultado.modelo_ganador,
                    metric=resultado.metrica_ganador,
                    metric_value=resultado.valor_metrica,
                    quality=resultado.calidad,
                    comparison_table=[
                        ComparisonRow(
                            model=fila.modelo,
                            metric=fila.metrica,
                            value=fila.valor,
                            winner=fila.ganador,
                        )
                        for fila in resultado.tabla_comparacion
                    ],
                    trained_at=resultado.fecha_entrenamiento,
                    technical_note=resultado.nota_tecnica,
                ),
            )
            reportes.append(reporte)

        except Exception as e:
            # Aislamiento por consulta: nunca convertimos un fallo puntual en 500 del módulo.
            log.error(f"Error ejecutando {consulta.id}: {e}", exc_info=True)
            reportes.append(_reporte_degradado(consulta, modulo, str(e)))

    # Bloque análisis/tendencia (serie de tiempo real: histórico + pronóstico referencial)
    analisis_tendencia = _tendencia_schema(modulo, df)

    respuesta = ModuleResponse(
        module=modulo,
        reports=reportes,
        trend_analysis=analisis_tendencia,
        dataset_info=dataset_info,
        executed_at=datetime.now(timezone.utc),
    )

    log.info(f"Análisis de {modulo} completado: {len(reportes)} reportes")
    return respuesta


# ==============================================================================
# POST /v3/{modulo} — Ejecutar 10 consultas automáticamente (JSON)
# ==============================================================================
@router.post("/{modulo}", summary="Ejecutar análisis (JSON)")
def analizar_modulo(
    modulo: str,
    solicitud: ModuleAnalysisRequest,
    client_id: ClientIdDep,
    modelos: ModelosOpcDep = None,
) -> ModuleResponse:
    """Ejecuta automáticamente las 10 consultas del módulo.

    Flujo:
    1. Valida que el módulo existe
    2. Convierte rows a DataFrame
    3. Ejecuta las 10 consultas en orden (4 regresión → 3 clasificación → 3 clustering)
    4. Devuelve 10 reportes + bloque análisis/tendencia
    """
    log.info(f"Analizando {modulo} con {len(solicitud.rows)} filas para cliente {client_id}")

    # Validar módulo
    try:
        modulo_config = obtener_modulo(modulo)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Módulo inexistente: {modulo}. Use ventas, compras o almacen.",
        )

    # Convertir rows a DataFrame
    df = pd.DataFrame(solicitud.rows)

    # Validar columnas mínimas
    faltan = set(modulo_config.columnas_todas) - set(df.columns)
    if faltan:
        raise HTTPException(
            status_code=422,
            detail=f"Faltan columnas del módulo {modulo}: {sorted(faltan)}",
        )

    # Ejecutar análisis (con retroalimentación de validación, A8)
    info = _construir_dataset_info(modulo_config, df, len(solicitud.rows))
    respuesta = _ejecutar_analisis_interno(modulo, df, info)
    _auditar_v3(modelos, modulo_config.dominio, client_id, len(df), respuesta)
    return respuesta


def _construir_dataset_info(modulo_config: Any, df: pd.DataFrame, filas_recibidas: int) -> DatasetInfo:
    """Retroalimentación de validación (A8): columnas reconocidas/faltantes y filas descartadas."""
    esperadas = list(modulo_config.columnas_todas)
    presentes = set(df.columns)
    return DatasetInfo(
        recognized_columns=[c for c in esperadas if c in presentes],
        missing_columns=[c for c in esperadas if c not in presentes],
        rows_received=int(filas_recibidas),
        rows_discarded=int(max(0, filas_recibidas - len(df))),
    )


# ==============================================================================
# Historial de predicciones — persistencia (best-effort) y lectura
# ==============================================================================
def _resumen_para_historial(respuesta: ModuleResponse, filas: int) -> tuple[dict, dict]:
    """Construye el ``request``/``response`` resumido que se guarda en la tabla ``predictions``.

    Guarda metadatos + los **valores predichos** de cada reporte (acotados a
    ``_MAX_FILAS_HISTORIAL`` filas), para poder re-ver los resultados sin re-ejecutar el modelo.
    """
    request_resumen = {
        "n_filas": int(filas),
        "columnas": list(respuesta.dataset_info.recognized_columns) if respuesta.dataset_info else [],
    }
    reportes_resumen = []
    for r in respuesta.reports:
        predicciones = (r.result or {}).get("predictions") or []
        reportes_resumen.append(
            {
                "query_id": r.query_id,
                "type": r.type,
                "question": r.question,
                "unit": r.unit,
                "winner_model": r.technical_detail.winner_model if r.technical_detail else None,
                "predictions": predicciones[:_MAX_FILAS_HISTORIAL],
                "n_predictions": len(predicciones),
            }
        )
    response_resumen = {"n_reportes": len(respuesta.reports), "reports": reportes_resumen}
    return request_resumen, response_resumen


def _auditar_v3(
    modelos: RepositorioModelos | None,
    modulo: str,
    client_id: str,
    filas: int,
    respuesta: ModuleResponse,
) -> None:
    """Guarda el análisis en el historial. **Best-effort**: un fallo no rompe la respuesta."""
    if modelos is None:
        return
    try:
        request_resumen, response_resumen = _resumen_para_historial(respuesta, filas)
        modelos.registrar_prediccion(
            tenant_id=client_id,
            domain=modulo,
            model_id=None,  # /v3 entrena al vuelo, no sirve una versión persistida
            horizon=respuesta.trend_analysis.horizon if respuesta.trend_analysis else None,
            request=request_resumen,
            response=response_resumen,
        )
    except Exception as e:  # noqa: BLE001 — auditoría nunca debe tumbar el análisis
        log.warning(f"No se pudo registrar el historial de {modulo}: {e}")


# ==============================================================================
# POST /v3/{modulo}/archivo — Procesar Excel/JSON como archivo
# ==============================================================================
def _leer_excel_datos(contenido: bytes, modulo_config: Any) -> list[dict[str, Any]]:
    """Lee un Excel y devuelve las filas de la hoja de DATOS.

    Robusto: no depende de un índice fijo de hoja. Recorre todas las hojas y elige la que
    tenga MÁS columnas coincidentes con las del módulo (así ignora hojas de instrucciones y
    funciona tanto con la plantilla como con archivos de una sola hoja).
    """
    esperadas = set(modulo_config.columnas_todas)
    xls = pd.ExcelFile(io.BytesIO(contenido))

    mejor_df = None
    mejor_score = -1
    for hoja in xls.sheet_names:
        try:
            df_hoja = xls.parse(hoja)
        except Exception:
            continue
        cols = {str(c).strip() for c in df_hoja.columns}
        score = len(esperadas & cols)
        if score > mejor_score:
            mejor_score, mejor_df = score, df_hoja

    if mejor_df is None or mejor_score == 0:
        raise ValueError(
            "ninguna hoja del Excel contiene las columnas del módulo "
            f"(se esperaban p. ej. {sorted(list(esperadas))[:4]}...)"
        )

    filas_crudas = int(len(mejor_df))
    return mejor_df.dropna(how="all").to_dict("records"), filas_crudas


@router.post("/{modulo}/archivo", summary="Procesar Excel o JSON")
async def analizar_desde_archivo(
    modulo: str,
    file: UploadFile,
    client_id: ClientIdDep,
    modelos: ModelosOpcDep = None,
) -> ModuleResponse:
    """Procesa un archivo Excel o JSON y ejecuta el análisis.

    Acepta:
    - ``.xlsx`` / ``.xls``: detecta automáticamente la hoja de datos por sus encabezados.
    - ``.json``: arreglo de objetos ``[...]`` o ``{"rows": [...]}``.
    """
    log.info(f"Procesando archivo para {modulo} (cliente {client_id})")

    try:
        modulo_config = obtener_modulo(modulo)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Módulo inexistente: {modulo}")

    nombre = (file.filename or "").lower()
    contenido = await file.read()

    # 1) Leer el archivo → filas (+ filas crudas, para reportar descartes)
    try:
        if nombre.endswith(".xlsx") or nombre.endswith(".xls"):
            rows, filas_crudas = _leer_excel_datos(contenido, modulo_config)
        elif nombre.endswith(".json"):
            data = json.loads(contenido.decode("utf-8"))
            rows = data if isinstance(data, list) else data.get("rows", [])
            filas_crudas = len(rows)
        else:
            raise HTTPException(status_code=400, detail="Sube un archivo .xlsx (Excel) o .json.")
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Error leyendo archivo {nombre}: {e}", exc_info=True)
        raise HTTPException(
            status_code=422,
            detail="No se pudo leer el archivo. Verifica que sea un Excel/JSON válido "
            "con las columnas del módulo (puedes usar la plantilla descargable).",
        )

    if not rows:
        raise HTTPException(status_code=422, detail="El archivo no tiene filas de datos.")

    # 2) Validar columnas y ejecutar
    df = pd.DataFrame(rows)
    faltan = set(modulo_config.columnas_todas) - set(df.columns)
    if faltan:
        raise HTTPException(
            status_code=422,
            detail=f"Al archivo le faltan columnas del módulo {modulo}: {sorted(faltan)}",
        )

    info = _construir_dataset_info(modulo_config, df, filas_crudas)
    respuesta = _ejecutar_analisis_interno(modulo, df, info)
    _auditar_v3(modelos, modulo_config.dominio, client_id, len(df), respuesta)
    return respuesta


# ==============================================================================
# GET /v3/{modulo}/historial — Historial de análisis del cliente por categoría
# ==============================================================================
@router.get("/{modulo}/historial", response_model=HistorialResponse, summary="Historial de análisis")
def historial_modulo(
    modulo: str,
    client_id: ClientIdDep,
    modelos: ModelosOpcDep = None,
    limite: int = Query(50, ge=1, le=500, description="Máximo de entradas a devolver"),
) -> HistorialResponse:
    """Lista los análisis pasados del cliente para el módulo (más recientes primero).

    El módulo ``todos`` (o cualquiera fuera de ventas/compras/almacen) devuelve el historial
    de todas las categorías.
    """
    if modelos is None:
        raise HTTPException(status_code=503, detail="El historial no está disponible.")
    dominio = modulo if modulo in ("ventas", "compras", "almacen") else None
    filas = modelos.listar_predicciones(tenant_id=client_id, domain=dominio, limite=limite)
    items = [
        PrediccionHistorialItem(
            id=p.id,
            module=p.domain,
            created_at=p.created_at,
            rows=int((p.request or {}).get("n_filas", 0)),
            reports=int((p.response or {}).get("n_reportes", 0)),
        )
        for p in filas
    ]
    return HistorialResponse(module=dominio, total=len(items), items=items)


# ==============================================================================
# GET /v3/historial/{id} — Detalle de un análisis pasado (valores predichos)
# ==============================================================================
@router.get("/historial/{prediction_id}", response_model=PrediccionDetalle, summary="Detalle de análisis")
def detalle_historial(
    prediction_id: int,
    client_id: ClientIdDep,
    modelos: ModelosOpcDep = None,
) -> PrediccionDetalle:
    """Devuelve una entrada del historial con sus valores predichos, para re-verla."""
    if modelos is None:
        raise HTTPException(status_code=503, detail="El historial no está disponible.")
    p = modelos.obtener_prediccion(prediction_id)
    if p is None or p.tenant_id != client_id:
        # No revelar predicciones de otros clientes: 404 tanto si no existe como si es de otro.
        raise HTTPException(status_code=404, detail="No existe esa entrada de historial.")
    return PrediccionDetalle(
        id=p.id,
        module=p.domain,
        created_at=p.created_at,
        request=p.request,
        response=p.response,
    )


# ==============================================================================
# GET /v3/{modulo}/demo — Análisis con datos de demostración
# ==============================================================================
@router.get("/{modulo}/demo", summary="Ejecuta análisis con datos de ejemplo")
def demo_analisis(modulo: str, client_id: ClientIdDep) -> ModuleResponse:
    """Ejecuta el análisis v3 con datos sintéticos de demostración para ver cómo funciona.

    Usa el **mismo generador sintético** del sistema (``spc.synthetic``) que las plantillas y
    la evaluación offline, en vez de fabricar filas ad-hoc: así el demo respeta exactamente el
    esquema del módulo (una sola fuente de verdad) y muestra señal realista.
    """
    from spc.synthetic import generar_dominio

    # Validar módulo (lanza ValueError si no existe → 400)
    try:
        obtener_modulo(modulo)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Módulo inexistente: {modulo}")

    # Parámetros modestos: suficientes para el split temporal y varias entidades de
    # clustering, pero acotados para que el demo responda rápido.
    params = {
        "ventas": dict(n_tiendas=2, n_productos=8, n_dias=90),
        "compras": dict(n_proveedores=6, n_productos=6, n_ordenes_por_serie=30),
        "almacen": dict(n_tiendas=2, n_productos=8, n_dias=90),
    }[modulo]
    df_demo = generar_dominio(modulo, seed=42, **params)

    return _ejecutar_analisis_interno(modulo, df_demo)
