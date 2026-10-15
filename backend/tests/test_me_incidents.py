from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from pathlib import Path
from threading import Event
from typing import Any

import pytest
from alembic.config import Config
from conftest import TEST_PASSWORD, TEST_PASSWORD_HASH
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event, text
from sqlalchemy.engine import Connection, ExecutionContext
from sqlalchemy.exc import IntegrityError

from alembic import command
from rentalab.auth.models import User
from rentalab.config import Settings
from rentalab.database import create_database_engine
from rentalab.incidents.models import Incident
from rentalab.main import create_app
from rentalab.reservations.models import Reservation

REPORT = {"title": "  Conector suelto  ", "description": "  Se desconecta al mover el cable.  "}
CLIENT_FIELDS = {"id", "reservation_id", "title", "description", "status", "public_response"}


def login(browser: TestClient, email: str) -> None:
    csrf = browser.get("/api/auth/csrf").json()["csrf_token"]
    response = browser.post(
        "/api/auth/login",
        json={"username": email, "password": TEST_PASSWORD},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 200, response.text
    browser.headers["X-CSRF-Token"] = browser.get("/api/auth/csrf").json()["csrf_token"]


@pytest.fixture
def actors(app: FastAPI) -> Iterator[dict[str, Any]]:
    with app.state.session_factory.begin() as session:
        accounts = [
            User(
                name=name,
                email=email,
                password_hash=TEST_PASSWORD_HASH,
                role=role,
                active=True,
            )
            for name, email, role in (
                ("Alicia Ficticia", "alicia@example.test", "customer"),
                ("Bruno Ficticio", "bruno@example.test", "customer"),
                ("Administración Ficticia", "admin@example.test", "admin"),
            )
        ]
        session.add_all(accounts)
        session.flush()
        identifiers = [account.id for account in accounts]
    with ExitStack() as stack:
        browsers = [stack.enter_context(TestClient(app)) for _ in accounts]
        for browser, account in zip(browsers, accounts, strict=True):
            login(browser, account.email)
        yield {
            "first": browsers[0],
            "second": browsers[1],
            "admin": browsers[2],
            "first_id": identifiers[0],
            "second_id": identifiers[1],
            "admin_id": identifiers[2],
        }


@pytest.fixture
def owned_booking(
    app: FastAPI, actors: dict[str, Any], equipment_payload: dict[str, object]
) -> dict[str, Any]:
    equipment = actors["admin"].post("/api/equipment", json=equipment_payload)
    assert equipment.status_code == 201
    response = actors["admin"].post(
        "/api/reservations",
        json={
            "equipment_id": equipment.json()["id"],
            "customer_name": "Alicia Ficticia",
            "customer_email": "alicia@example.test",
            "start_date": "2030-11-10",
            "end_date": "2030-11-12",
        },
    )
    assert response.status_code == 201, response.text
    booking = response.json()
    # Trusted setup supplies a historical owner without depending on /api/me creation.
    with app.state.session_factory.begin() as session:
        session.get(Reservation, booking["id"]).customer_user_id = actors["first_id"]
    return booking


def report(actors: dict[str, Any], booking: dict[str, Any]) -> dict[str, Any]:
    response = actors["first"].post(f"/api/me/reservations/{booking['id']}/incidents", json=REPORT)
    assert response.status_code == 201, response.text
    return response.json()


def test_customer_report_deduces_identity_equipment_and_safe_defaults(
    app: FastAPI, actors: dict[str, Any], owned_booking: dict[str, Any]
) -> None:
    response = actors["first"].post(
        f"/api/me/reservations/{owned_booking['id']}/incidents", json=REPORT
    )
    assert response.status_code == 201, response.text
    incident = response.json()
    assert incident == {
        "id": incident["id"],
        "reservation_id": owned_booking["id"],
        "title": "Conector suelto",
        "description": "Se desconecta al mover el cable.",
        "status": "open",
        "public_response": "",
    }
    assert response.headers["location"] == f"/api/me/incidents/{incident['id']}"
    assert actors["first"].get(response.headers["location"]).json() == incident
    assert actors["first"].get("/api/me/incidents").json() == [incident]
    with app.state.session_factory() as session:
        stored = session.get(Incident, incident["id"])
        assert stored.author_user_id == actors["first_id"]
        assert stored.reservation_id == owned_booking["id"]
        assert stored.equipment_id == owned_booking["equipment_id"]
        assert stored.priority == "medium"
        assert stored.blocking is False
        assert stored.resolution == stored.public_response == stored.internal_notes == ""


def test_identifier_tampering_cannot_read_or_report_another_customers_booking(
    actors: dict[str, Any], owned_booking: dict[str, Any]
) -> None:
    incident = report(actors, owned_booking)
    assert actors["second"].get("/api/me/incidents").json() == []
    hidden = actors["second"].get(f"/api/me/incidents/{incident['id']}")
    missing = actors["second"].get("/api/me/incidents/99999")
    assert hidden.status_code == missing.status_code == 404
    assert hidden.json() == missing.json()
    for reservation_id in (owned_booking["id"], 99999):
        response = actors["second"].post(
            f"/api/me/reservations/{reservation_id}/incidents", json=REPORT
        )
        assert response.status_code == 404
    assert len(actors["admin"].get("/api/incidents").json()) == 1


@pytest.mark.parametrize(
    "forbidden",
    [
        {"equipment_id": 1},
        {"reservation_id": 1},
        {"author_user_id": 2},
        {"customer_user_id": 2},
        {"customer_id": 2},
        {"customer_name": "Otra persona"},
        {"customer_email": "otra@example.test"},
        {"status": "resolved"},
        {"priority": "high"},
        {"blocking": True},
        {"resolution": "Resuelta por cliente"},
        {"public_response": "Autorizado"},
        {"internal_notes": "Forjado"},
    ],
)
def test_report_rejects_all_identity_and_management_fields(
    actors: dict[str, Any], owned_booking: dict[str, Any], forbidden: dict[str, object]
) -> None:
    response = actors["first"].post(
        f"/api/me/reservations/{owned_booking['id']}/incidents", json={**REPORT, **forbidden}
    )
    assert response.status_code == 422, response.text
    assert actors["admin"].get("/api/incidents").json() == []


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"title": "Problema"},
        {"description": "Descripción"},
        {"title": " ", "description": "Descripción"},
        {"title": "X" * 161, "description": "Descripción"},
        {"title": "Problema", "description": " "},
        {"title": "Problema", "description": "X" * 2001},
        {"title": "Problema", "description": "NUL\x00"},
        {"title": "Problema", "description": None},
    ],
)
def test_customer_reports_require_useful_bounded_text(
    actors: dict[str, Any], owned_booking: dict[str, Any], body: dict[str, object]
) -> None:
    response = actors["first"].post(
        f"/api/me/reservations/{owned_booking['id']}/incidents", json=body
    )
    assert response.status_code == 422
    assert actors["first"].get("/api/me/incidents").json() == []


def test_cancelled_booking_cannot_create_reports_and_existing_reports_remain(
    actors: dict[str, Any], owned_booking: dict[str, Any]
) -> None:
    incident = report(actors, owned_booking)
    assert (
        actors["admin"].post(f"/api/reservations/{owned_booking['id']}/cancel").status_code == 200
    )
    response = actors["first"].post(
        f"/api/me/reservations/{owned_booking['id']}/incidents", json=REPORT
    )
    assert response.status_code == 409
    assert "confirmada" in response.json()["detail"]
    assert actors["first"].get("/api/me/incidents").json() == [incident]


def test_unowned_historical_records_remain_admin_visible_and_cannot_be_claimed_by_email(
    app: FastAPI, actors: dict[str, Any], owned_booking: dict[str, Any]
) -> None:
    incident = report(actors, owned_booking)
    with app.state.session_factory.begin() as session:
        session.get(Reservation, owned_booking["id"]).customer_user_id = None
    assert actors["first"].get("/api/me/incidents").json() == []
    assert actors["first"].get(f"/api/me/incidents/{incident['id']}").status_code == 404
    assert (
        actors["first"]
        .post(f"/api/me/reservations/{owned_booking['id']}/incidents", json=REPORT)
        .status_code
        == 404
    )
    assert actors["admin"].get(f"/api/reservations/{owned_booking['id']}").status_code == 200
    historical = actors["admin"].get(f"/api/incidents/{incident['id']}")
    assert historical.status_code == 200
    assert historical.json()["author_user_id"] == actors["first_id"]


def test_authorship_alone_does_not_expose_another_owners_reservation(
    app: FastAPI, actors: dict[str, Any], owned_booking: dict[str, Any]
) -> None:
    incident = report(actors, owned_booking)
    with app.state.session_factory.begin() as session:
        session.get(Reservation, owned_booking["id"]).customer_user_id = actors["second_id"]
    for browser in (actors["first"], actors["second"]):
        assert browser.get("/api/me/incidents").json() == []
        assert browser.get(f"/api/me/incidents/{incident['id']}").status_code == 404


def test_public_response_is_separate_from_internal_notes_and_resolution(
    actors: dict[str, Any], owned_booking: dict[str, Any]
) -> None:
    incident = report(actors, owned_booking)
    url = f"/api/incidents/{incident['id']}"
    updated = actors["admin"].patch(
        url,
        json={
            "public_response": "  Hemos recibido tu aviso y te contactaremos.  ",
            "internal_notes": "PRIVATE-NOTES: enviar a taller interno",
            "priority": "high",
            "blocking": True,
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["priority"] == "high"
    assert updated.json()["blocking"] is True
    assert updated.json()["internal_notes"] == "PRIVATE-NOTES: enviar a taller interno"
    assert updated.json()["author_user_id"] == actors["first_id"]
    assert updated.json()["reservation_id"] == owned_booking["id"]
    resolved = actors["admin"].patch(
        f"{url}/status", json={"status": "resolved", "resolution": "PRIVATE-REPAIR: coste 120"}
    )
    assert resolved.status_code == 200
    for response in (
        actors["first"].get(f"/api/me/incidents/{incident['id']}"),
        actors["first"].get("/api/me/incidents"),
    ):
        assert response.status_code == 200
        assert "PRIVATE-" not in response.text
        value = response.json()
        if isinstance(value, list):
            value = value[0]
        assert set(value) == CLIENT_FIELDS
        assert value["status"] == "resolved"
        assert value["public_response"] == "Hemos recibido tu aviso y te contactaremos."
    # Directly requesting the old URL must never disclose internal resolution/notes.
    assert actors["first"].get(url).status_code == 403
    assert actors["second"].get(url).status_code == 403


def test_customer_cannot_manage_incidents_or_use_administrative_urls(
    actors: dict[str, Any], owned_booking: dict[str, Any]
) -> None:
    incident = report(actors, owned_booking)
    for browser in (actors["first"], actors["second"]):
        for method, url, body in (
            ("GET", "/api/incidents", None),
            ("GET", f"/api/incidents/{incident['id']}", None),
            ("PATCH", f"/api/incidents/{incident['id']}", {"blocking": True}),
            (
                "PATCH",
                f"/api/incidents/{incident['id']}/status",
                {"status": "resolved", "resolution": "Forjada"},
            ),
            ("POST", "/api/incidents", {"equipment_id": 1, "title": "Forjada"}),
        ):
            assert browser.request(method, url, json=body).status_code == 403
    stored = actors["admin"].get(f"/api/incidents/{incident['id']}").json()
    assert stored["blocking"] is False
    assert stored["status"] == "open"


def test_reports_and_management_require_csrf_and_session(
    app: FastAPI, actors: dict[str, Any], owned_booking: dict[str, Any]
) -> None:
    incident = report(actors, owned_booking)
    del actors["first"].headers["X-CSRF-Token"]
    assert (
        actors["first"]
        .post(f"/api/me/reservations/{owned_booking['id']}/incidents", json=REPORT)
        .status_code
        == 403
    )
    del actors["admin"].headers["X-CSRF-Token"]
    assert (
        actors["admin"]
        .patch(f"/api/incidents/{incident['id']}", json={"public_response": "Revisaremos el aviso"})
        .status_code
        == 403
    )
    with TestClient(app) as anonymous:
        for method, path in (
            ("GET", "/api/me/incidents"),
            ("GET", f"/api/me/incidents/{incident['id']}"),
            ("POST", f"/api/me/reservations/{owned_booking['id']}/incidents"),
        ):
            assert anonymous.request(method, path, json=REPORT).status_code == 401
    assert len(actors["first"].get("/api/me/incidents").json()) == 1


def test_admin_cannot_impersonate_a_customer_through_me_routes(
    actors: dict[str, Any], owned_booking: dict[str, Any]
) -> None:
    for method, path in (
        ("GET", "/api/me/incidents"),
        ("GET", "/api/me/incidents/1"),
        ("POST", f"/api/me/reservations/{owned_booking['id']}/incidents"),
    ):
        assert actors["admin"].request(method, path, json=REPORT).status_code == 403


def test_customer_report_does_not_block_public_availability_admin_controls_blocking(
    actors: dict[str, Any], owned_booking: dict[str, Any]
) -> None:
    incident = report(actors, owned_booking)
    url = f"/api/public/equipment/{owned_booking['equipment_id']}/availability"
    dates = {"start_date": "2030-11-12", "end_date": "2030-11-15"}
    assert actors["first"].get(url, params=dates).json()["available"] is True
    assert (
        actors["admin"]
        .patch(f"/api/incidents/{incident['id']}", json={"blocking": True, "priority": "high"})
        .status_code
        == 200
    )
    unavailable = actors["first"].get(url, params=dates)
    assert unavailable.json()["available"] is False
    assert "Conector" not in unavailable.text
    assert "incident" not in unavailable.text
    assert (
        actors["admin"]
        .patch(f"/api/incidents/{incident['id']}", json={"blocking": False})
        .status_code
        == 200
    )
    assert actors["first"].get(url, params=dates).json()["available"] is True


@pytest.mark.parametrize(
    "changes",
    [
        {},
        {"priority": None},
        {"blocking": None},
        {"blocking": 1},
        {"priority": "critical"},
        {"public_response": None},
        {"internal_notes": None},
        {"public_response": "X" * 2001},
        {"internal_notes": "X" * 2001},
        {"public_response": "bad\x00value"},
        {"internal_notes": "bad\x00value"},
        {"status": "resolved"},
        {"resolution": "Repair"},
        {"author_user_id": 2},
        {"reservation_id": 2},
        {"equipment_id": 2},
        {"title": "Changed"},
    ],
)
def test_admin_patch_validates_fields_without_changing_history(
    actors: dict[str, Any], owned_booking: dict[str, Any], changes: dict[str, object]
) -> None:
    incident = report(actors, owned_booking)
    url = f"/api/incidents/{incident['id']}"
    original = actors["admin"].get(url).json()
    assert actors["admin"].patch(url, json=changes).status_code == 422
    assert actors["admin"].get(url).json() == original


def test_admin_patch_omitted_fields_are_preserved_and_communication_can_be_cleared(
    actors: dict[str, Any], owned_booking: dict[str, Any]
) -> None:
    incident = report(actors, owned_booking)
    url = f"/api/incidents/{incident['id']}"
    first = actors["admin"].patch(
        url, json={"public_response": "Recibido", "internal_notes": "Pendiente de taller"}
    )
    assert first.status_code == 200
    second = actors["admin"].patch(url, json={"public_response": ""})
    assert second.status_code == 200
    assert second.json() == {**first.json(), "public_response": ""}
    assert (
        actors["admin"].patch("/api/incidents/99999", json={"priority": "high"}).status_code == 404
    )


def test_migration_from_public_catalogue_preserves_old_rows_and_keeps_internal_resolution_private(
    tmp_path: Path,
) -> None:
    backend = Path(__file__).resolve().parents[1]
    config = Config(str(backend / "alembic.ini"))
    config.set_main_option("script_location", str(backend / "alembic"))
    database_url = f"sqlite:///{(tmp_path / 'previous.sqlite3').as_posix()}"
    config.set_main_option("sqlalchemy.url", database_url)
    engine = create_database_engine(database_url)
    try:
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "0007_public_catalogue")
            connection.execute(
                text(
                    "INSERT INTO equipment(id,code,name,category,"
                    "public_description,technical_specs) "
                    "VALUES(41,'OLD-CAM','Cámara previa','Cámaras','Ficha pública','{}')"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO reservations(id,equipment_id,customer_name,customer_email,"
                    "start_date,end_date,status,external_reference) VALUES"
                    "(52,41,'Cliente previo','alicia@example.test','2030-11-10','2030-11-12',"
                    "'confirmed','CSV-OLD'),"
                    "(53,41,'Cliente previo','alicia@example.test','2030-11-13','2030-11-15',"
                    "'cancelled',NULL)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO incidents(id,equipment_id,title,blocking,status,resolution) "
                    "VALUES(63,41,'Avería previa',1,'resolved','PRIVATE-REPAIR histórico')"
                )
            )
            before = {
                table: [
                    dict(row)
                    for row in connection.execute(text(f"SELECT * FROM {table}")).mappings()
                ]
                for table in ("equipment", "reservations", "incidents", "users", "auth_sessions")
            }
            command.upgrade(config, "head")
            for table, rows in before.items():
                after = [
                    dict(row)
                    for row in connection.execute(text(f"SELECT * FROM {table}")).mappings()
                ]
                for actual, expected in zip(after, rows, strict=True):
                    assert {key: actual[key] for key in expected} == expected
            historic = (
                connection.execute(text("SELECT * FROM incidents WHERE id=63")).mappings().one()
            )
            assert historic["reservation_id"] is None
            assert historic["author_user_id"] is None
            assert historic["public_response"] == historic["internal_notes"] == ""
            assert historic["resolution"] == "PRIVATE-REPAIR histórico"
            assert connection.execute(
                text("SELECT customer_user_id FROM reservations")
            ).scalars().all() == [None, None]
            assert connection.execute(text("PRAGMA foreign_key_check")).all() == []
            assert connection.scalar(text("PRAGMA integrity_check")) == "ok"
            command.check(config)
        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.execute(text("UPDATE incidents SET reservation_id=99999 WHERE id=63"))
    finally:
        engine.dispose()


def test_client_openapi_schemas_only_publish_approved_fields(actors: dict[str, Any]) -> None:
    schema = actors["admin"].get("/api/openapi.json").json()
    read = schema["components"]["schemas"]["CustomerIncidentRead"]
    create = schema["components"]["schemas"]["CustomerIncidentCreate"]
    assert set(read["properties"]) == CLIENT_FIELDS
    assert set(create["properties"]) == {"title", "description"}
    assert create["additionalProperties"] is False
    operation = schema["paths"]["/api/me/incidents/{incident_id}"]["get"]
    assert operation["security"] == [{"SessionCookie": []}]
    assert "403" in operation["responses"]
    assert "404" in operation["responses"]


@pytest.mark.parametrize("report_first", [True, False])
def test_customer_report_and_cancellation_make_their_decision_under_the_same_writer_lock(
    app: FastAPI,
    settings: Settings,
    actors: dict[str, Any],
    owned_booking: dict[str, Any],
    report_first: bool,
) -> None:
    report_url = f"/api/me/reservations/{owned_booking['id']}/incidents"
    cancel_url = f"/api/reservations/{owned_booking['id']}/cancel"
    first_has_lock = Event()
    second_attempted_write = Event()
    second_app = create_app(settings)

    def hold_first_write_lock(
        _connection: Connection,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: ExecutionContext,
        _executemany: bool,
    ) -> None:
        if statement.strip().upper() == "BEGIN IMMEDIATE":
            first_has_lock.set()
            assert second_attempted_write.wait(timeout=5)

    def observe_second_write_attempt(
        _connection: Connection,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: ExecutionContext,
        _executemany: bool,
    ) -> None:
        if statement.strip().upper() == "BEGIN IMMEDIATE":
            second_attempted_write.set()

    try:
        with TestClient(second_app) as second, ThreadPoolExecutor(max_workers=2) as executor:
            login(second, "admin@example.test" if report_first else "alicia@example.test")
            event.listen(app.state.engine, "after_cursor_execute", hold_first_write_lock)
            event.listen(
                second_app.state.engine, "before_cursor_execute", observe_second_write_attempt
            )
            try:
                first = executor.submit(
                    actors["first" if report_first else "admin"].post,
                    report_url if report_first else cancel_url,
                    json=REPORT if report_first else None,
                )
                assert first_has_lock.wait(timeout=5)
                following = executor.submit(
                    second.post,
                    cancel_url if report_first else report_url,
                    json=None if report_first else REPORT,
                )
                first_response = first.result(timeout=10)
                second_response = following.result(timeout=10)
            finally:
                event.remove(app.state.engine, "after_cursor_execute", hold_first_write_lock)
                event.remove(
                    second_app.state.engine, "before_cursor_execute", observe_second_write_attempt
                )
            assert first_response.status_code == (201 if report_first else 200)
            assert second_response.status_code == (200 if report_first else 409)
        assert len(actors["admin"].get("/api/incidents").json()) == (1 if report_first else 0)
        assert (
            actors["admin"].get(f"/api/reservations/{owned_booking['id']}").json()["status"]
            == "cancelled"
        )
    finally:
        second_app.state.engine.dispose()


@pytest.mark.parametrize("operation", ["report", "management"])
def test_busy_customer_report_or_admin_management_leaves_no_partial_changes(
    app: FastAPI,
    settings: Settings,
    actors: dict[str, Any],
    owned_booking: dict[str, Any],
    operation: str,
) -> None:
    original = report(actors, owned_booking) if operation == "management" else None
    url = (
        f"/api/incidents/{original['id']}"
        if original
        else f"/api/me/reservations/{owned_booking['id']}/incidents"
    )
    method = "PATCH" if original else "POST"
    body = {"blocking": True, "public_response": "Revisaremos el aviso"} if original else REPORT
    second_app = create_app(settings.model_copy(update={"sqlite_busy_timeout_ms": 25}))
    try:
        with TestClient(second_app) as browser:
            login(browser, "admin@example.test" if original else "alicia@example.test")
            with app.state.engine.connect() as writer:
                writer.exec_driver_sql("BEGIN IMMEDIATE")
                failed = browser.request(method, url, json=body)
                assert failed.status_code == 503
                assert failed.headers["Retry-After"] == "1"
                writer.rollback()
            assert actors["first"].get("/api/me/incidents").json() == (
                [original] if original else []
            )
            retried = browser.request(method, url, json=body)
            assert retried.status_code == (200 if original else 201)
    finally:
        second_app.state.engine.dispose()
