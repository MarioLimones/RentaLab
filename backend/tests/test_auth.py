from datetime import datetime

import pytest
from conftest import TEST_PASSWORD, TEST_USERNAME, authenticate
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import Response

from rentalab.config import Settings
from rentalab.main import create_app


def csrf(client: TestClient) -> str:
    response = client.get("/api/auth/csrf")
    assert response.status_code == 200
    return response.json()["csrf_token"]


def login(client: TestClient, token: str, **changes: str) -> Response:
    return client.post(
        "/api/auth/login",
        json={"username": TEST_USERNAME, "password": TEST_PASSWORD, **changes},
        headers={"X-CSRF-Token": token},
    )


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/api/equipment"),
        ("get", "/api/equipment/1"),
        ("get", "/api/equipment/1/availability"),
        ("post", "/api/equipment"),
        ("get", "/api/reservations"),
        ("post", "/api/reservations"),
        ("post", "/api/reservations/1/cancel"),
        ("get", "/api/incidents"),
        ("post", "/api/incidents"),
        ("patch", "/api/incidents/1/status"),
        ("post", "/api/imports"),
        ("get", "/api/imports/example"),
        ("get", "/api/docs"),
        ("get", "/api/redoc"),
        ("get", "/api/openapi.json"),
    ],
)
def test_business_and_documentation_require_a_session(app: FastAPI, method: str, path: str) -> None:
    with TestClient(app) as anonymous:
        response = anonymous.request(method, path)
    assert response.status_code == 401
    assert set(response.json()) == {"detail"}


def test_anonymous_session_is_401_but_health_and_csrf_are_public(app: FastAPI) -> None:
    with TestClient(app) as anonymous:
        assert anonymous.get("/api/auth/session").status_code == 401
        assert anonymous.get("/health").json() == {"status": "ok"}
        response = anonymous.get("/api/auth/csrf")
        assert response.status_code == 200
        assert isinstance(response.json()["csrf_token"], str)
        assert len(response.json()["csrf_token"]) >= 32
        assert anonymous.get("/api/public/equipment").status_code == 200


def test_login_requires_a_session_bound_csrf_token(app: FastAPI) -> None:
    with TestClient(app) as anonymous:
        response = anonymous.post(
            "/api/auth/login", json={"username": "operator", "password": "test"}
        )
        assert response.status_code == 403
        assert set(response.json()) == {"detail"}


def test_cookie_is_httponly_same_site_and_csrf_is_stable(app: FastAPI) -> None:
    with TestClient(app) as anonymous:
        first = anonymous.get("/api/auth/csrf")
        assert first.status_code == 200
        cookie = first.headers["set-cookie"].lower()
        assert "rentalab_session=" in cookie
        assert "httponly" in cookie
        assert "samesite=lax" in cookie
        assert anonymous.get("/api/auth/csrf").json() == first.json()


def test_successful_login_returns_the_current_operator(client: TestClient) -> None:
    response = client.get("/api/auth/session")
    assert response.status_code == 200
    session = response.json()
    assert session["authenticated"] is True
    assert session["username"] == TEST_USERNAME
    assert datetime.fromisoformat(session["expires_at"]).tzinfo is not None


@pytest.mark.parametrize("changes", [{"username": "unknown"}, {"password": "incorrect"}])
def test_incorrect_credentials_are_generic_and_do_not_authenticate(
    app: FastAPI, changes: dict[str, str]
) -> None:
    with TestClient(app) as anonymous:
        response = login(anonymous, csrf(anonymous), **changes)
        assert response.status_code == 401
        detail = response.json()["detail"]
        assert isinstance(detail, str)
        assert TEST_USERNAME not in detail
        assert TEST_PASSWORD not in response.text
        assert "argon2" not in response.text.lower()
        assert anonymous.get("/api/auth/session").status_code == 401


def test_wrong_username_and_wrong_password_receive_the_same_error(app: FastAPI) -> None:
    with TestClient(app) as anonymous:
        token = csrf(anonymous)
        wrong_username = login(anonymous, token, username="unknown")
        wrong_password = login(anonymous, token, password="incorrect")
        assert wrong_username.status_code == wrong_password.status_code == 401
        assert wrong_username.json() == wrong_password.json()


def test_invalid_login_payload_never_echoes_the_password(app: FastAPI) -> None:
    password = "sensitive-password-never-reflected-" * 40
    with TestClient(app) as anonymous:
        response = login(anonymous, csrf(anonymous), password=password)
        assert response.status_code == 422
        assert password not in response.text
        assert "input" not in response.json()["detail"][0]


def test_login_rotates_the_anonymous_cookie_and_csrf_token(app: FastAPI) -> None:
    with TestClient(app) as anonymous:
        original_token = csrf(anonymous)
        original_cookie = anonymous.cookies.get("rentalab_session")
        response = login(anonymous, original_token)
        assert response.status_code == 200
        assert response.json()["authenticated"] is True
        assert anonymous.cookies.get("rentalab_session") != original_cookie
        assert csrf(anonymous) != original_token
        rejected = anonymous.post("/api/auth/logout", headers={"X-CSRF-Token": original_token})
        assert rejected.status_code == 403
        assert anonymous.get("/api/auth/session").status_code == 200


def test_login_rejects_a_csrf_token_without_its_cookie_or_from_another_browser(
    app: FastAPI,
) -> None:
    with TestClient(app) as first, TestClient(app) as second:
        token = csrf(first)
        assert login(second, token).status_code == 403
        csrf(second)
        assert login(second, token).status_code == 403
        assert login(first, token).status_code == 200


@pytest.mark.parametrize("token", [None, "invalid-csrf-token"])
@pytest.mark.parametrize(
    "method,path",
    [
        ("post", "/api/equipment"),
        ("put", "/api/equipment/1"),
        ("patch", "/api/equipment/1"),
        ("post", "/api/reservations"),
        ("post", "/api/reservations/1/cancel"),
        ("post", "/api/incidents"),
        ("patch", "/api/incidents/1/status"),
        ("post", "/api/imports"),
        ("post", "/api/auth/logout"),
    ],
)
def test_authenticated_writes_require_csrf_before_processing_the_body(
    client: TestClient, token: str | None, method: str, path: str
) -> None:
    client.headers.pop("X-CSRF-Token")
    response = client.request(
        method, path, headers={"X-CSRF-Token": token} if token is not None else {}
    )
    assert response.status_code == 403
    assert set(response.json()) == {"detail"}
    assert client.get("/api/equipment").json() == []


def test_reads_do_not_require_csrf_and_do_not_change_business_data(client: TestClient) -> None:
    client.headers.pop("X-CSRF-Token")
    for path in [
        "/api/equipment",
        "/api/reservations",
        "/api/incidents",
        "/api/imports/example",
        "/api/docs",
        "/api/redoc",
        "/api/openapi.json",
    ]:
        assert client.get(path).status_code == 200
    assert client.get("/api/equipment").json() == []
    assert client.get("/api/reservations").json() == []
    assert client.get("/api/incidents").json() == []


def test_logout_revokes_copied_cookies_and_clears_the_browser_cookie(
    app: FastAPI, client: TestClient
) -> None:
    original_cookie = client.cookies.get("rentalab_session")
    response = client.post("/api/auth/logout")
    assert response.status_code == 200
    assert response.json() == {"authenticated": False}
    assert "expires=thu, 01 jan 1970" in response.headers["set-cookie"].lower()
    assert client.cookies.get("rentalab_session") is None
    assert client.get("/api/auth/session").status_code == 401
    with TestClient(app) as replay:
        replay.cookies.set("rentalab_session", original_cookie)
        assert replay.get("/api/auth/session").status_code == 401
        assert replay.get("/api/reservations").status_code == 401


def test_tampered_session_cookie_cannot_authenticate(app: FastAPI) -> None:
    with TestClient(app) as browser:
        authenticate(browser)
        original = browser.cookies.get("rentalab_session")
        browser.cookies.clear()
        browser.cookies.set("rentalab_session", f"{original}tampered")
        assert browser.get("/api/auth/session").status_code == 401
        assert browser.get("/api/reservations").status_code == 401


def test_session_has_absolute_server_expiry_without_extending_on_activity(
    app: FastAPI, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = client.get("/api/auth/session").json()
    expiry = int(datetime.fromisoformat(original["expires_at"]).timestamp())
    monkeypatch.setattr("rentalab.auth.service.current_timestamp", lambda: expiry - 1)
    assert client.get("/api/auth/session").json() == original
    csrf(client)
    assert client.get("/api/equipment").status_code == 200
    assert client.get("/api/auth/session").json() == original
    monkeypatch.setattr("rentalab.auth.service.current_timestamp", lambda: expiry)
    assert client.get("/api/auth/session").status_code == 401
    assert client.get("/api/reservations").status_code == 401
    assert client.post("/api/incidents", json={}).status_code == 401


def test_production_cookie_is_secure_and_the_spa_can_stay_public(
    app: FastAPI, settings: Settings
) -> None:
    production = create_app(settings.model_copy(update={"environment": "production"}))
    try:
        with TestClient(production, base_url="https://testserver") as browser:
            response = browser.get("/api/auth/csrf")
            cookie = response.headers["set-cookie"].lower()
            assert "secure" in cookie
            assert "httponly" in cookie
            assert "samesite=lax" in cookie
            authenticate(browser)
            assert browser.get("/api/equipment").status_code == 200
    finally:
        production.state.engine.dispose()


def test_unicode_username_and_exact_password_are_supported(
    app: FastAPI, settings: Settings
) -> None:
    username = "Operador demostración 日本語"
    application = create_app(settings.model_copy(update={"operator_username": f"  {username}  "}))
    try:
        with TestClient(application) as browser:
            response = login(browser, csrf(browser), username=f"  {username}  ")
            assert response.status_code == 200
            assert response.json()["username"] == username
            assert browser.get("/api/auth/session").json()["username"] == username
    finally:
        application.state.engine.dispose()


def test_changed_operator_credentials_revoke_existing_server_sessions(
    app: FastAPI, settings: Settings, client: TestClient
) -> None:
    previous_cookie = client.cookies.get("rentalab_session")
    changed = create_app(settings.model_copy(update={"operator_username": "different-operator"}))
    try:
        with TestClient(changed) as browser:
            browser.cookies.set("rentalab_session", previous_cookie)
            assert browser.get("/api/auth/session").status_code == 401
            assert browser.get("/api/reservations").status_code == 401
    finally:
        changed.state.engine.dispose()


def test_unauthenticated_upload_is_rejected_before_reading_its_body(app: FastAPI) -> None:
    consumed = False

    def upload():
        nonlocal consumed
        consumed = True
        yield b"This body must not be read without a valid session"

    with TestClient(app) as anonymous:
        request = anonymous.build_request(
            "POST",
            "/api/imports",
            content=upload(),
            headers={"Content-Type": "multipart/form-data; boundary=missing"},
        )
        assert anonymous.send(request).status_code == 401
        assert consumed is False


def test_auth_responses_cannot_be_cached(app: FastAPI, client: TestClient) -> None:
    assert client.get("/api/auth/session").headers["cache-control"] == "no-store"
    assert client.get("/api/auth/csrf").headers["cache-control"] == "no-store"
    with TestClient(app) as anonymous:
        assert anonymous.get("/api/auth/session").headers["cache-control"] == "no-store"
        assert anonymous.get("/api/equipment").headers["cache-control"] == "no-store"


def test_exclusive_database_lock_during_session_lookup_is_a_controlled_temporary_failure(
    app: FastAPI, settings: Settings
) -> None:
    second = create_app(settings.model_copy(update={"sqlite_busy_timeout_ms": 25}))
    try:
        with TestClient(second, raise_server_exceptions=False) as browser:
            authenticate(browser)
            with app.state.engine.connect() as lock_owner:
                lock_owner.exec_driver_sql("BEGIN EXCLUSIVE")
                response = browser.get("/api/equipment")
                assert response.status_code == 503
                assert response.headers["retry-after"] == "1"
                assert isinstance(response.json()["detail"], str)
                assert "SELECT" not in response.text
                assert "auth_sessions" not in response.text
                lock_owner.rollback()
            assert browser.get("/api/equipment").json() == []
    finally:
        second.state.engine.dispose()
