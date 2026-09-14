"""Acciones reutilizables sobre la interfaz (capa fina de *page objects*).

Todas las esperas son **explícitas**: la app pide datos al backend y entrena modelos en el
momento, así que los tiempos varían; nunca se usan `sleep` fijos para sincronizar.
Los selectores se anclan a ``data-testid`` (estables ante cambios de estilo o texto).
"""

from __future__ import annotations

from pathlib import Path

from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait

ESPERA = 25  # segundos por defecto para que aparezca un elemento
ESPERA_ANALISIS = 240  # el análisis entrena 10 modelos en el momento

RAIZ = Path(__file__).resolve().parents[2]

# Cuentas de DEMOSTRACIÓN que siembra el repositorio de auth (contraseña = id).
ADMIN_ID = "256370"
ADMIN_PASS = "256370"

# Datos de ejemplo del repo (los mismos de la prueba manual grabada).
DATOS = RAIZ / "examples" / "datos_excel_pyme" / "botica_farmasalud"


def tid(nombre: str) -> tuple[str, str]:
    """Localizador por ``data-testid``."""
    return (By.CSS_SELECTOR, f'[data-testid="{nombre}"]')


def esperar(nav: WebDriver, localizador: tuple[str, str], t: float = ESPERA) -> WebElement:
    """Espera a que el elemento sea visible y lo devuelve."""
    return WebDriverWait(nav, t).until(EC.visibility_of_element_located(localizador))


def esperar_presente(nav: WebDriver, localizador: tuple[str, str], t: float = ESPERA) -> WebElement:
    """Espera a que el elemento exista en el DOM (aunque esté oculto)."""
    return WebDriverWait(nav, t).until(EC.presence_of_element_located(localizador))


def esperar_todos(nav: WebDriver, localizador: tuple[str, str], t: float = ESPERA) -> list[WebElement]:
    """Espera a que haya al menos un elemento y devuelve todos los que coinciden."""
    WebDriverWait(nav, t).until(EC.presence_of_element_located(localizador))
    return nav.find_elements(*localizador)


def esperar_ausencia(nav: WebDriver, localizador: tuple[str, str], t: float = ESPERA) -> None:
    """Espera a que el elemento desaparezca (o nunca haya estado)."""
    WebDriverWait(nav, t).until_not(EC.presence_of_element_located(localizador))


def existe(nav: WebDriver, localizador: tuple[str, str]) -> bool:
    """¿Hay al menos un elemento que coincida ahora mismo? (sin esperar)."""
    return len(nav.find_elements(*localizador)) > 0


def click(nav: WebDriver, localizador: tuple[str, str], t: float = ESPERA) -> WebElement:
    """Espera a que el elemento sea clicable y hace clic."""
    el = WebDriverWait(nav, t).until(EC.element_to_be_clickable(localizador))
    nav.execute_script("arguments[0].scrollIntoView({block:'center'})", el)
    el.click()
    return el


def escribir(nav: WebDriver, localizador: tuple[str, str], texto: str) -> WebElement:
    """Limpia el campo y escribe el texto."""
    el = esperar(nav, localizador)
    el.clear()
    el.send_keys(texto)
    return el


def elegir(nav: WebDriver, localizador: tuple[str, str], *, texto: str | None = None,
           indice: int | None = None) -> None:
    """Selecciona una opción de un ``<select>`` por texto visible o por índice."""
    sel = Select(esperar(nav, localizador))
    if texto is not None:
        sel.select_by_visible_text(texto)
    else:
        assert indice is not None, "elegir() necesita texto o indice"
        sel.select_by_index(indice)


# ---------------------------------------------------------------------------
# Sesión
# ---------------------------------------------------------------------------
def abrir(nav: WebDriver, web: str, ruta: str = "/") -> None:
    """Abre la aplicación (o una ruta concreta) y espera a que React pinte."""
    nav.get(f"{web.rstrip('/')}{ruta}")
    WebDriverWait(nav, ESPERA).until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )


def en_login(nav: WebDriver) -> bool:
    """¿Está visible el formulario de ingreso?"""
    return existe(nav, (By.ID, "user_id"))


def login(nav: WebDriver, web: str, usuario: str, password: str) -> None:
    """Ingresa con las credenciales dadas desde la pantalla de login."""
    if not en_login(nav):
        abrir(nav, web)
    esperar(nav, (By.ID, "user_id"))
    escribir(nav, (By.ID, "user_id"), usuario)
    escribir(nav, (By.ID, "password"), password)
    click(nav, tid("login-submit"))


def logout(nav: WebDriver) -> None:
    """Cierra la sesión desde la barra lateral y espera la pantalla de login."""
    click(nav, tid("btn-logout"))
    WebDriverWait(nav, ESPERA).until(lambda d: en_login(d))


def usuario_actual(nav: WebDriver) -> str:
    """Id del usuario que muestra la barra lateral."""
    return esperar(nav, tid("usuario-actual")).text.strip()


def sesion_admin(nav: WebDriver, web: str, usuario: str, password: str) -> None:
    """Garantiza que la sesión activa es la del usuario indicado (relogueando si hace falta)."""
    abrir(nav, web)
    if en_login(nav):
        login(nav, web, usuario, password)
    elif existe(nav, tid("usuario-actual")) and usuario_actual(nav) != usuario:
        logout(nav)
        login(nav, web, usuario, password)
    esperar(nav, tid("sidebar-nav"))


def completar_onboarding(nav: WebDriver, negocio: str) -> None:
    """Rellena el formulario de primer ingreso (sector/tamaño/región/moneda) y continúa."""
    escribir(nav, (By.ID, "business_name"), negocio)
    for campo in ("sector", "size", "region", "currency"):
        elegir(nav, (By.ID, campo), indice=1)  # 0 es el placeholder deshabilitado
    click(nav, tid("onboarding-submit"))
    esperar(nav, tid("sidebar-nav"))


# ---------------------------------------------------------------------------
# Navegación y módulos
# ---------------------------------------------------------------------------
def ir_a_seccion(nav: WebDriver, seccion: str) -> None:
    """Hace clic en una sección de la barra lateral (``home``/``sales``/``purchases``…)."""
    click(nav, tid(f"nav-{seccion}"))


def secciones_visibles(nav: WebDriver) -> list[str]:
    """Ids de las secciones que el rol tiene permitidas (lo que muestra el menú)."""
    esperar(nav, tid("sidebar-nav"))
    enlaces = nav.find_elements(By.CSS_SELECTOR, '[data-testid^="nav-"]')
    return [e.get_attribute("data-testid").removeprefix("nav-") for e in enlaces]


def subir_archivo(nav: WebDriver, ruta: Path) -> None:
    """Sube un archivo por el campo del Paso 3 (el input está oculto tras la etiqueta)."""
    campo = esperar_presente(nav, tid("input-archivo"))
    # El input real está oculto (`hidden` de Tailwind) y Selenium no escribe en elementos
    # no interactuables: se muestra solo para poder adjuntar la ruta, como hace el usuario
    # al elegir el archivo en el diálogo del sistema.
    nav.execute_script(
        "arguments[0].classList.remove('hidden'); arguments[0].style.display='block';", campo
    )
    campo.send_keys(str(ruta.resolve()))


def esperar_resultados(nav: WebDriver, t: float = ESPERA_ANALISIS) -> list[WebElement]:
    """Espera a que terminen los 10 análisis y devuelve las tarjetas de reporte."""
    esperar(nav, tid("resultados"), t)
    return esperar_todos(nav, tid("reporte-card"))


def analizar(nav: WebDriver, ruta: Path) -> list[WebElement]:
    """Sube el archivo del módulo abierto y espera los reportes."""
    subir_archivo(nav, ruta)
    return esperar_resultados(nav)


def abrir_detalle_tecnico(nav: WebDriver) -> str:
    """Despliega el primer «Ver detalle técnico» y devuelve su contenido."""
    detalles = nav.find_elements(By.XPATH, "//summary[contains(., 'detalle técnico')]")
    assert detalles, "No hay bloques de detalle técnico en los resultados"
    nav.execute_script("arguments[0].scrollIntoView({block:'center'})", detalles[0])
    detalles[0].click()
    return detalles[0].find_element(By.XPATH, "./..").text
