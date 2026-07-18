# Documento de Pruebas End to End (E2E)

**SPC — Sistema de Predicción y Comercialización**

- **Tipo de Prueba:** End to End / Integración de la API
- **Marco:** pytest + FastAPI TestClient (base SQLite temporal por test)
- **Total de Flujos:** 10
- **Universidad Privada Antenor Orrego — Proyecto de Taller Integrador I**

## Índice de Flujos E2E

| N° | Flujo | Archivo | Estado |
|----|-------|---------|--------|
| 1 | Autenticación y control de acceso por roles | tests/api/test_auth.py | **PASA** |
| 2 | Restablecer contraseña por correo | tests/api/test_reset_password.py | **PASA** |
| 3 | Análisis 3×3 por dominio (ventas/compras/almacén) | tests/api/test_dominios_3x3.py | **PASA** |
| 4 | Reentrenar → predecir con modelo guardado → elegir versión | tests/api/test_dominios_3x3.py | **PASA** |
| 5 | Onboarding de datos: esquema, plantilla y carga por Excel (v2) | tests/api/test_dominios_3x3.py | **PASA** |
| 6 | Catálogo v3: ejecutar 10 consultas por módulo (JSON) | tests/api/test_catalogo_v3.py | **PASA** |
| 7 | Catálogo v3: carga por archivo (Excel/JSON) y demo | tests/api/test_ingesta_v3_archivo.py | **PASA** |
| 8 | Historial de análisis y detalle | tests/api/test_historial_v3.py | **PASA** |
| 9 | Validación de tipos a nivel de API (v3) | tests/api/test_validacion_v3_api.py | **PASA** |
| 10 | Perfil de negocio, CORS y forma uniforme de error | tests/api/test_auth.py (perfil) / test_cors.py / test_errores_api.py | **PASA** |

## Flujo 1 — Autenticación y control de acceso por roles

- **Archivo de prueba:** tests/api/test_auth.py
- **Endpoints recorridos:** POST /auth/login, GET /auth/me, GET /permissions, POST/PATCH/DELETE /roles, POST/PATCH /users
- **Precondición:** Auth activado (SPC_AUTH_ENABLED=1) con base temporal sembrada (admins 256317/256370).

**Pasos:**

1. Login con credenciales válidas → token firmado.
2. Acceso a endpoint protegido sin token → 401.
3. Acceso con rol sin permiso → 403.
4. Alta de rol/usuario por administrador; edición y desactivación.

- **Verificación:** Token válido abre /auth/me; 401 sin token; 403 sin permiso; el rol admin está protegido.
- **Resultado:** **PASA**
- **Comando:** `venv/Scripts/python -m pytest tests/api/ -v`
- **Evidencia:** `final/evidencias/pruebas/e2e/`

## Flujo 2 — Restablecer contraseña por correo

- **Archivo de prueba:** tests/api/test_reset_password.py
- **Endpoints recorridos:** POST /auth/forgot, POST /auth/reset
- **Precondición:** Cuenta con correo; SMTP en modo desarrollo (enlace al log).

**Pasos:**

1. Solicitar enlace con correo válido → respuesta genérica.
2. Solicitar con correo inexistente → misma respuesta (no revela existencia).
3. Fijar nueva contraseña con token válido; reutilizar el token → 400.

- **Verificación:** Respuesta genérica siempre; token de un solo uso; contraseña nueva funciona.
- **Resultado:** **PASA**
- **Comando:** `venv/Scripts/python -m pytest tests/api/ -v`
- **Evidencia:** `final/evidencias/pruebas/e2e/`

## Flujo 3 — Análisis 3×3 por dominio (ventas/compras/almacén)

- **Archivo de prueba:** tests/api/test_dominios_3x3.py
- **Endpoints recorridos:** POST /v2/{dominio}, GET /v2/{dominio}/demo
- **Precondición:** Dataset del dominio con historia suficiente (generador sintético).

**Pasos:**

1. Enviar rows del dominio con horizonte.
2. Recibir los tres bloques: regresión, clasificación, clustering.
3. Ejecutar la demo integrada.

- **Verificación:** Los tres modelos presentes; regresión con modelo_ganador; clustering k≥2; alertas por serie.
- **Resultado:** **PASA**
- **Comando:** `venv/Scripts/python -m pytest tests/api/ -v`
- **Evidencia:** `final/evidencias/pruebas/e2e/`

## Flujo 4 — Reentrenar → predecir con modelo guardado → elegir versión

- **Archivo de prueba:** tests/api/test_dominios_3x3.py
- **Endpoints recorridos:** POST /v2/{dominio}/entrenar, POST /v2/{dominio}/predecir, GET /v2/{dominio}/modelos, POST /v2/{dominio}/modelos/{id}/servir
- **Precondición:** Corpus acumulado (idempotente) de dos lotes con fechas distintas.

**Pasos:**

1. Acumular corpus en dos lotes + un reenvío duplicado.
2. Entrenar (v1): versiona regresión y clasificación; corpus_filas = total sin duplicar.
3. Predecir: sirve el modelo adoptado (sin reentrenar) y reporta su versión.
4. Entrenar otra vez (v2) y elegir explícitamente servir la v1.

- **Verificación:** servido_desde='modelo_guardado'; solo una versión is_serving por tarea; /predecir respeta la versión elegida; auditoría en tabla predictions.
- **Resultado:** **PASA**
- **Comando:** `venv/Scripts/python -m pytest tests/api/ -v`
- **Evidencia:** `final/evidencias/pruebas/e2e/`

## Flujo 5 — Onboarding de datos: esquema, plantilla y carga por Excel (v2)

- **Archivo de prueba:** tests/api/test_dominios_3x3.py
- **Endpoints recorridos:** GET /v2/{dominio}/esquema, GET /v2/{dominio}/plantilla, POST /v2/{dominio}/excel
- **Precondición:** Ninguna (la plantilla y el esquema son informativos).

**Pasos:**

1. Consultar el diccionario de variables del dominio.
2. Descargar la plantilla (JSON y Excel).
3. Subir un Excel con historia suficiente → corre el análisis.
4. Subir un Excel corrupto → error controlado.

- **Verificación:** Esquema con columnas y roles; plantilla Excel es .xlsx (firma PK); Excel válido devuelve los 3 bloques; Excel malo → 400.
- **Resultado:** **PASA**
- **Comando:** `venv/Scripts/python -m pytest tests/api/ -v`
- **Evidencia:** `final/evidencias/pruebas/e2e/`

## Flujo 6 — Catálogo v3: ejecutar 10 consultas por módulo (JSON)

- **Archivo de prueba:** tests/api/test_catalogo_v3.py
- **Endpoints recorridos:** GET /v3/catalogo, POST /v3/{modulo}, GET /v3/{modulo}/plantilla
- **Precondición:** Datos del módulo conformes al esquema (columnas y tipos).

**Pasos:**

1. Listar el catálogo de 30 consultas.
2. Enviar datos JSON al módulo → 10 reportes + tendencia.
3. Enviar datos con columnas/tipos inválidos → error de validación.

- **Verificación:** 10 reportes con métrica y modelo ganador; validación de tipos rechaza antes del motor; el fallo de una consulta no tumba el módulo (degradación).
- **Resultado:** **PASA**
- **Comando:** `venv/Scripts/python -m pytest tests/api/ -v`
- **Evidencia:** `final/evidencias/pruebas/e2e/`

## Flujo 7 — Catálogo v3: carga por archivo (Excel/JSON) y demo

- **Archivo de prueba:** tests/api/test_ingesta_v3_archivo.py
- **Endpoints recorridos:** POST /v3/{modulo}/archivo, GET /v3/{modulo}/demo
- **Precondición:** Archivo con las columnas del módulo (o inválido para los casos de error).

**Pasos:**

1. Subir un Excel válido → corre el análisis (10 reportes).
2. Subir el JSON equivalente → mismo resultado.
3. Casos de error: módulo inexistente (400), formato no soportado (400), vacío (422), columnas faltantes (422), Excel corrupto (422).
4. Ejecutar la demo v3 de cada módulo.

- **Verificación:** Excel y JSON válidos devuelven module + reports + dataset_info; los errores dan el código correcto sin 500; la demo trae reportes y tendencia.
- **Resultado:** **PASA**
- **Comando:** `venv/Scripts/python -m pytest tests/api/ -v`
- **Evidencia:** `final/evidencias/pruebas/e2e/`

## Flujo 8 — Historial de análisis y detalle

- **Archivo de prueba:** tests/api/test_historial_v3.py
- **Endpoints recorridos:** GET /v3/{modulo}/historial, GET /v3/historial/{prediction_id}
- **Precondición:** Al menos un análisis ejecutado (persistencia conectada).

**Pasos:**

1. Ejecutar análisis para poblar el historial.
2. Listar el historial del módulo (más recientes primero).
3. Abrir el detalle de una predicción; probar un id inexistente/ajeno.

- **Verificación:** El historial lista las ejecuciones con métricas resumidas; el detalle trae los valores predichos; id inexistente/ajeno → 404.
- **Resultado:** **PASA**
- **Comando:** `venv/Scripts/python -m pytest tests/api/ -v`
- **Evidencia:** `final/evidencias/pruebas/e2e/`

## Flujo 9 — Validación de tipos a nivel de API (v3)

- **Archivo de prueba:** tests/api/test_validacion_v3_api.py
- **Endpoints recorridos:** POST /v3/{modulo}
- **Precondición:** Datos con una columna de tipo incorrecto.

**Pasos:**

1. Enviar datos con fecha no parseable o número con texto.
2. Recibir el rechazo con detalle por columna/fila.

- **Verificación:** 422 con el detalle de la columna/fila inválida; no hay coerción silenciosa.
- **Resultado:** **PASA**
- **Comando:** `venv/Scripts/python -m pytest tests/api/ -v`
- **Evidencia:** `final/evidencias/pruebas/e2e/`

## Flujo 10 — Perfil de negocio, CORS y forma uniforme de error

- **Archivo de prueba:** tests/api/test_auth.py (perfil) / test_cors.py / test_errores_api.py
- **Endpoints recorridos:** GET/PUT /profile, GET /profile/options, GET /health, GET /openapi.json
- **Precondición:** App levantada; origen del frontend permitido.

**Pasos:**

1. Leer y guardar el perfil de onboarding; opciones válidas del formulario.
2. Preflight CORS desde el origen del frontend.
3. Provocar un error y verificar el sobre uniforme; consultar /health y Swagger.

- **Verificación:** Perfil persistido; cabeceras CORS correctas; /health ok; error con forma uniforme; OpenAPI disponible.
- **Resultado:** **PASA**
- **Comando:** `venv/Scripts/python -m pytest tests/api/ -v`
- **Evidencia:** `final/evidencias/pruebas/e2e/`
