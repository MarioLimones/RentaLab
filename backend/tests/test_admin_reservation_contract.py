from pathlib import Path

import pytest
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from alembic import command
from rentalab.auth.schemas import RegisterRequest
from rentalab.database import create_database_engine
from rentalab.reservations.models import Reservation


def test_administrative_filters_are_combined_literal_and_casefolded(
    app: FastAPI, client: TestClient, equipment_payload: dict
) -> None:
    unit = client.post("/api/equipment", json=equipment_payload).json()
    user = app.state.auth_service.register(
        RegisterRequest(name="María", email="maria@example.test", password="isolated-admin-test")
    )
    bookings = []
    for index, name in enumerate(("MARÍA Prueba", "Usuario_100%", "Otra persona")):
        response = client.post(
            "/api/reservations",
            json={
                "equipment_id": unit["id"],
                "customer_name": name,
                "customer_email": f"persona{index}@example.test",
                "start_date": f"2030-11-{10 + index:02}",
                "end_date": f"2030-11-{11 + index:02}",
            },
        )
        assert response.status_code == 201, response.text
        bookings.append(response.json())
    with app.state.session_factory.begin() as session:
        row = session.get(Reservation, bookings[0]["id"])
        row.customer_user_id = user.id
        row.origin = "portal"
    bookings[0].update(customer_user_id=user.id, origin="portal")
    assert client.get("/api/reservations", params={"customer": "  maría  "}).json() == [bookings[0]]
    assert client.get("/api/reservations", params={"customer": "PERSONA1@EXAMPLE.TEST"}).json() == [
        bookings[1]
    ]
    for literal in ("_", "%", "100%"):
        assert client.get("/api/reservations", params={"customer": literal}).json() == [bookings[1]]
    filters = {
        "customer": "María",
        "customer_user_id": user.id,
        "origin": "portal",
        "equipment_id": unit["id"],
        "status": "confirmed",
        "start_date": "2030-11-09",
        "end_date": "2030-11-11",
    }
    assert client.get("/api/reservations", params=filters).json() == [bookings[0]]
    assert client.get("/api/reservations", params={**filters, "origin": "csv"}).json() == []
    assert client.get("/api/reservations", params={"customer_user_id": 999}).json() == []
    assert client.get("/api/reservations", params={"origin": "admin"}).json() == bookings[1:]


@pytest.mark.parametrize(
    "filters",
    [
        {"customer": ""},
        {"customer": "   "},
        {"customer": "a" * 255},
        {"customer": "private\x00name"},
        {"customer_user_id": 0},
        {"customer_user_id": str(2**63)},
        {"origin": "guessed"},
    ],
)
def test_admin_reservation_filter_contract_rejects_invalid_values(
    client: TestClient, filters: dict
) -> None:
    assert client.get("/api/reservations", params=filters).status_code == 422


@pytest.mark.parametrize("forbidden", ["customer_user_id", "origin", "status"])
def test_admin_create_never_accepts_server_assigned_ownership_or_origin(
    client: TestClient, equipment_payload: dict, forbidden: str
) -> None:
    equipment_id = client.post("/api/equipment", json=equipment_payload).json()["id"]
    response = client.post(
        "/api/reservations",
        json={
            "equipment_id": equipment_id,
            "customer_name": "Nombre",
            "customer_email": "nombre@example.test",
            "start_date": "2030-11-10",
            "end_date": "2030-11-12",
            forbidden: 1 if forbidden == "customer_user_id" else "portal",
        },
    )
    assert response.status_code == 422
    assert client.get("/api/reservations").json() == []


def test_administrative_openapi_documents_origin_owner_and_filters(client: TestClient) -> None:
    document = client.get("/api/openapi.json").json()
    schemas = document["components"]["schemas"]
    assert schemas["ReservationRead"]["properties"]["origin"]["enum"] == [
        "portal",
        "admin",
        "csv",
        "legacy",
    ]
    assert {"customer_user_id", "origin"} <= set(schemas["ReservationRead"]["required"])
    assert not {"customer_user_id", "origin"} & set(schemas["ReservationCreate"]["properties"])
    assert not {"customer_user_id", "origin"} & set(
        schemas["CustomerReservationRead"]["properties"]
    )
    operation = document["paths"]["/api/reservations"]["get"]
    assert {"customer", "customer_user_id", "origin"} <= {
        p["name"] for p in operation["parameters"]
    }
    assert operation["security"] == [{"SessionCookie": []}]
    assert {"401", "403"} <= set(operation["responses"])


def test_origin_migration_preserves_owned_unknown_and_linked_incident_rows(tmp_path: Path) -> None:
    backend = Path(__file__).resolve().parents[1]
    config = Config(str(backend / "alembic.ini"))
    config.set_main_option("script_location", str(backend / "alembic"))
    url = f"sqlite:///{(tmp_path / 'before-origin.db').as_posix()}"
    config.set_main_option("sqlalchemy.url", url)
    engine = create_database_engine(url)
    try:
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "0008_customer_incidents")
            connection.execute(
                text(
                    "INSERT INTO equipment(id,code,name,category,technical_specs) "
                    "VALUES (41,'HISTORIC','Equipo histórico','Audio','{}')"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO users(id,name,email,password_hash,role,active) "
                    "VALUES(51,'Cuenta','cuenta@example.test','unusable-placeholder','customer',1)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO reservations(id,equipment_id,customer_name,customer_email,"
                    "start_date,"
                    "end_date,status,external_reference,customer_user_id) VALUES"
                    "(61,41,'Cuenta','cuenta@example.test','2030-11-10','2030-11-12','confirmed',NULL,51),"
                    "(62,41,'Histórico','cuenta@example.test','2030-11-13','2030-11-15','cancelled','CSV-OLD',NULL)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO incidents(id,equipment_id,title,blocking,status,reservation_id,"
                    "author_user_id,public_response,internal_notes) VALUES "
                    "(71,41,'Aviso',0,'open',61,51,'Respuesta pública','Nota interna')"
                )
            )
            tables = ("equipment", "users", "reservations", "incidents", "auth_sessions")
            before = {
                table: list(connection.execute(text(f"SELECT * FROM {table}")).mappings())
                for table in tables
            }
            # A table rebuild would fire this trace. The upgrade must only ALTER reservations.
            statements: list[str] = []
            connection.connection.driver_connection.set_trace_callback(statements.append)
            command.upgrade(config, "head")
            connection.connection.driver_connection.set_trace_callback(None)
            assert not any("DROP TABLE" in statement.upper() for statement in statements)
            for table, rows in before.items():
                after = list(connection.execute(text(f"SELECT * FROM {table}")).mappings())
                for actual, expected in zip(after, rows, strict=True):
                    assert {key: actual[key] for key in expected} == dict(expected)
            assert connection.execute(
                text("SELECT origin FROM reservations ORDER BY id")
            ).scalars().all() == ["legacy", "legacy"]
            assert connection.execute(text("PRAGMA foreign_key_check")).all() == []
            assert connection.scalar(text("PRAGMA integrity_check")) == "ok"
            command.check(config)
        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.execute(text("UPDATE reservations SET origin='guessed' WHERE id=61"))
        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.execute(text("UPDATE incidents SET reservation_id=999 WHERE id=71"))
    finally:
        engine.dispose()
