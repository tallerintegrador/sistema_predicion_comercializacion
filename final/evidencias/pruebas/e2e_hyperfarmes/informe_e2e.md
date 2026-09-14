# Prueba E2E — Exploración continua SPC (Hyperfarmes)

**Fecha:** 2026-07-21
**Objetivo:** Recorrido E2E con grabación de sesión activa desde el segundo 0; recorrer todos los módulos en orden, interacción exhaustiva, cargar el Excel propuesto por módulo, no detenerse ante fallos.

## Entorno
- Frontend: `http://localhost:5173` (Vite, ya en ejecución)
- Backend: `http://localhost:8010` (uvicorn, levantado para la prueba; CORS 5173)
- Datos: `examples/datos_excel_pyme/botica_farmasalud/{ventas,compras,almacen}.xlsx`
- Navegador: Chrome real vía extensión Claude in Chrome (grabación GIF nativa)

## Recorrido ejecutado (en orden del menú)
1. **Login** — admin DEMO `256370` (sembrado en código, contraseña = id). OK.
2. **Inicio** — panel de bienvenida, atajos a los 3 dominios.
3. **Ventas** (`/sales`) — subida `ventas.xlsx` (10041 filas) → 10 análisis. Interacción: filtro Buscar (Analg→Analgésicos), scatter precisión real vs predicho, detalle técnico. Total ≈ 86,178 u / S/ 864,742.
4. **Compras** (`/purchases`) — subida `compras.xlsx` → 10 análisis (cantidad, lead-time, costo, cumplimiento proveedor). Interacción: "Mostrar todo (10)", detalle técnico.
5. **Almacén** (`/inventory`) — subida `almacen.xlsx` → 10 análisis (unidades a pedir, días de cobertura, ABC). Interacción: scatter precisión.
6. **Usuarios y permisos** (`/users`) — listado de roles + usuarios, dropdowns de rol, estados, acciones Editar/Desactivar.
   - **Rol creado:** `e2e_rol` (Ventas + Compras + Almacén + Predecir) — id 11.
   - **Usuario creado:** `e2e_test` con rol `e2e_rol`, activo.
7. **Re-login como `e2e_test`** — onboarding "Botica Farmasalud" (Farmacia/salud, Pequeña, América del Sur, PEN).
   - **RBAC verificado:** sidebar sin "Usuarios y permisos" (rol sin gestión). Corpus propio aislado (historial vacío).
   - Pronóstico generado como nuevo usuario en Ventas (86,178 u / S/ 864,742).
8. **Acerca del sistema** (`/about`) — cómo funciona, exactitud, detalles técnicos (2 motores, 3×3, scikit-learn, validación temporal sin fuga).

## Fallos funcionales de la plataforma
**0.** Todos los módulos cargaron, todas las subidas se procesaron, RBAC correcto, sin pantallas en blanco ni errores.

## Notas técnicas (no fallos de la app)
- La subida de `.xlsx` no se pudo automatizar 100%: la extensión Claude in Chrome sólo sube archivos adjuntados a la sesión, no rutas locales del proyecto. Workaround: Claude hace clic en "Subir mi plantilla" y el usuario selecciona el Excel en el diálogo nativo.
- Las listas de Roles/Usuarios no auto-refrescan tras crear (verificado por API que sí se persistió).

## Evidencia
- `e2e_spc_parte1_login_modulos.gif` — login + Ventas/Compras/Almacén + Usuarios (48 frames)
- `e2e_spc_parte2_rol_usuario_relogin.gif` — crear rol/usuario + re-login e2e_test + pronóstico + Acerca (50 frames)
- `e2e_spc_completo.mp4` — recorrido completo concatenado (~1:55)
