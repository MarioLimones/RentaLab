import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient

from alembic import command

# Las credenciales de prueba permiten validar la configuración de la aplicación ASGI del módulo.
# Este hash de bajo coste pertenece exclusivamente a bases de datos de prueba desechables.
PRUEBA_NOMBRE_USUARIO = "demo-operator"
PRUEBA_CONTRASENA = "phase6-test-password"
PRUEBA_CONTRASENA_HASH = (
    "$argon2id$v=19$m=1024,t=1,p=1$M0uxu008I9cVMtVI1lJVIw$"
    "TWtoGdyQCFGn+imYQmWNS0CGuDzuMqgyVlKVyZeVvn4"
)
PRUEBA_SESION_SECRETO = "explicit-test-session-secret-at-least-32-characters"
os.environ["RENTALAB_OPERATOR_USERNAME"] = PRUEBA_NOMBRE_USUARIO
os.environ["RENTALAB_OPERATOR_PASSWORD_HASH"] = PRUEBA_CONTRASENA_HASH
os.environ["RENTALAB_SESSION_SECRET"] = PRUEBA_SESION_SECRETO

from rentalab.configuracion import Configuracion  # noqa: E402
from rentalab.principal import crear_aplicacion  # noqa: E402


def autenticar(test_cliente_http: TestClient) -> None:
    csrf = test_cliente_http.get("/api/auth/csrf")
    assert csrf.status_code == 200
    iniciar_sesion = test_cliente_http.post(
        "/api/auth/login",
        json={"username": PRUEBA_NOMBRE_USUARIO, "password": PRUEBA_CONTRASENA},
        headers={"X-CSRF-Token": csrf.json()["csrf_token"]},
    )
    assert iniciar_sesion.status_code == 200
    # El acceso renueva la sesión anónima y su token CSRF.
    renovado = test_cliente_http.get("/api/auth/csrf")
    assert renovado.status_code == 200
    test_cliente_http.headers["X-CSRF-Token"] = renovado.json()["csrf_token"]


@pytest.fixture
def ajustes(tmp_path: Path) -> Configuracion:
    return Configuracion(
        url_base_datos=f"sqlite:///{(tmp_path / 'test.sqlite3').as_posix()}",
        entorno="test",
    )


@pytest.fixture
def aplicacion(ajustes: Configuracion) -> Iterator[FastAPI]:
    aplicacion = crear_aplicacion(ajustes)
    servidor_raiz = Path(__file__).resolve().parents[1]
    configuracion = Config(str(servidor_raiz / "alembic.ini"))
    configuracion.set_main_option("script_location", str(servidor_raiz / "alembic"))
    configuracion.set_main_option("sqlalchemy.url", ajustes.url_base_datos)
    with aplicacion.state.motor.begin() as conexion:
        configuracion.attributes["connection"] = conexion
        command.upgrade(configuracion, "head")
    yield aplicacion
    aplicacion.state.motor.dispose()


@pytest.fixture
def cliente_http(aplicacion: FastAPI) -> Iterator[TestClient]:
    with TestClient(aplicacion) as test_cliente_http:
        autenticar(test_cliente_http)
        yield test_cliente_http


@pytest.fixture
def equipo_contenido_envio() -> dict[str, object]:
    return {
        "code": "CAM-001",
        "name": "Cámara de prueba",
        "category": "Cámaras",
        "description": "Unidad ficticia para las pruebas",
        "active": True,
    }
