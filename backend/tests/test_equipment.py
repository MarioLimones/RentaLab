import pytest
from conftest import authenticate
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from rentalab.config import Settings
from rentalab.main import create_app


def test_create_normalizes_and_returns_equipment(
    client: TestClient, equipment_payload: dict[str, object]
) -> None:
    equipment_payload.update(
        code="  cam-001  ",
        name="  Cámara de prueba  ",
        category="  Cámaras  ",
        description="  Unidad ficticia para las pruebas  ",
    )
    response = client.post("/api/equipment", json=equipment_payload)

    assert response.status_code == 201
    equipment = response.json()
    assert isinstance(equipment["id"], int)
    assert equipment == {
        "id": equipment["id"],
        "code": "CAM-001",
        "name": "Cámara de prueba",
        "category": "Cámaras",
        "description": "Unidad ficticia para las pruebas",
        "public_description": "",
        "technical_specs": {},
        "image_url": None,
        "active": True,
    }
    assert response.headers["location"] == f"/api/equipment/{equipment['id']}"
    assert client.get(response.headers["location"]).json() == equipment


def test_create_uses_optional_field_defaults(client: TestClient) -> None:
    response = client.post(
        "/api/equipment", json={"code": "CAM-1", "name": "Cámara", "category": "Vídeo"}
    )
    assert response.status_code == 201
    assert response.json()["description"] == ""
    assert response.json()["active"] is True


def test_list_is_ordered_and_can_filter_active_equipment(
    client: TestClient, equipment_payload: dict[str, object]
) -> None:
    assert client.get("/api/equipment").json() == []
    for code, active in [("Z-1", True), ("A-1", False), ("M-1", True)]:
        response = client.post(
            "/api/equipment", json={**equipment_payload, "code": code, "active": active}
        )
        assert response.status_code == 201

    assert [item["code"] for item in client.get("/api/equipment").json()] == ["A-1", "M-1", "Z-1"]
    assert [item["code"] for item in client.get("/api/equipment?active=true").json()] == [
        "M-1",
        "Z-1",
    ]
    assert [item["code"] for item in client.get("/api/equipment?active=false").json()] == ["A-1"]


def test_replace_and_patch_preserve_the_physical_unit_id(
    client: TestClient, equipment_payload: dict[str, object]
) -> None:
    equipment = client.post("/api/equipment", json=equipment_payload).json()
    url = f"/api/equipment/{equipment['id']}"

    replaced = client.put(
        url,
        json={
            "code": "  cam_002 ",
            "name": "Nueva cámara",
            "category": "Vídeo",
            "description": "Descripción revisada",
            "active": False,
        },
    )
    assert replaced.status_code == 200
    assert replaced.json() == {
        "id": equipment["id"],
        "code": "CAM_002",
        "name": "Nueva cámara",
        "category": "Vídeo",
        "description": "Descripción revisada",
        "public_description": "",
        "technical_specs": {},
        "image_url": None,
        "active": False,
    }

    activated = client.patch(url, json={"active": True})
    assert activated.status_code == 200
    assert activated.json() == {**replaced.json(), "active": True}
    patched = client.patch(url, json={"name": "  Nombre corregido  "})
    assert patched.status_code == 200
    assert patched.json() == {**activated.json(), "name": "Nombre corregido"}
    assert client.get(url).json() == patched.json()
    assert client.patch(url, json={"active": False}).json()["active"] is False
    assert len(client.get("/api/equipment").json()) == 1


def test_replace_resets_optional_fields_to_defaults(
    client: TestClient, equipment_payload: dict[str, object]
) -> None:
    equipment = client.post("/api/equipment", json={**equipment_payload, "active": False}).json()
    response = client.put(
        f"/api/equipment/{equipment['id']}",
        json={"code": "CAM-2", "name": "Cámara", "category": "Vídeo"},
    )
    assert response.status_code == 200
    assert response.json()["description"] == ""
    assert response.json()["active"] is True


def test_duplicate_code_is_conflict_after_normalization(
    client: TestClient, equipment_payload: dict[str, object]
) -> None:
    assert client.post("/api/equipment", json=equipment_payload).status_code == 201
    response = client.post("/api/equipment", json={**equipment_payload, "code": "  cam-001 "})
    assert response.status_code == 409
    assert len(client.get("/api/equipment").json()) == 1


@pytest.mark.parametrize("method", ["put", "patch"])
def test_edit_cannot_reuse_another_units_code(
    client: TestClient, equipment_payload: dict[str, object], method: str
) -> None:
    first = client.post("/api/equipment", json=equipment_payload).json()
    second = client.post("/api/equipment", json={**equipment_payload, "code": "CAM-002"}).json()
    payload = (
        {**equipment_payload, "code": " cam-001 "} if method == "put" else {"code": " cam-001 "}
    )
    response = client.request(method, f"/api/equipment/{second['id']}", json=payload)
    assert response.status_code == 409
    assert client.get(f"/api/equipment/{first['id']}").json()["code"] == "CAM-001"
    assert client.get(f"/api/equipment/{second['id']}").json()["code"] == "CAM-002"


def test_edit_can_keep_its_own_code(
    client: TestClient, equipment_payload: dict[str, object]
) -> None:
    equipment = client.post("/api/equipment", json=equipment_payload).json()
    response = client.patch(f"/api/equipment/{equipment['id']}", json={"code": " cam-001 "})
    assert response.status_code == 200
    assert response.json() == equipment


@pytest.mark.parametrize("method", ["get", "put", "patch"])
def test_missing_equipment_is_404(
    client: TestClient, equipment_payload: dict[str, object], method: str
) -> None:
    kwargs = {} if method == "get" else {"json": equipment_payload}
    assert client.request(method, "/api/equipment/99999", **kwargs).status_code == 404


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("code", ""),
        ("code", "   "),
        ("code", "X" * 41),
        ("code", "CAM 001"),
        ("code", "-CAM"),
        ("code", "CÁM-1"),
        ("code", "CAM/1"),
        ("code", None),
        ("code", 123),
        ("name", ""),
        ("name", "   "),
        ("name", "X" * 121),
        ("name", None),
        ("category", ""),
        ("category", "  "),
        ("category", "X" * 81),
        ("category", None),
        ("description", "X" * 2001),
        ("description", None),
        ("active", "false"),
        ("active", 0),
        ("active", 1),
        ("active", None),
        ("unknown", "unexpected"),
    ],
)
def test_invalid_creation_is_rejected_without_writing(
    client: TestClient, equipment_payload: dict[str, object], field: str, value: object
) -> None:
    response = client.post("/api/equipment", json={**equipment_payload, field: value})
    assert response.status_code == 422
    assert client.get("/api/equipment").json() == []


@pytest.mark.parametrize("field", ["name", "category", "description"])
@pytest.mark.parametrize("value", ["\x00Texto", "Tex\x00to", "Texto\x00"])
def test_nul_creation_is_rejected_without_writes_and_next_save_succeeds(
    client: TestClient, equipment_payload: dict[str, object], field: str, value: str
) -> None:
    existing = client.post("/api/equipment", json=equipment_payload)
    assert existing.status_code == 201
    before = client.get("/api/equipment").json()
    valid_payload = {**equipment_payload, "code": "CAM-002"}

    response = client.post("/api/equipment", json={**valid_payload, field: value})

    assert response.status_code == 422
    assert any(
        error["loc"][:2] == ["body", field] and "NUL" in error["msg"]
        for error in response.json()["detail"]
    )
    assert client.get("/api/equipment").json() == before
    saved = client.post("/api/equipment", json=valid_payload)
    assert saved.status_code == 201
    assert len(client.get("/api/equipment").json()) == 2


@pytest.mark.parametrize("method", ["put", "patch"])
@pytest.mark.parametrize("field", ["name", "category", "description"])
@pytest.mark.parametrize("value", ["\x00Texto", "Tex\x00to", "Texto\x00"])
def test_nul_edit_cannot_partially_update_and_next_save_succeeds(
    client: TestClient,
    equipment_payload: dict[str, object],
    method: str,
    field: str,
    value: str,
) -> None:
    equipment = client.post("/api/equipment", json=equipment_payload).json()
    before = client.get("/api/equipment").json()
    url = f"/api/equipment/{equipment['id']}"
    changes = {**equipment_payload, "code": "CAM-002", "active": False, field: value}

    response = client.request(method, url, json=changes)

    assert response.status_code == 422
    assert any(
        error["loc"][:2] == ["body", field] and "NUL" in error["msg"]
        for error in response.json()["detail"]
    )
    assert client.get(url).json() == equipment
    assert client.get("/api/equipment").json() == before
    saved = client.request(method, url, json={**changes, field: "Texto válido"})
    assert saved.status_code == 200
    assert saved.json()[field] == "Texto válido"
    assert saved.json()["code"] == "CAM-002"
    assert saved.json()["active"] is False
    assert len(client.get("/api/equipment").json()) == 1


@pytest.mark.parametrize("method", ["post", "put", "patch"])
def test_equipment_text_preserves_unicode_and_trims_outer_whitespace(
    client: TestClient, equipment_payload: dict[str, object], method: str
) -> None:
    url = "/api/equipment"
    if method != "post":
        equipment = client.post(url, json=equipment_payload).json()
        url = f"{url}/{equipment['id']}"
    response = client.request(
        method,
        url,
        json={
            **equipment_payload,
            "name": "\u00a0Cámara Straße 東京\u00a0",
            "category": "\tVídeo e iluminación\u2003",
            "description": "\nÓptica útil — espacios  interiores.\u2003",
        },
    )

    assert response.status_code == (201 if method == "post" else 200)
    assert response.json()["name"] == "Cámara Straße 東京"
    assert response.json()["category"] == "Vídeo e iluminación"
    assert response.json()["description"] == "Óptica útil — espacios  interiores."


@pytest.mark.parametrize("field", ["code", "name", "category"])
def test_creation_requires_mandatory_fields(
    client: TestClient, equipment_payload: dict[str, object], field: str
) -> None:
    del equipment_payload[field]
    assert client.post("/api/equipment", json=equipment_payload).status_code == 422


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"active": None},
        {"active": "false"},
        {"name": "  "},
        {"code": "BAD CODE"},
        {"description": None},
        {"unknown": True},
    ],
)
def test_invalid_patch_is_rejected_without_changes(
    client: TestClient, equipment_payload: dict[str, object], payload: dict[str, object]
) -> None:
    equipment = client.post("/api/equipment", json=equipment_payload).json()
    url = f"/api/equipment/{equipment['id']}"
    assert client.patch(url, json=payload).status_code == 422
    assert client.get(url).json() == equipment


def test_put_requires_the_complete_mandatory_representation(
    client: TestClient, equipment_payload: dict[str, object]
) -> None:
    equipment = client.post("/api/equipment", json=equipment_payload).json()
    url = f"/api/equipment/{equipment['id']}"
    assert client.put(url, json={"name": "Otro nombre"}).status_code == 422
    assert client.get(url).json() == equipment


def test_equipment_persists_when_application_is_recreated(
    client: TestClient, equipment_payload: dict[str, object], settings: Settings
) -> None:
    original = client.post("/api/equipment", json=equipment_payload).json()
    application = create_app(settings)
    try:
        with TestClient(application) as recreated_client:
            authenticate(recreated_client)
            assert recreated_client.get(f"/api/equipment/{original['id']}").json() == original
            assert recreated_client.get("/api/equipment").json() == [original]
    finally:
        application.state.engine.dispose()


@pytest.mark.parametrize(
    "raw_code", ["CAM-001", "cam-002", " CAM-002 ", "CÁM-002", "BAD CODE", "CAM\x00bad"]
)
def test_sqlite_enforces_unique_canonical_codes(
    app: FastAPI, client: TestClient, equipment_payload: dict[str, object], raw_code: str
) -> None:
    assert client.post("/api/equipment", json=equipment_payload).status_code == 201
    with pytest.raises(IntegrityError), app.state.engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO equipment (code, name, category, description, active) "
                "VALUES (:code, 'Direct unit', 'Test', '', 1)"
            ),
            {"code": raw_code},
        )
