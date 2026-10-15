import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.mark.parametrize(
    "name",
    ["demo-camera.jpg", "demo-microphone.jpg", "demo-light.jpg"]
    + [f"catalogue-{number:02d}.jpg" for number in range(1, 21) if number != 2],
)
def test_example_photos_are_local_and_public(app: FastAPI, name: str) -> None:
    with TestClient(app) as visitor:
        response = visitor.get(f"/api/public/images/{name}")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert response.content.startswith(b"\xff\xd8\xff")


def test_catalogue_camcorder_photo_is_public_png(app: FastAPI) -> None:
    with TestClient(app) as visitor:
        response = visitor.get("/api/public/images/catalogue-02.png")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content.startswith(b"\x89PNG\r\n\x1a\n")


def test_photo_credits_are_public_and_include_authors_and_license(app: FastAPI) -> None:
    with TestClient(app) as visitor:
        response = visitor.get("/api/public/images/photo-credits.txt")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    for credit in ("Evan-Amos", "Sam Wilson", "https://creativecommons.org/licenses/by-sa/4.0/"):
        assert credit in response.text


@pytest.mark.parametrize("name", ["missing.jpg", "media.py", "runtime.json"])
def test_other_files_are_not_served_as_public_assets(client: TestClient, name: str) -> None:
    response = client.get(f"/api/public/images/{name}")
    assert response.status_code == 404
    assert response.headers["content-type"] == "application/json"
