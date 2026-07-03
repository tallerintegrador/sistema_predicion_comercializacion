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
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any

import pandas as pd
from fastapi import APIRouter, Depends, Query, HTTPException, File, UploadFile
from fastapi.responses import FileResponse

from spc.api.dependencies import obtener_client_id, obtener_corpus_opcional
from spc.api.schemas.catalogo_v3 import (
    RespuestaModulo,
    ReporteConsulta,
    DetalleTecnico,
    FilaComparacion,
    BloqueAnalisisTendencia,
    PuntoSerie,
    RespuestaCatalogo,
    ConsultaInfo,
    SolicitudAnalisisModulo,
)
from spc.catalogo.config import obtener_catalogo, obtener_modulo
from spc.catalogo.motor_catalogo import ejecutar_consulta
from spc.catalogo.plantillas import generar_plantilla_excel, generar_plantilla_json
from spc.service.errores import SolicitudInvalida
from spc.utils.logging import get_logger

log = get_logger("api.catalogo_v3")

router = APIRouter(prefix="/v3", tags=["Catálogo"])

ClientIdDep = Annotated[str, Depends(obtener_client_id)]


# ==============================================================================
# GET /v3/catalogo — Lista de 30 consultas
# ==============================================================================
@router.get("/catalogo", summary="Catálogo completo de 30 consultas predefinidas")
def listar_catalogo() -> RespuestaCatalogo:
    """Lista todas las 30 consultas disponibles (informativo, no entrena)."""
    catalogo = obtener_catalogo()
    consultas: list[ConsultaInfo] = []

    for modulo_config in catalogo.values():
        for consulta in modulo_config.consultas.values():
            consultas.append(
                ConsultaInfo(
                    id=consulta.id,
                    modulo=consulta.modulo,
                    tipo=consulta.tipo,
                    pregunta=consulta.pregunta,
                    descripcion=consulta.descripcion,
                )
            )

    return RespuestaCatalogo(
        total_consultas=len(consultas),
        consultas=sorted(consultas, key=lambda c: (c.modulo, c.id)),
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
def _reporte_degradado(consulta: Any, modulo: str, mensaje: str) -> ReporteConsulta:
    """Reporte de respaldo cuando una consulta falla de forma inesperada.

    Garantiza que el fallo de UNA consulta no tumbe el módulo completo (nunca un 500):
    devuelve un reporte válido, vacío y con un aviso claro en lenguaje de negocio.
    """
    metrica = {"regresion": "wape", "clasificacion": "pr_auc", "clustering": "silhouette"}.get(
        consulta.tipo, "wape"
    )
    return ReporteConsulta(
        consulta_id=consulta.id,
        modulo=modulo,
        tipo=consulta.tipo,
        pregunta=consulta.pregunta,
        descripcion=consulta.descripcion,
        unidad="",
        resultado={"predicciones": []},
        advertencia=f"No se pudo completar este análisis: {mensaje}",
        detalle_tecnico=DetalleTecnico(
            modelo_ganador="—",
            metrica=metrica,
            valor_metrica=0.0,
            tabla_comparacion=[],
            fecha_entrenamiento=datetime.utcnow(),
        ),
    )


# Magnitud principal y columna de fecha por módulo (para la línea de tendencia).
_TENDENCIA_POR_MODULO = {
    "ventas": ("fecha", "unidades_vendidas", "unidades"),
    "compras": ("fecha_orden", "cantidad_pedida", "unidades"),
    "almacen": ("fecha", "demanda_dia", "unidades"),
}


def _calcular_tendencia(modulo: str, df: pd.DataFrame) -> BloqueAnalisisTendencia:
    """Serie temporal del total diario de la magnitud principal + pronóstico simple y honesto.

    Método: tendencia lineal (mínimos cuadrados) sobre el total diario, con un factor de
    estacionalidad SEMANAL (día de la semana). Es la ÚNICA sección con línea de tiempo, y se
    etiqueta como referencial.
    """
    import numpy as np

    col_fecha, magnitud, unidad = _TENDENCIA_POR_MODULO.get(modulo, (None, None, ""))
    base = BloqueAnalisisTendencia(unidad=unidad, metodo="Tendencia lineal + estacionalidad semanal (referencial)")
    if not col_fecha or col_fecha not in df.columns or magnitud not in df.columns:
        return base

    try:
        tmp = df[[col_fecha, magnitud]].copy()
        tmp[col_fecha] = pd.to_datetime(tmp[col_fecha], errors="coerce")
        tmp[magnitud] = pd.to_numeric(tmp[magnitud], errors="coerce")
        tmp = tmp.dropna()
        if tmp.empty:
            return base

        serie = tmp.groupby(col_fecha)[magnitud].sum().sort_index()
        fechas = serie.index
        y = serie.to_numpy(dtype="float64")
        n = len(y)
        base.historico = [PuntoSerie(fecha=str(f.date()), valor=round(float(v), 2)) for f, v in zip(fechas, y)]

        if n < 8:  # muy corto para pronosticar con honestidad
            return base

        x = np.arange(n)
        coef = np.polyfit(x, y, 1)  # tendencia lineal
        dow = fechas.dayofweek.to_numpy()
        media = y.mean() or 1.0
        factor = {d: (y[dow == d].mean() / media if (dow == d).any() else 1.0) for d in range(7)}

        horizonte = 14
        ult = fechas[-1]
        pron = []
        for i in range(1, horizonte + 1):
            f = ult + pd.Timedelta(days=i)
            base_val = float(np.polyval(coef, n - 1 + i))
            val = max(0.0, base_val * factor.get(int(f.dayofweek), 1.0))
            pron.append(PuntoSerie(fecha=str(f.date()), valor=round(val, 2)))
        base.pronostico = pron
        return base
    except Exception as e:
        log.warning(f"Tendencia {modulo}: {e}")
        return base


def _ejecutar_analisis_interno(modulo: str, df: pd.DataFrame) -> RespuestaModulo:
    """Ejecuta las 10 consultas sobre un DataFrame.

    Auxiliar compartido por POST /v3/{modulo} y GET /v3/{modulo}/demo. Cada consulta se
    ejecuta de forma aislada: si una falla, se degrada con aviso y las demás continúan.
    """
    modulo_config = obtener_modulo(modulo)

    # Ejecutar las 10 consultas en orden
    reportes: list[ReporteConsulta] = []
    por_tipo = modulo_config.consultas_por_tipo()

    # Orden: regresión, clasificación, clustering
    for consulta in por_tipo["regresion"] + por_tipo["clasificacion"] + por_tipo["clustering"]:
        try:
            log.info(f"  Ejecutando {consulta.id}: {consulta.pregunta}")
            resultado = ejecutar_consulta(consulta.id, df)

            # Convertir a ReporteConsulta
            reporte = ReporteConsulta(
                consulta_id=resultado.consulta_id,
                modulo=modulo,
                tipo=resultado.tipo,
                pregunta=resultado.pregunta,
                descripcion=consulta.descripcion,
                unidad=resultado.unidad,
                resultado={
                    "predicciones": resultado.predicciones,  # Filas con predicciones/alertas/segmentos
                    "unidad": resultado.unidad,
                    **resultado.meta,  # ejes (clustering), clases (multiclase), etc.
                },
                advertencia=resultado.advertencia,
                detalle_tecnico=DetalleTecnico(
                    modelo_ganador=resultado.modelo_ganador,
                    metrica=resultado.metrica_ganador,
                    valor_metrica=resultado.valor_metrica,
                    tabla_comparacion=[
                        FilaComparacion(
                            modelo=fila.modelo,
                            metrica=fila.metrica,
                            valor=fila.valor,
                            ganador=fila.ganador,
                        )
                        for fila in resultado.tabla_comparacion
                    ],
                    fecha_entrenamiento=resultado.fecha_entrenamiento,
                    nota_tecnica=resultado.nota_tecnica,
                ),
            )
            reportes.append(reporte)

        except Exception as e:
            # Aislamiento por consulta: nunca convertimos un fallo puntual en 500 del módulo.
            log.error(f"Error ejecutando {consulta.id}: {e}", exc_info=True)
            reportes.append(_reporte_degradado(consulta, modulo, str(e)))

    # Bloque análisis/tendencia (serie de tiempo real: histórico + pronóstico referencial)
    analisis_tendencia = _calcular_tendencia(modulo, df)

    respuesta = RespuestaModulo(
        modulo=modulo,
        reportes=reportes,
        analisis_tendencia=analisis_tendencia,
        fecha_ejecución=datetime.utcnow(),
    )

    log.info(f"Análisis de {modulo} completado: {len(reportes)} reportes")
    return respuesta


# ==============================================================================
# POST /v3/{modulo} — Ejecutar 10 consultas automáticamente (JSON)
# ==============================================================================
@router.post("/{modulo}", summary="Ejecutar análisis (JSON)")
def analizar_modulo(
    modulo: str,
    solicitud: SolicitudAnalisisModulo,
    client_id: ClientIdDep,
) -> RespuestaModulo:
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

    # Ejecutar análisis
    return _ejecutar_analisis_interno(modulo, df)


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

    return mejor_df.dropna(how="all").to_dict("records")


@router.post("/{modulo}/archivo", summary="Procesar Excel o JSON")
async def analizar_desde_archivo(
    modulo: str,
    file: UploadFile,
    client_id: ClientIdDep,
) -> RespuestaModulo:
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

    # 1) Leer el archivo → filas
    try:
        if nombre.endswith(".xlsx") or nombre.endswith(".xls"):
            rows = _leer_excel_datos(contenido, modulo_config)
        elif nombre.endswith(".json"):
            data = json.loads(contenido.decode("utf-8"))
            rows = data if isinstance(data, list) else data.get("rows", [])
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

    return _ejecutar_analisis_interno(modulo, df)


# ==============================================================================
# GET /v3/{modulo}/demo — Análisis con datos de demostración
# ==============================================================================
@router.get("/{modulo}/demo", summary="Ejecuta análisis con datos de ejemplo")
def demo_analisis(modulo: str, client_id: ClientIdDep) -> RespuestaModulo:
    """Ejecuta el análisis v3 con datos sintéticos de demostración para ver cómo funciona."""
    import numpy as np

    # Validar módulo
    modulo_config = obtener_modulo(modulo)
    if not modulo_config:
        raise HTTPException(status_code=400, detail=f"Módulo inexistente: {modulo}")

    # Generar datos sintéticos según el módulo
    n_filas = 200 if modulo == "ventas" else 100 if modulo == "compras" else 150
    filas_demo = []

    if modulo == "ventas":
        for i in range(n_filas):
            filas_demo.append({
                "fecha": str((pd.Timestamp("2025-01-01") + pd.Timedelta(days=i % 60)).date()),
                "id_tienda": f"T{(i % 2) + 1}",
                "sku": f"SKU{(i % 5) + 1}",
                "categoria": ["Bebidas", "Abarrotes", "Lacteos"][i % 3],
                "unidades_vendidas": float(np.random.poisson(100) + np.random.randn() * 10),
                "precio_unitario": float(np.random.uniform(50, 200)),
                "ingreso": float(np.random.uniform(5000, 20000)),
                "en_promocion": int(np.random.randint(0, 2)),
                "descuento_pct": float(np.random.uniform(0, 30)),
                "metodo_pago": ["MP1", "MP2"][i % 2],
                "canal_venta": ["Online", "Tienda"][i % 2],
                "es_fin_de_semana": int(i % 7 >= 5),
                "dias_a_proximo_feriado": int(np.random.randint(1, 50)),
            })
    elif modulo == "compras":
        for i in range(n_filas):
            filas_demo.append({
                "fecha_orden": str((pd.Timestamp("2025-01-01") + pd.Timedelta(days=i % 60)).date()),
                "id_proveedor": f"P{(i % 5) + 1}",
                "sku": f"SKU{(i % 3) + 1}",
                "categoria": ["Cat1", "Cat2"][i % 2],
                "cantidad_pedida": float(np.random.randint(10, 100)),
                "precio_unitario_compra": float(np.random.uniform(50, 150)),
                "costo_total": float(np.random.uniform(1000, 10000)),
                "lead_time_dias": int(np.random.randint(1, 30)),
                "cantidad_recibida": float(np.random.randint(10, 100)),
                "cumplimiento": float(np.random.rand()),
                "metodo_pago": ["MP1", "MP2"][i % 2],
                "descuento_volumen": float(np.random.uniform(0, 0.2)),
            })
    elif modulo == "almacen":
        for i in range(n_filas):
            filas_demo.append({
                "fecha": str((pd.Timestamp("2025-01-01") + pd.Timedelta(days=i % 60)).date()),
                "id_tienda": f"T{(i % 2) + 1}",
                "sku": f"SKU{(i % 4) + 1}",
                "categoria": ["Cat1", "Cat2", "Cat3"][i % 3],
                "stock_actual": float(np.random.randint(10, 500)),
                "stock_minimo": float(np.random.randint(5, 50)),
                "stock_maximo": float(np.random.randint(100, 1000)),
                "demanda_dia": float(np.random.poisson(50)),
                "demanda_diaria_promedio": float(np.random.uniform(30, 150)),
                "dias_de_cobertura": float(np.random.uniform(1, 30)),
                "rotacion": float(np.random.uniform(0.1, 5.0)),
                "tiempo_reposicion_dias": int(np.random.randint(1, 15)),
                "zona_almacen": f"Z{(i % 3) + 1}",
            })

    # Convertir a DataFrame
    df_demo = pd.DataFrame(filas_demo)

    # Ejecutar análisis
    return _ejecutar_analisis_interno(modulo, df_demo)
