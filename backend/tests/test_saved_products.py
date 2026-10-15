from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from threading import Barrier

import pytest
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from alembic import command
from rentalab.auth.models import User
from rentalab.auth.schemas import RegisterRequest
from rentalab.database import create_database_engine
from rentalab.me.models import SavedProduct

BASE_URL = "/api/me/saved-products"
CUSTOMER_PASSWORD = "isolated-saved-products-password"


def login(browser: TestClient, email: str) -> None:
    token = browser.get("/api/auth/csrf").json()["csrf_token"]
    response = browser.post(
        "/api/auth/login",
        json={"username": email, "password": CUSTOMER_PASSWORD},
        headers={"X-CSRF-Token": token},
    )
    assert response.status_code == 200, response.text
    browser.headers["X-CSRF-Token"] = browser.get("/api/auth/csrf").json()["csrf_token"]


@dataclass
class SavedWorld:
    first: TestClient
    second: TestClient
    admin: TestClient
    first_id: int
    second_id: int
    equipment_id: int


@pytest.fixture
def world(app: FastAPI, equipment_payload: dict) -> Iterator[SavedWorld]:
    identities = [
        ("Primera cuenta", "saved-first@example.test", "customer"),
        ("Segunda cuenta", "saved-second@example.test", "customer"),
        ("Administración", "saved-admin@example.test", "admin"),
    ]
    users = [
        app.state.auth_service.register(
            RegisterRequest(name=name, email=email, password=CUSTOMER_PASSWORD), role=role
        )
        for name, email, role in identities
    ]
    with ExitStack() as stack:
        browsers = [stack.enter_context(TestClient(app)) for _identity in identities]
        for browser, (_name, email, _role) in zip(browsers, identities, strict=True):
            login(browser, email)
        first, second, admin = browsers
        response = admin.post("/api/equipment", json=equipment_payload)
        assert response.status_code == 201, response.text
        yield SavedWorld(first, second, admin, users[0].id, users[1].id, response.json()["id"])


def create_unit(world: SavedWorld, **changes: object) -> int:
    response = world.admin.post(
        "/api/equipment",
        json={
            "code": "CAM-ALIAS",
            "name": "Cámara de prueba",
            "category": "Cámaras",
            "description": "INTERNAL-PRIVATE-INVENTORY-NOTE",
            **changes,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_saved_products_persist_across_sessions_and_isolate_accounts(
    app: FastAPI, world: SavedWorld
) -> None:
    expected = {"equipment_ids": [world.equipment_id]}
    assert world.first.get(BASE_URL).json() == {"equipment_ids": []}
    response = world.first.put(f"{BASE_URL}/{world.equipment_id}")
    assert response.status_code == 200, response.text
    assert response.json() == expected
    assert response.headers["Cache-Control"] == "no-store"
    assert world.second.get(BASE_URL).json() == {"equipment_ids": []}
    assert world.second.delete(f"{BASE_URL}/{world.equipment_id}").json() == {"equipment_ids": []}
    with TestClient(app) as fresh_browser:
        login(fresh_browser, "saved-first@example.test")
        read = fresh_browser.get(BASE_URL)
        assert read.json() == expected
        assert read.headers["Cache-Control"] == "no-store"
        assert "PRIVATE" not in read.text
        assert "customer" not in read.text
    with app.state.session_factory() as session:
        rows = session.scalars(select(SavedProduct)).all()
        assert [(row.customer_user_id, row.equipment_id) for row in rows] == [
            (world.first_id, world.equipment_id)
        ]
    assert world.first.delete(f"{BASE_URL}/{world.equipment_id}").json() == {"equipment_ids": []}
    assert world.first.delete(f"{BASE_URL}/{world.equipment_id}").json() == {"equipment_ids": []}
    assert world.first.delete(f"{BASE_URL}/999999").json() == {"equipment_ids": []}


def test_aliases_save_one_canonical_model_and_archive_keeps_removable_favorite(
    app: FastAPI, world: SavedWorld
) -> None:
    alias = create_unit(world, name="CA\u0301MARA DE PRUEBA", category="CA\u0301MARAS")
    other_category = create_unit(world, code="ACCESSORY", category="Accesorios")
    expected = {"equipment_ids": [world.equipment_id]}
    for equipment_id in [alias, world.equipment_id, alias]:
        response = world.first.put(f"{BASE_URL}/{equipment_id}")
        assert response.status_code == 200, response.text
        assert response.json() == expected
    assert world.first.put(f"{BASE_URL}/{other_category}").json() == {
        "equipment_ids": [world.equipment_id, other_category]
    }
    with app.state.session_factory() as session:
        assert len(session.scalars(select(SavedProduct)).all()) == 2
    assert (
        world.admin.patch(
            f"/api/equipment/{world.equipment_id}", json={"active": False}
        ).status_code
        == 200
    )
    assert world.first.get(BASE_URL).json() == {"equipment_ids": [alias, other_category]}
    assert world.first.put(f"{BASE_URL}/{alias}").json() == {
        "equipment_ids": [alias, other_category]
    }
    assert world.first.delete(f"{BASE_URL}/{alias}").json() == {"equipment_ids": [other_category]}
    assert world.first.put(f"{BASE_URL}/{alias}").json() == {
        "equipment_ids": [alias, other_category]
    }
    assert world.admin.patch(f"/api/equipment/{alias}", json={"active": False}).status_code == 200
    assert world.first.get(BASE_URL).json() == {"equipment_ids": [alias, other_category]}
    assert world.first.put(f"{BASE_URL}/{alias}").status_code == 404
    # An archived alias can still remove the same model saved through another unit.
    assert world.first.delete(f"{BASE_URL}/{world.equipment_id}").json() == {
        "equipment_ids": [other_category]
    }


def test_missing_and_inactive_products_cannot_be_saved(world: SavedWorld) -> None:
    inactive = create_unit(world, active=False)
    missing = world.first.put(f"{BASE_URL}/999999")
    assert missing.status_code == 404
    archived = world.first.put(f"{BASE_URL}/{inactive}")
    assert archived.status_code == 404
    assert archived.json() == missing.json() == {"detail": "El equipo no existe"}
    assert world.first.get(BASE_URL).json() == {"equipment_ids": []}


@pytest.mark.parametrize("method", ["GET", "PUT", "DELETE"])
def test_saved_products_require_customer_session_and_hide_data(
    app: FastAPI, world: SavedWorld, method: str
) -> None:
    path = BASE_URL if method == "GET" else f"{BASE_URL}/{world.equipment_id}"
    with TestClient(app) as anonymous:
        assert anonymous.request(method, path).status_code == 401
    forbidden = world.admin.request(method, path)
    assert forbidden.status_code == 403
    assert "equipment_ids" not in forbidden.text
    assert forbidden.headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize("method", ["PUT", "DELETE"])
def test_writes_require_csrf_and_reject_owner_injection(world: SavedWorld, method: str) -> None:
    path = f"{BASE_URL}/{world.equipment_id}"
    response = world.first.request(method, path, headers={"X-CSRF-Token": "invalid"})
    assert response.status_code == 403
    response = world.first.request(method, path, json={"customer_user_id": world.second_id})
    assert response.status_code == 422
    response = world.first.request(method, path, params={"customer_user_id": world.second_id})
    assert response.status_code == 422
    assert world.first.get(BASE_URL).json() == {"equipment_ids": []}
    assert world.second.get(BASE_URL).json() == {"equipment_ids": []}


def test_reads_reject_owner_query_parameter(world: SavedWorld) -> None:
    assert world.first.put(f"{BASE_URL}/{world.equipment_id}").status_code == 200
    response = world.second.get(BASE_URL, params={"customer_user_id": world.first_id})
    assert response.status_code == 422
    assert world.second.get(BASE_URL).json() == {"equipment_ids": []}


@pytest.mark.parametrize("equipment_id", ["0", "-1", str(2**63), "not-an-id"])
@pytest.mark.parametrize("method", ["PUT", "DELETE"])
def test_saved_product_ids_are_bounded(world: SavedWorld, equipment_id: str, method: str) -> None:
    assert world.first.request(method, f"{BASE_URL}/{equipment_id}").status_code == 422


@pytest.mark.parametrize("change", ["deactivated", "changed_role"])
def test_saved_products_recheck_current_account_access(
    app: FastAPI, world: SavedWorld, change: str
) -> None:
    assert world.first.put(f"{BASE_URL}/{world.equipment_id}").status_code == 200
    with app.state.session_factory() as session, session.begin():
        user = session.get(User, world.first_id)
        assert user is not None
        if change == "deactivated":
            user.active = False
        else:
            user.role = "admin"
    expected = 401 if change == "deactivated" else 403
    assert world.first.get(BASE_URL).status_code == expected
    assert world.first.put(f"{BASE_URL}/{world.equipment_id}").status_code == expected
    assert world.first.delete(f"{BASE_URL}/{world.equipment_id}").status_code == expected


def test_concurrent_alias_additions_are_idempotent(app: FastAPI, world: SavedWorld) -> None:
    alias = create_unit(world)
    barrier = Barrier(2)
    with TestClient(app) as other_session:
        login(other_session, "saved-first@example.test")

        def save(browser: TestClient, equipment_id: int) -> dict:
            barrier.wait(timeout=10)
            response = browser.put(f"{BASE_URL}/{equipment_id}")
            assert response.status_code == 200, response.text
            return response.json()

        with ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(save, world.first, world.equipment_id)
            second = executor.submit(save, other_session, alias)
            assert (
                first.result(timeout=15)
                == second.result(timeout=15)
                == {"equipment_ids": [world.equipment_id]}
            )
    with app.state.session_factory() as session:
        assert len(session.scalars(select(SavedProduct)).all()) == 1
    with app.state.session_factory() as session:
        session.add(SavedProduct(customer_user_id=world.first_id, equipment_id=world.equipment_id))
        with pytest.raises(IntegrityError):
            session.commit()


def test_saved_products_migration_preserves_existing_data_and_reverses_cleanly(
    tmp_path: Path,
) -> None:
    backend = Path(__file__).resolve().parents[1]
    config = Config(str(backend / "alembic.ini"))
    config.set_main_option("script_location", str(backend / "alembic"))
    database_url = f"sqlite:///{(tmp_path / 'saved-products-migration.sqlite3').as_posix()}"
    config.set_main_option("sqlalchemy.url", database_url)
    engine = create_database_engine(database_url)
    try:
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "0009_reservation_origin")
            for statement in (
                "INSERT INTO users (id,name,email,password_hash,role,active) "
                "VALUES (7,'Cliente previo','previous@example.test','test-hash','customer',1)",
                "INSERT INTO equipment (id,code,name,category,description,active) "
                "VALUES (41,'OLD-CAM','Equipo previo','Cámaras','Nota interna privada',0)",
                "INSERT INTO reservations (id,equipment_id,customer_user_id,customer_name,"
                "customer_email,start_date,end_date,status,external_reference,origin) "
                "VALUES (52,41,7,'Cliente previo','previous@example.test','2026-11-10',"
                "'2026-11-12','confirmed','HISTORICAL','portal')",
                "INSERT INTO incidents (id,equipment_id,author_user_id,title,description,"
                "blocking,status,resolution,reservation_id) "
                "VALUES (63,41,7,'Aviso previo','Información sensible',0,'resolved','Reparada',52)",
                "INSERT INTO auth_sessions (id,expires_at,credential_version,user_id) "
                "VALUES ('" + "a" * 64 + "',2000000000,'" + "b" * 64 + "',7)",
            ):
                connection.execute(text(statement))
            tables = ("users", "equipment", "reservations", "incidents", "auth_sessions")

            def snapshot() -> dict:
                return {
                    table: list(connection.execute(text(f"SELECT * FROM {table}")).mappings())
                    for table in tables
                }

            before = snapshot()
            command.upgrade(config, "head")
            assert snapshot() == before
            connection.execute(
                text("INSERT INTO saved_products (customer_user_id,equipment_id) VALUES (7,41)")
            )
            assert connection.execute(text("SELECT * FROM saved_products")).one() == (7, 41)
            assert connection.scalar(text("PRAGMA integrity_check")) == "ok"
            assert connection.execute(text("PRAGMA foreign_key_check")).all() == []
            command.check(config)
            command.downgrade(config, "0009_reservation_origin")
            assert snapshot() == before
            command.upgrade(config, "head")
            assert connection.execute(text("SELECT * FROM saved_products")).all() == []
            assert snapshot() == before
            assert connection.execute(text("PRAGMA foreign_key_check")).all() == []
    finally:
        engine.dispose()
