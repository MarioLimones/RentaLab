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
from conftest import TEST_PASSWORD_HASH, TEST_USERNAME
from fastapi import FastAPI
from fastapi.testclient import TestClient
from itsdangerous import TimestampSigner
from sqlalchemy import select, text

from alembic import command
from rentalab.auth.models import User
from rentalab.config import Settings
from rentalab.database import create_database_engine
from rentalab.main import create_app

PASSWORD = "customer-only-test-password"
REGISTRATION = {
    "name": "  Alicia Prueba  ",
    "email": "  ALICIA@Example.TEST  ",
    "password": PASSWORD,
}


def token(browser: TestClient) -> str:
    return browser.get("/api/auth/csrf").json()["csrf_token"]


def register(browser: TestClient, **changes: object):
    return browser.post(
        "/api/auth/register",
        json={**REGISTRATION, **changes},
        headers={"X-CSRF-Token": token(browser)},
    )


def login(browser: TestClient, *, username: str = "ALICIA@example.test", password: str = PASSWORD):
    return browser.post(
        "/api/auth/login",
        json={"username": username, "password": password},
        headers={"X-CSRF-Token": token(browser)},
    )


def test_register_persists_normalized_customer_and_only_password_hash(app: FastAPI) -> None:
    with TestClient(app) as browser:
        response = register(browser)
        assert response.status_code == 201
        user = response.json()
        assert user == {
            "id": 1,
            "name": "Alicia Prueba",
            "email": "alicia@example.test",
            "role": "customer",
            "active": True,
        }
        assert "password" not in response.text
        assert browser.get("/api/auth/session").status_code == 401
    with app.state.session_factory() as database_session:
        record = database_session.get(User, user["id"])
        assert record.password_hash.startswith("$argon2id$")
        assert record.password_hash != PASSWORD
        assert PasswordHasher().verify(record.password_hash, PASSWORD)


@pytest.mark.parametrize(
    "email", ["alicia@example.test", "ALICIA@EXAMPLE.TEST", " alicia@Example.Test "]
)
def test_email_uniqueness_uses_normalized_address(app: FastAPI, email: str) -> None:
    with TestClient(app) as browser:
        assert register(browser).status_code == 201
        assert register(browser, email=email).status_code == 409
    with app.state.session_factory() as database_session:
        assert len(database_session.scalars(select(User)).all()) == 1


@pytest.mark.parametrize(
    "extra",
    [
        {"role": "admin"},
        {"role": "customer"},
        {"active": False},
        {"id": 1},
        {"password_hash": TEST_PASSWORD_HASH},
        {"customer_user_id": 1},
    ],
)
def test_register_rejects_any_administrative_or_unknown_field(app: FastAPI, extra: dict) -> None:
    with TestClient(app) as browser:
        response = register(browser, **extra)
        assert response.status_code == 422
        assert PASSWORD not in response.text
        assert TEST_PASSWORD_HASH not in response.text
    with app.state.session_factory() as database_session:
        assert database_session.scalar(select(User.id)) is None


@pytest.mark.parametrize(
    "changes",
    [
        {"password": "tinyXYZ"},
        {"password": "x" * 1025},
        {"email": "invalid"},
        {"name": " "},
        {"name": "bad\x00name"},
        {"password": None},
    ],
)
def test_register_validation_never_reflects_password(app: FastAPI, changes: dict) -> None:
    with TestClient(app) as browser:
        response = register(browser, **changes)
        assert response.status_code == 422
        assert "input" not in response.json()["detail"][0]
        assert "password_hash" not in response.text
        if isinstance(changes.get("password"), str):
            assert changes["password"] not in response.text


@pytest.mark.parametrize("csrf", [None, "incorrect"])
def test_registration_requires_csrf_and_creates_nothing(app: FastAPI, csrf: str | None) -> None:
    with TestClient(app) as browser:
        token(browser)
        response = browser.post(
            "/api/auth/register",
            json=REGISTRATION,
            headers={} if csrf is None else {"X-CSRF-Token": csrf},
        )
        assert response.status_code == 403
    with app.state.session_factory() as database_session:
        assert database_session.scalar(select(User.id)) is None


def test_customer_login_rotates_csrf_cookie_and_logout_revokes_copied_cookie(app: FastAPI) -> None:
    with TestClient(app) as browser:
        user = register(browser).json()
        previous_token = token(browser)
        response = login(browser)
        assert response.status_code == 200
        assert response.json()["role"] == "customer"
        assert response.json()["user"] == user
        assert response.json()["username"] == "alicia@example.test"
        assert datetime.fromisoformat(response.json()["expires_at"]).tzinfo is not None
        assert browser.get("/api/auth/session").json() == response.json()
        assert token(browser) != previous_token
        copied_cookie = browser.cookies.get("rentalab_session")
        payload = json.loads(base64.b64decode(copied_cookie.split(".")[0]))
        assert set(payload) == {"sid", "csrf"}
        assert (
            browser.post("/api/auth/logout", headers={"X-CSRF-Token": previous_token}).status_code
            == 403
        )
        assert (
            browser.post("/api/auth/logout", headers={"X-CSRF-Token": token(browser)}).status_code
            == 200
        )
    with TestClient(app) as replay:
        replay.cookies.set("rentalab_session", copied_cookie)
        assert replay.get("/api/auth/session").status_code == 401


def test_persistent_customer_session_has_absolute_server_expiration(
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with TestClient(app) as browser:
        register(browser)
        response = login(browser)
        expiry = int(datetime.fromisoformat(response.json()["expires_at"]).timestamp())
        monkeypatch.setattr("rentalab.auth.service.current_timestamp", lambda: expiry - 1)
        assert browser.get("/api/auth/session").json() == response.json()
        monkeypatch.setattr("rentalab.auth.service.current_timestamp", lambda: expiry)
        assert browser.get("/api/auth/session").status_code == 401


def test_deactivating_user_revokes_session_and_rejects_new_login(app: FastAPI) -> None:
    with TestClient(app) as browser:
        user = register(browser).json()
        assert login(browser).status_code == 200
        with app.state.session_factory.begin() as database_session:
            database_session.get(User, user["id"]).active = False
        assert browser.get("/api/auth/session").status_code == 401
        assert login(browser).status_code == 401


def test_password_change_revokes_existing_session(app: FastAPI) -> None:
    with TestClient(app) as browser:
        user = register(browser).json()
        assert login(browser).status_code == 200
        with app.state.session_factory.begin() as database_session:
            database_session.get(User, user["id"]).password_hash = PasswordHasher().hash(
                "new-test-password"
            )
        assert browser.get("/api/auth/session").status_code == 401
        assert login(browser).status_code == 401
        assert login(browser, password="new-test-password").status_code == 200


def test_persisted_accounts_work_without_legacy_operator(app: FastAPI, settings: Settings) -> None:
    persistent_only = create_app(
        settings.model_copy(
            update={
                "operator_username": None,
                "operator_password_hash": None,
            }
        )
    )
    try:
        with TestClient(persistent_only) as browser:
            assert register(browser).status_code == 201
            assert login(browser).status_code == 200
            assert browser.get("/api/auth/session").json()["user"]["role"] == "customer"
    finally:
        persistent_only.state.engine.dispose()


def test_registration_reserves_an_email_used_by_the_legacy_operator(
    app: FastAPI,
    settings: Settings,
) -> None:
    legacy_email_app = create_app(
        settings.model_copy(
            update={
                "operator_username": "ALICIA@example.test",
            }
        )
    )
    try:
        with TestClient(legacy_email_app) as browser:
            assert register(browser).status_code == 409
        with app.state.session_factory() as database_session:
            assert database_session.scalar(select(User.id)) is None
    finally:
        legacy_email_app.state.engine.dispose()


def test_legacy_operator_response_is_explicitly_admin_with_no_persistent_user(
    client: TestClient,
) -> None:
    response = client.get("/api/auth/session").json()
    assert response["username"] == TEST_USERNAME
    assert response["role"] == "admin"
    assert response["user"] is None


def test_provision_cli_creates_admin_and_repeatable_demo_without_exposing_passwords(
    app: FastAPI,
    settings: Settings,
) -> None:
    environment = {
        **os.environ,
        "RENTALAB_DATABASE_URL": settings.database_url,
        "RENTALAB_TEST_PROVISION_PASSWORD": PASSWORD,
    }
    base = [sys.executable, "-m", "rentalab.auth.manage_users"]
    admin_args = [
        "create-admin",
        "--name",
        "Admin de prueba",
        "--email",
        "ADMIN@example.test",
        "--password-env",
        "RENTALAB_TEST_PROVISION_PASSWORD",
    ]
    demo_args = ["demo-users", "--password-env", "RENTALAB_TEST_PROVISION_PASSWORD"]
    for arguments, expected in [(admin_args, 0), (admin_args, 1), (demo_args, 0), (demo_args, 0)]:
        result = subprocess.run(
            base + arguments,
            env=environment,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        assert result.returncode == expected, result.stderr
        assert PASSWORD not in result.stdout + result.stderr
        assert "$argon2" not in result.stdout + result.stderr
    with app.state.session_factory() as database_session:
        users = database_session.scalars(select(User).order_by(User.email)).all()
        assert len(users) == 3
        assert {user.role for user in users} == {"admin", "customer"}
    with TestClient(app) as browser:
        assert login(browser, username="admin@example.test").json()["role"] == "admin"
        assert browser.get("/api/reservations").status_code == 200


def test_provision_cli_rejects_secret_argument_without_reflecting_it() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "rentalab.auth.manage_users", "demo-users", "--password", PASSWORD],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 2
    assert PASSWORD not in result.stdout + result.stderr


def test_migration_from_0005_conserves_business_rows_and_legacy_sessions(tmp_path: Path) -> None:
    backend = Path(__file__).resolve().parents[1]
    config = Config(str(backend / "alembic.ini"))
    config.set_main_option("script_location", str(backend / "alembic"))
    database_url = f"sqlite:///{(tmp_path / 'previous.sqlite3').as_posix()}"
    config.set_main_option("sqlalchemy.url", database_url)
    engine = create_database_engine(database_url)
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0005_auth_sessions")
        connection.execute(
            text(
                "INSERT INTO equipment (id,code,name,category) "
                "VALUES (41,'OLD-CAM','Equipo previo','Cámaras')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO reservations (id,equipment_id,customer_name,customer_email,"
                "start_date,end_date,status,external_reference) VALUES (52,41,'Cliente previo',"
                "'alicia@example.test','2026-11-10','2026-11-12','cancelled','CSV-HISTORICAL')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO incidents (id,equipment_id,title,blocking,status,resolution) "
                "VALUES (63,41,'Incidencia previa',1,'resolved','Reparada')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO auth_sessions (id,expires_at,credential_version) "
                "VALUES (:sid,2000000000,:version)"
            ),
            {
                "sid": "a" * 64,
                "version": hashlib.sha256(
                    json.dumps([TEST_USERNAME, TEST_PASSWORD_HASH]).encode("utf-8")
                ).hexdigest(),
            },
        )
        before = {
            table: [
                dict(row) for row in connection.execute(text(f"SELECT * FROM {table}")).mappings()
            ]
            for table in ("equipment", "reservations", "incidents", "auth_sessions")
        }
        command.upgrade(config, "head")
        for table, old_rows in before.items():
            after = [
                dict(row) for row in connection.execute(text(f"SELECT * FROM {table}")).mappings()
            ]
            for actual, expected in zip(after, old_rows, strict=True):
                assert {key: actual[key] for key in expected} == expected
        assert (
            connection.scalar(text("SELECT customer_user_id FROM reservations WHERE id=52")) is None
        )
        assert connection.scalar(text("SELECT author_user_id FROM incidents WHERE id=63")) is None
        assert connection.scalar(text("SELECT user_id FROM auth_sessions")) is None
        assert connection.execute(text("PRAGMA foreign_key_check")).all() == []
        assert connection.scalar(text("PRAGMA integrity_check")) == "ok"
        command.check(config)
    engine.dispose()
    # Cookie and fingerprint use the exact pre-0006 format; migration must not sign users out.
    migrated_settings = Settings(database_url=database_url, environment="test")
    migrated = create_app(migrated_settings)
    cookie_payload = base64.b64encode(json.dumps({"sid": "a" * 64, "csrf": "c" * 64}).encode())
    cookie = (
        TimestampSigner(migrated_settings.session_secret.get_secret_value())
        .sign(cookie_payload)
        .decode()
    )
    try:
        with TestClient(migrated) as browser:
            browser.cookies.set("rentalab_session", cookie)
            assert browser.get("/api/auth/session").json()["role"] == "admin"
            assert browser.get("/api/reservations").json()[0]["id"] == 52
    finally:
        migrated.state.engine.dispose()


def test_register_does_not_claim_email_matching_historical_reservation(
    app: FastAPI,
    client: TestClient,
    equipment_payload: dict,
) -> None:
    equipment = client.post("/api/equipment", json=equipment_payload).json()
    reservation = client.post(
        "/api/reservations",
        json={
            "equipment_id": equipment["id"],
            "customer_name": "Sin cuenta",
            "customer_email": "alicia@example.test",
            "start_date": "2026-12-10",
            "end_date": "2026-12-12",
        },
    ).json()
    with TestClient(app) as browser:
        assert register(browser).status_code == 201
        assert login(browser).status_code == 200
        assert browser.get(f"/api/me/reservations/{reservation['id']}").status_code == 404
    with app.state.session_factory() as database_session:
        assert database_session.scalar(text("SELECT customer_user_id FROM reservations")) is None
