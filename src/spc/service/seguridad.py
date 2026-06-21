"""Primitivas de seguridad: hashing de contraseñas y tokens de sesión (ADR-0014).

Funciones **puras de la capa de servicio**: no importan FastAPI ni tocan la base.
Dos responsabilidades, ambas con la **biblioteca estándar** (cero dependencias nuevas,
mismo criterio que el resto del proyecto):

- **Contraseñas:** se almacenan HASHEADAS con ``hashlib.scrypt`` (KDF con sal por
  contraseña). El formato serializado guarda los parámetros para poder verificar más
  tarde aunque cambien los defaults: ``scrypt$n$r$p$salt_b64$hash_b64``.
- **Sesión:** un token autocontenido y firmado con **HMAC-SHA256** (estilo JWT compacto)
  que transporta el ``sub`` (id de usuario) y una expiración ``exp``. Como va firmado y
  lleva su propia caducidad, **no hace falta un almacén de sesión externo** — respeta el
  despliegue de un solo worker. El rol y los permisos NO viajan en el token: se leen de la
  base en cada petición, de modo que un cambio de rol surte efecto sin re-emitir tokens.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any

# Parámetros de scrypt (RFC 7914). Coste de memoria ≈ 128·n·r·p = 16 MiB con estos
# valores, cómodo para un login interactivo y por debajo del tope por defecto de hashlib.
_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 32
_SCRYPT_SALT_BYTES = 16


def _b64e(datos: bytes) -> str:
    """Codifica en base64url sin relleno (compacto y seguro para URL/JSON)."""
    return base64.urlsafe_b64encode(datos).rstrip(b"=").decode("ascii")


def _b64d(texto: str) -> bytes:
    """Decodifica base64url sin relleno (re-añade el padding que falte)."""
    relleno = "=" * (-len(texto) % 4)
    return base64.urlsafe_b64decode(texto + relleno)


# ---------------------------------------------------------------------------
# Contraseñas (hash con sal, verificación en tiempo constante)
# ---------------------------------------------------------------------------
def hash_password(password: str) -> str:
    """Devuelve el hash serializado de ``password`` (con sal aleatoria por contraseña).

    Formato: ``scrypt$n$r$p$salt_b64$hash_b64``. Guardar los parámetros permite verificar
    aunque los defaults cambien en el futuro. Nunca se almacena la contraseña en claro.
    """
    import os

    salt = os.urandom(_SCRYPT_SALT_BYTES)
    derivado = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_SCRYPT_DKLEN,
    )
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${_b64e(salt)}${_b64e(derivado)}"


def verify_password(password: str, almacenado: str) -> bool:
    """Verifica ``password`` contra el hash serializado (comparación en tiempo constante).

    Tolerante a un hash mal formado (devuelve ``False`` en vez de lanzar): un registro
    corrupto no debe colgar el login.
    """
    try:
        etiqueta, n_s, r_s, p_s, salt_b64, hash_b64 = almacenado.split("$")
        if etiqueta != "scrypt":
            return False
        n, r, p = int(n_s), int(r_s), int(p_s)
        salt = _b64d(salt_b64)
        esperado = _b64d(hash_b64)
    except (ValueError, AttributeError):
        return False
    derivado = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=len(esperado)
    )
    return hmac.compare_digest(derivado, esperado)


# ---------------------------------------------------------------------------
# Token de sesión firmado (HMAC-SHA256, autocontenido)
# ---------------------------------------------------------------------------
def _firmar(mensaje: bytes, secret: str) -> str:
    firma = hmac.new(secret.encode("utf-8"), mensaje, hashlib.sha256).digest()
    return _b64e(firma)


def crear_token(*, subject: str, secret: str, ttl_segundos: int, ahora: int | None = None) -> str:
    """Emite un token firmado para ``subject`` (id de usuario), válido ``ttl_segundos``.

    El cuerpo lleva ``sub``, ``iat`` (emisión) y ``exp`` (expiración). Va firmado con
    HMAC-SHA256 sobre el cuerpo codificado: cualquier manipulación invalida la firma.
    """
    emitido = int(time.time()) if ahora is None else ahora
    cuerpo = {"sub": subject, "iat": emitido, "exp": emitido + ttl_segundos}
    cuerpo_b64 = _b64e(json.dumps(cuerpo, separators=(",", ":")).encode("utf-8"))
    firma_b64 = _firmar(cuerpo_b64.encode("ascii"), secret)
    return f"{cuerpo_b64}.{firma_b64}"


def verificar_token(token: str, secret: str, *, ahora: int | None = None) -> dict[str, Any] | None:
    """Verifica firma y expiración. Devuelve el cuerpo ``{sub, iat, exp}`` o ``None``.

    ``None`` ante: formato inválido, firma que no coincide (token manipulado o secreto
    distinto) o token expirado. Nunca lanza: una credencial inválida no es un error del
    servidor sino un rechazo de acceso (lo traduce la capa API a 401).
    """
    try:
        cuerpo_b64, firma_b64 = token.split(".")
    except (ValueError, AttributeError):
        return None
    esperada = _firmar(cuerpo_b64.encode("ascii"), secret)
    if not hmac.compare_digest(firma_b64, esperada):
        return None
    try:
        cuerpo = json.loads(_b64d(cuerpo_b64))
    except (ValueError, json.JSONDecodeError):
        return None
    momento = int(time.time()) if ahora is None else ahora
    if int(cuerpo.get("exp", 0)) < momento:
        return None
    return cuerpo
