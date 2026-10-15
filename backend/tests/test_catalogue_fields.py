from pathlib import Path

import pytest
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from alembic import command
from rentalab.database import create_database_engine
from rentalab.equipment.models import Equipment
from rentalab.seed import DEMO_EQUIPMENT, seed_equipment


def test_admin_can_create_and_edit_public_fields_separately_from_internal_description(
    client: TestClient, equipment_payload: dict[str, object]
) -> None:
    created = client.post(
        "/api/equipment",
        json={
            **equipment_payload,
            "public_description": "  Cámara ligera para entrevistas.  ",
            "technical_specs": {"  Resolución  ": "  4K UHD  ", "Peso": "1,2 kg"},
            "image_url": "  /api/public/images/camera.svg  ",
        },
    )
    assert created.status_code == 201
    equipment = created.json()
    assert equipment["description"] == equipment_payload["description"]
    assert equipment["public_description"] == "Cámara ligera para entrevistas."
    assert equipment["technical_specs"] == {"Resolución": "4K UHD", "Peso": "1,2 kg"}
    assert equipment["image_url"] == "/api/public/images/camera.svg"
    url = f"/api/equipment/{equipment['id']}"
    edited = client.patch(url, json={"technical_specs": {"Óptica": "24–70 mm"}})
    assert edited.status_code == 200
    assert edited.json() == {**equipment, "technical_specs": {"Óptica": "24–70 mm"}}
    removed = client.patch(url, json={"image_url": None})
    assert removed.status_code == 200
    assert removed.json() == {**edited.json(), "image_url": None}
    assert client.get(url).json() == removed.json()


def test_replace_resets_public_fields_to_defaults(
    client: TestClient, equipment_payload: dict[str, object]
) -> None:
    equipment = client.post(
        "/api/equipment",
        json={
            **equipment_payload,
            "public_description": "Descripción para clientes",
            "technical_specs": {"Audio": "48 kHz"},
            "image_url": "https://images.example.test/microphone.webp",
        },
    ).json()
    replacement = client.put(f"/api/equipment/{equipment['id']}", json=equipment_payload)
    assert replacement.status_code == 200
    assert replacement.json()["public_description"] == ""
    assert replacement.json()["technical_specs"] == {}
    assert replacement.json()["image_url"] is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("public_description", None),
        ("public_description", 123),
        ("public_description", "X" * 2001),
        ("public_description", "Visible\x00privado"),
        ("technical_specs", None),
        ("technical_specs", []),
        ("technical_specs", {str(index): "Dato" for index in range(21)}),
        ("technical_specs", {" ": "Dato"}),
        ("technical_specs", {"X" * 81: "Dato"}),
        ("technical_specs", {"Peso": " "}),
        ("technical_specs", {"Peso": "X" * 301}),
        ("technical_specs", {"Peso": 123}),
        ("technical_specs", {"Peso\x00": "Dato"}),
        ("technical_specs", {"Peso": "Dato\x00"}),
        ("technical_specs", {" Peso ": "1 kg", "Peso": "2 kg"}),
        ("image_url", ""),
        ("image_url", 123),
        ("image_url", "http://example.test/image.png"),
        ("image_url", "javascript:alert(1)"),
        ("image_url", "//example.test/image.png"),
        ("image_url", "https://user:password@example.test/image.png"),
        ("image_url", "https://example.test/image.png?token=private"),
        ("image_url", "https://example.test/image.png#fragment"),
        ("image_url", "https:///image.png"),
        ("image_url", "https://example.test:99999/image.png"),
        ("image_url", "https://example.test/ima\nge.png"),
        ("image_url", "/other/image.png"),
        ("image_url", "/api/public/images/../private.png"),
        ("image_url", "/api/public/images/%2e%2e/private.png"),
        ("image_url", "/api/public/images/..\\private.png"),
        ("image_url", "/api/public/images/image.png?private=true"),
        ("image_url", "/api/public/images/image.png#fragment"),
    ],
)
def test_invalid_public_fields_are_rejected_for_creation_and_patch_without_changes(
    client: TestClient,
    equipment_payload: dict[str, object],
    field: str,
    value: object,
) -> None:
    rejected = client.post("/api/equipment", json={**equipment_payload, field: value})
    assert rejected.status_code == 422
    assert client.get("/api/equipment").json() == []
    equipment = client.post("/api/equipment", json=equipment_payload).json()
    url = f"/api/equipment/{equipment['id']}"
    assert client.patch(url, json={field: value}).status_code == 422
    assert client.get(url).json() == equipment


def test_maximum_public_specs_and_empty_public_description_are_accepted(
    client: TestClient, equipment_payload: dict[str, object]
) -> None:
    specs = {f"{index:02d}" + "X" * 78: "V" * 300 for index in range(20)}
    response = client.post(
        "/api/equipment",
        json={**equipment_payload, "public_description": "  ", "technical_specs": specs},
    )
    assert response.status_code == 201
    assert response.json()["public_description"] == ""
    assert response.json()["technical_specs"] == specs
    assert response.json()["image_url"] is None


def test_demo_catalogue_is_useful_without_remote_images_and_does_not_replace_existing_fields(
    app: FastAPI,
) -> None:
    assert len(DEMO_EQUIPMENT) == 4
    with app.state.session_factory() as session, session.begin():
        assert seed_equipment(session) == 4
        equipment = list(session.scalars(select(Equipment).order_by(Equipment.id)))
        assert all(item.public_description and item.technical_specs for item in equipment)
        assert {item.image_url for item in equipment} == {
            "/api/public/images/demo-camera.jpg",
            "/api/public/images/demo-microphone.jpg",
            "/api/public/images/demo-light.jpg",
        }
        first = equipment[0]
        first.public_description = "Contenido revisado por administración"
        first.technical_specs = {"Accesorios": "Trípode propio"}
        first.image_url = "/api/public/images/custom-camera.svg"
        session.flush()
        before = [
            dict(row)
            for row in session.execute(text("SELECT * FROM equipment ORDER BY id")).mappings()
        ]
        assert seed_equipment(session) == 0
        after = [
            dict(row)
            for row in session.execute(text("SELECT * FROM equipment ORDER BY id")).mappings()
        ]
        assert after == before


def test_catalogue_migration_preserves_every_previous_column_without_publishing_internal_notes(
    tmp_path: Path,
) -> None:
    backend = Path(__file__).resolve().parents[1]
    config = Config(str(backend / "alembic.ini"))
    config.set_main_option("script_location", str(backend / "alembic"))
    database_url = f"sqlite:///{(tmp_path / 'catalogue-migration.sqlite3').as_posix()}"
    config.set_main_option("sqlalchemy.url", database_url)
    engine = create_database_engine(database_url)
    try:
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "0006_users_ownership")
            for statement in (
                "INSERT INTO users (id,name,email,password_hash,role,active) "
                "VALUES (7,'Cliente previo','previous@example.test','test-hash','customer',1)",
                "INSERT INTO equipment (id,code,name,category,description,active) "
                "VALUES (41,'OLD-CAM','Equipo previo','Cámaras','Nota interna privada',0)",
                "INSERT INTO reservations (id,equipment_id,customer_user_id,customer_name,"
                "customer_email,start_date,end_date,status,external_reference) "
                "VALUES (52,41,7,'Cliente previo','previous@example.test','2026-11-10',"
                "'2026-11-12','confirmed','HISTORICAL')",
                "INSERT INTO incidents (id,equipment_id,author_user_id,title,description,"
                "blocking,status,resolution) VALUES (63,41,7,'Avería privada','Información "
                "sensible',1,'resolved','Reparada')",
                "INSERT INTO auth_sessions (id,expires_at,credential_version,user_id) "
                "VALUES ('" + "a" * 64 + "',2000000000,'" + "b" * 64 + "',7)",
            ):
                connection.execute(text(statement))
            tables = ("users", "equipment", "reservations", "incidents", "auth_sessions")
            before = {
                table: [
                    dict(row)
                    for row in connection.execute(
                        text(f"SELECT * FROM {table} ORDER BY id")
                    ).mappings()
                ]
                for table in tables
            }
            command.upgrade(config, "head")
            for table, expected_rows in before.items():
                actual_rows = list(
                    connection.execute(text(f"SELECT * FROM {table} ORDER BY id")).mappings()
                )
                for expected, actual in zip(expected_rows, actual_rows, strict=True):
                    assert {key: actual[key] for key in expected} == expected
            migrated = (
                connection.execute(text("SELECT * FROM equipment WHERE id=41")).mappings().one()
            )
            assert migrated["public_description"] == ""
            assert migrated["technical_specs"] == "{}"
            assert migrated["image_url"] is None
            assert connection.scalar(text("PRAGMA integrity_check")) == "ok"
            assert connection.execute(text("PRAGMA foreign_key_check")).all() == []
            command.check(config)
    finally:
        engine.dispose()
