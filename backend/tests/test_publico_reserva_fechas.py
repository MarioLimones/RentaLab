"""
Las fechas públicas de reservas conservan un intervalo por reserva activa sin exponer
identidades.
"""

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event
from test_catalogo_publico import crear_equipo
from test_catalogo_publico import visitante as visitante
from test_publico_calendario import reservar
from test_publico_reserva_recuentos import negocio_hoy as negocio_hoy


@pytest.mark.usefixtures("negocio_hoy")
def test_publico_fechas_mantener_duplicados_solapamiento_y_original_fechas_en_estable_orden(
    aplicacion: FastAPI, cliente_http: TestClient, visitante: TestClient
) -> None:
    unidades = [crear_equipo(cliente_http, codigo=f"MODEL-{indice}") for indice in range(3)]
    reservar(cliente_http, unidades[0]["id"], "2030-12-10", "2030-12-12")
    reservar(cliente_http, unidades[0]["id"], "2030-11-14", "2030-11-18")
    reservar(cliente_http, unidades[1]["id"], "2030-11-14", "2030-11-18")
    reservar(cliente_http, unidades[2]["id"], "2030-11-14", "2030-11-16")
    reservar(cliente_http, unidades[2]["id"], "2030-11-16", "2030-11-19")
    esperado = {
        "equipment_id": unidades[0]["id"],
        "reservations": [
            {"start_date": "2030-11-14", "end_date": "2030-11-16"},
            {"start_date": "2030-11-14", "end_date": "2030-11-18"},
            {"start_date": "2030-11-14", "end_date": "2030-11-18"},
            {"start_date": "2030-11-16", "end_date": "2030-11-19"},
            {"start_date": "2030-12-10", "end_date": "2030-12-12"},
        ],
    }
    consultas: list[str] = []

    def registro_consulta(_conexion: Any, _cursor: Any, sentencia: str, *_argumentos: Any) -> None:
        if "reservations" in sentencia:
            consultas.append(sentencia)

    event.listen(aplicacion.state.motor, "before_cursor_execute", registro_consulta)
    try:
        respuesta = visitante.get(f"/api/public/equipment/{unidades[1]['id']}/reservations")
    finally:
        event.remove(aplicacion.state.motor, "before_cursor_execute", registro_consulta)
    assert respuesta.status_code == 200
    assert respuesta.json() == esperado
    assert respuesta.headers["cache-control"] == "no-store"
    assert (
        cliente_http.get(f"/api/public/equipment/{unidades[0]['id']}/reservations").json()
        == esperado
    )
    assert visitante.get("/api/public/equipment").json()[0]["active_reservations_count"] == 5
    assert len(consultas) == 1
    selected_columns = consultas[0].split("FROM")[0].strip()
    assert selected_columns == "SELECT reservations.start_date, reservations.end_date"
    assert "customer" not in consultas[0]
    assert "external_reference" not in consultas[0]
    assert (
        "ORDER BY reservations.start_date, reservations.end_date, reservations.id" in consultas[0]
    )
    assert "PRIVATE-" not in respuesta.text
    assert "private-calendar@example.test" not in respuesta.text


def test_publico_fechas_son_vacio_sin_reservas_y_ocultar_inactivo_o_ausente_equipo(
    cliente_http: TestClient, visitante: TestClient
) -> None:
    equipo = crear_equipo(cliente_http)
    url = f"/api/public/equipment/{equipo['id']}/reservations"
    respuesta = visitante.get(url)
    assert respuesta.status_code == 200
    assert respuesta.json() == {"equipment_id": equipo["id"], "reservations": []}
    desactivado = cliente_http.patch(f"/api/equipment/{equipo['id']}", json={"active": False})
    assert desactivado.status_code == 200
    inactivo = visitante.get(url)
    ausente = visitante.get("/api/public/equipment/999999/reservations")
    assert inactivo.status_code == ausente.status_code == 404
    assert inactivo.json() == ausente.json() == {"detail": "El equipo no existe"}


@pytest.mark.parametrize("metodo", ["POST", "PUT", "PATCH", "DELETE"])
def test_publico_reserva_fechas_rechazar_escrituras_y_preservar_historial(
    cliente_http: TestClient, visitante: TestClient, metodo: str
) -> None:
    equipo = crear_equipo(cliente_http)
    reservar(cliente_http, equipo["id"], "2030-11-18", "2030-11-20")
    antes = cliente_http.get("/api/reservations").json()
    ruta = f"/api/public/equipment/{equipo['id']}/reservations"
    assert visitante.request(metodo, ruta, json={"status": "cancelled"}).status_code == 401
    assert cliente_http.request(metodo, ruta, json={"status": "cancelled"}).status_code == 405
    assert cliente_http.get("/api/reservations").json() == antes


@pytest.mark.parametrize("parametros", [{"start_date": "2030-11-18"}, {"status": "cancelled"}])
def test_publico_reserva_fechas_hacer_no_aceptar_filtros(
    cliente_http: TestClient, visitante: TestClient, parametros: dict[str, str]
) -> None:
    equipo = crear_equipo(cliente_http)
    respuesta = visitante.get(
        f"/api/public/equipment/{equipo['id']}/reservations", params=parametros
    )
    assert respuesta.status_code == 422


def test_publico_reserva_fechas_openapi_expone_solo_fechas_sin_autenticacion(
    cliente_http: TestClient,
) -> None:
    esquema = cliente_http.get("/api/openapi.json").json()
    operacion = esquema["paths"]["/api/public/equipment/{equipment_id}/reservations"]["get"]
    assert operacion["security"] == []
    assert {parametro["in"] for parametro in operacion["parameters"]} == {"path"}
    assert "503" in operacion["responses"]
    modelo = esquema["components"]["schemas"]["PublicoReservasLectura"]
    assert set(modelo["properties"]) == {"equipment_id", "reservations"}
    elemento_ref = modelo["properties"]["reservations"]["items"]["$ref"].split("/")[-1]
    assert set(esquema["components"]["schemas"][elemento_ref]["properties"]) == {
        "start_date",
        "end_date",
    }
