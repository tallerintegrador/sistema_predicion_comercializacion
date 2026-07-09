"""Tests del restablecimiento de contraseña por correo (endpoints públicos /auth/forgot y /auth/reset).

Control de acceso ACTIVO con base de auth temporal (admins sembrados). El envío SMTP está
deshabilitado por defecto (sin ``SPC_SMTP_HOST``): el enlace se registra en el log, así que
para probar ``/auth/reset`` generamos el token de reset directamente con la primitiva de
seguridad (lo mismo que pondría el correo).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from spc.api.main import crear_app
from spc.config import auth_reset_ttl, auth_secret
from spc.service.repositorio_auth import RepositorioAuth
from spc.service.seguridad import crear_token_reset


@pytest.fixture
def auth_client(tmp_path, monkeypatch):
    monkeypatch.setenv("SPC_AUTH_ENABLED", "1")
    monkeypatch.setenv("SPC_AUTH_SECRET", "secreto-de-prueba")
    repo = RepositorioAuth.crear(tmp_path / "auth.db")
    app = crear_app(auth_repo=repo, client_models_dir=tmp_path / "clientes")
    with TestClient(app) as c:
        c.repo = repo  # type: ignore[attr-defined]
        yield c


def _login(client: TestClient, user_id: str, password: str) -> str:
    r = client.post("/auth/login", json={"user_id": user_id, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _crear_usuario_con_email(client: TestClient, user_id: str, email: str) -> None:
    admin = _login(client, "256317", "256317")
    rid = client.get("/auth/me", headers={"Authorization": f"Bearer {admin}"}).json()["role_id"]
    r = client.post(
        "/users",
        json={"user_id": user_id, "password": "clave123", "role_id": rid, "email": email},
        headers={"Authorization": f"Bearer {admin}"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["email"] == email.lower()


def _token_reset(client: TestClient, user_id: str) -> str:
    ph = client.repo.obtener_password_hash(user_id)  # type: ignore[attr-defined]
    return crear_token_reset(
        subject=user_id, password_hash=ph, secret=auth_secret(), ttl_segundos=auth_reset_ttl()
    )


def test_forgot_responde_generico_para_cuenta_existente(auth_client) -> None:
    _crear_usuario_con_email(auth_client, "u1", "Juan@Example.com")
    r = auth_client.post("/auth/forgot", json={"email": "juan@example.com"})
    assert r.status_code == 200
    assert "message" in r.json()


def test_forgot_no_revela_cuenta_inexistente(auth_client) -> None:
    r = auth_client.post("/auth/forgot", json={"email": "nadie@x.com"})
    assert r.status_code == 200  # mismo cuerpo genérico, sin filtrar existencia


def test_reset_cambia_password_y_permite_login(auth_client) -> None:
    _crear_usuario_con_email(auth_client, "u2", "u2@x.com")
    token = _token_reset(auth_client, "u2")
    r = auth_client.post("/auth/reset", json={"token": token, "new_password": "nuevaClave9"})
    assert r.status_code == 200, r.text
    # La contraseña vieja ya no sirve; la nueva sí.
    assert auth_client.post("/auth/login", json={"user_id": "u2", "password": "clave123"}).status_code == 401
    assert _login(auth_client, "u2", "nuevaClave9")


def test_token_de_reset_es_de_un_solo_uso(auth_client) -> None:
    _crear_usuario_con_email(auth_client, "u3", "u3@x.com")
    token = _token_reset(auth_client, "u3")
    assert auth_client.post("/auth/reset", json={"token": token, "new_password": "claveNueva1"}).status_code == 200
    # Reusar el mismo token (la contraseña ya cambió → huella no coincide) → 400.
    again = auth_client.post("/auth/reset", json={"token": token, "new_password": "otraMas2"})
    assert again.status_code == 400
    assert again.json()["error"]["type"] == "invalid_request"


def test_token_manipulado_es_rechazado(auth_client) -> None:
    _crear_usuario_con_email(auth_client, "u4", "u4@x.com")
    r = auth_client.post("/auth/reset", json={"token": "basura.invalida", "new_password": "clave1234"})
    assert r.status_code == 400
