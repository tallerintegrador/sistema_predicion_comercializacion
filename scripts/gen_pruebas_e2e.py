"""Genera el Documento de Pruebas End to End (E2E) del sistema SPC.

Documenta los flujos que recorren la app completa vía ``TestClient`` de FastAPI con una base
SQLite temporal por test (``tests/api/``): autenticación y control de acceso, análisis 3×3
por dominio, reentrenamiento y servido del modelo guardado, catálogo v3 y sus 10 reportes,
carga por archivo (Excel/JSON), historial y CORS/errores. La lista ``FLUJOS`` es la única
fuente de verdad; emite ``.docx`` + ``.md`` con el estilo de ``_docx_estilo``.

Uso:
    python scripts/gen_pruebas_e2e.py

Salida:
    final/Pruebas End to End SPC.docx
    final/Pruebas End to End SPC.md
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _docx_estilo as est  # noqa: E402

ENTORNO = (
    "FastAPI (crear_app) sobre TestClient de Starlette; base SQLite temporal por test "
    "(aislada, no toca la base real ni models/); datos del generador sintético del sistema "
    "(spc.synthetic); Supabase Storage deshabilitado (artefactos a disco temporal)."
)
COMANDO = "venv/Scripts/python -m pytest tests/api/ -v"

# ================================================================================
# Flujos E2E (única fuente de verdad; nombres de test reales de tests/api/)
# ================================================================================
FLUJOS: list[dict] = [
    {
        "num": 1,
        "archivo": "tests/api/test_auth.py",
        "flujo": "Autenticación y control de acceso por roles",
        "endpoints": "POST /auth/login, GET /auth/me, GET /permissions, POST/PATCH/DELETE /roles, POST/PATCH /users",
        "precondicion": "Auth activado (SPC_AUTH_ENABLED=1) con base temporal sembrada (admins 256317/256370).",
        "pasos": [
            "Login con credenciales válidas → token firmado.",
            "Acceso a endpoint protegido sin token → 401.",
            "Acceso con rol sin permiso → 403.",
            "Alta de rol/usuario por administrador; edición y desactivación.",
        ],
        "verificacion": "Token válido abre /auth/me; 401 sin token; 403 sin permiso; el rol admin está protegido.",
        "resultado": "PASA",
    },
    {
        "num": 2,
        "archivo": "tests/api/test_reset_password.py",
        "flujo": "Restablecer contraseña por correo",
        "endpoints": "POST /auth/forgot, POST /auth/reset",
        "precondicion": "Cuenta con correo; SMTP en modo desarrollo (enlace al log).",
        "pasos": [
            "Solicitar enlace con correo válido → respuesta genérica.",
            "Solicitar con correo inexistente → misma respuesta (no revela existencia).",
            "Fijar nueva contraseña con token válido; reutilizar el token → 400.",
        ],
        "verificacion": "Respuesta genérica siempre; token de un solo uso; contraseña nueva funciona.",
        "resultado": "PASA",
    },
    {
        "num": 3,
        "archivo": "tests/api/test_dominios_3x3.py",
        "flujo": "Análisis 3×3 por dominio (ventas/compras/almacén)",
        "endpoints": "POST /v2/{dominio}, GET /v2/{dominio}/demo",
        "precondicion": "Dataset del dominio con historia suficiente (generador sintético).",
        "pasos": [
            "Enviar rows del dominio con horizonte.",
            "Recibir los tres bloques: regresión, clasificación, clustering.",
            "Ejecutar la demo integrada.",
        ],
        "verificacion": "Los tres modelos presentes; regresión con modelo_ganador; clustering k≥2; alertas por serie.",
        "resultado": "PASA",
    },
    {
        "num": 4,
        "archivo": "tests/api/test_dominios_3x3.py",
        "flujo": "Reentrenar → predecir con modelo guardado → elegir versión",
        "endpoints": "POST /v2/{dominio}/entrenar, POST /v2/{dominio}/predecir, GET /v2/{dominio}/modelos, POST /v2/{dominio}/modelos/{id}/servir",
        "precondicion": "Corpus acumulado (idempotente) de dos lotes con fechas distintas.",
        "pasos": [
            "Acumular corpus en dos lotes + un reenvío duplicado.",
            "Entrenar (v1): versiona regresión y clasificación; corpus_filas = total sin duplicar.",
            "Predecir: sirve el modelo adoptado (sin reentrenar) y reporta su versión.",
            "Entrenar otra vez (v2) y elegir explícitamente servir la v1.",
        ],
        "verificacion": "servido_desde='modelo_guardado'; solo una versión is_serving por tarea; /predecir respeta la versión elegida; auditoría en tabla predictions.",
        "resultado": "PASA",
    },
    {
        "num": 5,
        "archivo": "tests/api/test_dominios_3x3.py",
        "flujo": "Onboarding de datos: esquema, plantilla y carga por Excel (v2)",
        "endpoints": "GET /v2/{dominio}/esquema, GET /v2/{dominio}/plantilla, POST /v2/{dominio}/excel",
        "precondicion": "Ninguna (la plantilla y el esquema son informativos).",
        "pasos": [
            "Consultar el diccionario de variables del dominio.",
            "Descargar la plantilla (JSON y Excel).",
            "Subir un Excel con historia suficiente → corre el análisis.",
            "Subir un Excel corrupto → error controlado.",
        ],
        "verificacion": "Esquema con columnas y roles; plantilla Excel es .xlsx (firma PK); Excel válido devuelve los 3 bloques; Excel malo → 400.",
        "resultado": "PASA",
    },
    {
        "num": 6,
        "archivo": "tests/api/test_catalogo_v3.py",
        "flujo": "Catálogo v3: ejecutar 10 consultas por módulo (JSON)",
        "endpoints": "GET /v3/catalogo, POST /v3/{modulo}, GET /v3/{modulo}/plantilla",
        "precondicion": "Datos del módulo conformes al esquema (columnas y tipos).",
        "pasos": [
            "Listar el catálogo de 30 consultas.",
            "Enviar datos JSON al módulo → 10 reportes + tendencia.",
            "Enviar datos con columnas/tipos inválidos → error de validación.",
        ],
        "verificacion": "10 reportes con métrica y modelo ganador; validación de tipos rechaza antes del motor; el fallo de una consulta no tumba el módulo (degradación).",
        "resultado": "PASA",
    },
    {
        "num": 7,
        "archivo": "tests/api/test_ingesta_v3_archivo.py",
        "flujo": "Catálogo v3: carga por archivo (Excel/JSON) y demo",
        "endpoints": "POST /v3/{modulo}/archivo, GET /v3/{modulo}/demo",
        "precondicion": "Archivo con las columnas del módulo (o inválido para los casos de error).",
        "pasos": [
            "Subir un Excel válido → corre el análisis (10 reportes).",
            "Subir el JSON equivalente → mismo resultado.",
            "Casos de error: módulo inexistente (400), formato no soportado (400), vacío (422), columnas faltantes (422), Excel corrupto (422).",
            "Ejecutar la demo v3 de cada módulo.",
        ],
        "verificacion": "Excel y JSON válidos devuelven module + reports + dataset_info; los errores dan el código correcto sin 500; la demo trae reportes y tendencia.",
        "resultado": "PASA",
    },
    {
        "num": 8,
        "archivo": "tests/api/test_historial_v3.py",
        "flujo": "Historial de análisis y detalle",
        "endpoints": "GET /v3/{modulo}/historial, GET /v3/historial/{prediction_id}",
        "precondicion": "Al menos un análisis ejecutado (persistencia conectada).",
        "pasos": [
            "Ejecutar análisis para poblar el historial.",
            "Listar el historial del módulo (más recientes primero).",
            "Abrir el detalle de una predicción; probar un id inexistente/ajeno.",
        ],
        "verificacion": "El historial lista las ejecuciones con métricas resumidas; el detalle trae los valores predichos; id inexistente/ajeno → 404.",
        "resultado": "PASA",
    },
    {
        "num": 9,
        "archivo": "tests/api/test_validacion_v3_api.py",
        "flujo": "Validación de tipos a nivel de API (v3)",
        "endpoints": "POST /v3/{modulo}",
        "precondicion": "Datos con una columna de tipo incorrecto.",
        "pasos": [
            "Enviar datos con fecha no parseable o número con texto.",
            "Recibir el rechazo con detalle por columna/fila.",
        ],
        "verificacion": "422 con el detalle de la columna/fila inválida; no hay coerción silenciosa.",
        "resultado": "PASA",
    },
    {
        "num": 10,
        "archivo": "tests/api/test_auth.py (perfil) / test_cors.py / test_errores_api.py",
        "flujo": "Perfil de negocio, CORS y forma uniforme de error",
        "endpoints": "GET/PUT /profile, GET /profile/options, GET /health, GET /openapi.json",
        "precondicion": "App levantada; origen del frontend permitido.",
        "pasos": [
            "Leer y guardar el perfil de onboarding; opciones válidas del formulario.",
            "Preflight CORS desde el origen del frontend.",
            "Provocar un error y verificar el sobre uniforme; consultar /health y Swagger.",
        ],
        "verificacion": "Perfil persistido; cabeceras CORS correctas; /health ok; error con forma uniforme; OpenAPI disponible.",
        "resultado": "PASA",
    },
]


def construir_docx(destino: Path) -> None:
    doc = est.nuevo_documento()
    est.portada(
        doc,
        "DOCUMENTO DE PRUEBAS END TO END (E2E)",
        [
            "Tipo de Prueba: End to End / Integración de la API",
            "Marco: pytest + FastAPI TestClient (base SQLite temporal por test)",
            f"Total de Flujos: {len(FLUJOS)}",
        ],
    )
    est.tabla_indice(
        doc,
        "Índice de Flujos E2E",
        ["N°", "Flujo", "Archivo", "Estado"],
        [[f["num"], f["flujo"], f["archivo"], f["resultado"]] for f in FLUJOS],
    )

    for f in FLUJOS:
        tabla = est.nueva_tabla(doc)
        est.fila_titulo(tabla, f"Flujo {f['num']} — {f['flujo']}")
        est.fila_kv(tabla, "Archivo de prueba", f["archivo"])
        est.fila_kv(tabla, "Endpoints recorridos", f["endpoints"])
        est.fila_kv(tabla, "Precondición", f["precondicion"])
        est.fila_seccion(tabla, "PASOS")
        est.fila_kv(tabla, "Procedimiento", est.numerado(f["pasos"]))
        est.fila_seccion(tabla, "VERIFICACIÓN")
        est.fila_kv(tabla, "Aserciones", f["verificacion"])
        est.fila_kv(tabla, "Resultado", f["resultado"], fondo_valor=est.VERDE_OK)
        est.fila_seccion(tabla, "CONFIGURACIÓN")
        est.fila_kv(tabla, "Entorno", ENTORNO)
        est.fila_kv(tabla, "Comando", COMANDO)
        est.fila_kv(tabla, "Evidencia", "Ver final/evidencias/pruebas/e2e/")
        doc.add_paragraph()
        if f["num"] != FLUJOS[-1]["num"]:
            doc.add_page_break()

    doc.save(str(destino))


def construir_md(destino: Path) -> None:
    L: list[str] = [
        "# Documento de Pruebas End to End (E2E)",
        "",
        f"**{est.SISTEMA}**",
        "",
        "- **Tipo de Prueba:** End to End / Integración de la API",
        "- **Marco:** pytest + FastAPI TestClient (base SQLite temporal por test)",
        f"- **Total de Flujos:** {len(FLUJOS)}",
        f"- **{est.UNIVERSIDAD}**",
        "",
        "## Índice de Flujos E2E",
        "",
        "| N° | Flujo | Archivo | Estado |",
        "|----|-------|---------|--------|",
    ]
    for f in FLUJOS:
        L.append(f"| {f['num']} | {f['flujo']} | {f['archivo']} | **{f['resultado']}** |")
    L.append("")
    for f in FLUJOS:
        L.append(f"## Flujo {f['num']} — {f['flujo']}")
        L.append("")
        L.append(f"- **Archivo de prueba:** {f['archivo']}")
        L.append(f"- **Endpoints recorridos:** {f['endpoints']}")
        L.append(f"- **Precondición:** {f['precondicion']}")
        L.append("")
        L.append("**Pasos:**")
        L.append("")
        for i, paso in enumerate(f["pasos"], 1):
            L.append(f"{i}. {paso}")
        L.append("")
        L.append(f"- **Verificación:** {f['verificacion']}")
        L.append(f"- **Resultado:** **{f['resultado']}**")
        L.append(f"- **Comando:** `{COMANDO}`")
        L.append("- **Evidencia:** `final/evidencias/pruebas/e2e/`")
        L.append("")
    destino.write_text("\n".join(L), encoding="utf-8")


def main() -> None:
    final = Path(__file__).resolve().parent.parent / "final"
    construir_docx(final / "Pruebas End to End SPC.docx")
    construir_md(final / "Pruebas End to End SPC.md")
    print(f"OK  ->  {final / 'Pruebas End to End SPC.docx'}")
    print(f"OK  ->  {final / 'Pruebas End to End SPC.md'}")


if __name__ == "__main__":
    main()
