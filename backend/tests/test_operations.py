from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text

from rentalab.config import Settings
from rentalab.main import create_app
from rentalab.seed import seed_equipment


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_openapi_and_documentation_live_under_api(client: TestClient) -> None:
    schema_response = client.get("/api/openapi.json")
    assert schema_response.status_code == 200
    schema = schema_response.json()
    assert schema["info"]["title"] == "RentaLab API"
    assert schema["components"]["schemas"]["EquipmentUpdate"]["minProperties"] == 1
    assert "/health" in schema["paths"]
    assert {"get", "post"} <= schema["paths"]["/api/equipment"].keys()
    assert {"get", "put", "patch"} <= schema["paths"]["/api/equipment/{equipment_id}"].keys()
    assert client.get("/api/docs").status_code == 200
    assert client.get("/api/redoc").status_code == 200
    for old_path in ["/docs", "/redoc", "/openapi.json"]:
        assert client.get(old_path).status_code == 404


def test_startup_does_not_create_or_reset_the_schema(tmp_path: Path) -> None:
    application = create_app(
        Settings(
            database_url=f"sqlite:///{(tmp_path / 'empty.sqlite3').as_posix()}", environment="test"
        )
    )
    try:
        with TestClient(application) as test_client:
            assert test_client.get("/health").status_code == 200
            assert inspect(application.state.engine).get_table_names() == []
    finally:
        application.state.engine.dispose()


def test_migration_starts_with_an_empty_catalog(client: TestClient) -> None:
    assert client.get("/api/equipment").json() == []


def test_explicit_seed_is_repeatable_and_preserves_existing_edits(app: FastAPI) -> None:
    with app.state.session_factory() as session:
        created = seed_equipment(session)
        assert created > 0
        session.commit()
        initial_rows = session.execute(text("SELECT id, code FROM equipment ORDER BY id")).all()
        assert len(initial_rows) == created
        first_id = initial_rows[0].id
        session.execute(
            text("UPDATE equipment SET name = :name, active = 0 WHERE id = :id"),
            {"name": "Nombre editado a mano", "id": first_id},
        )
        session.commit()
        assert seed_equipment(session) == 0
        session.commit()
        final_rows = session.execute(text("SELECT id, code FROM equipment ORDER BY id")).all()
        assert final_rows == initial_rows
        edited = session.execute(
            text("SELECT name, active FROM equipment WHERE id = :id"), {"id": first_id}
        ).one()
        assert edited.name == "Nombre editado a mano"
        assert edited.active == 0


def test_production_can_serve_the_spa_without_swallowing_unknown_server_routes(
    tmp_path: Path,
) -> None:
    frontend_dist = tmp_path / "dist"
    assets = frontend_dist / "assets"
    assets.mkdir(parents=True)
    (frontend_dist / "index.html").write_text(
        "<html><body>RentaLab SPA</body></html>", encoding="utf-8"
    )
    (assets / "app.js").write_text("console.log('RentaLab');", encoding="utf-8")
    (tmp_path / "private.txt").write_text("Private content", encoding="utf-8")
    application = create_app(
        Settings(
            database_url=f"sqlite:///{(tmp_path / 'spa.sqlite3').as_posix()}",
            environment="production",
            frontend_dist=frontend_dist,
        )
    )
    try:
        with TestClient(application) as test_client:
            for path in ["/", "/equipment", "/future/client/route"]:
                response = test_client.get(path)
                assert response.status_code == 200
                assert "RentaLab SPA" in response.text
            assert "RentaLab" in test_client.get("/assets/app.js").text
            assert test_client.get("/api/missing").status_code == 401
            for path in ["/health/missing", "/assets/missing.js", "/missing.png"]:
                assert test_client.get(path).status_code == 404
            assert test_client.get("/assets/%2e%2e/%2e%2e/private.txt").status_code == 404
    finally:
        application.state.engine.dispose()


@pytest.mark.parametrize("path", ["/api/missing", "/health/missing"])
def test_unknown_api_routes_are_404(client: TestClient, path: str) -> None:
    assert client.get(path).status_code == 404
