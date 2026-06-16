# syntax=docker/dockerfile:1
#
# Imagen de SERVICIO para la API del SPC (Fase 3).
#
# Carga los artefactos del motor (models/, horneados en la imagen) y expone el
# contrato de datos por FastAPI. NO entrena: en produccion solo se carga y predice
# (la decision de diseno esta en docs/decisiones/0007-capa-api-fase3.md).
#
# Pensada para plataformas tipo Render / Railway: el puerto lo inyecta la
# plataforma via $PORT y la app hace bind en 0.0.0.0.

FROM python:3.11-slim AS runtime

# - PYTHONUNBUFFERED: logs a stdout sin buffer (Render/Railway los muestran en vivo).
# - PYTHONDONTWRITEBYTECODE: sin .pyc en la imagen.
# - PIP_NO_CACHE_DIR / PIP_DISABLE_PIP_VERSION_CHECK: build mas limpio y chico.
# - PYTHONPATH: layout src/ -> "import spc" funciona sin instalar el paquete.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app/src

# libgomp1: runtime de OpenMP que requieren LightGBM y XGBoost. Sin el, el import
# del booster falla con "libgomp.so.1: cannot open shared object file".
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependencias primero: capa cacheable. Mientras requirements-api.txt no cambie,
# Docker reutiliza esta capa y el build es rapido.
COPY requirements-api.txt ./
RUN pip install -r requirements-api.txt

# Codigo de la app + artefactos del motor. models/ se hornea en la imagen: el
# servicio arranca sin volumenes, sin descargas externas y sin reentrenar.
COPY src/ ./src/
COPY models/ ./models/

# Usuario sin privilegios (buena practica de seguridad para contenedores).
RUN useradd --create-home --uid 1000 appuser \
    && chown -R appuser:appuser /app
USER appuser

# Documental: el puerto real lo inyecta la plataforma ($PORT). 8000 es el fallback
# para correr en local.
EXPOSE 8000

# Shell form para expandir $PORT. 1 worker: el motor carga ~40 MB en RAM por
# proceso; un solo worker basta y entra holgado en el free tier (512 MB).
CMD ["sh", "-c", "uvicorn spc.api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
