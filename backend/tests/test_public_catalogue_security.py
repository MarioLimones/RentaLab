import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

PUBLIC_EQUIPMENT_FIELDS = {
    "id",
    "name",
    "category",
    "public_description",
    "technical_specs",
    "image_url",
    "image_fallback_url",
    "active_reservations_count",
}
PUBLIC_AVAILABILITY_FIELDS = {
    "equipment_id",
    "start_date",
    "end_date",
    "available",
    "status",
}


def create_private_equipment(client: TestClient, active: bool = True) -> dict:
    response = client.post(
        "/api/equipment",
        json={
            "code": "PRIVATE-CODE-CANARY",
            "name": "Cámara pública",
            "category": "Cámaras",
            "description": "INTERNAL-NOTE-CANARY",
            "public_description": "Cámara para proyectos audiovisuales",
            "technical_specs": {"Resolución": "4K"},
            "active": active,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_public_schema_does_not_expand_when_an_administrator_is_authenticated(
    app: FastAPI, client: TestClient
) -> None:
    equipment = create_private_equipment(client)
    incident = client.post(
        "/api/incidents",
        json={
            "equipment_id": equipment["id"],
            "title": "PRIVATE-FAULT-TITLE-CANARY",
            "description": "PRIVATE-FAULT-DESCRIPTION-CANARY",
            "blocking": True,
        },
    )
    assert incident.status_code == 201
    paths = [
        "/api/public/equipment",
        f"/api/public/equipment/{equipment['id']}",
        f"/api/public/equipment/{equipment['id']}/availability"
        "?start_date=2026-11-10&end_date=2026-11-12",
    ]
    with TestClient(app) as anonymous:
        for path in paths:
            public_response = anonymous.get(path)
            administrative_response = client.get(path)
            assert public_response.status_code == administrative_response.status_code == 200
            assert public_response.json() == administrative_response.json()
            assert "PRIVATE-" not in public_response.text
            assert "INTERNAL-" not in public_response.text


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
@pytest.mark.parametrize("suffix", ["", "/1"])
def test_public_catalogue_never_accepts_management_writes(
    app: FastAPI, client: TestClient, method: str, suffix: str
) -> None:
    equipment = create_private_equipment(client)
    before = client.get(f"/api/equipment/{equipment['id']}").json()
    # The administrator already has the current CSRF token: even a valid
    # administrative session must use the protected management namespace.
    with TestClient(app) as anonymous:
        path = f"/api/public/equipment{suffix}"
        for browser in [anonymous, client]:
            response = browser.request(method, path, json={"name": "Mutated name"})
            assert response.status_code in {401, 403, 405}
            assert "PRIVATE-CODE-CANARY" not in response.text
            assert "INTERNAL-NOTE-CANARY" not in response.text
    assert client.get(f"/api/equipment/{equipment['id']}").json() == before
    assert len(client.get("/api/equipment").json()) == 1


def test_public_error_responses_do_not_reveal_inactive_equipment_or_private_notes(
    app: FastAPI, client: TestClient
) -> None:
    equipment = create_private_equipment(client, active=False)
    with TestClient(app) as anonymous:
        missing = anonymous.get("/api/public/equipment/999999")
        inactive = anonymous.get(f"/api/public/equipment/{equipment['id']}")
        unavailable = anonymous.get(
            f"/api/public/equipment/{equipment['id']}/availability",
            params={"start_date": "2026-11-10", "end_date": "2026-11-12"},
        )
        assert missing.status_code == inactive.status_code == unavailable.status_code == 404
        assert missing.json() == inactive.json() == unavailable.json()
        invalid_dates = anonymous.get(
            f"/api/public/equipment/{equipment['id']}/availability",
            params={"start_date": "2026-11-10"},
        )
        assert invalid_dates.status_code == 422
        for response in [missing, inactive, unavailable, invalid_dates]:
            assert "PRIVATE-CODE-CANARY" not in response.text
            assert "INTERNAL-NOTE-CANARY" not in response.text
            assert "Cámara pública" not in response.text


def test_openapi_separates_explicit_public_responses_from_admin_management(
    client: TestClient,
) -> None:
    response = client.get("/api/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    public_paths = {
        "/api/public/equipment",
        "/api/public/equipment/{equipment_id}",
        "/api/public/equipment/{equipment_id}/availability",
    }
    for path in public_paths:
        operation = schema["paths"][path]["get"]
        assert operation["security"] == []
        result = operation["responses"]["200"]["content"]["application/json"]["schema"]
        if path == "/api/public/equipment":
            result = result["items"]
        model = schema["components"]["schemas"][result["$ref"].split("/")[-1]]
        expected = (
            PUBLIC_AVAILABILITY_FIELDS
            if path.endswith("/availability")
            else PUBLIC_EQUIPMENT_FIELDS
        )
        assert set(model["properties"]) == expected
    for path in [
        "/api/equipment",
        "/api/equipment/{equipment_id}",
        "/api/equipment/{equipment_id}/availability",
    ]:
        operation = schema["paths"][path]["get"]
        assert operation["security"] == [{"SessionCookie": []}]
        assert "admin" in operation["description"]
        assert {"401", "403"} <= set(operation["responses"])
