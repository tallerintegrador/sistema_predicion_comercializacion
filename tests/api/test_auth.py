"""Pruebas del **control de acceso por roles** (ADR-0014).

Activan ``SPC_AUTH_ENABLED`` (la suite previa lo desactiva por defecto) y construyen una
app con un repositorio de auth **temporal** (no toca el ``spc.db`` del repo). Cubren:
login, identidad, enforcement por endpoint (401/403), administración de roles/usuarios y
el onboarding del perfil de cliente. La predicción protegida se ejercita contra el
contrato 3×3 (``/v2/ventas``), que entrena en el momento (sin artefactos).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from spc.api.main import crear_app
from spc.service.repositorio_auth import RepositorioAuth
from spc.synthetic import generar_dominio


@pytest.fixture
def auth_client(tmp_path, monkeypatch):
    """`TestClient` con control de acceso ACTIVO y base de auth temporal (admins sembrados)."""
    monkeypatch.setenv("SPC_AUTH_ENABLED", "1")
    monkeypatch.setenv("SPC_AUTH_SECRET", "secreto-de-prueba")
    repo = RepositorioAuth.crear(tmp_path / "auth.db")
    app = crear_app(
        auth_repo=repo,
        client_models_dir=tmp_path / "clientes",
        cors_origins=["http://localhost:5173"],
    )
    with TestClient(app) as c:
        yield c


def _login(client: TestClient, user_id: str, password: str) -> str:
    r = client.post("/auth/login", json={"user_id": user_id, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _cuerpo_ventas() -> dict:
    """Cuerpo válido de ``/v2/ventas`` (filas pequeñas del formato fijo del dominio)."""
    df = generar_dominio("ventas", seed=42, n_tiendas=2, n_productos=4, n_dias=120)
    df["fecha"] = df["fecha"].astype(str)
    return {"rows": df.to_dict(orient="records"), "horizon": 7}


# ---------------------------------------------------------------------------
# Login e identidad
# ---------------------------------------------------------------------------
def test_login_admin_sembrado(auth_client) -> None:
    r = auth_client.post("/auth/login", json={"user_id": "256317", "password": "256317"})
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["token_type"] == "bearer"
    assert cuerpo["user"]["role"] == "administrator"
    assert "action:users_manage" in cuerpo["user"]["permissions"]


def test_login_segundo_admin_sembrado(auth_client) -> None:
    assert _login(auth_client, "256370", "256370")


def test_login_password_incorrecta_es_401(auth_client) -> None:
    r = auth_client.post("/auth/login", json={"user_id": "256317", "password": "mala"})
    assert r.status_code == 401
    assert r.json()["error"]["type"] == "invalid_credentials"


def test_login_usuario_inexistente_es_401(auth_client) -> None:
    r = auth_client.post("/auth/login", json={"user_id": "000000", "password": "x"})
    assert r.status_code == 401
    assert r.json()["error"]["type"] == "invalid_credentials"


def test_me_sin_token_es_401(auth_client) -> None:
    r = auth_client.get("/auth/me")
    assert r.status_code == 401
    assert r.json()["error"]["type"] == "unauthorized"


def test_me_con_token_devuelve_identidad(auth_client) -> None:
    token = _login(auth_client, "256317", "256317")
    r = auth_client.get("/auth/me", headers=_auth(token))
    assert r.status_code == 200
    assert r.json()["user_id"] == "256317"


# ---------------------------------------------------------------------------
# Enforcement en endpoints existentes
# ---------------------------------------------------------------------------
def test_prediccion_sin_token_es_401(auth_client) -> None:
    r = auth_client.post("/v2/ventas", json=_cuerpo_ventas())
    assert r.status_code == 401


def test_admin_puede_predecir(auth_client) -> None:
    token = _login(auth_client, "256317", "256317")
    r = auth_client.post("/v2/ventas", json=_cuerpo_ventas(), headers=_auth(token))
    assert r.status_code == 200, r.text
    assert "regresion" in r.json()


def test_demo_sin_token_es_401(auth_client) -> None:
    assert auth_client.get("/v2/ventas/demo").status_code == 401


# ---------------------------------------------------------------------------
# Administración de roles y usuarios + autorización por permiso
# ---------------------------------------------------------------------------
def test_permisos_catalogo_para_admin(auth_client) -> None:
    token = _login(auth_client, "256317", "256317")
    r = auth_client.get("/permissions", headers=_auth(token))
    assert r.status_code == 200
    claves = {p["key"] for p in r.json()["permissions"]}
    assert "module:sales" in claves
    assert "action:forecast" in claves


def test_flujo_rol_restringido_y_autorizacion(auth_client) -> None:
    admin = _login(auth_client, "256317", "256317")

    # El admin crea un rol restringido (solo el permiso de catálogo, sin predicción).
    r = auth_client.post(
        "/roles",
        json={"name": "viewer", "description": "Solo lectura", "permissions": ["action:catalog"]},
        headers=_auth(admin),
    )
    assert r.status_code == 201, r.text
    role_id = r.json()["id"]

    # El admin crea un usuario con ese rol.
    r = auth_client.post(
        "/users",
        json={"user_id": "900001", "password": "secret123", "role_id": role_id},
        headers=_auth(admin),
    )
    assert r.status_code == 201, r.text
    assert r.json()["onboarding_done"] is False

    viewer = _login(auth_client, "900001", "secret123")

    # Puede consultar su propia identidad (autenticado)...
    assert auth_client.get("/auth/me", headers=_auth(viewer)).status_code == 200
    # ...pero no predecir (le faltan module:sales y action:forecast)...
    r = auth_client.post("/v2/ventas", json=_cuerpo_ventas(), headers=_auth(viewer))
    assert r.status_code == 403
    assert r.json()["error"]["type"] == "forbidden"
    # ...ni administrar usuarios.
    assert auth_client.get("/users", headers=_auth(viewer)).status_code == 403


def test_no_admin_no_puede_crear_roles(auth_client) -> None:
    admin = _login(auth_client, "256317", "256317")
    r = auth_client.post(
        "/roles", json={"name": "r1", "permissions": []}, headers=_auth(admin)
    )
    role_id = r.json()["id"]
    auth_client.post(
        "/users",
        json={"user_id": "900002", "password": "secret123", "role_id": role_id},
        headers=_auth(admin),
    )
    token = _login(auth_client, "900002", "secret123")
    r = auth_client.post("/roles", json={"name": "r2", "permissions": []}, headers=_auth(token))
    assert r.status_code == 403


def test_crear_rol_con_permiso_desconocido_es_400(auth_client) -> None:
    admin = _login(auth_client, "256317", "256317")
    r = auth_client.post(
        "/roles",
        json={"name": "malo", "permissions": ["action:inexistente"]},
        headers=_auth(admin),
    )
    assert r.status_code == 400
    assert r.json()["error"]["type"] == "invalid_request"


def test_crear_usuario_duplicado_es_409(auth_client) -> None:
    admin = _login(auth_client, "256317", "256317")
    rol = auth_client.get("/roles", headers=_auth(admin)).json()[0]["id"]
    auth_client.post(
        "/users",
        json={"user_id": "900003", "password": "secret123", "role_id": rol},
        headers=_auth(admin),
    )
    r = auth_client.post(
        "/users",
        json={"user_id": "900003", "password": "secret123", "role_id": rol},
        headers=_auth(admin),
    )
    assert r.status_code == 409


def test_no_se_puede_eliminar_el_rol_admin(auth_client) -> None:
    admin = _login(auth_client, "256317", "256317")
    roles = auth_client.get("/roles", headers=_auth(admin)).json()
    admin_role = next(r for r in roles if r["name"] == "administrator")
    r = auth_client.delete(f"/roles/{admin_role['id']}", headers=_auth(admin))
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# Onboarding del perfil de cliente
# ---------------------------------------------------------------------------
def test_onboarding_perfil(auth_client) -> None:
    admin = _login(auth_client, "256317", "256317")
    rol = auth_client.post(
        "/roles", json={"name": "negocio", "permissions": ["action:catalog"]}, headers=_auth(admin)
    ).json()["id"]
    auth_client.post(
        "/users",
        json={"user_id": "900010", "password": "secret123", "role_id": rol},
        headers=_auth(admin),
    )
    token = _login(auth_client, "900010", "secret123")

    # Antes del onboarding no hay perfil.
    assert auth_client.get("/profile", headers=_auth(token)).status_code == 404

    # Opciones servidas por el backend (no hardcodeadas en la UI).
    opciones = auth_client.get("/profile/options", headers=_auth(token)).json()
    assert "retail" in opciones["sectors"]

    # Guardar el onboarding marca onboarding_done y crea el perfil.
    r = auth_client.put(
        "/profile",
        json={
            "business_name": "Mi PyME",
            "sector": "retail",
            "size": "small",
            "region": "south_america",
            "currency": "PEN",
        },
        headers=_auth(token),
    )
    assert r.status_code == 200, r.text
    assert r.json()["business_name"] == "Mi PyME"
    assert auth_client.get("/auth/me", headers=_auth(token)).json()["onboarding_done"] is True
    assert auth_client.get("/profile", headers=_auth(token)).status_code == 200


def test_onboarding_con_opcion_invalida_es_400(auth_client) -> None:
    admin = _login(auth_client, "256317", "256317")
    rol = auth_client.post(
        "/roles", json={"name": "negocio2", "permissions": ["action:catalog"]}, headers=_auth(admin)
    ).json()["id"]
    auth_client.post(
        "/users",
        json={"user_id": "900011", "password": "secret123", "role_id": rol},
        headers=_auth(admin),
    )
    token = _login(auth_client, "900011", "secret123")
    r = auth_client.put(
        "/profile",
        json={
            "business_name": "X",
            "sector": "retail",
            "size": "small",
            "region": "south_america",
            "currency": "XYZ",
        },
        headers=_auth(token),
    )
    assert r.status_code == 400
