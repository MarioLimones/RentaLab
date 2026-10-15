"""
Los recuentos del catálogo describen alquileres confirmados vigentes o futuros entre unidades de
un modelo.
"""

from collections.abc import Iterator
from datetime import UTC, date, datetime
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event
from test_catalogo_publico import crear_equipo, informe_problema
from test_catalogo_publico import visitante as visitante
from test_publico_calendario import reservar

from rentalab.reloj import obtener_hoy_proveedor

HOY = date(2030, 11, 15)


@pytest.fixture
def negocio_hoy(aplicacion: FastAPI) -> Iterator[None]:
    aplicacion.dependency_overrides[obtener_hoy_proveedor] = lambda: lambda: HOY
    yield
    aplicacion.dependency_overrides.pop(obtener_hoy_proveedor, None)


@pytest.mark.usefixtures("negocio_hoy")
@pytest.mark.parametrize(
    ("arranque", "fin", "canceladas", "esperado"),
    [
        ("2030-11-01", "2030-11-05", False, 0),
        ("2030-11-13", "2030-11-15", False, 0),
        ("2030-11-14", "2030-11-16", False, 1),
        ("2030-11-15", "2030-11-17", False, 1),
        ("2030-11-18", "2030-11-20", False, 1),
        ("2030-11-14", "2030-11-16", True, 0),
        ("2030-11-18", "2030-11-20", True, 0),
    ],
)
def test_solo_confirmadas_alquileres_con_dias_restantes_son_contados(
    cliente_http: TestClient,
    visitante: TestClient,
    arranque: str,
    fin: str,
    canceladas: bool,
    esperado: int,
) -> None:
    equipo = crear_equipo(cliente_http)
    reserva = reservar(cliente_http, equipo["id"], arranque, fin)
    if canceladas:
        assert cliente_http.post(f"/api/reservations/{reserva['id']}/cancel").status_code == 200
    for navegador in (visitante, cliente_http):
        listado = navegador.get("/api/public/equipment")
        detalle = navegador.get(f"/api/public/equipment/{equipo['id']}")
        fechas = navegador.get(f"/api/public/equipment/{equipo['id']}/reservations")
        assert listado.status_code == detalle.status_code == fechas.status_code == 200
        assert listado.json()[0]["active_reservations_count"] == esperado
        assert detalle.json() == listado.json()[0]
        assert fechas.json() == {
            "equipment_id": equipo["id"],
            "reservations": [{"start_date": arranque, "end_date": fin}] if esperado else [],
        }
        assert "PRIVATE-" not in listado.text + detalle.text + fechas.text
        assert "private-calendar@example.test" not in listado.text + detalle.text + fechas.text


@pytest.mark.usefixtures("negocio_hoy")
def test_recuentos_suma_reservas_entre_normalizado_activo_modelo_unidades(
    cliente_http: TestClient, visitante: TestClient
) -> None:
    primero = crear_equipo(cliente_http, codigo="MODEL-01", nombre="Cámara Straße")
    alias = crear_equipo(
        cliente_http, codigo="MODEL-02", nombre="CA\u0301MARA STRASSE", categoria="CA\u0301MARAS"
    )
    inactivo = crear_equipo(cliente_http, codigo="MODEL-03", nombre="Cámara Straße")
    otro = crear_equipo(
        cliente_http, codigo="MODEL-04", nombre="Cámara Straße", categoria="Accesorios"
    )
    vacio = crear_equipo(cliente_http, codigo="MODEL-05", nombre="Modelo sin reservas")
    reservar(cliente_http, primero["id"], "2030-11-14", "2030-11-17")
    reservar(cliente_http, primero["id"], "2030-11-19", "2030-11-21")
    reservar(cliente_http, alias["id"], "2030-11-15", "2030-11-16")
    reservar(cliente_http, alias["id"], "2030-11-22", "2030-11-23")
    reservar(cliente_http, inactivo["id"], "2030-11-15", "2030-11-16")
    reservar(cliente_http, otro["id"], "2030-11-15", "2030-11-16")
    desactivado = cliente_http.patch(f"/api/equipment/{inactivo['id']}", json={"active": False})
    assert desactivado.status_code == 200
    # Bloquear la disponibilidad no cancela las reservas existentes ni oculta su recuento.
    informe_problema(cliente_http, primero["id"], bloqueante=True)

    respuesta = visitante.get("/api/public/equipment")
    assert respuesta.status_code == 200
    productos = {elemento["id"]: elemento for elemento in respuesta.json()}
    assert productos[primero["id"]]["active_reservations_count"] == 4
    assert productos[otro["id"]]["active_reservations_count"] == 1
    assert productos[vacio["id"]]["active_reservations_count"] == 0
    assert inactivo["id"] not in productos
    for unidad in (primero, alias):
        assert (
            visitante.get(f"/api/public/equipment/{unidad['id']}").json()
            == productos[primero["id"]]
        )
        assert visitante.get(f"/api/public/equipment/{unidad['id']}/reservations").json() == {
            "equipment_id": primero["id"],
            "reservations": [
                {"start_date": "2030-11-14", "end_date": "2030-11-17"},
                {"start_date": "2030-11-15", "end_date": "2030-11-16"},
                {"start_date": "2030-11-19", "end_date": "2030-11-21"},
                {"start_date": "2030-11-22", "end_date": "2030-11-23"},
            ],
        }
    filtrados = visitante.get(
        "/api/public/equipment", params={"q": "STRASSE", "category": "Cámaras"}
    )
    assert filtrados.status_code == 200
    assert filtrados.json() == [productos[primero["id"]]]


@pytest.mark.usefixtures("negocio_hoy")
def test_contar_actualiza_despues_reserva_y_cancelacion(
    cliente_http: TestClient, visitante: TestClient
) -> None:
    equipo = crear_equipo(cliente_http)
    url = f"/api/public/equipment/{equipo['id']}"
    assert visitante.get(url).json()["active_reservations_count"] == 0
    assert visitante.get(f"{url}/reservations").json()["reservations"] == []
    reserva = reservar(cliente_http, equipo["id"], "2030-11-18", "2030-11-20")
    assert visitante.get(url).json()["active_reservations_count"] == 1
    assert visitante.get(f"{url}/reservations").json()["reservations"] == [
        {"start_date": "2030-11-18", "end_date": "2030-11-20"}
    ]
    assert cliente_http.post(f"/api/reservations/{reserva['id']}/cancel").status_code == 200
    assert visitante.get(url).json()["active_reservations_count"] == 0
    assert visitante.get("/api/public/equipment").json()[0]["active_reservations_count"] == 0
    assert visitante.get(f"{url}/reservations").json()["reservations"] == []


@pytest.mark.usefixtures("negocio_hoy")
def test_catalogo_agrupa_recuentos_en_una_consulta_sin_leyendo_cliente_registros(
    aplicacion: FastAPI, cliente_http: TestClient, visitante: TestClient
) -> None:
    for indice in range(6):
        equipo = crear_equipo(cliente_http, codigo=f"MODEL-{indice}", nombre=f"Modelo {indice}")
        reservar(cliente_http, equipo["id"], "2030-11-18", "2030-11-20")
    consultas: list[str] = []

    def registro_consulta(_conexion: Any, _cursor: Any, sentencia: str, *_argumentos: Any) -> None:
        if "reservations" in sentencia:
            consultas.append(sentencia)

    event.listen(aplicacion.state.motor, "before_cursor_execute", registro_consulta)
    try:
        respuesta = visitante.get("/api/public/equipment")
    finally:
        event.remove(aplicacion.state.motor, "before_cursor_execute", registro_consulta)
    assert respuesta.status_code == 200
    assert [elemento["active_reservations_count"] for elemento in respuesta.json()] == [1] * 6
    assert len(consultas) == 1
    assert "count(" in consultas[0].lower()
    assert "customer_name" not in consultas[0]
    assert "customer_email" not in consultas[0]
    assert "external_reference" not in consultas[0]


def test_contar_usa_madrid_fecha_entre_utc_medianoche(
    monkeypatch: pytest.MonkeyPatch, cliente_http: TestClient, visitante: TestClient
) -> None:
    monkeypatch.setattr(
        "rentalab.reloj.utc_ahora", lambda: datetime(2030, 11, 14, 23, 30, tzinfo=UTC)
    )
    equipo = crear_equipo(cliente_http)
    reservar(cliente_http, equipo["id"], "2030-11-13", "2030-11-15")
    reservar(cliente_http, equipo["id"], "2030-11-15", "2030-11-17")
    listado = visitante.get("/api/public/equipment")
    detalle = visitante.get(f"/api/public/equipment/{equipo['id']}")
    assert listado.status_code == detalle.status_code == 200
    assert listado.json()[0]["active_reservations_count"] == 1
    assert detalle.json() == listado.json()[0]
    assert visitante.get(f"/api/public/equipment/{equipo['id']}/reservations").json() == {
        "equipment_id": equipo["id"],
        "reservations": [{"start_date": "2030-11-15", "end_date": "2030-11-17"}],
    }
