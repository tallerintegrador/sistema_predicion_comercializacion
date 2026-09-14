# Pruebas End to End con Selenium

Recorren la aplicación **completa** en un Chrome real (Selenium WebDriver): frontend React,
API FastAPI y base de datos. La suite se levanta sola — no hay que arrancar nada a mano.

## Ejecutar

```bash
venv/Scripts/python -m pytest tests/e2e_selenium -m selenium -v
```

Opciones:

| Opción        | Efecto                                                        |
|---------------|---------------------------------------------------------------|
| `--sin-video` | No graba el video (deja capturas y logs). Corrida más rápida.  |
| `--headless`  | Chrome sin ventana (implica `--sin-video`); útil en servidores. |

Requisitos: Google Chrome instalado (Selenium Manager descarga el driver), `npm` en el PATH
y `ffmpeg` si se quiere el video. Dependencias Python: `pip install -e ".[e2e]"`.

La suite está marcada como `selenium` y **no** corre en la batería normal
(`pytest` la excluye con `-m 'not selenium'`), porque abre un navegador y levanta servidores.

## Qué levanta cada corrida

- **Backend**: `uvicorn spc.api.main:app` en un puerto libre, con control de acceso activo y
  una base **SQLite temporal**; sin Supabase y sin SMTP (el enlace de restablecimiento queda
  en el log, que es de donde lo toma el flujo 9). Nunca toca la base real.
- **Frontend**: `npm run dev` (Vite) en otro puerto libre, apuntando al backend temporal.

## Evidencia

Se escribe en `final/evidencias/pruebas/e2e_selenium/`:

- `e2e_selenium.mp4` — video del recorrido + paneles finales con el resumen y los logs.
- `capturas/` — una captura por paso (se limpian al iniciar cada corrida).
- `logs/` — `backend.log`, `frontend.log`, `navegador.log` (consola), `pasos.log`.
- `informe_e2e_selenium.md` y `pytest_e2e_selenium.txt`.

## Estructura

- `conftest.py` — servidores, navegador, bitácora de pasos, grabación e informe.
- `ayudas.py` — acciones sobre la interfaz (esperas explícitas, sin `sleep` fijos) y
  constantes compartidas.
- `test_01…test_11` — un flujo por archivo; el orden importa (el 8 usa el usuario creado en
  el 7, el 6 el análisis del 3).

Los selectores se anclan a `data-testid` para no romperse con cambios de estilo o de texto.
El documento entregable se genera con `python scripts/gen_pruebas_e2e.py`.
