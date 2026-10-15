"""
Los modelos públicos comparten existencias y las reservas conservan unidades físicas
independientes.
"""

from datetime import date, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from test_catalogo_publico import (
    PUBLICO_CAMPOS,
    crear_equipo,
    informe_problema,
    obtener_disponibilidad,
)
from test_catalogo_publico import visitante as visitante
from test_publico_calendario import CALENDARIO_CAMPOS, reservar

from rentalab.compatibilidad import alias_json

FECHAS = {"start_date": "2026-11-15", "end_date": "2026-11-20"}
VENTANA = {"start_date": "2026-11-01", "end_date": "2026-12-01"}


@pytest.fixture
def gemelos(cliente_http: TestClient) -> tuple[dict[str, Any], dict[str, Any]]:
    primero = crear_equipo(
        cliente_http,
        codigo="CAM-AURORA-01",
        nombre="Cámara Aurora S4",
        descripcion_publica="La ficha del modelo",
        caracteristicas_tecnicas={"Resolución": "4K"},
    )
    segundo = crear_equipo(
        cliente_http,
        codigo="CAM-AURORA-02",
        nombre="Cámara Aurora S4",
        descripcion_publica="Otra descripción de la unidad física",
    )
    return primero, segundo


def calendario(navegador: TestClient, id_equipo: int, **fechas: str) -> dict[str, Any]:
    respuesta = navegador.get(
        f"/api/public/equipment/{id_equipo}/calendar",
        params={alias_json(clave): valor for clave, valor in (fechas or VENTANA).items()},
    )
    assert respuesta.status_code == 200, respuesta.text
    assert set(respuesta.json()) == CALENDARIO_CAMPOS
    return respuesta.json()


def test_catalogo_publica_una_modelo_sin_existencias_recuentos_y_mantiene_alias(
    cliente_http: TestClient, visitante: TestClient, gemelos: tuple[dict[str, Any], dict[str, Any]]
) -> None:
    primero, segundo = gemelos
    respuesta = visitante.get("/api/public/equipment")
    assert respuesta.status_code == 200
    assert len(respuesta.json()) == 1
    producto = respuesta.json()[0]
    assert set(producto) == PUBLICO_CAMPOS
    assert producto["id"] == primero["id"]
    assert producto["name"] == "Cámara Aurora S4"
    assert producto["public_description"] == "La ficha del modelo"
    assert producto["technical_specs"] == {"Resolución": "4K"}
    for unidad in gemelos:
        detalle = visitante.get(f"/api/public/equipment/{unidad['id']}")
        assert detalle.status_code == 200
        assert detalle.json() == producto
    inventario = cliente_http.get("/api/equipment").json()
    assert {elemento["id"] for elemento in inventario} == {primero["id"], segundo["id"]}
    assert "CAM-AURORA-" not in respuesta.text


def test_producto_identidad_normaliza_unicode_caso_y_mantiene_otro_categorias_separados(
    cliente_http: TestClient, visitante: TestClient
) -> None:
    primero = crear_equipo(
        cliente_http, codigo="UNICODE-01", nombre="Cámara Straße", categoria="Cámaras"
    )
    alias = crear_equipo(
        cliente_http, codigo="UNICODE-02", nombre="CA\u0301MARA STRASSE", categoria="CA\u0301MARAS"
    )
    otro_categoria = crear_equipo(
        cliente_http, codigo="UNICODE-03", nombre="Cámara Straße", categoria="Accesorios"
    )
    otro_modelo = crear_equipo(cliente_http, codigo="UNICODE-04", nombre="Cámara Strasse Plus")
    crear_equipo(cliente_http, codigo="UNICODE-05", nombre="Cámara Straße", activo=False)
    listado = visitante.get("/api/public/equipment").json()
    assert {elemento["id"] for elemento in listado} == {
        primero["id"],
        otro_categoria["id"],
        otro_modelo["id"],
    }
    assert visitante.get(f"/api/public/equipment/{alias['id']}").json()["id"] == primero["id"]


def test_activo_representante_mueve_a_restantes_unidad_cuando_primero_es_desactivado(
    cliente_http: TestClient, visitante: TestClient, gemelos: tuple[dict[str, Any], dict[str, Any]]
) -> None:
    primero, segundo = gemelos
    assert (
        cliente_http.patch(f"/api/equipment/{primero['id']}", json={"active": False}).status_code
        == 200
    )
    listado = visitante.get("/api/public/equipment").json()
    assert [elemento["id"] for elemento in listado] == [segundo["id"]]
    assert visitante.get(f"/api/public/equipment/{primero['id']}").status_code == 404
    assert visitante.get(f"/api/public/equipment/{segundo['id']}").json() == listado[0]


def test_disponibilidad_y_calendario_reflejan_existencias_y_cancelaciones(
    cliente_http: TestClient, visitante: TestClient, gemelos: tuple[dict[str, Any], dict[str, Any]]
) -> None:
    primero, segundo = gemelos
    reservar(cliente_http, primero["id"], FECHAS["start_date"], FECHAS["end_date"])
    for unidad in gemelos:
        assert obtener_disponibilidad(visitante, unidad["id"], **FECHAS)["available"] is True
        assert calendario(visitante, unidad["id"])["occupied_ranges"] == []
    assert (
        cliente_http.get(f"/api/equipment/{primero['id']}/availability", params=FECHAS).json()[
            "available"
        ]
        is False
    )
    assert (
        cliente_http.get(f"/api/equipment/{segundo['id']}/availability", params=FECHAS).json()[
            "available"
        ]
        is True
    )

    ultimo = reservar(cliente_http, segundo["id"], FECHAS["start_date"], FECHAS["end_date"])
    for unidad in gemelos:
        assert obtener_disponibilidad(visitante, unidad["id"], **FECHAS)["available"] is False
        resultado = calendario(
            visitante, unidad["id"], **VENTANA, inicio_reserva=FECHAS["start_date"]
        )
        assert resultado["can_book"] is True
        assert resultado["occupied_ranges"] == [FECHAS]
        assert "2026-11-16" in resultado["unavailable_end_dates"]

    assert cliente_http.post(f"/api/reservations/{ultimo['id']}/cancel").status_code == 200
    assert obtener_disponibilidad(visitante, primero["id"], **FECHAS)["available"] is True
    renovado = calendario(visitante, primero["id"], **VENTANA, inicio_reserva=FECHAS["start_date"])
    assert renovado["occupied_ranges"] == []
    assert renovado["unavailable_end_dates"] == []


@pytest.mark.parametrize(
    ("primero_periodo", "segundo_periodo", "ventana", "inicio_reserva", "ultimo_valido_devolver"),
    [
        (
            ("2026-11-15", "2026-11-18"),
            ("2026-11-18", "2026-11-20"),
            VENTANA,
            "2026-11-15",
            "2026-11-18",
        ),
        (
            ("2026-10-29", "2026-11-02"),
            ("2026-11-02", "2026-11-05"),
            {"start_date": "2026-11-01", "end_date": "2026-11-08"},
            "2026-10-29",
            "2026-11-02",
        ),
        (
            ("2026-10-15", "2026-10-18"),
            ("2026-10-18", "2026-10-20"),
            VENTANA,
            "2026-10-15",
            "2026-10-18",
        ),
    ],
)
def test_libre_dias_hacer_no_ofrecer_a_devolver_requiriendo_a_cambiar_de_fisica_unidad(
    cliente_http: TestClient,
    visitante: TestClient,
    gemelos: tuple[dict[str, Any], dict[str, Any]],
    primero_periodo: tuple[str, str],
    segundo_periodo: tuple[str, str],
    ventana: dict[str, str],
    inicio_reserva: str,
    ultimo_valido_devolver: str,
) -> None:
    primero, segundo = gemelos
    reservar(cliente_http, primero["id"], *primero_periodo)
    reservar(cliente_http, segundo["id"], *segundo_periodo)
    resultado = calendario(visitante, primero["id"], **ventana, inicio_reserva=inicio_reserva)
    assert resultado["occupied_ranges"] == []
    assert resultado["can_book"] is True
    esperado = []
    dia = date.fromisoformat(ventana["start_date"])
    while dia < date.fromisoformat(ventana["end_date"]):
        if dia.isoformat() > ultimo_valido_devolver:
            esperado.append(dia.isoformat())
        dia += timedelta(days=1)
    assert resultado["unavailable_end_dates"] == esperado
    assert (
        obtener_disponibilidad(
            visitante, primero["id"], fecha_inicio=inicio_reserva, fecha_fin=ultimo_valido_devolver
        )["available"]
        is True
    )
    assert (
        obtener_disponibilidad(
            visitante, primero["id"], fecha_inicio=inicio_reserva, fecha_fin=segundo_periodo[1]
        )["available"]
        is False
    )


def test_calendario_intersecta_ocupacion_de_unidades_y_preserva_devolver_dia_limite(
    cliente_http: TestClient, visitante: TestClient, gemelos: tuple[dict[str, Any], dict[str, Any]]
) -> None:
    primero, segundo = gemelos
    reservar(cliente_http, primero["id"], "2026-11-10", "2026-11-15")
    reservar(cliente_http, segundo["id"], "2026-11-12", "2026-11-18")
    resultado = calendario(visitante, primero["id"], **VENTANA, inicio_reserva="2026-11-09")
    assert resultado["occupied_ranges"] == [{"start_date": "2026-11-12", "end_date": "2026-11-15"}]
    assert "2026-11-12" not in resultado["unavailable_end_dates"]
    assert "2026-11-13" in resultado["unavailable_end_dates"]
    assert (
        obtener_disponibilidad(
            visitante, primero["id"], fecha_inicio="2026-11-09", fecha_fin="2026-11-12"
        )["available"]
        is True
    )


@pytest.mark.parametrize("otro_estado", ["blocking_incident", "inactive"])
def test_unidades_bloqueadas_o_inactivas_no_aportan_disponibilidad(
    cliente_http: TestClient,
    visitante: TestClient,
    gemelos: tuple[dict[str, Any], dict[str, Any]],
    otro_estado: str,
) -> None:
    primero, segundo = gemelos
    if otro_estado == "blocking_incident":
        informe_problema(cliente_http, segundo["id"], bloqueante=True)
    else:
        assert (
            cliente_http.patch(
                f"/api/equipment/{segundo['id']}", json={"active": False}
            ).status_code
            == 200
        )
    assert obtener_disponibilidad(visitante, primero["id"], **FECHAS)["available"] is True
    reservar(cliente_http, primero["id"], FECHAS["start_date"], FECHAS["end_date"])
    assert obtener_disponibilidad(visitante, primero["id"], **FECHAS)["available"] is False
    assert calendario(visitante, primero["id"])["occupied_ranges"] == [FECHAS]
    informe_problema(cliente_http, primero["id"], bloqueante=True)
    resultado = calendario(visitante, primero["id"])
    assert resultado["can_book"] is False
    assert resultado["occupied_ranges"] == []


def test_bloqueado_representante_hace_no_ocultar_libre_unidad_o_divulgar_incidencia(
    cliente_http: TestClient, visitante: TestClient, gemelos: tuple[dict[str, Any], dict[str, Any]]
) -> None:
    primero, _segundo = gemelos
    informe_problema(cliente_http, primero["id"], bloqueante=True)
    assert obtener_disponibilidad(visitante, primero["id"], **FECHAS)["available"] is True
    resultado = calendario(visitante, primero["id"], **VENTANA, inicio_reserva=FECHAS["start_date"])
    assert resultado["can_book"] is True
    assert resultado["occupied_ranges"] == resultado["unavailable_end_dates"] == []
    assert "PRIVATE-" not in str(resultado)
