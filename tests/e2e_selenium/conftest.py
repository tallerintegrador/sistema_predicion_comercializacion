"""Infraestructura de las pruebas End to End con Selenium (navegador real).

La suite se levanta **sola**: arranca el backend (uvicorn sobre una base SQLite temporal,
control de acceso activo) y el frontend (Vite) en puertos libres, abre Chrome con Selenium
WebDriver y recorre la aplicación como lo haría una persona.

Evidencia que deja en ``final/evidencias/pruebas/e2e_selenium/``:

- ``e2e_selenium.mp4`` — video de la corrida (captura de pantalla con ffmpeg) al que se le
  anexan al final los fotogramas con el **resumen y los logs** (backend, frontend, bitácora).
- ``capturas/`` — una captura por paso, numerada.
- ``logs/backend.log``, ``logs/frontend.log``, ``logs/navegador.log``, ``logs/pasos.log``.
- ``informe_e2e_selenium.md`` — resumen de la corrida (pasos, resultados, entorno).

Uso:
    venv/Scripts/python -m pytest tests/e2e_selenium -m selenium -v

Opciones:
    --headless      corre Chrome sin ventana (no graba video)
    --sin-video     no graba video (sí deja capturas y logs)
"""

from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import pytest

# Las constantes viven en `ayudas` (nombre único): varios `conftest.py` del repo comparten
# basename y no es fiable importar de "conftest" desde los módulos de prueba.
from ayudas import DATOS, RAIZ  # noqa: E402  (pytest inserta este directorio en sys.path)
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

EVIDENCIA = RAIZ / "final" / "evidencias" / "pruebas" / "e2e_selenium"
CAPTURAS = EVIDENCIA / "capturas"
LOGS = EVIDENCIA / "logs"


# ===========================================================================
# Opciones de línea de comandos
# ===========================================================================
def _opcion(config: pytest.Config, nombre: str) -> bool:
    """Lee una opción de la suite tolerando que no esté registrada.

    Las opciones solo se registran cuando la corrida arranca en este directorio; al recolectar
    toda la batería (`pytest` a secas) este conftest se carga después y no existen.
    """
    return bool(config.getoption(nombre, default=False))


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--headless", action="store_true", help="Chrome sin ventana (sin video).")
    parser.addoption("--sin-video", action="store_true", help="No grabar el video de la corrida.")


# ===========================================================================
# Utilidades de proceso / red
# ===========================================================================
def _puerto_libre() -> int:
    """Reserva un puerto libre del sistema operativo y lo devuelve."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _esperar_http(url: str, timeout: float, proceso: subprocess.Popen, quien: str) -> None:
    """Espera a que ``url`` responda; falla con contexto si el proceso murió antes."""
    limite = time.time() + timeout
    ultimo = ""
    while time.time() < limite:
        if proceso.poll() is not None:
            raise RuntimeError(f"{quien} terminó con código {proceso.returncode} antes de responder")
        try:
            with urllib.request.urlopen(url, timeout=3) as r:
                if r.status < 500:
                    return
        except Exception as exc:  # noqa: BLE001 — reintentar hasta el timeout
            ultimo = str(exc)
        time.sleep(0.5)
    raise RuntimeError(f"{quien} no respondió en {timeout}s ({url}): {ultimo}")


def _volcar_a(proceso: subprocess.Popen, destino: Path) -> None:
    """Vuelca la salida del proceso al archivo, línea a línea y con flush inmediato.

    Escribir directo a un archivo dejaría el log rezagado por el buffer del proceso hijo, y
    las pruebas comprueban el log del servidor mientras la corrida avanza.
    """

    def bombear() -> None:
        with destino.open("w", encoding="utf-8", errors="replace") as f:
            assert proceso.stdout is not None
            for linea in iter(proceso.stdout.readline, b""):
                f.write(linea.decode("utf-8", errors="replace"))
                f.flush()

    threading.Thread(target=bombear, daemon=True, name=f"log-{destino.stem}").start()


def _matar_arbol(proceso: subprocess.Popen | None) -> None:
    """Termina el proceso y sus hijos (npm lanza node; uvicorn puede lanzar workers)."""
    if proceso is None or proceso.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(proceso.pid)],
            capture_output=True,
            check=False,
        )
    else:
        proceso.terminate()
    try:
        proceso.wait(timeout=20)
    except subprocess.TimeoutExpired:
        proceso.kill()


# ===========================================================================
# Servidores (backend + frontend)
# ===========================================================================
@dataclass
class Servidores:
    """Direcciones de los servidores levantados para la corrida."""

    api: str
    web: str
    db: Path
    log_backend: Path
    log_frontend: Path

    def log_api(self) -> str:
        """Contenido actual del log del backend (para aserciones sobre el servidor)."""
        return self.log_backend.read_text(encoding="utf-8", errors="replace")

    def esperar_en_log(self, fragmento: str, t: float = 30) -> str:
        """Espera a que el log del backend contenga el fragmento y lo devuelve completo.

        El volcado del log corre en otro hilo: la línea puede aparecer unos instantes
        después de que el navegador reciba la respuesta.
        """
        limite = time.time() + t
        registro = ""
        while time.time() < limite:
            registro = self.log_api()
            if fragmento in registro:
                return registro
            time.sleep(0.3)
        raise AssertionError(f"El backend nunca registró «{fragmento}»")


@pytest.fixture(scope="session")
def servidores(tmp_path_factory: pytest.TempPathFactory) -> Servidores:
    """Levanta uvicorn + Vite en puertos libres, sobre una base SQLite temporal."""
    for carpeta in (EVIDENCIA, CAPTURAS, LOGS):
        carpeta.mkdir(parents=True, exist_ok=True)

    tmp = tmp_path_factory.mktemp("e2e")
    db = tmp / "spc_e2e.db"
    puerto_api = _puerto_libre()
    puerto_web = _puerto_libre()
    api = f"http://127.0.0.1:{puerto_api}"
    web = f"http://localhost:{puerto_web}"

    log_backend = LOGS / "backend.log"
    log_frontend = LOGS / "frontend.log"

    # --- Backend -----------------------------------------------------------
    # Las variables explícitas ganan al `.env` del repo (python-dotenv carga con
    # override=False): la corrida NUNCA toca Postgres/Supabase ni la base real.
    entorno = os.environ.copy()
    entorno.update(
        {
            "SPC_DATABASE_URL": f"sqlite:///{db.as_posix()}",
            "SPC_DB_PATH": str(db),
            "SPC_PERSIST_ENABLED": "1",
            "SPC_AUTH_ENABLED": "1",
            "SPC_AUTH_SECRET": "e2e-selenium-secreto-de-prueba",
            "SPC_CLIENT_MODELS_DIR": str(tmp / "clientes"),
            "SPC_CORS_ORIGINS": f"{web},http://127.0.0.1:{puerto_web}",
            "SPC_APP_BASE_URL": web,
            "SUPABASE_URL": "",  # artefactos a disco temporal, no al bucket real
            "SUPABASE_KEY": "",
            "SPC_SMTP_HOST": "",  # sin SMTP: el enlace de reset queda en el log (modo dev)
            "PYTHONPATH": str(RAIZ / "src"),
            "PYTHONUNBUFFERED": "1",
        }
    )

    proc_back = subprocess.Popen(
        [sys.executable, "-u", "-m", "uvicorn", "spc.api.main:app", "--host", "127.0.0.1",
         "--port", str(puerto_api), "--log-level", "info"],
        cwd=str(RAIZ),
        env=entorno,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    _volcar_a(proc_back, log_backend)

    # --- Frontend ----------------------------------------------------------
    npm = shutil.which("npm.cmd") or shutil.which("npm")
    if npm is None:
        _matar_arbol(proc_back)
        pytest.skip("npm no está en el PATH: no se puede levantar el frontend")

    entorno_web = os.environ.copy()
    entorno_web.update({"VITE_API_BASE_URL": api, "BROWSER": "none"})
    proc_front = subprocess.Popen(
        [npm, "run", "dev", "--", "--port", str(puerto_web), "--strictPort"],
        cwd=str(RAIZ / "frontend"),
        env=entorno_web,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    _volcar_a(proc_front, log_frontend)

    try:
        _esperar_http(f"{api}/health", 120, proc_back, "El backend (uvicorn)")
        _esperar_http(web, 120, proc_front, "El frontend (Vite)")
    except Exception:
        _matar_arbol(proc_front)
        _matar_arbol(proc_back)
        raise

    yield Servidores(api=api, web=web, db=db, log_backend=log_backend, log_frontend=log_frontend)

    _matar_arbol(proc_front)
    _matar_arbol(proc_back)


# ===========================================================================
# Navegador
# ===========================================================================
@pytest.fixture(scope="session")
def driver(request: pytest.FixtureRequest, servidores: Servidores) -> webdriver.Chrome:
    """Chrome real gobernado por Selenium (una sola ventana para toda la corrida)."""
    opciones = Options()
    if _opcion(request.config, "headless"):
        opciones.add_argument("--headless=new")
    opciones.add_argument("--window-size=1600,1000")
    opciones.add_argument("--lang=es-PE")
    opciones.add_argument("--disable-search-engine-choice-screen")
    opciones.add_argument("--no-first-run")
    opciones.add_argument("--disable-features=Translate,PasswordLeakDetection")
    opciones.add_experimental_option("excludeSwitches", ["enable-automation"])
    opciones.add_experimental_option(
        "prefs",
        {
            "credentials_enable_service": False,
            "profile.password_manager_leak_detection": False,
        },
    )
    # Log de la consola del navegador: evidencia de que la app no lanza errores JS.
    opciones.set_capability("goog:loggingPrefs", {"browser": "ALL"})

    # Sin log del driver: son megas de tráfico WebDriver que no aportan a la evidencia
    # (la trazabilidad de la corrida está en pasos.log, backend.log y las capturas).
    nav = webdriver.Chrome(options=opciones, service=Service())
    nav.implicitly_wait(0)  # las esperas son explícitas (ayudas.py)
    nav.set_page_load_timeout(60)
    if not _opcion(request.config, "headless"):
        nav.maximize_window()

    yield nav

    consola = [
        f"{e.get('level')} {e.get('timestamp')} {e.get('message')}"
        for e in _consola_segura(nav)
    ]
    (LOGS / "navegador.log").write_text("\n".join(consola), encoding="utf-8")
    nav.quit()


def _consola_segura(nav: webdriver.Chrome) -> list[dict]:
    """Lee el log de consola del navegador sin romper si el driver ya no lo expone."""
    try:
        return nav.get_log("browser")
    except Exception:  # noqa: BLE001 — la evidencia de consola es opcional
        return []


# ===========================================================================
# Bitácora de pasos (texto + captura por paso)
# ===========================================================================
@dataclass
class Bitacora:
    """Registra cada paso del recorrido: línea de log + captura numerada."""

    nav: webdriver.Chrome
    pasos: list[str] = field(default_factory=list)
    _n: int = 0

    def paso(self, texto: str, captura: bool = True) -> None:
        """Anota un paso del recorrido y guarda la captura de pantalla correspondiente."""
        self._n += 1
        marca = datetime.now().strftime("%H:%M:%S")
        nombre = ""
        if captura:
            slug = re.sub(r"[^a-z0-9]+", "_", texto.lower())[:60].strip("_")
            nombre = f"{self._n:03d}_{slug}.png"
            try:
                self.nav.save_screenshot(str(CAPTURAS / nombre))
            except Exception:  # noqa: BLE001 — una captura fallida no invalida el paso
                nombre = ""
        linea = f"[{marca}] {self._n:03d} {texto}" + (f"  -> capturas/{nombre}" if nombre else "")
        self.pasos.append(linea)
        print(linea)  # visible en la salida de pytest -v (evidencia en el .txt)
        (LOGS / "pasos.log").write_text("\n".join(self.pasos), encoding="utf-8")


@pytest.fixture(scope="session")
def bitacora(driver: webdriver.Chrome) -> Bitacora:
    """Bitácora compartida por toda la corrida."""
    return Bitacora(nav=driver)


# ===========================================================================
# Grabación en video (ffmpeg) + fotogramas de logs
# ===========================================================================
@dataclass
class Grabador:
    """Captura la pantalla con ffmpeg mientras corre la suite."""

    destino: Path
    proceso: subprocess.Popen | None = None

    def iniciar(self, region: tuple[int, int, int, int] | None = None) -> bool:
        """Arranca la captura; devuelve False si ffmpeg no está disponible.

        ``region`` (x, y, ancho, alto) recorta la captura a la pantalla donde está el
        navegador: en un escritorio de varios monitores, grabar todo dejaría el recorrido
        ilegible al escalar.
        """
        if shutil.which("ffmpeg") is None:
            return False
        entrada = ["-f", "gdigrab" if os.name == "nt" else "x11grab", "-framerate", "8"]
        if region is not None:
            x, y, ancho, alto = region
            entrada += ["-offset_x", str(x), "-offset_y", str(y), "-video_size", f"{ancho}x{alto}"]
        entrada += ["-i", "desktop" if os.name == "nt" else ":0.0"]
        self.proceso = subprocess.Popen(
            ["ffmpeg", "-y", *entrada,
             "-vf", "scale=1600:-2", "-pix_fmt", "yuv420p", "-c:v", "libx264",
             "-preset", "veryfast", "-crf", "28", str(self.destino)],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=(LOGS / "ffmpeg.log").open("w", encoding="utf-8"),
        )
        return True

    def detener(self) -> None:
        """Cierra la captura pidiéndole a ffmpeg que finalice el archivo limpiamente."""
        if self.proceso is None or self.proceso.poll() is not None:
            return
        try:
            assert self.proceso.stdin is not None
            self.proceso.stdin.write(b"q")
            self.proceso.stdin.flush()
            self.proceso.wait(timeout=30)
        except Exception:  # noqa: BLE001 — si no responde, se fuerza
            _matar_arbol(self.proceso)


# Contadores de resultados: los llena el hook de reporte y los usa el cierre del video.
RESULTADOS: dict[str, int] = {"pasaron": 0, "fallaron": 0}


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    """Acumula el resultado de cada prueba para el resumen final (video e informe)."""
    if report.when != "call":
        return
    RESULTADOS["pasaron" if report.passed else "fallaron"] += 1


def _region_del_navegador(nav: webdriver.Chrome) -> tuple[int, int, int, int] | None:
    """Rectángulo (en píxeles físicos) de la pantalla que ocupa la ventana de Chrome."""
    try:
        rect = nav.get_window_rect()
        dpr = float(nav.execute_script("return window.devicePixelRatio") or 1)
        ancho, alto = nav.execute_script("return [screen.width, screen.height]")
    except Exception:  # noqa: BLE001 — sin datos, se graba el escritorio completo
        return None
    # El monitor donde vive la ventana: origen de la ventana redondeado al tamaño de pantalla.
    ancho_f, alto_f = int(ancho * dpr), int(alto * dpr)
    x = int(round(rect["x"] * dpr / ancho_f)) * ancho_f if ancho_f else 0
    y = int(round(rect["y"] * dpr / alto_f)) * alto_f if alto_f else 0
    return (max(x, 0), max(y, 0), ancho_f - ancho_f % 2, alto_f - alto_f % 2)


@pytest.fixture(scope="session", autouse=True)
def grabacion(request: pytest.FixtureRequest, bitacora: Bitacora, servidores: Servidores):
    """Graba el video de la corrida y le anexa los fotogramas con el resumen y los logs."""
    apagado = _opcion(request.config, "sin_video") or _opcion(request.config, "headless")
    grabador = Grabador(destino=EVIDENCIA / "_recorrido.mp4")
    activo = False if apagado else grabador.iniciar(_region_del_navegador(bitacora.nav))
    if not apagado and not activo:
        print("AVISO: ffmpeg no está en el PATH; la corrida no se grabará en video.")

    yield

    grabador.detener()
    _escribir_informe(bitacora, servidores)
    if activo and grabador.destino.exists():
        _componer_video(grabador.destino, EVIDENCIA / "e2e_selenium.mp4", bitacora, servidores)


def _cola(archivo: Path, lineas: int) -> str:
    """Últimas ``lineas`` del archivo (vacío si no existe)."""
    if not archivo.exists():
        return "(sin datos)"
    texto = archivo.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(texto[-lineas:])


def _escribir_informe(bitacora: Bitacora, servidores: Servidores) -> None:
    """Deja el informe en markdown con el resumen, el entorno y el recorrido."""
    total = RESULTADOS["pasaron"] + RESULTADOS["fallaron"]
    lineas = [
        "# Prueba E2E con Selenium — SPC",
        "",
        f"**Fecha:** {datetime.now():%Y-%m-%d %H:%M}",
        f"**Resultado:** {RESULTADOS['pasaron']}/{total} flujos PASAN"
        + (f" · {RESULTADOS['fallaron']} FALLAN" if RESULTADOS["fallaron"] else ""),
        "",
        "## Entorno",
        "",
        "- Navegador: Chrome real gobernado por Selenium WebDriver",
        f"- Frontend (Vite): {servidores.web}",
        f"- Backend (uvicorn): {servidores.api}",
        f"- Base de datos: SQLite temporal ({servidores.db.name}), aislada de la base real",
        f"- Datos de prueba: {DATOS.relative_to(RAIZ).as_posix()}/{{ventas,compras,almacen}}.xlsx",
        "",
        "## Recorrido ejecutado",
        "",
        "```",
        "\n".join(bitacora.pasos) or "(sin pasos)",
        "```",
        "",
        "## Log del backend (últimas líneas)",
        "",
        "```",
        _cola(servidores.log_backend, 40),
        "```",
        "",
        "## Log del frontend (últimas líneas)",
        "",
        "```",
        _cola(servidores.log_frontend, 20),
        "```",
        "",
        "## Evidencia",
        "",
        "- `e2e_selenium.mp4` — video de la corrida + fotogramas con los logs",
        "- `capturas/` — captura por paso",
        "- `logs/` — backend, frontend, consola del navegador, bitácora de pasos",
        "",
    ]
    (EVIDENCIA / "informe_e2e_selenium.md").write_text("\n".join(lineas), encoding="utf-8")


def _dimensiones(video: Path) -> tuple[int, int]:
    """Ancho y alto reales del video grabado (para que los paneles encajen al concatenar)."""
    if shutil.which("ffprobe") is not None:
        proc = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
             "stream=width,height", "-of", "csv=p=0:s=x", str(video)],
            capture_output=True, text=True, check=False,
        )
        medidas = proc.stdout.strip().split("x")
        if len(medidas) == 2 and all(m.isdigit() for m in medidas):
            return int(medidas[0]), int(medidas[1])
    return 1600, 900


def _fotograma(texto: str, titulo: str, destino: Path, ancho: int = 1600, alto: int = 900) -> bool:
    """Renderiza un panel de logs como imagen (fondo oscuro, tipografía monoespaciada)."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return False

    img = Image.new("RGB", (ancho, alto), (16, 20, 28))
    dib = ImageDraw.Draw(img)
    try:
        fuente = ImageFont.truetype("consola.ttf", 17)
        fuente_tit = ImageFont.truetype("consolab.ttf", 26)
    except OSError:
        fuente = ImageFont.load_default()
        fuente_tit = ImageFont.load_default()

    dib.text((40, 30), titulo, fill=(120, 220, 160), font=fuente_tit)
    y = 90
    for linea in texto.splitlines()[: (alto - 120) // 22]:
        dib.text((40, y), linea[:150], fill=(210, 215, 225), font=fuente)
        y += 22
    img.save(destino)
    return True


def _componer_video(base: Path, destino: Path, bitacora: Bitacora, servidores: Servidores) -> None:
    """Concatena el video del recorrido con los fotogramas del resumen y los logs."""
    total = RESULTADOS["pasaron"] + RESULTADOS["fallaron"]
    paneles = [
        (
            "RESUMEN DE LA CORRIDA E2E (Selenium)",
            f"Flujos ejecutados: {total}\n"
            f"PASAN: {RESULTADOS['pasaron']}    FALLAN: {RESULTADOS['fallaron']}\n"
            f"Frontend: {servidores.web}\nBackend:  {servidores.api}\n"
            f"Base: SQLite temporal ({servidores.db.name})\n\n"
            + "\n".join(bitacora.pasos[-22:]),
        ),
        ("LOG DEL BACKEND (uvicorn)", _cola(servidores.log_backend, 32)),
        ("LOG DEL FRONTEND (Vite) Y CONSOLA DEL NAVEGADOR",
         _cola(servidores.log_frontend, 14) + "\n\n--- consola del navegador ---\n"
         + _cola(LOGS / "navegador.log", 14)),
    ]

    ancho, alto = _dimensiones(base)
    imagenes: list[Path] = []
    for i, (titulo, cuerpo) in enumerate(paneles, 1):
        ruta = EVIDENCIA / f"_panel_{i}.png"
        if _fotograma(cuerpo, titulo, ruta, ancho=ancho, alto=alto):
            imagenes.append(ruta)

    if not imagenes:
        base.replace(destino)
        return

    entradas: list[str] = ["-i", str(base)]
    filtros = [f"[0:v]scale={ancho}:{alto},setsar=1,fps=8[v0]"]
    for i, img in enumerate(imagenes, 1):
        entradas += ["-loop", "1", "-t", "8", "-i", str(img)]
        filtros.append(f"[{i}:v]scale={ancho}:{alto},setsar=1,fps=8[v{i}]")
    cadena = "".join(f"[v{i}]" for i in range(len(imagenes) + 1))
    filtros.append(f"{cadena}concat=n={len(imagenes) + 1}:v=1:a=0[out]")

    cmd = (
        ["ffmpeg", "-y", *entradas, "-filter_complex", ";".join(filtros),
         "-map", "[out]", "-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "veryfast",
         "-crf", "28", str(destino)]
    )
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        (LOGS / "ffmpeg_concat.log").write_text(proc.stderr, encoding="utf-8")
        base.replace(destino)
        return
    base.unlink(missing_ok=True)
    for img in imagenes:
        img.unlink(missing_ok=True)


# ===========================================================================
# Datos auxiliares
# ===========================================================================
@pytest.fixture(scope="session")
def excel_corrupto(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Archivo con extensión .xlsx pero contenido inválido (caso de error controlado)."""
    ruta = tmp_path_factory.mktemp("malos") / "roto.xlsx"
    ruta.write_bytes(b"esto no es un libro de Excel")
    return ruta


@pytest.fixture(scope="session")
def contexto(servidores: Servidores, driver: webdriver.Chrome, bitacora: Bitacora) -> dict:
    """Atajo con todo lo que necesita un flujo: servidores, navegador y bitácora."""
    return {"srv": servidores, "nav": driver, "log": bitacora}


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Marca como ``selenium`` las pruebas de ESTA suite (no corren en la batería normal).

    El hook recibe todos los ítems de la sesión, así que se filtra por carpeta: marcar el
    resto dejaría la batería completa fuera del filtro por defecto (``-m 'not selenium'``).
    """
    aqui = Path(__file__).parent
    for item in items:
        ruta = getattr(item, "path", None)
        if ruta is not None and aqui in Path(ruta).parents:
            item.add_marker(pytest.mark.selenium)


def pytest_configure(config: pytest.Config) -> None:
    """Limpia la evidencia anterior y deja constancia de la configuración de la corrida."""
    LOGS.mkdir(parents=True, exist_ok=True)
    CAPTURAS.mkdir(parents=True, exist_ok=True)
    # Las capturas se numeran por paso: mezclarlas con las de una corrida anterior daría una
    # evidencia inconsistente (dos figuras con el mismo número y contenido distinto).
    for viejo in CAPTURAS.glob("*.png"):
        viejo.unlink(missing_ok=True)
    (LOGS / "entorno.json").write_text(
        json.dumps(
            {
                "python": sys.version.split()[0],
                "headless": _opcion(config, "headless"),
                "video": not (_opcion(config, "sin_video") or _opcion(config, "headless")),
                "ffmpeg": shutil.which("ffmpeg") is not None,
                "fecha": datetime.now().isoformat(timespec="seconds"),
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
