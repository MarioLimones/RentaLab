from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text

from rentalab.cargar_datos import cargar_datos_equipo
from rentalab.configuracion import Configuracion
from rentalab.principal import crear_aplicacion


def test_salud(cliente_http: TestClient) -> None:
    respuesta = cliente_http.get("/health")
    assert respuesta.status_code == 200
    assert respuesta.json() == {"status": "ok"}


def test_openapi_y_documentacion_vigente_bajo_api(cliente_http: TestClient) -> None:
    esquema_respuesta = cliente_http.get("/api/openapi.json")
    assert esquema_respuesta.status_code == 200
    esquema = esquema_respuesta.json()
    assert esquema["info"]["title"] == "RentaLab API"
    assert esquema["components"]["schemas"]["ActualizarEquipo"]["minProperties"] == 1
    assert "/health" in esquema["paths"]
    assert {"get", "post"} <= esquema["paths"]["/api/equipment"].keys()
    assert {"get", "put", "patch"} <= esquema["paths"]["/api/equipment/{equipment_id}"].keys()
    assert cliente_http.get("/api/docs").status_code == 200
    assert cliente_http.get("/api/redoc").status_code == 200
    for antiguo_ruta in ["/docs", "/redoc", "/openapi.json"]:
        assert cliente_http.get(antiguo_ruta).status_code == 404


def test_arranque_hace_no_crear_o_restablecer_la_esquema(tmp_path: Path) -> None:
    aplicacion = crear_aplicacion(
        Configuracion(
            url_base_datos=f"sqlite:///{(tmp_path / 'empty.sqlite3').as_posix()}", entorno="test"
        )
    )
    try:
        with TestClient(aplicacion) as test_cliente_http:
            assert test_cliente_http.get("/health").status_code == 200
            assert inspect(aplicacion.state.motor).get_table_names() == []
    finally:
        aplicacion.state.motor.dispose()


def test_migracion_comienza_con_un_vacio_catalogo(cliente_http: TestClient) -> None:
    assert cliente_http.get("/api/equipment").json() == []


def test_explicito_cargar_datos_es_repetible_y_preserva_existentes_ediciones(
    aplicacion: FastAPI,
) -> None:
    with aplicacion.state.fabrica_sesiones() as sesion:
        creados = cargar_datos_equipo(sesion)
        assert creados > 0
        sesion.commit()
        inicial_filas = sesion.execute(text("SELECT id, code FROM equipment ORDER BY id")).all()
        assert len(inicial_filas) == creados
        primero_id = inicial_filas[0].id
        sesion.execute(
            text("UPDATE equipment SET name = :name, active = 0 WHERE id = :id"),
            {"name": "Nombre editado a mano", "id": primero_id},
        )
        sesion.commit()
        assert cargar_datos_equipo(sesion) == 0
        sesion.commit()
        final_filas = sesion.execute(text("SELECT id, code FROM equipment ORDER BY id")).all()
        assert final_filas == inicial_filas
        editados = sesion.execute(
            text("SELECT name, active FROM equipment WHERE id = :id"), {"id": primero_id}
        ).one()
        assert editados.name == "Nombre editado a mano"
        assert editados.active == 0


def test_produccion_puede_servir_la_spa_sin_ocultando_desconocido_servidor_rutas(
    tmp_path: Path,
) -> None:
    interfaz_compilada = tmp_path / "dist"
    recursos = interfaz_compilada / "assets"
    recursos.mkdir(parents=True)
    (interfaz_compilada / "index.html").write_text(
        "<html><body>RentaLab SPA</body></html>", encoding="utf-8"
    )
    (recursos / "app.js").write_text("console.log('RentaLab');", encoding="utf-8")
    (tmp_path / "private.txt").write_text("Private content", encoding="utf-8")
    aplicacion = crear_aplicacion(
        Configuracion(
            url_base_datos=f"sqlite:///{(tmp_path / 'spa.sqlite3').as_posix()}",
            entorno="production",
            interfaz_compilada=interfaz_compilada,
        )
    )
    try:
        with TestClient(aplicacion) as test_cliente_http:
            for ruta in ["/", "/equipment", "/future/client/route"]:
                respuesta = test_cliente_http.get(ruta)
                assert respuesta.status_code == 200
                assert "RentaLab SPA" in respuesta.text
            assert "RentaLab" in test_cliente_http.get("/assets/app.js").text
            assert test_cliente_http.get("/api/missing").status_code == 401
            for ruta in ["/health/missing", "/assets/missing.js", "/missing.png"]:
                assert test_cliente_http.get(ruta).status_code == 404
            assert test_cliente_http.get("/assets/%2e%2e/%2e%2e/private.txt").status_code == 404
    finally:
        aplicacion.state.motor.dispose()


@pytest.mark.parametrize("ruta", ["/api/missing", "/health/missing"])
def test_desconocido_api_rutas_son_404(cliente_http: TestClient, ruta: str) -> None:
    assert cliente_http.get(ruta).status_code == 404
