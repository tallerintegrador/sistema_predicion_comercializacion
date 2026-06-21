"""Pruebas unitarias de las primitivas de seguridad (ADR-0014).

No tocan FastAPI ni la base: solo hashing de contraseñas y tokens firmados.
"""

from __future__ import annotations

from spc.service import permisos
from spc.service.seguridad import (
    crear_token,
    hash_password,
    verificar_token,
    verify_password,
)


def test_hash_password_no_guarda_la_contraseña_en_claro() -> None:
    hashed = hash_password("256317")
    assert "256317" not in hashed
    assert hashed.startswith("scrypt$")


def test_verify_password_acepta_la_correcta_y_rechaza_la_incorrecta() -> None:
    hashed = hash_password("clave-secreta")
    assert verify_password("clave-secreta", hashed) is True
    assert verify_password("otra-clave", hashed) is False


def test_hash_password_usa_sal_distinta_por_llamada() -> None:
    # Dos hashes de la misma contraseña difieren (sal aleatoria), pero ambos verifican.
    a = hash_password("igual")
    b = hash_password("igual")
    assert a != b
    assert verify_password("igual", a)
    assert verify_password("igual", b)


def test_verify_password_tolera_hash_malformado() -> None:
    assert verify_password("x", "no-es-un-hash") is False
    assert verify_password("x", "") is False


def test_token_valido_se_verifica_y_devuelve_el_subject() -> None:
    token = crear_token(subject="256317", secret="s3cr3t", ttl_segundos=3600, ahora=1_000)
    cuerpo = verificar_token(token, "s3cr3t", ahora=1_500)
    assert cuerpo is not None
    assert cuerpo["sub"] == "256317"


def test_token_con_secreto_distinto_es_rechazado() -> None:
    token = crear_token(subject="u", secret="s3cr3t", ttl_segundos=3600, ahora=1_000)
    assert verificar_token(token, "otro-secreto", ahora=1_500) is None


def test_token_expirado_es_rechazado() -> None:
    token = crear_token(subject="u", secret="s3cr3t", ttl_segundos=100, ahora=1_000)
    assert verificar_token(token, "s3cr3t", ahora=2_000) is None


def test_token_manipulado_es_rechazado() -> None:
    token = crear_token(subject="u", secret="s3cr3t", ttl_segundos=3600, ahora=1_000)
    cuerpo_b64, firma = token.split(".")
    manipulado = cuerpo_b64 + "x." + firma
    assert verificar_token(manipulado, "s3cr3t", ahora=1_500) is None


def test_catalogo_permisos_incluye_modulos_y_acciones() -> None:
    claves = permisos.claves_validas()
    # Los módulos derivan del catálogo de dominios; las acciones son fijas.
    assert "module:sales" in claves
    assert "action:forecast" in claves
    assert "action:users_manage" in claves
    # El rol administrador recibe TODO el vocabulario.
    assert set(permisos.permisos_administrador()) == claves
