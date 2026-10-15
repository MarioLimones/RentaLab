import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient

from alembic import command

# Explicit test credentials also let the module-level ASGI app validate its config.
# This low-cost hash belongs only to disposable test databases.
TEST_USERNAME = "demo-operator"
TEST_PASSWORD = "phase6-test-password"
TEST_PASSWORD_HASH = (
    "$argon2id$v=19$m=1024,t=1,p=1$M0uxu008I9cVMtVI1lJVIw$"
    "TWtoGdyQCFGn+imYQmWNS0CGuDzuMqgyVlKVyZeVvn4"
)
TEST_SESSION_SECRET = "explicit-test-session-secret-at-least-32-characters"
os.environ["RENTALAB_OPERATOR_USERNAME"] = TEST_USERNAME
os.environ["RENTALAB_OPERATOR_PASSWORD_HASH"] = TEST_PASSWORD_HASH
os.environ["RENTALAB_SESSION_SECRET"] = TEST_SESSION_SECRET

from rentalab.config import Settings  # noqa: E402
from rentalab.main import create_app  # noqa: E402


def authenticate(test_client: TestClient) -> None:
    csrf = test_client.get("/api/auth/csrf")
    assert csrf.status_code == 200
    login = test_client.post(
        "/api/auth/login",
        json={"username": TEST_USERNAME, "password": TEST_PASSWORD},
        headers={"X-CSRF-Token": csrf.json()["csrf_token"]},
    )
    assert login.status_code == 200
    # Login rotates the anonymous session and its CSRF token.
    refreshed = test_client.get("/api/auth/csrf")
    assert refreshed.status_code == 200
    test_client.headers["X-CSRF-Token"] = refreshed.json()["csrf_token"]


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        database_url=f"sqlite:///{(tmp_path / 'test.sqlite3').as_posix()}",
        environment="test",
    )


@pytest.fixture
def app(settings: Settings) -> Iterator[FastAPI]:
    application = create_app(settings)
    backend_root = Path(__file__).resolve().parents[1]
    config = Config(str(backend_root / "alembic.ini"))
    config.set_main_option("script_location", str(backend_root / "alembic"))
    config.set_main_option("sqlalchemy.url", settings.database_url)
    with application.state.engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    yield application
    application.state.engine.dispose()


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        authenticate(test_client)
        yield test_client


@pytest.fixture
def equipment_payload() -> dict[str, object]:
    return {
        "code": "CAM-001",
        "name": "Cámara de prueba",
        "category": "Cámaras",
        "description": "Unidad ficticia para las pruebas",
        "active": True,
    }
