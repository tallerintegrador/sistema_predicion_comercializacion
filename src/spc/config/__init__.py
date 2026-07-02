"""Configuracion central del paquete `spc`.

Todo lo que antes eran constantes sueltas en `eda.py` (rutas, semilla, archivos
esperados, parametros de figuras) vive aqui en una dataclass tipada e inmutable.
La configuracion se inyecta al pipeline y los modulos la reciben como argumento,
de modo que las rutas se pueden sobreescribir desde la CLI sin tocar el codigo.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# Tope de tamaño (bytes) para un archivo .xlsx subido por el canal Excel.
# Es un límite plano de protección anti-abuso (DoS), NO el ruteo por volumen
# (en línea/lote): esa frontera se mide por NÚMERO DE FILAS (ver online_max_rows()).
# Como el modo lote (Fase 3.4) admite entradas grandes, este techo se sube a 25 MB
# para que un .xlsx de lote quepa; hay que parsear el archivo para contar sus filas.
# Configurable por entorno (igual que SPC_CORS_ORIGINS).
EXCEL_MAX_BYTES_DEFAULT = 25 * 1024 * 1024  # 25 MB

# Umbral de ruteo en línea/lote, medido por NÚMERO DE FILAS del bloque `history`
# (P6, Fase 3.4). Una petición con `len(history) <= umbral` se procesa en línea
# (síncrona, 200 con el resultado); por encima del umbral se acepta como trabajo por
# lote (202 con job_id). El default se fijó MIDIENDO el tiempo de respuesta del flujo
# síncrono (scripts/bench_umbral_online.py; ver ADR-0008): en la medición indicativa
# (artefacto diminuto, máquina de desarrollo) ~2.000 filas se resuelven en ~2 s
# (cómodamente por debajo de unos pocos segundos), mientras que 10.000 ya rondan ~7 s.
# Es CONFIGURABLE: producción debería re-medir con el modelo y el hardware reales y
# ajustar SPC_ONLINE_MAX_ROWS en consecuencia.
ONLINE_MAX_ROWS_DEFAULT = 2_000

# Nº de hilos del executor in-process que procesa los trabajos por lote (P5: sin
# Celery/Redis). 1 por defecto: procesa FIFO y acota el uso de memoria.
BATCH_WORKERS_DEFAULT = 1

# Persistencia incremental del corpus (Fase A MEJORADO, ADR-0011). Cada predicción
# guarda el `history` del cliente (corpus de entrenamiento que crece) y su salida
# (auditoría/replay) en una base SQLite. Es best-effort: un fallo de BD NUNCA rompe
# la predicción. Activa por defecto; se desactiva con SPC_PERSIST_ENABLED=0 (p. ej.
# en algunos tests). La ruta del archivo es configurable (SPC_DB_PATH); por defecto
# `<base>/data/spc.db`.
PERSIST_ENABLED_DEFAULT = True
DB_FILE_DEFAULT = "spc.db"

# ---------------------------------------------------------------------------
# Entrenamiento por cliente bajo demanda (Camino A completo, ADR-0013)
# ---------------------------------------------------------------------------
# OPT-IN: solo se reentrena cuando el cliente lo pide; el camino por defecto (modelo
# CONGELADO) queda intacto para todos los demás. El entrenamiento corre como trabajo
# asíncrono LOCAL, desacoplado del flujo de predicción. Un modelo por cliente solo se
# adopta (y se sirve a ESE cliente) si **supera al congelado** en validación temporal
# honesta (WAPE recursivo); "no mejora" es un resultado válido que se reporta.
CLIENT_ADJ_ENABLED_DEFAULT = True
# Carpeta raíz de los artefactos por cliente (namespaced por client_id). Conviven con
# los congelados de ``models/`` sin reemplazarlos.
CLIENT_MODELS_SUBDIR_DEFAULT = "clientes"
# Nº de hilos del executor de entrenamiento (SEPARADO del de lote, para no competir con
# la predicción). 1 por defecto: entrena FIFO y acota memoria/CPU.
TRAINING_WORKERS_DEFAULT = 1
# Gate de datos mínimos para entrenar (si no se cumple → aviso honesto, NO se entrena):
# días de historia distintos, nº de observaciones y nº de series (store×product).
CLIENT_ADJ_MIN_DAYS_DEFAULT = 60
CLIENT_ADJ_MIN_ROWS_DEFAULT = 120
CLIENT_ADJ_MIN_SERIES_DEFAULT = 1
# Ventana de validación temporal ADAPTATIVA a la historia: cada holdout (valid y test)
# dura ``round(dias_utiles * FRAC)``, recortado a [MIN_W, MAX_W]. MAX_W = 16 = la ventana
# del modelo congelado (espejo del test de Favorita); así clientes con mucha historia se
# validan igual que el congelado y los de poca con ventanas más cortas pero honestas.
CLIENT_ADJ_VALID_FRAC_DEFAULT = 0.15
CLIENT_ADJ_MIN_WINDOW_DEFAULT = 7
CLIENT_ADJ_MAX_WINDOW_DEFAULT = 16
# Mejora mínima de WAPE (puntos absolutos) del candidato sobre el congelado para
# adoptar. Default 0.0 = **cualquier mejora estricta** (el candidato debe además no ser
# peor que el mejor baseline ingenuo). Subirlo exige mejoras más claras.
CLIENT_ADJ_MIN_IMPROVEMENT_DEFAULT = 0.0
# Los boosters del entrenamiento por cliente usan GPU solo si se activa explícitamente;
# por defecto CPU (el trabajo es local y debe correr sin GPU, igual que los tests).
CLIENT_ADJ_USE_GPU_DEFAULT = False

# ---------------------------------------------------------------------------
# Control de acceso por roles (autenticación, usuarios, roles) — ADR-0014
# ---------------------------------------------------------------------------
# La capacidad de autenticación se habilita a nivel de despliegue. Con la bandera en
# False, los endpoints protegidos NO exigen credenciales (comportamiento previo a la
# fase de control de acceso); con True, cada endpoint protegido valida rol/permiso en el
# BACKEND. Los tests de predicción la desactivan por defecto (mismo patrón que la
# persistencia del corpus) y los tests de auth la activan explícitamente.
AUTH_ENABLED_DEFAULT = True
# Secreto para firmar los tokens de sesión (HMAC-SHA256). Hay un valor de DESARROLLO
# para que la app arranque sin configuración, pero en producción DEBE fijarse uno propio
# vía SPC_AUTH_SECRET (de lo contrario los tokens son falsificables). El arranque registra
# una advertencia si se usa el default.
AUTH_SECRET_DEFAULT = "spc-dev-secret-NO-USAR-EN-PRODUCCION"
# Vida útil del token de sesión, en segundos (8 horas por defecto). Tras expirar, el
# usuario debe volver a iniciar sesión (el token es autocontenido; no hay almacén de
# sesión externo, lo que respeta el despliegue de un solo worker).
AUTH_TOKEN_TTL_DEFAULT = 8 * 3600
# Cuentas administrador de DEMOSTRACIÓN que se siembran al arranque (ADR-0014). La
# contraseña inicial es IGUAL al id y se almacena HASHEADA. NO son credenciales de
# producción: se documentan como demo en el README y deben rotarse en un despliegue real.
ADMIN_SEED_IDS: tuple[str, ...] = ("256317", "256370")


def _entero_positivo_env(nombre: str, por_defecto: int) -> int:
    """Lee un entero positivo de la variable ``nombre`` (o ``por_defecto`` si falta/inválida)."""
    valor = os.getenv(nombre, "").strip()
    if not valor:
        return por_defecto
    try:
        n = int(valor)
    except ValueError:
        return por_defecto
    return n if n > 0 else por_defecto


def _bool_env(nombre: str, por_defecto: bool) -> bool:
    """Lee un booleano de la variable ``nombre`` (``1/true/yes/on`` → True; ``0/false/no/off`` → False).

    Si la variable falta o trae un valor no reconocido, cae al ``por_defecto``.
    """
    valor = os.getenv(nombre, "").strip().lower()
    if not valor:
        return por_defecto
    if valor in ("1", "true", "yes", "on"):
        return True
    if valor in ("0", "false", "no", "off"):
        return False
    return por_defecto


def _float_positivo_env(nombre: str, por_defecto: float) -> float:
    """Lee un float positivo de la variable ``nombre`` (o ``por_defecto`` si falta/inválida)."""
    valor = os.getenv(nombre, "").strip()
    if not valor:
        return por_defecto
    try:
        x = float(valor)
    except ValueError:
        return por_defecto
    return x if x > 0 else por_defecto


# Métodos válidos del stock de seguridad (knob de política, ADR-0010).
SAFETY_METHODS: tuple[str, ...] = ("coverage_days", "service_level")


def _metodo_safety_env(nombre: str, por_defecto: str) -> str:
    """Lee el método de stock de seguridad (``coverage_days``|``service_level``).

    Si la variable falta o trae un valor no reconocido, cae al ``por_defecto`` del dominio.
    """
    valor = os.getenv(nombre, "").strip().lower()
    return valor if valor in SAFETY_METHODS else por_defecto


def excel_max_bytes() -> int:
    """Tope de tamaño del .xlsx subido, en bytes (``SPC_EXCEL_MAX_BYTES`` o 25 MB)."""
    return _entero_positivo_env("SPC_EXCEL_MAX_BYTES", EXCEL_MAX_BYTES_DEFAULT)


def online_max_rows() -> int:
    """Máximo de filas (``len(history)``) que se procesan en línea (``SPC_ONLINE_MAX_ROWS``).

    Por encima de este número, el envío se rutea al modo por lote (asíncrono). Es la
    **frontera en línea/lote** de la Fase 3.4: configurable y medida en filas, no en
    bytes (el tope de bytes es solo una guarda anti-abuso).
    """
    return _entero_positivo_env("SPC_ONLINE_MAX_ROWS", ONLINE_MAX_ROWS_DEFAULT)


def batch_workers() -> int:
    """Nº de hilos del executor in-process de lote (``SPC_BATCH_WORKERS`` o 1)."""
    return _entero_positivo_env("SPC_BATCH_WORKERS", BATCH_WORKERS_DEFAULT)


def db_enabled() -> bool:
    """¿Está activa la persistencia incremental del corpus? (``SPC_PERSIST_ENABLED`` o True).

    Si es ``False``, la API no abre la base ni guarda predicciones (el comportamiento de
    predicción es idéntico; solo no se acumula corpus). Ver ADR-0011 (Fase A MEJORADO).
    """
    return _bool_env("SPC_PERSIST_ENABLED", PERSIST_ENABLED_DEFAULT)


def db_path() -> Path:
    """Ruta del archivo SQLite del corpus (``SPC_DB_PATH`` o ``<base>/data/spc.db``).

    Default relativo al directorio de trabajo del proceso (igual criterio que
    ``Settings.base_dir``). La carpeta se crea al abrir la base si no existe.
    """
    valor = os.getenv("SPC_DB_PATH", "").strip()
    if valor:
        return Path(valor)
    return Settings().base_dir / "data" / DB_FILE_DEFAULT


def _float_no_negativo_env(nombre: str, por_defecto: float) -> float:
    """Lee un float ``>= 0`` de la variable ``nombre`` (o ``por_defecto`` si falta/inválida)."""
    valor = os.getenv(nombre, "").strip()
    if not valor:
        return por_defecto
    try:
        x = float(valor)
    except ValueError:
        return por_defecto
    return x if x >= 0 else por_defecto


# ---------------------------------------------------------------------------
# Accesores del entrenamiento por cliente bajo demanda (ADR-0013)
# ---------------------------------------------------------------------------
def client_adjustment_enabled() -> bool:
    """¿Está activo el entrenamiento por cliente bajo demanda? (``SPC_CLIENT_ADJ_ENABLED``).

    Si es ``False``, los endpoints de entrenamiento responden 503 y el serving usa siempre
    el modelo congelado: el camino por defecto queda intacto. Es OPT-IN por cliente; esta
    bandera solo habilita/inhabilita la **capacidad** a nivel de despliegue.
    """
    return _bool_env("SPC_CLIENT_ADJ_ENABLED", CLIENT_ADJ_ENABLED_DEFAULT)


def client_models_dir() -> Path:
    """Carpeta de artefactos por cliente (``SPC_CLIENT_MODELS_DIR`` o ``<base>/models/clientes``)."""
    valor = os.getenv("SPC_CLIENT_MODELS_DIR", "").strip()
    if valor:
        return Path(valor)
    return Settings().base_dir / "models" / CLIENT_MODELS_SUBDIR_DEFAULT


def training_workers() -> int:
    """Nº de hilos del executor de entrenamiento por cliente (``SPC_TRAINING_WORKERS`` o 1)."""
    return _entero_positivo_env("SPC_TRAINING_WORKERS", TRAINING_WORKERS_DEFAULT)


def client_adj_min_days() -> int:
    """Días de historia mínimos para entrenar por cliente (``SPC_CLIENT_ADJ_MIN_DAYS`` o 60)."""
    return _entero_positivo_env("SPC_CLIENT_ADJ_MIN_DAYS", CLIENT_ADJ_MIN_DAYS_DEFAULT)


def client_adj_min_rows() -> int:
    """Observaciones mínimas para entrenar por cliente (``SPC_CLIENT_ADJ_MIN_ROWS`` o 120)."""
    return _entero_positivo_env("SPC_CLIENT_ADJ_MIN_ROWS", CLIENT_ADJ_MIN_ROWS_DEFAULT)


def client_adj_min_series() -> int:
    """Series (store×product) mínimas para entrenar por cliente (``SPC_CLIENT_ADJ_MIN_SERIES`` o 1)."""
    return _entero_positivo_env("SPC_CLIENT_ADJ_MIN_SERIES", CLIENT_ADJ_MIN_SERIES_DEFAULT)


def client_adj_valid_frac() -> float:
    """Fracción de la historia útil por holdout temporal (``SPC_CLIENT_ADJ_VALID_FRAC`` o 0.15)."""
    return _float_positivo_env("SPC_CLIENT_ADJ_VALID_FRAC", CLIENT_ADJ_VALID_FRAC_DEFAULT)


def client_adj_min_window() -> int:
    """Mínimo de días por holdout temporal por cliente (``SPC_CLIENT_ADJ_MIN_WINDOW`` o 7)."""
    return _entero_positivo_env("SPC_CLIENT_ADJ_MIN_WINDOW", CLIENT_ADJ_MIN_WINDOW_DEFAULT)


def client_adj_max_window() -> int:
    """Máximo de días por holdout temporal por cliente (``SPC_CLIENT_ADJ_MAX_WINDOW`` o 16)."""
    return _entero_positivo_env("SPC_CLIENT_ADJ_MAX_WINDOW", CLIENT_ADJ_MAX_WINDOW_DEFAULT)


def client_adj_min_improvement() -> float:
    """Mejora mínima de WAPE (puntos) para adoptar (``SPC_CLIENT_ADJ_MIN_IMPROVEMENT`` o 0.0)."""
    return _float_no_negativo_env(
        "SPC_CLIENT_ADJ_MIN_IMPROVEMENT", CLIENT_ADJ_MIN_IMPROVEMENT_DEFAULT
    )


def client_adj_use_gpu() -> bool:
    """¿El entrenamiento por cliente usa GPU? (``SPC_CLIENT_ADJ_USE_GPU`` o False)."""
    return _bool_env("SPC_CLIENT_ADJ_USE_GPU", CLIENT_ADJ_USE_GPU_DEFAULT)


# ---------------------------------------------------------------------------
# Accesores del control de acceso por roles (ADR-0014)
# ---------------------------------------------------------------------------
def auth_enabled() -> bool:
    """¿Está activo el control de acceso por roles? (``SPC_AUTH_ENABLED`` o True).

    Si es ``False``, los endpoints protegidos no exigen credenciales (comportamiento
    previo). La autorización efectiva (validar permiso por endpoint) solo ocurre con la
    bandera en ``True``. Es un knob de despliegue, no un permiso de usuario.
    """
    return _bool_env("SPC_AUTH_ENABLED", AUTH_ENABLED_DEFAULT)


def auth_secret() -> str:
    """Secreto para firmar los tokens de sesión (``SPC_AUTH_SECRET`` o un default de DEV).

    El default de desarrollo permite arrancar sin configuración pero NO es seguro: en
    producción debe fijarse un secreto propio (ver ``AUTH_SECRET_DEFAULT``).
    """
    valor = os.getenv("SPC_AUTH_SECRET", "").strip()
    return valor or AUTH_SECRET_DEFAULT


def auth_secret_es_default() -> bool:
    """True si se está usando el secreto de DESARROLLO (para advertir en el arranque)."""
    return not os.getenv("SPC_AUTH_SECRET", "").strip()


def auth_token_ttl() -> int:
    """Vida útil del token de sesión en segundos (``SPC_AUTH_TOKEN_TTL`` o 8 h)."""
    return _entero_positivo_env("SPC_AUTH_TOKEN_TTL", AUTH_TOKEN_TTL_DEFAULT)


# ---------------------------------------------------------------------------
# Base de datos real (Postgres/Supabase) — ADR-0026
# ---------------------------------------------------------------------------
# Toda la persistencia (auth + corpus acumulativo + registro de modelos) vive en UNA
# base de datos, accedida vía SQLAlchemy. En producción se apunta a Postgres/Supabase con
# SPC_DATABASE_URL (formato SQLAlchemy, p. ej.
#   postgresql+psycopg://usuario:clave@host:5432/postgres
# usando el pooler de Supabase). Si la variable NO está, se cae a un archivo SQLite local
# (``db_path()``) para que la app y los tests sigan funcionando sin infraestructura. Los
# tests usan SQLite (archivo temporal o ``:memory:``); el ORM es el mismo en ambos motores.
def database_url() -> str:
    """URL SQLAlchemy de la base de datos (``SPC_DATABASE_URL`` o SQLite local de respaldo).

    Producción: Postgres/Supabase (``postgresql+psycopg://...``). Sin la variable, deriva
    una URL SQLite del archivo ``db_path()`` — mismo ORM, motor distinto.
    """
    valor = os.getenv("SPC_DATABASE_URL", "").strip()
    if valor:
        return valor
    # SQLite de respaldo: ruta del archivo del corpus histórico (compat + dev/tests).
    ruta = db_path().as_posix()
    return f"sqlite:///{ruta}"


def usa_postgres() -> bool:
    """True si la base configurada es Postgres (para elegir tipos/índices específicos)."""
    return database_url().startswith(("postgres://", "postgresql"))


# --- Supabase Storage (bucket de artefactos .joblib) -----------------------
# Los modelos entrenados se suben a un bucket de Supabase Storage. Si estas variables no
# están todas configuradas, ``storage_habilitado()`` es False y el registro de modelos cae
# a disco local (``client_models_dir()``): la funcionalidad no se rompe, solo cambia dónde
# viven los bytes del artefacto.
def supabase_url() -> str | None:
    """URL del proyecto Supabase para Storage (``SUPABASE_URL``) o ``None``."""
    return os.getenv("SUPABASE_URL", "").strip() or None


def supabase_key() -> str | None:
    """Clave de servicio de Supabase para Storage (``SUPABASE_KEY``) o ``None``.

    Debe ser la *service role key* (no la anon) porque el backend sube/borra artefactos.
    """
    return os.getenv("SUPABASE_KEY", "").strip() or None


def supabase_bucket() -> str:
    """Nombre del bucket de artefactos (``SUPABASE_BUCKET`` o ``spc-modelos``)."""
    return os.getenv("SUPABASE_BUCKET", "").strip() or "spc-modelos"


def storage_habilitado() -> bool:
    """True si hay URL + clave de Supabase para subir artefactos al bucket."""
    return bool(supabase_url() and supabase_key())


# ---------------------------------------------------------------------------
# Constantes de POLÍTICA de inventario/compras (Fase 3.5, ADR-0010)
# ---------------------------------------------------------------------------
# Antes vivían clavadas en la capa de servicio (compras_service / almacen_service).
# Ahora son configurables por entorno con el MISMO patrón que online_max_rows(). Los
# defaults = los valores históricos, de modo que **sin configurar nada la salida NO
# cambia** (regresión). NO son parámetros del modelo (esos se leen de la metadata del
# artefacto): son decisiones de política de negocio del cliente.

# Stock de seguridad de PURCHASES (método coverage_days) = este factor × demanda(lead).
PURCHASES_SAFETY_FACTOR_DEFAULT = 0.30
# Días de cobertura objetivo SUGERIDOS POR DEFECTO en la UI de COMPRAS cuando el cliente
# no especifica uno por producto. Es una prefill EDITABLE (la UI la usa para no obligar a
# llenar el campo fila por fila); NO altera el cálculo: si el cliente no la cambia, se envía
# este valor como target_coverage_days. Configurable por entorno, mismo patrón que el resto
# de la política (ADR-0010). Vive aquí —y no como literal en catalog.py— para que la fuente
# del valor sea la configuración de política, no la capa de presentación.
PURCHASES_TARGET_COVERAGE_DAYS_DEFAULT = 14
# Método de stock de seguridad por dominio (knob, ADR-0010). El default de cada dominio
# es su método histórico: PURCHASES por días de cobertura; INVENTORY por nivel de
# servicio (z·σ·√lead). Unificar INVENTORY con PURCHASES = poner su método en
# coverage_days (un solo cambio de variable de entorno).
PURCHASES_SAFETY_METHOD_DEFAULT = "coverage_days"
INVENTORY_SAFETY_METHOD_DEFAULT = "service_level"
# Lead time supuesto en INVENTORY cuando el cliente no envía lead_time_days (días).
INVENTORY_LEAD_TIME_DEFAULT = 7
# Ventana reciente (días) para estimar μ/σ de la demanda desde el histórico (INVENTORY).
INVENTORY_DEMAND_WINDOW_DEFAULT = 28
# Niveles de servicio (z) del método service_level de INVENTORY. El segmento de alto
# volumen recibe un z más exigente (política afinada por el clustering).
INVENTORY_Z_BASE_DEFAULT = 1.28  # ~90 %
INVENTORY_Z_HIGH_VOLUME_DEFAULT = 1.65  # ~95 %
# Si σ no es estimable (serie demasiado corta), el service_level cae a este factor ×
# demanda(lead). Constante de política, no de artefacto.
INVENTORY_SAFETY_FALLBACK_FACTOR_DEFAULT = 0.5
# Factor de cobertura usado SOLO si INVENTORY se conmuta a coverage_days (puente de
# unificación, ADR-0010). Default = el factor de PURCHASES, para que conmutar el método
# deje a INVENTORY exactamente igual que PURCHASES con un único cambio de variable.
INVENTORY_COVERAGE_FACTOR_DEFAULT = 0.30


def purchases_safety_factor() -> float:
    """Factor del colchón de COMPRAS (``SPC_PURCHASES_SAFETY_FACTOR`` o 0.30)."""
    return _float_positivo_env("SPC_PURCHASES_SAFETY_FACTOR", PURCHASES_SAFETY_FACTOR_DEFAULT)


def purchases_safety_method() -> str:
    """Método de stock de seguridad de COMPRAS (``SPC_PURCHASES_SAFETY_METHOD`` o coverage_days)."""
    return _metodo_safety_env("SPC_PURCHASES_SAFETY_METHOD", PURCHASES_SAFETY_METHOD_DEFAULT)


def purchases_target_coverage_days() -> int:
    """Días de cobertura objetivo sugeridos por defecto en la UI de COMPRAS.

    Lee ``SPC_PURCHASES_TARGET_COVERAGE_DAYS`` (o 14). Es solo una prefill editable de la
    interfaz; no cambia el cálculo de reposición (que usa el valor que finalmente envíe el
    cliente). Centralizado aquí para que la UI no clave un literal.
    """
    return _entero_positivo_env(
        "SPC_PURCHASES_TARGET_COVERAGE_DAYS", PURCHASES_TARGET_COVERAGE_DAYS_DEFAULT
    )


def inventory_safety_method() -> str:
    """Método de stock de seguridad de INVENTORY (``SPC_INVENTORY_SAFETY_METHOD`` o service_level)."""
    return _metodo_safety_env("SPC_INVENTORY_SAFETY_METHOD", INVENTORY_SAFETY_METHOD_DEFAULT)


def inventory_lead_time_default() -> int:
    """Lead time por defecto de INVENTORY en días (``SPC_INVENTORY_LEAD_TIME_DEFAULT`` o 7)."""
    return _entero_positivo_env("SPC_INVENTORY_LEAD_TIME_DEFAULT", INVENTORY_LEAD_TIME_DEFAULT)


def inventory_demand_window() -> int:
    """Ventana (días) para estimar μ/σ de la demanda (``SPC_INVENTORY_DEMAND_WINDOW`` o 28)."""
    return _entero_positivo_env("SPC_INVENTORY_DEMAND_WINDOW", INVENTORY_DEMAND_WINDOW_DEFAULT)


def inventory_z_base() -> float:
    """z del nivel de servicio base de INVENTORY (``SPC_INVENTORY_Z_BASE`` o 1.28)."""
    return _float_positivo_env("SPC_INVENTORY_Z_BASE", INVENTORY_Z_BASE_DEFAULT)


def inventory_z_high_volume() -> float:
    """z del nivel de servicio del segmento de alto volumen (``SPC_INVENTORY_Z_HIGH_VOLUME`` o 1.65)."""
    return _float_positivo_env("SPC_INVENTORY_Z_HIGH_VOLUME", INVENTORY_Z_HIGH_VOLUME_DEFAULT)


def inventory_safety_fallback_factor() -> float:
    """Factor de respaldo del service_level cuando σ no es estimable (``SPC_INVENTORY_SAFETY_FALLBACK_FACTOR`` o 0.5)."""
    return _float_positivo_env(
        "SPC_INVENTORY_SAFETY_FALLBACK_FACTOR", INVENTORY_SAFETY_FALLBACK_FACTOR_DEFAULT
    )


def inventory_coverage_factor() -> float:
    """Factor de cobertura de INVENTORY si se conmuta a coverage_days (``SPC_INVENTORY_COVERAGE_FACTOR`` o 0.30)."""
    return _float_positivo_env("SPC_INVENTORY_COVERAGE_FACTOR", INVENTORY_COVERAGE_FACTOR_DEFAULT)


# Nombre logico -> archivo esperado en data/raw.
EXPECTED_FILES: dict[str, str] = {
    "train": "train.csv",
    "test": "test.csv",
    "stores": "stores.csv",
    "transactions": "transactions.csv",
    "oil": "oil.csv",
    "holidays_events": "holidays_events.csv",
    "sample_submission": "sample_submission.csv",
}


@dataclass(frozen=True)
class FigureStyle:
    """Parametros visuales compartidos por todas las figuras."""

    theme: str = "whitegrid"
    context: str = "notebook"
    dpi: int = 160
    figsize_default: tuple[float, float] = (9.0, 5.0)
    figsize_wide: tuple[float, float] = (13.0, 5.0)
    figsize_square: tuple[float, float] = (8.0, 6.0)
    # Paleta coherente por rol semantico (no un color por figura al azar).
    color_primary: str = "#2f6f8f"
    color_secondary: str = "#8a5a44"
    color_accent: str = "#4f8a5f"
    color_highlight: str = "#7a5c91"
    palette_qualitative: str = "tab10"
    cmap_diverging: str = "vlag"
    cmap_sequential: str = "YlGnBu"


@dataclass(frozen=True)
class Settings:
    """Rutas y parametros del pipeline. Inmutable y reproducible."""

    base_dir: Path = field(default_factory=Path.cwd)
    random_seed: int = 42
    style: FigureStyle = field(default_factory=FigureStyle)
    expected_files: dict[str, str] = field(default_factory=lambda: dict(EXPECTED_FILES))

    # --- Rutas derivadas (todas relativas a base_dir) ---
    @property
    def raw_dir(self) -> Path:
        return self.base_dir / "data" / "raw"

    @property
    def processed_dir(self) -> Path:
        return self.base_dir / "data" / "processed"

    @property
    def figures_dir(self) -> Path:
        return self.base_dir / "figures"

    @property
    def report_path(self) -> Path:
        return self.base_dir / "docs" / "reporte_eda.md"

    @property
    def notebook_path(self) -> Path:
        return self.base_dir / "notebooks" / "eda.ipynb"

    def ensure_dirs(self) -> None:
        """Crea las carpetas de salida si no existen."""
        for directory in (self.processed_dir, self.figures_dir, self.notebook_path.parent):
            directory.mkdir(parents=True, exist_ok=True)
