from collections.abc import Iterator
from pathlib import Path

import pytest
from conftest import autenticar
from fastapi import FastAPI
from fastapi.testclient import TestClient

from rentalab.configuracion import Configuracion
from rentalab.principal import agregar_interfaz_rutas, crear_aplicacion


@pytest.fixture
def spa_cliente(ajustes: Configuracion, tmp_path: Path) -> Iterator[TestClient]:
    compilacion = tmp_path / "dist"
    (compilacion / "assets").mkdir(parents=True)
    (compilacion / "downloads").mkdir()
    (compilacion / ".private").mkdir()
    (compilacion / "index.html").write_text("<html>RentaLab compiled</html>", encoding="utf-8")
    (compilacion / "assets" / "app.js").write_text(
        "export const compiled = true;", encoding="utf-8"
    )
    (compilacion / "assets" / "app.css").write_text("body { color: blue; }", encoding="utf-8")
    (compilacion / "downloads" / "instructions").write_text("Public instructions", encoding="utf-8")
    (compilacion / ".private" / "config").write_text("Not public", encoding="utf-8")
    (compilacion / ".env").write_text("Not public", encoding="utf-8")
    (tmp_path / "private.txt").write_text("Outside dist", encoding="utf-8")
    aplicacion = crear_aplicacion(ajustes.model_copy(update={"interfaz_compilada": compilacion}))
    try:
        with TestClient(aplicacion) as test_cliente_http:
            yield test_cliente_http
    finally:
        aplicacion.state.motor.dispose()


@pytest.mark.parametrize(
    "ruta",
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
def test_directa_spa_navegacion_y_actualizacion_son_publico(
    spa_cliente: TestClient, ruta: str
) -> None:
    for _ in range(2):
        respuesta = spa_cliente.get(ruta)
        assert respuesta.status_code == 200
        assert respuesta.headers["content-type"].startswith("text/html")
        assert respuesta.headers["cache-control"] == "no-cache"
        assert respuesta.text == "<html>RentaLab compiled</html>"
        assert "set-cookie" not in respuesta.headers


@pytest.mark.parametrize(
    "ruta", ["/", "/catalogo", "/mis-reservas", "/admin", "/reservas", "/assets/app.js"]
)
def test_spa_y_estaticos_recursos_compatibilidad_head(spa_cliente: TestClient, ruta: str) -> None:
    respuesta = spa_cliente.head(ruta)
    assert respuesta.status_code == 200
    assert respuesta.content == b""
    assert int(respuesta.headers["content-length"]) > 0


@pytest.mark.parametrize(
    ("ruta", "contenido_tipo", "contenido"),
    [
        ("/assets/app.js", "javascript", "export const compiled = true;"),
        ("/assets/app.css", "text/css", "body { color: blue; }"),
        ("/downloads/instructions", "application/octet-stream", "Public instructions"),
    ],
)
def test_solo_real_compilada_archivos_son_servido(
    spa_cliente: TestClient, ruta: str, contenido_tipo: str, contenido: str
) -> None:
    respuesta = spa_cliente.get(ruta)
    assert respuesta.status_code == 200
    assert contenido_tipo in respuesta.headers["content-type"]
    assert respuesta.text == contenido


@pytest.mark.parametrize(
    "ruta",
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
def test_ausente_estaticos_archivos_y_inseguro_rutas_nunca_devolver_la_spa(
    spa_cliente: TestClient, ruta: str
) -> None:
    respuesta = spa_cliente.get(ruta)
    assert respuesta.status_code == 404
    assert respuesta.headers["content-type"].startswith("application/json")
    assert "detail" in respuesta.json()
    assert "RentaLab compiled" not in respuesta.text


@pytest.mark.parametrize(
    ("ruta", "estado"),
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
def test_servidor_rutas_mantener_json_errores_sin_a_sesion(
    spa_cliente: TestClient, ruta: str, estado: int
) -> None:
    respuesta = spa_cliente.get(ruta)
    assert respuesta.status_code == estado
    assert respuesta.headers["content-type"].startswith("application/json")
    assert "detail" in respuesta.json()


def test_salud_permanece_la_minimo_json_punto_acceso(spa_cliente: TestClient) -> None:
    respuesta = spa_cliente.get("/health")
    assert respuesta.status_code == 200
    assert respuesta.json() == {"status": "ok"}


@pytest.mark.parametrize(
    ("ruta", "estado"),
    [
        ("/api/does-not-exist", 404),
        ("/api/equipment/999", 404),
        ("/api/equipment/not-an-id", 422),
        ("/api/public/equipment/999", 404),
        ("/api/public/equipment/not-an-id", 422),
        ("/health/does-not-exist", 404),
    ],
)
def test_api_errores_despues_iniciar_sesion_permanecen_json_con_la_spa_activado(
    aplicacion: FastAPI, cliente_http: TestClient, tmp_path: Path, ruta: str, estado: int
) -> None:
    (tmp_path / "index.html").write_text("<html>RentaLab compiled</html>", encoding="utf-8")
    agregar_interfaz_rutas(aplicacion, tmp_path)
    respuesta = cliente_http.get(ruta)
    assert respuesta.status_code == estado
    assert respuesta.headers["content-type"].startswith("application/json")
    assert "detail" in respuesta.json()


@pytest.mark.parametrize(
    ("metodo", "ruta"),
    [("GET", "/api/imports"), ("HEAD", "/api/equipment"), ("HEAD", "/health")],
)
def test_la_spa_preserva_metodo_no_permitidos_y_permitir_cabeceras(
    cliente_http: TestClient, ajustes: Configuracion, tmp_path: Path, metodo: str, ruta: str
) -> None:
    original = cliente_http.request(metodo, ruta)
    assert original.status_code == 405
    (tmp_path / "index.html").write_text("<html>RentaLab compiled</html>", encoding="utf-8")
    aplicacion = crear_aplicacion(ajustes.model_copy(update={"interfaz_compilada": tmp_path}))
    with TestClient(aplicacion) as spa_navegador:
        autenticar(spa_navegador)
        con_spa = spa_navegador.request(metodo, ruta)

    assert con_spa.status_code == original.status_code
    assert con_spa.headers["allow"] == original.headers["allow"]
    assert con_spa.headers["content-type"] == original.headers["content-type"]
    assert con_spa.content == original.content


def test_no_admitido_metodo_hace_no_servir_la_spa(spa_cliente: TestClient) -> None:
    respuesta = spa_cliente.post("/reservas")
    assert respuesta.status_code == 405
    assert respuesta.headers["content-type"].startswith("application/json")


def test_interfaz_configuracion_requiere_a_compilada_indice(
    ajustes: Configuracion, tmp_path: Path
) -> None:
    with pytest.raises(ValueError, match="built index.html"):
        crear_aplicacion(ajustes.model_copy(update={"interfaz_compilada": tmp_path}))
