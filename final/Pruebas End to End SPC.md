# Documento de Pruebas End to End (E2E)

**SPC — Sistema de Predicción y Comercialización**

- **Tipo de Prueba:** End to End sobre la aplicación completa (navegador real)
- **Herramienta:** Selenium WebDriver 4 + Chrome, ejecutado con pytest
- **Total de Flujos:** 11
- **Universidad Privada Antenor Orrego — Proyecto de Taller Integrador I**

## Entorno

Selenium WebDriver 4 sobre Google Chrome real (ventana visible, resolución 1600×1000). La propia suite levanta el backend (uvicorn, spc.api.main:app) y el frontend (Vite) en puertos libres; el control de acceso está activo y la persistencia usa una base SQLite temporal por corrida (no toca la base real ni Supabase). Datos: los Excel del negocio de ejemplo examples/datos_excel_pyme/botica_farmasalud/.

Comando: `venv/Scripts/python -m pytest tests/e2e_selenium -m selenium -v`

## Índice de Flujos E2E

| N° | Flujo | Archivo | Estado |
|----|-------|---------|--------|
| 1 | Ingreso al sistema y cierre de sesión | tests/e2e_selenium/test_01_login.py | **PASA** |
| 2 | Solicitud de restablecimiento de contraseña | tests/e2e_selenium/test_02_recuperar_password.py | **PASA** |
| 3 | Ventas: subir el Excel del negocio y obtener los 10 análisis | tests/e2e_selenium/test_03_ventas.py | **PASA** |
| 4 | Compras: análisis de abastecimiento desde el Excel | tests/e2e_selenium/test_04_compras.py | **PASA** |
| 5 | Almacén: reposición y clasificación ABC desde el Excel | tests/e2e_selenium/test_05_almacen.py | **PASA** |
| 6 | Historial: los análisis quedan guardados y se pueden reabrir | tests/e2e_selenium/test_06_historial.py | **PASA** |
| 7 | Administración: crear un rol con permisos y un usuario | tests/e2e_selenium/test_07_usuarios_roles.py | **PASA** |
| 8 | Usuario nuevo: onboarding, permisos aplicados y datos aislados | tests/e2e_selenium/test_08_rbac_usuario_nuevo.py | **PASA** |
| 9 | Restablecer la contraseña de punta a punta con el enlace | tests/e2e_selenium/test_09_reset_password_completo.py | **PASA** |
| 10 | Recorrido por todas las secciones y «Acerca del sistema» | tests/e2e_selenium/test_10_navegacion.py | **PASA** |
| 11 | Errores de carga explicados, sin caídas | tests/e2e_selenium/test_11_errores_carga.py | **PASA** |

## Flujo 1 — Ingreso al sistema y cierre de sesión

- **Archivo de prueba:** tests/e2e_selenium/test_01_login.py
- **Pantallas recorridas:** Login → Panel principal → Login
- **Precondición:** Aplicación abierta en el navegador; cuentas de demostración sembradas.

**Pasos:**

1. Abrir la aplicación: se muestra la pantalla de ingreso.
2. Ingresar con contraseña incorrecta.
3. Ingresar con las credenciales del administrador (256370).
4. Verificar a qué servidor apunta el panel y cerrar sesión.

- **Comprobaciones:** El intento fallido muestra un mensaje genérico y no deja pasar; el ingreso correcto abre el panel con el usuario en la barra lateral; el cierre de sesión vuelve al login; el log del backend registra POST /auth/login.
- **Resultado:** **PASA**

![Flujo 1](../final/evidencias/pruebas/e2e_selenium/capturas/003_ingreso_correcto_como_administrador_256370_se_muestra_el_pan.png)

*Figura 1. Ingreso al sistema y cierre de sesión (captura de la corrida).*

## Flujo 2 — Solicitud de restablecimiento de contraseña

- **Archivo de prueba:** tests/e2e_selenium/test_02_recuperar_password.py
- **Pantallas recorridas:** Login → ¿Olvidaste tu contraseña?
- **Precondición:** Sin sesión iniciada.

**Pasos:**

1. Abrir «¿Olvidaste tu contraseña?».
2. Enviar un correo que no existe en el sistema.
3. Leer la respuesta y volver al login.

- **Comprobaciones:** La respuesta es genérica («si la cuenta existe…»): no revela si el correo está registrado; el backend registra la solicitud (POST /auth/forgot).
- **Resultado:** **PASA**

![Flujo 2](../final/evidencias/pruebas/e2e_selenium/capturas/007_correo_inexistente_respuesta_gen_rica_si_la_cuenta_existe_te.png)

*Figura 2. Solicitud de restablecimiento de contraseña (captura de la corrida).*

## Flujo 3 — Ventas: subir el Excel del negocio y obtener los 10 análisis

- **Archivo de prueba:** tests/e2e_selenium/test_03_ventas.py
- **Pantallas recorridas:** Panel → Ventas (3 pasos guiados)
- **Precondición:** Sesión de administrador; archivo ventas.xlsx del negocio de ejemplo.

**Pasos:**

1. Entrar al módulo Ventas.
2. Subir ventas.xlsx en el Paso 3 (el navegador adjunta el archivo real).
3. Esperar a que el sistema entrene y devuelva los resultados.
4. Abrir el detalle técnico de un reporte.

- **Comprobaciones:** Llegan 10 reportes con los tres tipos (predicción, alerta y segmento); la carga informa las columnas reconocidas; el detalle técnico muestra modelo y métrica; el backend registra POST /v3/ventas/archivo.
- **Resultado:** **PASA**

![Flujo 3](../final/evidencias/pruebas/e2e_selenium/capturas/011_se_sube_ventas_xlsx_y_el_sistema_entrena_y_devuelve_10_an_li.png)

*Figura 3. Ventas: subir el Excel del negocio y obtener los 10 análisis (captura de la corrida).*

## Flujo 4 — Compras: análisis de abastecimiento desde el Excel

- **Archivo de prueba:** tests/e2e_selenium/test_04_compras.py
- **Pantallas recorridas:** Panel → Compras
- **Precondición:** Sesión de administrador; archivo compras.xlsx.

**Pasos:**

1. Entrar al módulo Compras.
2. Subir compras.xlsx.
3. Revisar las preguntas que responde cada tarjeta.

- **Comprobaciones:** Se generan los 10 análisis del módulo (cantidad a pedir, tiempo de entrega, costo y cumplimiento del proveedor) y cada tarjeta indica la pregunta que responde.
- **Resultado:** **PASA**

![Flujo 4](../final/evidencias/pruebas/e2e_selenium/capturas/016_se_sube_compras_xlsx_y_llegan_10_an_lisis_de_compras.png)

*Figura 4. Compras: análisis de abastecimiento desde el Excel (captura de la corrida).*

## Flujo 5 — Almacén: reposición y clasificación ABC desde el Excel

- **Archivo de prueba:** tests/e2e_selenium/test_05_almacen.py
- **Pantallas recorridas:** Panel → Almacén
- **Precondición:** Sesión de administrador; archivo almacen.xlsx.

**Pasos:**

1. Entrar al módulo Almacén.
2. Subir almacen.xlsx.
3. Comprobar que hay segmentaciones entre los resultados.

- **Comprobaciones:** Se generan los 10 análisis, incluida al menos una segmentación (clasificación ABC / agrupación de productos); el backend registra POST /v3/almacen/archivo.
- **Resultado:** **PASA**

![Flujo 5](../final/evidencias/pruebas/e2e_selenium/capturas/019_se_sube_almacen_xlsx_y_llegan_10_an_lisis_de_almac_n.png)

*Figura 5. Almacén: reposición y clasificación ABC desde el Excel (captura de la corrida).*

## Flujo 6 — Historial: los análisis quedan guardados y se pueden reabrir

- **Archivo de prueba:** tests/e2e_selenium/test_06_historial.py
- **Pantallas recorridas:** Ventas → Paso 4 (Historial de análisis)
- **Precondición:** Haber ejecutado los análisis de los flujos 3 a 5.

**Pasos:**

1. Volver al módulo Ventas.
2. Revisar la tabla del historial.
3. Pulsar «Ver resultados» de un análisis anterior.

- **Comprobaciones:** El historial lista los análisis con fecha, filas y número de reportes; al abrirlo se muestran los valores predichos guardados (GET /v3/ventas/historial).
- **Resultado:** **PASA**

![Flujo 6](../final/evidencias/pruebas/e2e_selenium/capturas/022_se_reabre_un_an_lisis_del_historial_y_se_ven_sus_resultados.png)

*Figura 6. Historial: los análisis quedan guardados y se pueden reabrir (captura de la corrida).*

## Flujo 7 — Administración: crear un rol con permisos y un usuario

- **Archivo de prueba:** tests/e2e_selenium/test_07_usuarios_roles.py
- **Pantallas recorridas:** Panel → Usuarios y permisos
- **Precondición:** Sesión de administrador (único rol con la acción de administrar).

**Pasos:**

1. Entrar a «Usuarios y permisos».
2. Crear el rol e2e_rol con los tres módulos y la acción de predecir.
3. Crear el usuario e2e_test con ese rol y un correo de contacto.
4. Comprobar las tablas de roles y usuarios.

- **Comprobaciones:** El rol y el usuario quedan persistidos y aparecen en las tablas; el usuario figura como Activo y con su correo; el backend registra POST /roles y POST /users.
- **Resultado:** **PASA**

![Flujo 7](../final/evidencias/pruebas/e2e_selenium/capturas/027_el_usuario_aparece_en_la_tabla_e2e_test_e2e_test_ejemplo_com.png)

*Figura 7. Administración: crear un rol con permisos y un usuario (captura de la corrida).*

## Flujo 8 — Usuario nuevo: onboarding, permisos aplicados y datos aislados

- **Archivo de prueba:** tests/e2e_selenium/test_08_rbac_usuario_nuevo.py
- **Pantallas recorridas:** Login → Onboarding → Panel (menú recortado) → Ventas
- **Precondición:** El usuario e2e_test creado en el flujo 7.

**Pasos:**

1. Ingresar como e2e_test (primer ingreso).
2. Completar el onboarding del negocio (nombre, sector, tamaño, región y moneda).
3. Revisar el menú y escribir a mano la ruta /users.
4. Abrir Ventas, revisar el historial y generar su propio pronóstico.

- **Comprobaciones:** El menú no muestra «Usuarios y permisos» y la ruta escrita a mano redirige (el permiso se aplica de verdad); el historial de la cuenta nueva arranca vacío — los datos del administrador no se filtran — y su análisis devuelve los 10 reportes.
- **Resultado:** **PASA**

![Flujo 8](../final/evidencias/pruebas/e2e_selenium/capturas/030_secciones_visibles_para_su_rol_home_sales_purchases_inventor.png)

*Figura 8. Usuario nuevo: onboarding, permisos aplicados y datos aislados (captura de la corrida).*

## Flujo 9 — Restablecer la contraseña de punta a punta con el enlace

- **Archivo de prueba:** tests/e2e_selenium/test_09_reset_password_completo.py
- **Pantallas recorridas:** Login → ¿Olvidaste tu contraseña? → /reset?token=… → Login
- **Precondición:** Cuenta con correo (e2e_test); SMTP en modo desarrollo (enlace al log).

**Pasos:**

1. Solicitar el enlace desde el login con el correo de la cuenta.
2. Tomar el enlace emitido por el servidor y abrirlo en el navegador.
3. Fijar la contraseña nueva y confirmarla.
4. Reutilizar el mismo enlace y volver a ingresar con la contraseña nueva.

- **Comprobaciones:** El enlace permite fijar la contraseña una sola vez: el segundo intento se rechaza; la cuenta entra con la contraseña nueva.
- **Resultado:** **PASA**

![Flujo 9](../final/evidencias/pruebas/e2e_selenium/capturas/036_se_fija_la_nueva_contrase_a_desde_el_enlace_del_correo.png)

*Figura 9. Restablecer la contraseña de punta a punta con el enlace (captura de la corrida).*

## Flujo 10 — Recorrido por todas las secciones y «Acerca del sistema»

- **Archivo de prueba:** tests/e2e_selenium/test_10_navegacion.py
- **Pantallas recorridas:** Inicio, Ventas, Compras, Almacén, Usuarios, Acerca del sistema
- **Precondición:** Sesión de administrador.

**Pasos:**

1. Recorrer una por una las secciones del menú.
2. Comprobar que cada sección carga contenido.
3. Abrir «Acerca del sistema».
4. Revisar la consola del navegador.

- **Comprobaciones:** Ninguna sección queda en blanco; «Acerca del sistema» explica el funcionamiento y la exactitud; la consola no acumula errores de la aplicación.
- **Resultado:** **PASA**

![Flujo 10](../final/evidencias/pruebas/e2e_selenium/capturas/039_el_administrador_ve_todas_las_secciones_home_sales_purchases.png)

*Figura 10. Recorrido por todas las secciones y «Acerca del sistema» (captura de la corrida).*

## Flujo 11 — Errores de carga explicados, sin caídas

- **Archivo de prueba:** tests/e2e_selenium/test_11_errores_carga.py
- **Pantallas recorridas:** Ventas → Paso 3 (subida de archivo)
- **Precondición:** Sesión de administrador; un .txt y un .xlsx corrupto.

**Pasos:**

1. Subir un archivo .txt (extensión no admitida).
2. Subir un .xlsx corrupto.
3. Seguir usando la aplicación.

- **Comprobaciones:** El .txt lo rechaza la interfaz con un aviso claro; el Excel corrupto devuelve un error controlado (422, no 500) que se muestra en el panel de error; la aplicación sigue operativa, sin pantalla en blanco.
- **Resultado:** **PASA**

![Flujo 11](../final/evidencias/pruebas/e2e_selenium/capturas/049_excel_corrupto_error_controlado_del_servidor_http_error.png)

*Figura 11. Errores de carga explicados, sin caídas (captura de la corrida).*

## Evidencia de la corrida

- `final/evidencias/pruebas/e2e_selenium/e2e_selenium.mp4` — video del recorrido completo en el navegador, con los logs del backend y del frontend al final.
- `final/evidencias/pruebas/e2e_selenium/capturas/` — una captura por paso.
- `final/evidencias/pruebas/e2e_selenium/logs/` — backend (uvicorn), frontend (Vite), consola del navegador y bitácora de pasos.
- `final/evidencias/pruebas/e2e_selenium/pytest_e2e_selenium.txt` — salida de pytest.
