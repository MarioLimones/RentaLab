import base64
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest
from alembic.config import Config
from argon2 import PasswordHasher
from conftest import PRUEBA_CONTRASENA_HASH, PRUEBA_NOMBRE_USUARIO
from fastapi import FastAPI
from fastapi.testclient import TestClient
from itsdangerous import TimestampSigner
from sqlalchemy import select, text

from alembic import command
from rentalab.autenticacion.modelos import Usuario
from rentalab.base_datos import crear_base_datos_motor
from rentalab.compatibilidad import alias_json
from rentalab.configuracion import Configuracion
from rentalab.principal import crear_aplicacion

CONTRASENA = "customer-only-test-password"
REGISTRO = {
    "name": "  Alicia Prueba  ",
    "email": "  ALICIA@Example.TEST  ",
    "password": CONTRASENA,
}


def token(navegador: TestClient) -> str:
    return navegador.get("/api/auth/csrf").json()["csrf_token"]


def registrar(navegador: TestClient, **cambios: object):
    return navegador.post(
        "/api/auth/register",
        json={**REGISTRO, **{alias_json(clave): valor for clave, valor in cambios.items()}},
        headers={"X-CSRF-Token": token(navegador)},
    )


def iniciar_sesion(
    navegador: TestClient,
    *,
    nombre_usuario: str = "ALICIA@example.test",
    contrasena: str = CONTRASENA,
):
    return navegador.post(
        "/api/auth/login",
        json={"username": nombre_usuario, "password": contrasena},
        headers={"X-CSRF-Token": token(navegador)},
    )


def test_registrar_persiste_normalizado_cliente_y_solo_contrasena_hash(
    aplicacion: FastAPI,
) -> None:
    with TestClient(aplicacion) as navegador:
        respuesta = registrar(navegador)
        assert respuesta.status_code == 201
        usuario = respuesta.json()
        assert usuario == {
            "id": 1,
            "name": "Alicia Prueba",
            "email": "alicia@example.test",
            "role": "customer",
            "active": True,
        }
        assert "password" not in respuesta.text
        assert navegador.get("/api/auth/session").status_code == 401
    with aplicacion.state.fabrica_sesiones() as base_datos_sesion:
        registro = base_datos_sesion.get(Usuario, usuario["id"])
        assert registro.hash_contrasena.startswith("$argon2id$")
        assert registro.hash_contrasena != CONTRASENA
        assert PasswordHasher().verify(registro.hash_contrasena, CONTRASENA)


@pytest.mark.parametrize(
    "correo", ["alicia@example.test", "ALICIA@EXAMPLE.TEST", " alicia@Example.Test "]
)
def test_correo_unicidad_usa_normalizado_direccion(aplicacion: FastAPI, correo: str) -> None:
    with TestClient(aplicacion) as navegador:
        assert registrar(navegador).status_code == 201
        assert registrar(navegador, correo=correo).status_code == 409
    with aplicacion.state.fabrica_sesiones() as base_datos_sesion:
        assert len(base_datos_sesion.scalars(select(Usuario)).all()) == 1


@pytest.mark.parametrize(
    "adicional",
    [
        {"role": "admin"},
        {"role": "customer"},
        {"active": False},
        {"id": 1},
        {"password_hash": PRUEBA_CONTRASENA_HASH},
        {"customer_user_id": 1},
    ],
)
def test_registrar_rechaza_cualquier_administrativa_o_desconocido_campo(
    aplicacion: FastAPI, adicional: dict
) -> None:
    with TestClient(aplicacion) as navegador:
        respuesta = registrar(navegador, **adicional)
        assert respuesta.status_code == 422
        assert CONTRASENA not in respuesta.text
        assert PRUEBA_CONTRASENA_HASH not in respuesta.text
    with aplicacion.state.fabrica_sesiones() as base_datos_sesion:
        assert base_datos_sesion.scalar(select(Usuario.id)) is None


@pytest.mark.parametrize(
    "cambios",
    [
        {"password": "tinyXYZ"},
        {"password": "x" * 1025},
        {"email": "invalid"},
        {"name": " "},
        {"name": "bad\x00name"},
        {"password": None},
    ],
)
def test_registrar_validacion_nunca_refleja_contrasena(aplicacion: FastAPI, cambios: dict) -> None:
    with TestClient(aplicacion) as navegador:
        respuesta = registrar(navegador, **cambios)
        assert respuesta.status_code == 422
        assert "input" not in respuesta.json()["detail"][0]
        assert "password_hash" not in respuesta.text
        if isinstance(cambios.get("password"), str):
            assert cambios["password"] not in respuesta.text


@pytest.mark.parametrize("csrf", [None, "incorrect"])
def test_registro_requiere_csrf_y_crea_nada(aplicacion: FastAPI, csrf: str | None) -> None:
    with TestClient(aplicacion) as navegador:
        token(navegador)
        respuesta = navegador.post(
            "/api/auth/register",
            json=REGISTRO,
            headers={} if csrf is None else {"X-CSRF-Token": csrf},
        )
        assert respuesta.status_code == 403
    with aplicacion.state.fabrica_sesiones() as base_datos_sesion:
        assert base_datos_sesion.scalar(select(Usuario.id)) is None


def test_cliente_iniciar_sesion_renueva_csrf_cookie_y_cerrar_sesion_revoca_copiada_cookie(
    aplicacion: FastAPI,
) -> None:
    with TestClient(aplicacion) as navegador:
        usuario = registrar(navegador).json()
        anterior_token = token(navegador)
        respuesta = iniciar_sesion(navegador)
        assert respuesta.status_code == 200
        assert respuesta.json()["role"] == "customer"
        assert respuesta.json()["user"] == usuario
        assert respuesta.json()["username"] == "alicia@example.test"
        assert datetime.fromisoformat(respuesta.json()["expires_at"]).tzinfo is not None
        assert navegador.get("/api/auth/session").json() == respuesta.json()
        assert token(navegador) != anterior_token
        copiada_cookie = navegador.cookies.get("rentalab_session")
        contenido_envio = json.loads(base64.b64decode(copiada_cookie.split(".")[0]))
        assert set(contenido_envio) == {"sid", "csrf"}
        assert (
            navegador.post("/api/auth/logout", headers={"X-CSRF-Token": anterior_token}).status_code
            == 403
        )
        assert (
            navegador.post(
                "/api/auth/logout", headers={"X-CSRF-Token": token(navegador)}
            ).status_code
            == 200
        )
    with TestClient(aplicacion) as repetir:
        repetir.cookies.set("rentalab_session", copiada_cookie)
        assert repetir.get("/api/auth/session").status_code == 401


def test_persistente_cliente_sesion_tiene_absoluto_servidor_caducidad(
    aplicacion: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with TestClient(aplicacion) as navegador:
        registrar(navegador)
        respuesta = iniciar_sesion(navegador)
        caducidad = int(datetime.fromisoformat(respuesta.json()["expires_at"]).timestamp())
        monkeypatch.setattr(
            "rentalab.autenticacion.servicio.actual_marca_temporal", lambda: caducidad - 1
        )
        assert navegador.get("/api/auth/session").json() == respuesta.json()
        monkeypatch.setattr(
            "rentalab.autenticacion.servicio.actual_marca_temporal", lambda: caducidad
        )
        assert navegador.get("/api/auth/session").status_code == 401


def test_desactivar_usuario_revoca_sesion_y_rechaza_nuevo_iniciar_sesion(
    aplicacion: FastAPI,
) -> None:
    with TestClient(aplicacion) as navegador:
        usuario = registrar(navegador).json()
        assert iniciar_sesion(navegador).status_code == 200
        with aplicacion.state.fabrica_sesiones.begin() as base_datos_sesion:
            base_datos_sesion.get(Usuario, usuario["id"]).activo = False
        assert navegador.get("/api/auth/session").status_code == 401
        assert iniciar_sesion(navegador).status_code == 401


def test_contrasena_cambiar_revoca_existentes_sesion(aplicacion: FastAPI) -> None:
    with TestClient(aplicacion) as navegador:
        usuario = registrar(navegador).json()
        assert iniciar_sesion(navegador).status_code == 200
        with aplicacion.state.fabrica_sesiones.begin() as base_datos_sesion:
            base_datos_sesion.get(Usuario, usuario["id"]).hash_contrasena = PasswordHasher().hash(
                "new-test-password"
            )
        assert navegador.get("/api/auth/session").status_code == 401
        assert iniciar_sesion(navegador).status_code == 401
        assert iniciar_sesion(navegador, contrasena="new-test-password").status_code == 200


def test_persistidos_cuentas_funcionar_sin_heredado_operador(
    aplicacion: FastAPI, ajustes: Configuracion
) -> None:
    persistente_solo = crear_aplicacion(
        ajustes.model_copy(
            update={
                "usuario_operador": None,
                "hash_contrasena_operador": None,
            }
        )
    )
    try:
        with TestClient(persistente_solo) as navegador:
            assert registrar(navegador).status_code == 201
            assert iniciar_sesion(navegador).status_code == 200
            assert navegador.get("/api/auth/session").json()["user"]["role"] == "customer"
    finally:
        persistente_solo.state.motor.dispose()


def test_registro_reserva_un_correo_usado_por_la_heredado_operador(
    aplicacion: FastAPI,
    ajustes: Configuracion,
) -> None:
    heredado_correo_aplicacion = crear_aplicacion(
        ajustes.model_copy(
            update={
                "usuario_operador": "ALICIA@example.test",
            }
        )
    )
    try:
        with TestClient(heredado_correo_aplicacion) as navegador:
            assert registrar(navegador).status_code == 409
        with aplicacion.state.fabrica_sesiones() as base_datos_sesion:
            assert base_datos_sesion.scalar(select(Usuario.id)) is None
    finally:
        heredado_correo_aplicacion.state.motor.dispose()


def test_operador_anterior_responde_como_administrador_sin_usuario_persistente(
    cliente_http: TestClient,
) -> None:
    respuesta = cliente_http.get("/api/auth/session").json()
    assert respuesta["username"] == PRUEBA_NOMBRE_USUARIO
    assert respuesta["role"] == "admin"
    assert respuesta["user"] is None


def test_aprovisionar_cli_crea_administrador_y_repetible_demostracion_sin_exponer_contrasenas(
    aplicacion: FastAPI,
    ajustes: Configuracion,
) -> None:
    entorno = {
        **os.environ,
        "RENTALAB_DATABASE_URL": ajustes.url_base_datos,
        "RENTALAB_TEST_PROVISION_PASSWORD": CONTRASENA,
    }
    base = [sys.executable, "-m", "rentalab.autenticacion.gestionar_usuarios"]
    administrador_argumentos = [
        "create-admin",
        "--name",
        "Admin de prueba",
        "--email",
        "ADMIN@example.test",
        "--password-env",
        "RENTALAB_TEST_PROVISION_PASSWORD",
    ]
    demostracion_argumentos = ["demo-users", "--password-env", "RENTALAB_TEST_PROVISION_PASSWORD"]
    for argumentos, esperado in [
        (administrador_argumentos, 0),
        (administrador_argumentos, 1),
        (demostracion_argumentos, 0),
        (demostracion_argumentos, 0),
    ]:
        resultado = subprocess.run(
            base + argumentos,
            env=entorno,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        assert resultado.returncode == esperado, resultado.stderr
        assert CONTRASENA not in resultado.stdout + resultado.stderr
        assert "$argon2" not in resultado.stdout + resultado.stderr
    with aplicacion.state.fabrica_sesiones() as base_datos_sesion:
        usuarios = base_datos_sesion.scalars(select(Usuario).order_by(Usuario.correo)).all()
        assert len(usuarios) == 3
        assert {usuario.rol for usuario in usuarios} == {"admin", "customer"}
    with TestClient(aplicacion) as navegador:
        assert (
            iniciar_sesion(navegador, nombre_usuario="admin@example.test").json()["role"] == "admin"
        )
        assert navegador.get("/api/reservations").status_code == 200


def test_aprovisionar_cli_rechaza_secreto_argumento_sin_reflejando_ello() -> None:
    resultado = subprocess.run(
        [
            sys.executable,
            "-m",
            "rentalab.autenticacion.gestionar_usuarios",
            "demo-users",
            "--password",
            CONTRASENA,
        ],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert resultado.returncode == 2
    assert CONTRASENA not in resultado.stdout + resultado.stderr


def test_migracion_desde_0005_conserva_negocio_filas_y_heredado_sesiones(tmp_path: Path) -> None:
    servidor = Path(__file__).resolve().parents[1]
    configuracion = Config(str(servidor / "alembic.ini"))
    configuracion.set_main_option("script_location", str(servidor / "alembic"))
    url_base_datos = f"sqlite:///{(tmp_path / 'previous.sqlite3').as_posix()}"
    configuracion.set_main_option("sqlalchemy.url", url_base_datos)
    motor = crear_base_datos_motor(url_base_datos)
    with motor.begin() as conexion:
        configuracion.attributes["connection"] = conexion
        command.upgrade(configuracion, "0005_auth_sessions")
        conexion.execute(
            text(
                "INSERT INTO equipment (id,code,name,category) "
                "VALUES (41,'OLD-CAM','Equipo previo','Cámaras')"
            )
        )
        conexion.execute(
            text(
                "INSERT INTO reservations (id,equipment_id,customer_name,customer_email,"
                "start_date,end_date,status,external_reference) VALUES (52,41,'Cliente previo',"
                "'alicia@example.test','2026-11-10','2026-11-12','cancelled','CSV-HISTORICAL')"
            )
        )
        conexion.execute(
            text(
                "INSERT INTO incidents (id,equipment_id,title,blocking,status,resolution) "
                "VALUES (63,41,'Incidencia previa',1,'resolved','Reparada')"
            )
        )
        conexion.execute(
            text(
                "INSERT INTO auth_sessions (id,expires_at,credential_version) "
                "VALUES (:sid,2000000000,:version)"
            ),
            {
                "sid": "a" * 64,
                "version": hashlib.sha256(
                    json.dumps([PRUEBA_NOMBRE_USUARIO, PRUEBA_CONTRASENA_HASH]).encode("utf-8")
                ).hexdigest(),
            },
        )
        antes = {
            tabla: [
                dict(fila) for fila in conexion.execute(text(f"SELECT * FROM {tabla}")).mappings()
            ]
            for tabla in ("equipment", "reservations", "incidents", "auth_sessions")
        }
        command.upgrade(configuracion, "head")
        for tabla, antiguo_filas in antes.items():
            despues = [
                dict(fila) for fila in conexion.execute(text(f"SELECT * FROM {tabla}")).mappings()
            ]
            for real, esperado in zip(despues, antiguo_filas, strict=True):
                assert {clave: real[clave] for clave in esperado} == esperado
        assert (
            conexion.scalar(text("SELECT customer_user_id FROM reservations WHERE id=52")) is None
        )
        assert conexion.scalar(text("SELECT author_user_id FROM incidents WHERE id=63")) is None
        assert conexion.scalar(text("SELECT user_id FROM auth_sessions")) is None
        assert conexion.execute(text("PRAGMA foreign_key_check")).all() == []
        assert conexion.scalar(text("PRAGMA integrity_check")) == "ok"
        command.check(configuracion)
    motor.dispose()
    # La cookie y su huella usan exactamente el formato anterior a 0006; la migración debe
    # conservar las sesiones.
    migrada_configuracion = Configuracion(url_base_datos=url_base_datos, entorno="test")
    migrada = crear_aplicacion(migrada_configuracion)
    cookie_contenido_envio = base64.b64encode(
        json.dumps({"sid": "a" * 64, "csrf": "c" * 64}).encode()
    )
    cookie = (
        TimestampSigner(migrada_configuracion.secreto_sesion.get_secret_value())
        .sign(cookie_contenido_envio)
        .decode()
    )
    try:
        with TestClient(migrada) as navegador:
            navegador.cookies.set("rentalab_session", cookie)
            assert navegador.get("/api/auth/session").json()["role"] == "admin"
            assert navegador.get("/api/reservations").json()[0]["id"] == 52
    finally:
        migrada.state.motor.dispose()


def test_registrar_hace_no_apropiarse_correo_coincidente_historico_reserva(
    aplicacion: FastAPI,
    cliente_http: TestClient,
    equipo_contenido_envio: dict,
) -> None:
    equipo = cliente_http.post("/api/equipment", json=equipo_contenido_envio).json()
    reserva = cliente_http.post(
        "/api/reservations",
        json={
            "equipment_id": equipo["id"],
            "customer_name": "Sin cuenta",
            "customer_email": "alicia@example.test",
            "start_date": "2026-12-10",
            "end_date": "2026-12-12",
        },
    ).json()
    with TestClient(aplicacion) as navegador:
        assert registrar(navegador).status_code == 201
        assert iniciar_sesion(navegador).status_code == 200
        assert navegador.get(f"/api/me/reservations/{reserva['id']}").status_code == 404
    with aplicacion.state.fabrica_sesiones() as base_datos_sesion:
        assert base_datos_sesion.scalar(text("SELECT customer_user_id FROM reservations")) is None
