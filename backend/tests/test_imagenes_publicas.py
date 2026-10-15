import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.mark.parametrize(
    "nombre",
    ["demo-camera.jpg", "demo-microphone.jpg", "demo-light.jpg"]
    + [f"catalogue-{numero:02d}.jpg" for numero in range(1, 21) if numero != 2],
)
def test_ejemplo_fotos_son_local_y_publico(aplicacion: FastAPI, nombre: str) -> None:
    with TestClient(aplicacion) as visitante:
        respuesta = visitante.get(f"/api/public/images/{nombre}")
    assert respuesta.status_code == 200
    assert respuesta.headers["content-type"] == "image/jpeg"
    assert respuesta.content.startswith(b"\xff\xd8\xff")


def test_catalogo_videocamara_foto_es_publico_png(aplicacion: FastAPI) -> None:
    with TestClient(aplicacion) as visitante:
        respuesta = visitante.get("/api/public/images/catalogue-02.png")
    assert respuesta.status_code == 200
    assert respuesta.headers["content-type"] == "image/png"
    assert respuesta.content.startswith(b"\x89PNG\r\n\x1a\n")


def test_foto_creditos_son_publico_y_incluir_autores_y_licencia(aplicacion: FastAPI) -> None:
    with TestClient(aplicacion) as visitante:
        respuesta = visitante.get("/api/public/images/photo-credits.txt")
    assert respuesta.status_code == 200
    assert respuesta.headers["content-type"].startswith("text/plain")
    for credito in ("Evan-Amos", "Sam Wilson", "https://creativecommons.org/licenses/by-sa/4.0/"):
        assert credito in respuesta.text


@pytest.mark.parametrize("nombre", ["missing.jpg", "media.py", "runtime.json"])
def test_otro_archivos_son_no_servido_como_publico_recursos(
    cliente_http: TestClient, nombre: str
) -> None:
    respuesta = cliente_http.get(f"/api/public/images/{nombre}")
    assert respuesta.status_code == 404
    assert respuesta.headers["content-type"] == "application/json"
