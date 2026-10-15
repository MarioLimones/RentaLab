import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError

from rentalab import start
from rentalab.auth.schemas import RegisterRequest
from rentalab.config import Settings
from rentalab.main import create_app


@pytest.fixture
def startup_settings(settings: Settings, tmp_path: Path) -> Settings:
    dist = tmp_path / "frontend" / "dist"
    dist.mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>RentaLab</title>", encoding="utf-8")
    return settings.model_copy(update={"frontend_dist": dist})


def test_startup_validates_auth_before_creating_or_migrating_database(
    startup_settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "not-created" / "rentalab.db"
    invalid = startup_settings.model_copy(
        update={"session_secret": SecretStr("invalid"), "database_url": f"sqlite:///{database}"}
    )
    migrated: list[str] = []
    monkeypatch.setattr(start.command, "upgrade", lambda *_args: migrated.append("upgrade"))
    with pytest.raises(ValueError, match="configuración de acceso"):
        start.prepare_startup(invalid)
    assert migrated == []
    assert not database.parent.exists()


def test_startup_applies_real_migrations_without_loading_demo_data(
    startup_settings: Settings,
) -> None:
    start.prepare_startup(startup_settings)
    database = Path(startup_settings.database_url.removeprefix("sqlite:///"))
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            "0011_booking_requests",
        )
        for table in (
            "equipment",
            "users",
            "reservations",
            "incidents",
            "auth_sessions",
            "booking_requests",
            "booking_request_reservations",
        ):
            assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone() == (0,)
        connection.execute(
            "INSERT INTO equipment (code, name, category, description, active) "
            "VALUES ('PERSIST-001', 'Equipo previo', 'Pruebas', '', 1)"
        )
    start.prepare_startup(startup_settings)
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT code FROM equipment").fetchall() == [("PERSIST-001",)]


def test_restart_preserves_accounts_sessions_ownership_and_customer_reports(
    startup_settings: Settings,
) -> None:
    """Recreate the app/engine over one migrated file, preserving signed-cookie sessions."""
    start.prepare_startup(startup_settings)
    database = Path(startup_settings.database_url.removeprefix("sqlite:///"))
    password = "restart-only-fictitious-password"
    application = create_app(startup_settings)
    administrator = application.state.auth_service.register(
        RegisterRequest(name="Administración", email="admin@example.test", password=password),
        role="admin",
    )

    def login(browser: TestClient, email: str) -> None:
        token = browser.get("/api/auth/csrf").json()["csrf_token"]
        response = browser.post(
            "/api/auth/login",
            json={"username": email, "password": password},
            headers={"X-CSRF-Token": token},
        )
        assert response.status_code == 200
        browser.headers["X-CSRF-Token"] = browser.get("/api/auth/csrf").json()["csrf_token"]

    with TestClient(application) as admin, TestClient(application) as customer:
        login(admin, administrator.email)
        token = customer.get("/api/auth/csrf").json()["csrf_token"]
        response = customer.post(
            "/api/auth/register",
            json={"name": "Cliente", "email": "customer@example.test", "password": password},
            headers={"X-CSRF-Token": token},
        )
        assert response.status_code == 201
        owner_id = response.json()["id"]
        login(customer, "customer@example.test")
        unit = admin.post(
            "/api/equipment", json={"code": "PERSIST", "name": "Cámara", "category": "Vídeo"}
        )
        assert unit.status_code == 201
        first_day = date.today() + timedelta(days=20)
        reservation = customer.post(
            "/api/me/reservations",
            json={
                "equipment_id": unit.json()["id"],
                "start_date": first_day.isoformat(),
                "end_date": (first_day + timedelta(days=2)).isoformat(),
            },
        )
        assert reservation.status_code == 201
        reservation_id = reservation.json()["id"]
        report = customer.post(
            f"/api/me/reservations/{reservation_id}/incidents",
            json={"title": "Aviso persistente", "description": "Descripción del cliente"},
        )
        assert report.status_code == 201
        incident_id = report.json()["id"]
        managed = admin.patch(
            f"/api/incidents/{incident_id}",
            json={
                "blocking": True,
                "public_response": "Revisaremos el equipo",
                "internal_notes": "Sólo administración",
            },
        )
        assert managed.status_code == 200
        admin_cookies = dict(admin.cookies)
        customer_cookies = dict(customer.cookies)
        tables = ("equipment", "users", "reservations", "incidents", "auth_sessions")
        with sqlite3.connect(database) as connection:
            before = {
                table: connection.execute(f"SELECT * FROM {table} ORDER BY id").fetchall()
                for table in tables
            }
    # prepare_startup is the same entry point used by the container before every HTTP start.
    start.prepare_startup(startup_settings)
    restarted = create_app(startup_settings)
    with (
        TestClient(restarted, cookies=admin_cookies) as admin,
        TestClient(restarted, cookies=customer_cookies) as customer,
    ):
        with sqlite3.connect(database) as connection:
            for table, expected in before.items():
                assert (
                    connection.execute(f"SELECT * FROM {table} ORDER BY id").fetchall() == expected
                )
            assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
            assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert admin.get("/api/auth/session").json()["role"] == "admin"
        assert customer.get("/api/auth/session").json()["user"]["id"] == owner_id
        own = customer.get(f"/api/me/reservations/{reservation_id}")
        assert own.status_code == 200
        assert own.json() == reservation.json()
        global_reservation = admin.get(f"/api/reservations/{reservation_id}").json()
        assert global_reservation["customer_user_id"] == owner_id
        assert global_reservation["origin"] == "portal"
        own_report = customer.get(f"/api/me/incidents/{incident_id}")
        assert own_report.status_code == 200
        assert own_report.json()["public_response"] == "Revisaremos el equipo"
        assert "internal_notes" not in own_report.json()
        incident = admin.get(f"/api/incidents/{incident_id}").json()
        assert incident["blocking"] is True
        assert incident["internal_notes"] == "Sólo administración"
        # A fresh login also proves that the password hashes, not just cookies, survived.
        login(customer, "customer@example.test")
        assert customer.get("/api/auth/session").json()["user"]["id"] == owner_id


@pytest.mark.parametrize(
    "database_url",
    ["sqlite:///:memory:", "postgresql://localhost/rentalab", "invalid-private-database-setting"],
)
def test_startup_requires_a_persistent_sqlite_file_before_migrating(
    startup_settings: Settings, monkeypatch: pytest.MonkeyPatch, database_url: str
) -> None:
    migrated: list[str] = []
    monkeypatch.setattr(start.command, "upgrade", lambda *_args: migrated.append("upgrade"))
    invalid = startup_settings.model_copy(update={"database_url": database_url})
    with pytest.raises(start.StartupError, match="SQLite"):
        start.prepare_startup(invalid)
    assert migrated == []


def test_startup_requires_frontend_build_before_migrating(
    startup_settings: Settings, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    migrated: list[str] = []
    monkeypatch.setattr(start.command, "upgrade", lambda *_args: migrated.append("upgrade"))
    missing = startup_settings.model_copy(update={"frontend_dist": tmp_path / "missing"})
    with pytest.raises(start.StartupError, match="frontend"):
        start.prepare_startup(missing)
    assert migrated == []


def test_unwritable_data_directory_stops_before_migrations(
    startup_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    migrated: list[str] = []

    def denied(*_args: object, **_kwargs: object) -> None:
        raise PermissionError("sensitive internal path")

    monkeypatch.setattr(start.tempfile, "NamedTemporaryFile", denied)
    monkeypatch.setattr(start.command, "upgrade", lambda *_args: migrated.append("upgrade"))
    with pytest.raises(start.StartupError, match="permisos") as error:
        start.prepare_startup(startup_settings)
    assert "sensitive internal path" not in str(error.value)
    assert migrated == []


def test_main_migrates_before_replacing_process_with_exactly_one_worker(
    startup_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = startup_settings.model_copy(update={"port": 8123, "forwarded_allow_ips": "10.0.0.1"})
    events: list[object] = []
    monkeypatch.setattr(start, "Settings", lambda: settings)
    monkeypatch.setattr(start, "prepare_startup", lambda _settings: events.append("migrated"))
    monkeypatch.setenv("WEB_CONCURRENCY", "8")

    def replace_process(executable: str, arguments: list[str]) -> None:
        assert events == ["migrated"]
        events.append((executable, arguments))

    monkeypatch.setattr(start.os, "execv", replace_process)
    assert start.main() == 0
    executable, arguments = events[1]
    assert executable == sys.executable
    assert arguments[:4] == [sys.executable, "-m", "uvicorn", "rentalab.main:app"]
    assert arguments[arguments.index("--host") + 1] == "0.0.0.0"
    assert arguments[arguments.index("--port") + 1] == "8123"
    assert arguments[arguments.index("--workers") + 1] == "1"
    assert arguments[arguments.index("--forwarded-allow-ips") + 1] == "10.0.0.1"
    assert "--reload" not in arguments
    assert "--proxy-headers" in arguments


def test_failed_migration_never_starts_http_and_does_not_print_internal_details(
    startup_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fail(*_args: object) -> None:
        raise RuntimeError("secret-internal-database-diagnostic")

    executed: list[object] = []
    monkeypatch.setattr(start, "Settings", lambda: startup_settings)
    monkeypatch.setattr(start.command, "upgrade", fail)
    monkeypatch.setattr(start.os, "execv", lambda *_args: executed.append("started"))
    assert start.main() == 1
    output = capsys.readouterr()
    assert "migraciones" in output.err
    assert "secret-internal" not in output.out + output.err
    assert "Traceback" not in output.err
    assert executed == []


def test_main_missing_configuration_has_a_generic_failure_before_side_effects(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    database = tmp_path / "missing" / "rentalab.db"
    monkeypatch.setattr(
        start,
        "Settings",
        lambda: Settings(
            _env_file=None,
            operator_username=None,
            operator_password_hash=None,
            session_secret=None,
            database_url=f"sqlite:///{database}",
        ),
    )
    assert start.main() == 1
    assert "configuración de acceso" in capsys.readouterr().err
    assert not database.parent.exists()


@pytest.mark.parametrize("port", [0, 65536])
def test_runtime_port_rejects_values_outside_tcp_range(port: int) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, port=port)


def test_runtime_settings_are_read_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RENTALAB_PORT", "8123")
    monkeypatch.setenv("RENTALAB_FORWARDED_ALLOW_IPS", "127.0.0.1,172.20.0.1")
    settings = Settings(_env_file=None)
    assert settings.port == 8123
    assert settings.forwarded_allow_ips == "127.0.0.1,172.20.0.1"
