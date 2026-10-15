from collections.abc import Iterator
from pathlib import Path

import pytest
from conftest import authenticate
from fastapi import FastAPI
from fastapi.testclient import TestClient

from rentalab.config import Settings
from rentalab.main import add_frontend_routes, create_app


@pytest.fixture
def spa_client(settings: Settings, tmp_path: Path) -> Iterator[TestClient]:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "downloads").mkdir()
    (dist / ".private").mkdir()
    (dist / "index.html").write_text("<html>RentaLab compiled</html>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("export const compiled = true;", encoding="utf-8")
    (dist / "assets" / "app.css").write_text("body { color: blue; }", encoding="utf-8")
    (dist / "downloads" / "instructions").write_text("Public instructions", encoding="utf-8")
    (dist / ".private" / "config").write_text("Not public", encoding="utf-8")
    (dist / ".env").write_text("Not public", encoding="utf-8")
    (tmp_path / "private.txt").write_text("Outside dist", encoding="utf-8")
    application = create_app(settings.model_copy(update={"frontend_dist": dist}))
    try:
        with TestClient(application) as test_client:
            yield test_client
    finally:
        application.state.engine.dispose()


@pytest.mark.parametrize(
    "path",
    [
        "/",
        "/catalogo",
        "/equipos/12?start_date=2030-11-10&end_date=2030-11-12",
        "/mis-reservas",
        "/mis-reservas/12",
        "/mis-incidencias",
        "/mi-cuenta",
        "/admin",
        "/admin/reservas/12",
        "/reservas",
        "/reservas/nueva",
        "/equipos/12/editar",
        "/future/client/route",
    ],
)
def test_direct_spa_navigation_and_refresh_are_public(spa_client: TestClient, path: str) -> None:
    for _ in range(2):
        response = spa_client.get(path)
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")
        assert response.headers["cache-control"] == "no-cache"
        assert response.text == "<html>RentaLab compiled</html>"
        assert "set-cookie" not in response.headers


@pytest.mark.parametrize(
    "path", ["/", "/catalogo", "/mis-reservas", "/admin", "/reservas", "/assets/app.js"]
)
def test_spa_and_static_assets_support_head(spa_client: TestClient, path: str) -> None:
    response = spa_client.head(path)
    assert response.status_code == 200
    assert response.content == b""
    assert int(response.headers["content-length"]) > 0


@pytest.mark.parametrize(
    ("path", "content_type", "content"),
    [
        ("/assets/app.js", "javascript", "export const compiled = true;"),
        ("/assets/app.css", "text/css", "body { color: blue; }"),
        ("/downloads/instructions", "application/octet-stream", "Public instructions"),
    ],
)
def test_only_real_compiled_files_are_served(
    spa_client: TestClient, path: str, content_type: str, content: str
) -> None:
    response = spa_client.get(path)
    assert response.status_code == 200
    assert content_type in response.headers["content-type"]
    assert response.text == content


@pytest.mark.parametrize(
    "path",
    [
        "/assets/missing.js",
        "/assets/missing",
        "/assets/missing/deep",
        "/downloads/missing",
        "/downloads/missing/deep",
        "/missing.svg",
        "/missing.folder/file",
        "/.env",
        "/.private/config",
        "/assets/%2e%2e/%2e%2e/private.txt",
        "/assets%2fmissing",
        "/assets%5cmissing",
        "/assets/%00",
    ],
)
def test_missing_static_files_and_unsafe_paths_never_return_the_spa(
    spa_client: TestClient, path: str
) -> None:
    response = spa_client.get(path)
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")
    assert "detail" in response.json()
    assert "RentaLab compiled" not in response.text


@pytest.mark.parametrize(
    ("path", "status"),
    [
        ("/api", 401),
        ("/api/does-not-exist", 401),
        ("/api/equipment/does-not-exist", 401),
        ("/api/docs", 401),
        ("/api/openapi.json", 401),
        ("/health/does-not-exist", 404),
        ("/docs", 404),
        ("/redoc", 404),
        ("/openapi.json", 404),
    ],
)
def test_server_routes_keep_json_errors_without_a_session(
    spa_client: TestClient, path: str, status: int
) -> None:
    response = spa_client.get(path)
    assert response.status_code == status
    assert response.headers["content-type"].startswith("application/json")
    assert "detail" in response.json()


def test_health_remains_the_minimal_json_endpoint(spa_client: TestClient) -> None:
    response = spa_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.parametrize(
    ("path", "status"),
    [
        ("/api/does-not-exist", 404),
        ("/api/equipment/999", 404),
        ("/api/equipment/not-an-id", 422),
        ("/api/public/equipment/999", 404),
        ("/api/public/equipment/not-an-id", 422),
        ("/health/does-not-exist", 404),
    ],
)
def test_api_errors_after_login_remain_json_with_the_spa_enabled(
    app: FastAPI, client: TestClient, tmp_path: Path, path: str, status: int
) -> None:
    (tmp_path / "index.html").write_text("<html>RentaLab compiled</html>", encoding="utf-8")
    add_frontend_routes(app, tmp_path)
    response = client.get(path)
    assert response.status_code == status
    assert response.headers["content-type"].startswith("application/json")
    assert "detail" in response.json()


@pytest.mark.parametrize(
    ("method", "path"),
    [("GET", "/api/imports"), ("HEAD", "/api/equipment"), ("HEAD", "/health")],
)
def test_the_spa_preserves_method_not_allowed_and_allow_headers(
    client: TestClient, settings: Settings, tmp_path: Path, method: str, path: str
) -> None:
    original = client.request(method, path)
    assert original.status_code == 405
    (tmp_path / "index.html").write_text("<html>RentaLab compiled</html>", encoding="utf-8")
    application = create_app(settings.model_copy(update={"frontend_dist": tmp_path}))
    with TestClient(application) as spa_browser:
        authenticate(spa_browser)
        with_spa = spa_browser.request(method, path)

    assert with_spa.status_code == original.status_code
    assert with_spa.headers["allow"] == original.headers["allow"]
    assert with_spa.headers["content-type"] == original.headers["content-type"]
    assert with_spa.content == original.content


def test_unsupported_method_does_not_serve_the_spa(spa_client: TestClient) -> None:
    response = spa_client.post("/reservas")
    assert response.status_code == 405
    assert response.headers["content-type"].startswith("application/json")


def test_frontend_configuration_requires_a_compiled_index(
    settings: Settings, tmp_path: Path
) -> None:
    with pytest.raises(ValueError, match="built index.html"):
        create_app(settings.model_copy(update={"frontend_dist": tmp_path}))
