from typing import Any

import pytest
from conftest import autenticar
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from rentalab.compatibilidad import alias_json
from rentalab.configuracion import Configuracion
from rentalab.principal import crear_aplicacion


@pytest.fixture
def reserva_contenido_envio(
    cliente_http: TestClient, equipo_contenido_envio: dict[str, object]
) -> dict[str, object]:
    equipo = cliente_http.post("/api/equipment", json=equipo_contenido_envio)
    assert equipo.status_code == 201
    return {
        "equipment_id": equipo.json()["id"],
        "customer_name": "Cliente ficticio",
        "customer_email": "cliente@example.test",
        "start_date": "2026-11-10",
        "end_date": "2026-11-12",
    }


def crear_reserva(
    cliente_http: TestClient, contenido_envio: dict[str, object], **cambios: object
) -> dict[str, Any]:
    respuesta = cliente_http.post(
        "/api/reservations",
        json={**contenido_envio, **{alias_json(clave): valor for clave, valor in cambios.items()}},
    )
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()


def test_crear_normaliza_devuelve_y_recupera_a_confirmadas_reserva(
    cliente_http: TestClient, reserva_contenido_envio: dict[str, object]
) -> None:
    contenido_envio = {
        **reserva_contenido_envio,
        "customer_name": "  Cliente ficticio  ",
        "customer_email": "  cliente@example.test  ",
        "external_reference": "  ORDER-001  ",
    }
    respuesta = cliente_http.post("/api/reservations", json=contenido_envio)
    assert respuesta.status_code == 201
    reserva = respuesta.json()
    assert isinstance(reserva["id"], int)
    assert reserva == {
        **reserva_contenido_envio,
        "id": reserva["id"],
        "external_reference": "ORDER-001",
        "status": "confirmed",
        "customer_user_id": None,
        "origin": "admin",
    }
    assert respuesta.headers["location"] == f"/api/reservations/{reserva['id']}"
    assert cliente_http.get(respuesta.headers["location"]).json() == reserva
    assert cliente_http.get("/api/reservations").json() == [reserva]


def test_referencia_es_opcionales_y_multiples_nulo_referencias_son_permitidos(
    cliente_http: TestClient, reserva_contenido_envio: dict[str, object]
) -> None:
    primero = crear_reserva(cliente_http, reserva_contenido_envio)
    segundo = crear_reserva(
        cliente_http,
        reserva_contenido_envio,
        fecha_inicio="2026-11-12",
        fecha_fin="2026-11-13",
        referencia_externa=None,
    )
    assert primero["external_reference"] is None
    assert segundo["external_reference"] is None


@pytest.mark.parametrize(
    ("fecha_inicio", "fecha_fin"),
    [
        ("2026-11-09", "2026-11-11"),
        ("2026-11-11", "2026-11-13"),
        ("2026-11-10", "2026-11-12"),
        ("2026-11-09", "2026-11-13"),
        ("2026-11-10", "2026-11-11"),
        ("2026-11-11", "2026-11-12"),
    ],
)
def test_parcial_total_y_contenidos_solapamientos_son_conflictos(
    cliente_http: TestClient,
    reserva_contenido_envio: dict[str, object],
    fecha_inicio: str,
    fecha_fin: str,
) -> None:
    original = crear_reserva(cliente_http, reserva_contenido_envio)
    respuesta = cliente_http.post(
        "/api/reservations",
        json={**reserva_contenido_envio, "start_date": fecha_inicio, "end_date": fecha_fin},
    )
    assert respuesta.status_code == 409
    assert isinstance(respuesta.json()["detail"], str)
    assert cliente_http.get("/api/reservations").json() == [original]
    disponibilidad = cliente_http.get(
        f"/api/equipment/{reserva_contenido_envio['equipment_id']}/availability",
        params={"start_date": fecha_inicio, "end_date": fecha_fin},
    )
    assert disponibilidad.status_code == 200
    assert disponibilidad.json() == {
        "equipment_id": reserva_contenido_envio["equipment_id"],
        "start_date": fecha_inicio,
        "end_date": fecha_fin,
        "available": False,
        "reason": "reservation_overlap",
        "conflicting_reservation_ids": [original["id"]],
    }


@pytest.mark.parametrize(
    ("fecha_inicio", "fecha_fin"),
    [
        ("2026-11-08", "2026-11-10"),
        ("2026-11-12", "2026-11-14"),
        ("2026-11-01", "2026-11-03"),
        ("2026-11-20", "2026-11-21"),
    ],
)
def test_adyacentes_y_separados_intervalos_son_disponible_y_puede_ser_reservado(
    cliente_http: TestClient,
    reserva_contenido_envio: dict[str, object],
    fecha_inicio: str,
    fecha_fin: str,
) -> None:
    crear_reserva(cliente_http, reserva_contenido_envio)
    respuesta = cliente_http.get(
        f"/api/equipment/{reserva_contenido_envio['equipment_id']}/availability",
        params={"start_date": fecha_inicio, "end_date": fecha_fin},
    )
    assert respuesta.status_code == 200
    assert respuesta.json() == {
        "equipment_id": reserva_contenido_envio["equipment_id"],
        "start_date": fecha_inicio,
        "end_date": fecha_fin,
        "available": True,
        "reason": None,
        "conflicting_reservation_ids": [],
    }
    crear_reserva(
        cliente_http, reserva_contenido_envio, fecha_inicio=fecha_inicio, fecha_fin=fecha_fin
    )


def test_la_mismo_fechas_puede_ser_reservado_para_distinto_fisica_unidades(
    cliente_http: TestClient,
    reserva_contenido_envio: dict[str, object],
    equipo_contenido_envio: dict[str, object],
) -> None:
    primero = crear_reserva(cliente_http, reserva_contenido_envio)
    segundo_equipo = cliente_http.post(
        "/api/equipment", json={**equipo_contenido_envio, "code": "CAM-002"}
    ).json()
    segundo = crear_reserva(cliente_http, reserva_contenido_envio, id_equipo=segundo_equipo["id"])
    assert primero["equipment_id"] != segundo["equipment_id"]
    assert len(cliente_http.get("/api/reservations").json()) == 2


def test_cancelacion_preserva_historial_es_idempotente_y_desbloquea_la_intervalo(
    cliente_http: TestClient, reserva_contenido_envio: dict[str, object]
) -> None:
    original = crear_reserva(cliente_http, reserva_contenido_envio, referencia_externa="ORDER-1")
    url = f"/api/reservations/{original['id']}"
    canceladas = cliente_http.post(f"{url}/cancel")
    assert canceladas.status_code == 200
    assert canceladas.json() == {**original, "status": "cancelled"}
    assert cliente_http.post(f"{url}/cancel").json() == canceladas.json()
    assert cliente_http.get(url).json() == canceladas.json()
    disponibilidad = cliente_http.get(
        f"/api/equipment/{reserva_contenido_envio['equipment_id']}/availability",
        params={"start_date": "2026-11-10", "end_date": "2026-11-12"},
    )
    assert disponibilidad.json()["available"] is True
    assert disponibilidad.json()["conflicting_reservation_ids"] == []
    reemplazo = crear_reserva(cliente_http, reserva_contenido_envio)
    assert reemplazo["id"] != original["id"]
    assert len(cliente_http.get("/api/reservations").json()) == 2


def test_inactivo_equipo_es_no_disponible_y_no_puede_recibir_nuevo_reservas(
    cliente_http: TestClient, reserva_contenido_envio: dict[str, object]
) -> None:
    id_equipo = reserva_contenido_envio["equipment_id"]
    assert (
        cliente_http.patch(f"/api/equipment/{id_equipo}", json={"active": False}).status_code == 200
    )
    respuesta = cliente_http.get(
        f"/api/equipment/{id_equipo}/availability",
        params={"start_date": "2026-11-10", "end_date": "2026-11-12"},
    )
    assert respuesta.status_code == 200
    assert respuesta.json() == {
        "equipment_id": id_equipo,
        "start_date": "2026-11-10",
        "end_date": "2026-11-12",
        "available": False,
        "reason": "equipment_inactive",
        "conflicting_reservation_ids": [],
    }
    assert cliente_http.post("/api/reservations", json=reserva_contenido_envio).status_code == 409
    assert cliente_http.get("/api/reservations").json() == []


def test_desactivacion_hace_no_borrar_reservas_o_impedir_cancelacion(
    cliente_http: TestClient, reserva_contenido_envio: dict[str, object]
) -> None:
    original = crear_reserva(cliente_http, reserva_contenido_envio)
    cliente_http.patch(
        f"/api/equipment/{reserva_contenido_envio['equipment_id']}", json={"active": False}
    )
    assert cliente_http.get(f"/api/reservations/{original['id']}").json() == original
    assert (
        cliente_http.post(f"/api/reservations/{original['id']}/cancel").json()["status"]
        == "cancelled"
    )


def test_externa_referencia_es_recortado_unico_y_permanece_reservado_despues_cancelacion(
    cliente_http: TestClient, reserva_contenido_envio: dict[str, object]
) -> None:
    original = crear_reserva(cliente_http, reserva_contenido_envio, referencia_externa=" ORDER-1 ")
    cliente_http.post(f"/api/reservations/{original['id']}/cancel")
    respuesta = cliente_http.post(
        "/api/reservations", json={**reserva_contenido_envio, "external_reference": "ORDER-1"}
    )
    assert respuesta.status_code == 409
    assert len(cliente_http.get("/api/reservations").json()) == 1
    distinto_caso = crear_reserva(
        cliente_http, reserva_contenido_envio, referencia_externa="order-1"
    )
    assert distinto_caso["external_reference"] == "order-1"


def test_listar_filtros_y_ordenes_reservas_por_arranque_despues_id(
    cliente_http: TestClient,
    reserva_contenido_envio: dict[str, object],
    equipo_contenido_envio: dict[str, object],
) -> None:
    assert cliente_http.get("/api/reservations").json() == []
    tardio = crear_reserva(
        cliente_http, reserva_contenido_envio, fecha_inicio="2026-11-20", fecha_fin="2026-11-22"
    )
    segundo_equipo = cliente_http.post(
        "/api/equipment", json={**equipo_contenido_envio, "code": "MIC-002"}
    ).json()
    temprano = crear_reserva(cliente_http, reserva_contenido_envio)
    mismo_arranque = crear_reserva(
        cliente_http, reserva_contenido_envio, id_equipo=segundo_equipo["id"]
    )
    cliente_http.post(f"/api/reservations/{mismo_arranque['id']}/cancel")
    canceladas = {**mismo_arranque, "status": "cancelled"}
    assert cliente_http.get("/api/reservations").json() == [temprano, canceladas, tardio]
    assert cliente_http.get("/api/reservations", params={"status": "confirmed"}).json() == [
        temprano,
        tardio,
    ]
    assert cliente_http.get("/api/reservations", params={"status": "cancelled"}).json() == [
        canceladas
    ]
    assert cliente_http.get(
        "/api/reservations", params={"equipment_id": segundo_equipo["id"]}
    ).json() == [canceladas]
    assert (
        cliente_http.get(
            "/api/reservations",
            params={"equipment_id": reserva_contenido_envio["equipment_id"], "status": "cancelled"},
        ).json()
        == []
    )
    assert cliente_http.get(
        "/api/reservations", params={"start_date": "2026-11-11", "end_date": "2026-11-20"}
    ).json() == [temprano, canceladas]
    assert (
        cliente_http.get(
            "/api/reservations", params={"start_date": "2026-11-12", "end_date": "2026-11-20"}
        ).json()
        == []
    )


def test_disponibilidad_informa_todos_solapamientos_sin_exponer_cliente_datos(
    cliente_http: TestClient, reserva_contenido_envio: dict[str, object]
) -> None:
    primero = crear_reserva(cliente_http, reserva_contenido_envio)
    segundo = crear_reserva(
        cliente_http, reserva_contenido_envio, fecha_inicio="2026-11-12", fecha_fin="2026-11-14"
    )
    respuesta = cliente_http.get(
        f"/api/equipment/{reserva_contenido_envio['equipment_id']}/availability",
        params={"start_date": "2026-11-09", "end_date": "2026-11-15"},
    )
    assert respuesta.status_code == 200
    assert respuesta.json()["conflicting_reservation_ids"] == [primero["id"], segundo["id"]]
    assert "customer_name" not in respuesta.text
    assert "customer_email" not in respuesta.text


@pytest.mark.parametrize(
    ("metodo", "url"),
    [
        ("get", "/api/reservations/99999"),
        ("post", "/api/reservations/99999/cancel"),
        ("get", "/api/reservations?equipment_id=99999"),
        (
            "get",
            "/api/equipment/99999/availability?start_date=2026-11-10&end_date=2026-11-12",
        ),
    ],
)
def test_ausente_recursos_son_404(cliente_http: TestClient, metodo: str, url: str) -> None:
    respuesta = cliente_http.request(metodo, url)
    assert respuesta.status_code == 404
    assert isinstance(respuesta.json()["detail"], str)


def test_reservando_ausente_equipo_es_404(
    cliente_http: TestClient, reserva_contenido_envio: dict[str, object]
) -> None:
    respuesta = cliente_http.post(
        "/api/reservations", json={**reserva_contenido_envio, "equipment_id": 99999}
    )
    assert respuesta.status_code == 404
    assert cliente_http.get("/api/reservations").json() == []


@pytest.mark.parametrize(
    ("campo", "valor"),
    [
        ("equipment_id", 0),
        ("equipment_id", -1),
        ("equipment_id", True),
        ("equipment_id", "1"),
        ("equipment_id", None),
        ("equipment_id", 2**63),
        ("customer_name", ""),
        ("customer_name", "   "),
        ("customer_name", "X" * 121),
        ("customer_name", None),
        ("customer_name", 123),
        ("customer_name", "\x00Cliente"),
        ("customer_name", "Cliente\x00ficticio"),
        ("customer_email", ""),
        ("customer_email", "no-email"),
        ("customer_email", "no-at.example.test"),
        ("customer_email", "@example.test"),
        ("customer_email", "cliente@"),
        ("customer_email", "cli ente@example.test"),
        ("customer_email", "cliente@@example.test"),
        ("customer_email", "X" * 255),
        ("customer_email", None),
        ("start_date", "2026-11-12"),
        ("start_date", "2026-11-13"),
        ("start_date", "2026-02-30"),
        ("start_date", "2026-1-01"),
        ("start_date", "10/11/2026"),
        ("start_date", "2026-11-10T00:00:00"),
        ("start_date", " 2026-11-10 "),
        ("start_date", 1794268800),
        ("start_date", None),
        ("end_date", "2026-11-10"),
        ("end_date", "2026-11-09"),
        ("end_date", "2026-13-01"),
        ("end_date", "2026-11-12T00:00:00Z"),
        ("end_date", 1794441600),
        ("end_date", None),
        ("external_reference", ""),
        ("external_reference", "   "),
        ("external_reference", "X" * 121),
        ("external_reference", 42),
        ("external_reference", "\x00ORDER-1"),
        ("external_reference", "ORDER-1\x00ficticio"),
        ("status", "confirmed"),
        ("status", "cancelled"),
        ("unknown", "unexpected"),
    ],
)
def test_invalido_reservas_son_422_sin_escribiendo(
    cliente_http: TestClient, reserva_contenido_envio: dict[str, object], campo: str, valor: object
) -> None:
    respuesta = cliente_http.post(
        "/api/reservations", json={**reserva_contenido_envio, campo: valor}
    )
    assert respuesta.status_code == 422
    assert cliente_http.get("/api/reservations").json() == []


@pytest.mark.parametrize(
    "campo", ["equipment_id", "customer_name", "customer_email", "start_date", "end_date"]
)
def test_creacion_requiere_todos_obligatorios_campos(
    cliente_http: TestClient, reserva_contenido_envio: dict[str, object], campo: str
) -> None:
    del reserva_contenido_envio[campo]
    assert cliente_http.post("/api/reservations", json=reserva_contenido_envio).status_code == 422


@pytest.mark.parametrize(
    "parametros",
    [
        {},
        {"start_date": "2026-11-10"},
        {"end_date": "2026-11-12"},
        {"start_date": "2026-11-10", "end_date": "2026-11-10"},
        {"start_date": "2026-11-12", "end_date": "2026-11-10"},
        {"start_date": "2026-02-30", "end_date": "2026-11-12"},
        {"start_date": "2026-11-10T00:00:00", "end_date": "2026-11-12"},
        {"start_date": "2026-11-10", "end_date": "2026-11-12T00:00:00Z"},
        {"start_date": "1794268800", "end_date": "2026-11-12"},
    ],
)
def test_disponibilidad_requiere_a_valido_completo_iso_fecha_intervalo(
    cliente_http: TestClient, reserva_contenido_envio: dict[str, object], parametros: dict[str, str]
) -> None:
    respuesta = cliente_http.get(
        f"/api/equipment/{reserva_contenido_envio['equipment_id']}/availability", params=parametros
    )
    assert respuesta.status_code == 422


@pytest.mark.parametrize(
    "parametros",
    [
        {"equipment_id": "0"},
        {"equipment_id": "-1"},
        {"equipment_id": "invalid"},
        {"equipment_id": str(2**63)},
        {"status": "pending"},
        {"start_date": "2026-11-10"},
        {"end_date": "2026-11-12"},
        {"start_date": "2026-11-10", "end_date": "2026-11-10"},
        {"start_date": "2026-11-12", "end_date": "2026-11-10"},
        {"start_date": "2026-11-10T00:00:00", "end_date": "2026-11-12"},
    ],
)
def test_invalido_listar_filtros_son_422(
    cliente_http: TestClient, parametros: dict[str, str]
) -> None:
    assert cliente_http.get("/api/reservations", params=parametros).status_code == 422


@pytest.mark.parametrize(
    ("metodo", "ruta"),
    [
        ("get", f"/api/reservations/{2**63}"),
        ("post", f"/api/reservations/{2**63}/cancel"),
        ("get", f"/api/equipment/{2**63}"),
        ("get", f"/api/equipment/{2**63}/availability?start_date=2026-11-10&end_date=2026-11-12"),
    ],
)
def test_ids_fuera_sqlite_entero_intervalo_son_422(
    cliente_http: TestClient, metodo: str, ruta: str
) -> None:
    assert cliente_http.request(metodo, ruta).status_code == 422


def test_reservas_y_cancelacion_persiste_cuando_aplicacion_es_recreada(
    cliente_http: TestClient, reserva_contenido_envio: dict[str, object], ajustes: Configuracion
) -> None:
    original = crear_reserva(cliente_http, reserva_contenido_envio)
    canceladas = cliente_http.post(f"/api/reservations/{original['id']}/cancel").json()
    aplicacion = crear_aplicacion(ajustes)
    try:
        with TestClient(aplicacion) as recreada_cliente:
            autenticar(recreada_cliente)
            assert recreada_cliente.get("/api/reservations").json() == [canceladas]
            assert recreada_cliente.get(f"/api/reservations/{original['id']}").json() == canceladas
            crear_reserva(recreada_cliente, reserva_contenido_envio)
    finally:
        aplicacion.state.motor.dispose()


@pytest.mark.parametrize(
    "cambios",
    [
        {"external_reference": "ORDER-DB"},
        {"equipment_id": 99999, "external_reference": None},
        {"end_date": "2026-11-10", "external_reference": None},
        {"end_date": "2026-11-09", "external_reference": None},
        {"status": "pending", "external_reference": None},
    ],
)
def test_sqlite_exige_externa_referencia_fecha_estado_y_ajena_clave_restricciones(
    aplicacion: FastAPI,
    cliente_http: TestClient,
    reserva_contenido_envio: dict[str, object],
    cambios: dict[str, object],
) -> None:
    crear_reserva(cliente_http, reserva_contenido_envio, referencia_externa="ORDER-DB")
    parametros = {
        **reserva_contenido_envio,
        "status": "confirmed",
        "external_reference": None,
        **{alias_json(clave): valor for clave, valor in cambios.items()},
    }
    with pytest.raises(IntegrityError), aplicacion.state.motor.begin() as conexion:
        conexion.execute(
            text(
                "INSERT INTO reservations (equipment_id, customer_name, customer_email, "
                "start_date, end_date, status, external_reference) "
                "VALUES (:equipment_id, :customer_name, :customer_email, "
                ":start_date, :end_date, :status, :external_reference)"
            ),
            parametros,
        )
