from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_catalogo_publico import crear_equipo, informe_problema

from rentalab.configuracion import Configuracion
from rentalab.principal import crear_aplicacion

VENTANA = {"start_date": "2026-11-01", "end_date": "2026-12-01"}
CALENDARIO_CAMPOS = {
    "equipment_id",
    "start_date",
    "end_date",
    "occupied_ranges",
    "can_book",
    "unavailable_end_dates",
}


@pytest.fixture
def calendario_visitante(aplicacion: FastAPI) -> Iterator[TestClient]:
    with TestClient(aplicacion) as navegador:
        yield navegador


def reservar(administrador_http: TestClient, id_equipo: int, arranque: str, fin: str) -> dict:
    respuesta = administrador_http.post(
        "/api/reservations",
        json={
            "equipment_id": id_equipo,
            "start_date": arranque,
            "end_date": fin,
            "customer_name": "PRIVATE-CALENDAR-NAME",
            "customer_email": "private-calendar@example.test",
        },
    )
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()


def test_calendario_publica_fechas_confirmadas_recortadas_y_actualiza_cancelaciones(
    cliente_http: TestClient, calendario_visitante: TestClient
) -> None:
    equipo = crear_equipo(cliente_http)
    otro = crear_equipo(cliente_http, codigo="OTHER-UNIT", nombre="Otro modelo")
    reservar(cliente_http, equipo["id"], "2026-10-30", "2026-11-03")
    reservar(cliente_http, equipo["id"], "2026-11-03", "2026-11-06")
    ultimo = reservar(cliente_http, equipo["id"], "2026-11-10", "2026-12-03")
    reservar(cliente_http, otro["id"], "2026-11-01", "2026-12-01")
    url = f"/api/public/equipment/{equipo['id']}/calendar"
    for navegador in (cliente_http, calendario_visitante):
        respuesta = navegador.get(url, params=VENTANA)
        assert respuesta.status_code == 200, respuesta.text
        assert respuesta.json() == {
            "equipment_id": equipo["id"],
            **VENTANA,
            "can_book": True,
            "unavailable_end_dates": [],
            "occupied_ranges": [
                {"start_date": "2026-11-01", "end_date": "2026-11-06"},
                {"start_date": "2026-11-10", "end_date": "2026-12-01"},
            ],
        }
        assert set(respuesta.json()) == CALENDARIO_CAMPOS
        assert "PRIVATE-" not in respuesta.text
        assert "private-calendar@example.test" not in respuesta.text
        for periodo in respuesta.json()["occupied_ranges"]:
            assert set(periodo) == {"start_date", "end_date"}
    consecutivos = calendario_visitante.get(
        url, params={"start_date": "2026-11-06", "end_date": "2026-11-10"}
    )
    assert consecutivos.json()["occupied_ranges"] == []
    assert cliente_http.post(f"/api/reservations/{ultimo['id']}/cancel").status_code == 200
    renovado = calendario_visitante.get(url, params=VENTANA)
    assert renovado.json()["occupied_ranges"] == [
        {"start_date": "2026-11-01", "end_date": "2026-11-06"}
    ]


@pytest.mark.parametrize("bloqueante", [False, True])
@pytest.mark.parametrize("estado", ["open", "in_progress", "resolved"])
def test_calendario_explica_generico_reserva_bloqueo_sin_incidencia_datos(
    cliente_http: TestClient, calendario_visitante: TestClient, bloqueante: bool, estado: str
) -> None:
    equipo = crear_equipo(cliente_http)
    incidencia = informe_problema(cliente_http, equipo["id"], bloqueante)
    if estado != "open":
        cuerpo = {"status": estado}
        if estado == "resolved":
            cuerpo["resolution"] = "PRIVATE-RESOLUTION"
        assert (
            cliente_http.patch(f"/api/incidents/{incidencia['id']}/status", json=cuerpo).status_code
            == 200
        )
    respuesta = calendario_visitante.get(
        f"/api/public/equipment/{equipo['id']}/calendar", params=VENTANA
    )
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["can_book"] is (not bloqueante or estado == "resolved")
    assert respuesta.json()["occupied_ranges"] == []
    assert set(respuesta.json()) == CALENDARIO_CAMPOS
    assert "PRIVATE-" not in respuesta.text


@pytest.mark.parametrize(
    "fechas",
    [
        {},
        {"start_date": "2026-11-01"},
        {"end_date": "2026-12-01"},
        {"start_date": "2026-11-01", "end_date": "2026-11-01"},
        {"start_date": "2026-12-01", "end_date": "2026-11-01"},
        {"start_date": "2026-02-30", "end_date": "2026-12-01"},
        {"start_date": "2026-11-01T00:00:00", "end_date": "2026-12-01"},
        {"start_date": "2026-1-01", "end_date": "2026-12-01"},
        {"start_date": "2026-01-01", "end_date": "2027-01-03"},
        {**VENTANA, "customer_user_id": "1"},
        {**VENTANA, "booking_start": "2026-02-30"},
        {**VENTANA, "booking_start": "2026-11-01T00:00:00"},
        {**VENTANA, "booking_start": "2026-1-01"},
        {**VENTANA, "booking_start": "2025-11-29"},
    ],
)
def test_calendario_rechaza_invalido_parcial_ilimitado_o_privado_consultas(
    cliente_http: TestClient, calendario_visitante: TestClient, fechas: dict[str, str]
) -> None:
    equipo = crear_equipo(cliente_http)
    respuesta = calendario_visitante.get(
        f"/api/public/equipment/{equipo['id']}/calendar", params=fechas
    )
    assert respuesta.status_code == 422, respuesta.text


def test_calendario_acepta_en_maximo_366_dias_y_oculta_inactivo_unidades(
    cliente_http: TestClient, calendario_visitante: TestClient
) -> None:
    equipo = crear_equipo(cliente_http)
    url = f"/api/public/equipment/{equipo['id']}/calendar"
    maximo = {"start_date": "2026-01-01", "end_date": "2027-01-02"}
    assert calendario_visitante.get(url, params=maximo).status_code == 200
    assert (
        cliente_http.patch(f"/api/equipment/{equipo['id']}", json={"active": False}).status_code
        == 200
    )
    inactivo = calendario_visitante.get(url, params=VENTANA)
    ausente = calendario_visitante.get("/api/public/equipment/999999/calendar", params=VENTANA)
    assert inactivo.status_code == ausente.status_code == 404
    assert inactivo.json() == ausente.json()


def test_calendario_persiste_entre_aplicacion_y_conexion_grupo_recreacion(
    cliente_http: TestClient, ajustes: Configuracion
) -> None:
    equipo = crear_equipo(cliente_http)
    reservar(cliente_http, equipo["id"], "2026-11-10", "2026-11-12")
    canceladas = reservar(cliente_http, equipo["id"], "2026-11-20", "2026-11-22")
    assert cliente_http.post(f"/api/reservations/{canceladas['id']}/cancel").status_code == 200
    url = f"/api/public/equipment/{equipo['id']}/calendar"
    antes = cliente_http.get(url, params=VENTANA).json()
    recreada = crear_aplicacion(ajustes)
    try:
        with TestClient(recreada) as visitante:
            despues = visitante.get(url, params=VENTANA)
            assert despues.status_code == 200
            assert despues.json() == antes
            assert antes["occupied_ranges"] == [
                {"start_date": "2026-11-10", "end_date": "2026-11-12"}
            ]
    finally:
        recreada.state.motor.dispose()


def test_calendario_openapi_es_anonimo_y_tiene_solo_permitidos_campos(
    cliente_http: TestClient,
) -> None:
    esquema = cliente_http.get("/api/openapi.json").json()
    operacion = esquema["paths"]["/api/public/equipment/{equipment_id}/calendar"]["get"]
    assert operacion["security"] == []
    assert (
        set(esquema["components"]["schemas"]["PublicoCalendarioLectura"]["properties"])
        == CALENDARIO_CAMPOS
    )
    assert "503" in operacion["responses"]
