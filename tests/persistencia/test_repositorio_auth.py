"""Tests del repositorio de auth (`spc.service.repositorio_auth`, ADR-0014/0026).

Verifican la siembra idempotente (rol administrador + cuentas DEMO 256317/256370 con la
contraseña hasheada), el ciclo de roles/usuarios y el perfil de onboarding, todo sobre
SQLite temporal. No prueban HTTP: eso vive en `tests/api/test_auth.py`.
"""

from __future__ import annotations

from spc.service.repositorio_auth import NOMBRE_ROL_ADMIN, RepositorioAuth
from spc.service.seguridad import verify_password


def test_siembra_admin_y_cuentas_demo(engine) -> None:
    repo = RepositorioAuth.desde_engine(engine)
    admin = repo.obtener_rol_por_nombre(NOMBRE_ROL_ADMIN)
    assert admin is not None
    assert len(admin.permissions) > 0  # el admin refleja el catálogo completo
    for uid in ("256317", "256370"):
        u = repo.obtener_usuario(uid)
        assert u is not None and u.is_active
        # Contraseña inicial = id, almacenada HASHEADA (no en claro).
        h = repo.obtener_password_hash(uid)
        assert h != uid
        assert verify_password(uid, h)


def test_siembra_es_idempotente(engine) -> None:
    RepositorioAuth.desde_engine(engine)
    repo2 = RepositorioAuth.desde_engine(engine)  # segunda siembra sobre la misma base
    # No se duplican las cuentas DEMO.
    ids = [u.user_id for u in repo2.listar_usuarios()]
    assert ids.count("256317") == 1
    assert ids.count("256370") == 1


def test_crear_y_actualizar_rol(engine) -> None:
    repo = RepositorioAuth.desde_engine(engine)
    rol = repo.crear_rol(name="ventas_only", description="Solo ventas", permissions=["ventas:leer"])
    assert rol.permissions == ["ventas:leer"]
    actualizado = repo.actualizar_rol(rol.id, permissions=["ventas:leer", "compras:leer"])
    assert set(actualizado.permissions) == {"ventas:leer", "compras:leer"}


def test_crear_usuario_hashea_password(engine) -> None:
    repo = RepositorioAuth.desde_engine(engine)
    rol = repo.crear_rol(name="r", description=None, permissions=[])
    repo.crear_usuario(user_id="u1", password="secreta", role_id=rol.id)
    h = repo.obtener_password_hash("u1")
    assert h != "secreta"
    assert verify_password("secreta", h)
    u = repo.obtener_usuario("u1")
    assert u.onboarding_done is False  # cuenta nueva: aún sin onboarding


def test_desactivar_usuario_y_contar_por_rol(engine) -> None:
    repo = RepositorioAuth.desde_engine(engine)
    rol = repo.crear_rol(name="r", description=None, permissions=[])
    repo.crear_usuario(user_id="u1", password="x", role_id=rol.id)
    assert repo.contar_usuarios_de_rol(rol.id) == 1
    repo.actualizar_usuario("u1", is_active=False)
    assert repo.obtener_usuario("u1").is_active is False


def test_guardar_y_leer_perfil(engine) -> None:
    repo = RepositorioAuth.desde_engine(engine)
    repo.guardar_perfil(
        client_id="cli-1", business_name="Bodega X", sector="retail",
        size="micro", region="La Libertad", currency="PEN", owner_user_id="u1",
    )
    perfil = repo.obtener_perfil("cli-1")
    assert perfil is not None
    assert perfil.business_name == "Bodega X"
    assert perfil.currency == "PEN"
