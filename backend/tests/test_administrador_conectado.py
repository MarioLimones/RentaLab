from collections.abc import Iterator
from contextlib import ExitStack
from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from rentalab.autenticacion.esquemas import SolicitudRegistro
from rentalab.reloj import obtener_hoy_proveedor

CONTRASENA = "isolated-phase-e-behaviour-password"
FECHAS = {"start_date": "2030-11-20", "end_date": "2030-11-22"}


def acceder_en(navegador: TestClient, correo: str) -> None:
    csrf = navegador.get("/api/auth/csrf").json()["csrf_token"]
    respuesta = navegador.post(
        "/api/auth/login",
        json={"username": correo, "password": CONTRASENA},
        headers={"X-CSRF-Token": csrf},
    )
    assert respuesta.status_code == 200, respuesta.text
    navegador.headers["X-CSRF-Token"] = navegador.get("/api/auth/csrf").json()["csrf_token"]


@pytest.fixture
def conectado_escenario(aplicacion: FastAPI, equipo_contenido_envio: dict) -> Iterator[tuple]:
    aplicacion.dependency_overrides[obtener_hoy_proveedor] = lambda: lambda: date(2030, 10, 15)
    identidades = [
        ("Cliente Uno", "one-phase-e@example.test", "customer"),
        ("Cliente Dos", "two-phase-e@example.test", "customer"),
        ("Administración", "admin-phase-e@example.test", "admin"),
    ]
    usuarios = [
        aplicacion.state.autenticacion_servicio.registrar(
            SolicitudRegistro(nombre=nombre, correo=correo, contrasena=CONTRASENA), rol=rol
        )
        for nombre, correo, rol in identidades
    ]
    with ExitStack() as pila:
        navegadores = [pila.enter_context(TestClient(aplicacion)) for _ in identidades]
        for navegador, (_, correo, _) in zip(navegadores, identidades, strict=True):
            acceder_en(navegador, correo)
        primero, segundo, administrador_http = navegadores
        equipo = administrador_http.post("/api/equipment", json=equipo_contenido_envio)
        assert equipo.status_code == 201
        yield primero, segundo, administrador_http, usuarios[0].id, equipo.json()["id"]
    aplicacion.dependency_overrides.pop(obtener_hoy_proveedor, None)


def test_cliente_y_administrador_comparten_cancelacion_comunicacion_y_disponibilidad(
    conectado_escenario: tuple,
) -> None:
    primero, segundo, administrador_http, propietario_id, id_equipo = conectado_escenario
    inicial = primero.post(
        "/api/me/reservations",
        json={"equipment_id": id_equipo, "start_date": "2030-11-10", "end_date": "2030-11-12"},
    )
    assert inicial.status_code == 201
    id_reserva = inicial.json()["id"]
    gestion = administrador_http.get(f"/api/reservations/{id_reserva}").json()
    assert gestion["customer_user_id"] == propietario_id
    assert gestion["origin"] == "portal"
    assert gestion["customer_email"] == "one-phase-e@example.test"
    assert administrador_http.post(f"/api/reservations/{id_reserva}/cancel").status_code == 200
    propia = primero.get(f"/api/me/reservations/{id_reserva}").json()
    assert propia == {**inicial.json(), "status": "cancelled"}
    assert segundo.get(f"/api/me/reservations/{id_reserva}").status_code == 404

    real = primero.post(
        "/api/me/reservations",
        json={"equipment_id": id_equipo, "start_date": "2030-11-14", "end_date": "2030-11-16"},
    )
    assert real.status_code == 201
    informe = primero.post(
        f"/api/me/reservations/{real.json()['id']}/incidents",
        json={"title": "Problema de prueba", "description": "El visor no responde."},
    )
    assert informe.status_code == 201
    id_incidencia = informe.json()["id"]
    pendiente = administrador_http.get(f"/api/incidents/{id_incidencia}").json()
    assert pendiente["author_user_id"] == propietario_id
    assert pendiente["reservation_id"] == real.json()["id"]
    assert pendiente["status"] == "open"
    assert pendiente["blocking"] is False
    disponibilidad_ruta = f"/api/public/equipment/{id_equipo}/availability"
    assert primero.get(disponibilidad_ruta, params=FECHAS).json()["available"] is True

    updated = administrador_http.patch(
        f"/api/incidents/{id_incidencia}",
        json={
            "priority": "high",
            "blocking": True,
            "public_response": "Revisaremos el visor contigo.",
            "internal_notes": "Nota privada centinela.",
        },
    )
    assert updated.status_code == 200
    cliente_informe = primero.get(f"/api/me/incidents/{id_incidencia}").json()
    assert cliente_informe["public_response"] == "Revisaremos el visor contigo."
    assert "internal_notes" not in cliente_informe
    assert "resolution" not in cliente_informe
    assert "Nota privada" not in str(cliente_informe)
    assert segundo.get(f"/api/me/incidents/{id_incidencia}").status_code == 404
    assert primero.get(disponibilidad_ruta, params=FECHAS).json()["available"] is False
    assert (
        segundo.post("/api/me/reservations", json={"equipment_id": id_equipo, **FECHAS}).status_code
        == 409
    )
    assert (
        administrador_http.post(
            "/api/reservations",
            json={
                "equipment_id": id_equipo,
                "customer_name": "Intento de gestión",
                "customer_email": "manual@example.test",
                **FECHAS,
            },
        ).status_code
        == 409
    )

    otra = administrador_http.post(
        "/api/incidents",
        json={"equipment_id": id_equipo, "title": "Segundo bloqueo", "blocking": True},
    )
    assert otra.status_code == 201
    assert (
        administrador_http.patch(
            f"/api/incidents/{id_incidencia}/status",
            json={"status": "resolved", "resolution": "Resolución interna del primer aviso."},
        ).status_code
        == 200
    )
    assert primero.get(disponibilidad_ruta, params=FECHAS).json()["available"] is False
    assert (
        segundo.post("/api/me/reservations", json={"equipment_id": id_equipo, **FECHAS}).status_code
        == 409
    )

    assert (
        administrador_http.patch(f"/api/equipment/{id_equipo}", json={"active": False}).status_code
        == 200
    )
    assert (
        administrador_http.patch(
            f"/api/incidents/{otra.json()['id']}/status",
            json={"status": "resolved", "resolution": "Segundo bloqueo resuelto."},
        ).status_code
        == 200
    )
    assert (
        administrador_http.get(f"/api/equipment/{id_equipo}/availability", params=FECHAS).json()[
            "reason"
        ]
        == "equipment_inactive"
    )
    assert primero.get(disponibilidad_ruta, params=FECHAS).status_code == 404
    assert (
        segundo.post("/api/me/reservations", json={"equipment_id": id_equipo, **FECHAS}).status_code
        == 409
    )
    assert (
        administrador_http.patch(f"/api/equipment/{id_equipo}", json={"active": True}).status_code
        == 200
    )
    assert primero.get(disponibilidad_ruta, params=FECHAS).json()["available"] is True
    confirmadas = segundo.post("/api/me/reservations", json={"equipment_id": id_equipo, **FECHAS})
    assert confirmadas.status_code == 201
    resuelta = primero.get(f"/api/me/incidents/{id_incidencia}").json()
    assert resuelta["status"] == "resolved"
    assert resuelta["public_response"] == "Revisaremos el visor contigo."
    assert "Resolución interna" not in str(resuelta)
    assert len(administrador_http.get("/api/reservations").json()) == 3


def test_csv_mantiene_su_propietario_desconocido_incluso_cuando_a_coincidente_correo_registra(
    aplicacion: FastAPI,
    conectado_escenario: tuple,
) -> None:
    _, _, administrador_http, _, _ = conectado_escenario
    contenido = (
        b"external_reference,customer_name,customer_email,equipment_code,starts_on,ends_on\n"
        b"E-CSV,Nombre del pedido,matching-phase-e@example.test,CAM-001,2030-12-10,2030-12-12\n"
    )
    importadas = administrador_http.post(
        "/api/imports", files={"file": ("orders.csv", contenido, "text/csv")}
    )
    assert importadas.status_code == 200
    reserva = importadas.json()["rows"][0]["reservation"]
    assert reserva["origin"] == "csv"
    assert reserva["customer_user_id"] is None
    with TestClient(aplicacion) as coincidente:
        csrf = coincidente.get("/api/auth/csrf").json()["csrf_token"]
        registrado = coincidente.post(
            "/api/auth/register",
            json={
                "name": "Cuenta creada después",
                "email": "matching-phase-e@example.test",
                "password": CONTRASENA,
            },
            headers={"X-CSRF-Token": csrf},
        )
        assert registrado.status_code == 201
        acceder_en(coincidente, "matching-phase-e@example.test")
        assert coincidente.get("/api/me/reservations").json() == []
        historico = f"/api/me/reservations/{reserva['id']}"
        ausente = coincidente.get("/api/me/reservations/999999")
        assert coincidente.get(historico).json() == ausente.json()
        assert coincidente.get(historico).status_code == 404
        denegado_cancelar = coincidente.post(f"{historico}/cancel")
        denegado_informe = coincidente.post(
            f"{historico}/incidents",
            json={"title": "Intento de apropiación", "description": "Solo coincide el correo."},
        )
        assert denegado_cancelar.status_code == denegado_informe.status_code == 404
        assert denegado_cancelar.json() == denegado_informe.json() == ausente.json()
        assert coincidente.get("/api/me/incidents").json() == []
    repetidas = administrador_http.post(
        "/api/imports", files={"file": ("orders.csv", contenido, "text/csv")}
    )
    assert repetidas.status_code == 200
    assert repetidas.json()["rows"][0]["status"] == "already_imported"
    assert repetidas.json()["rows"][0]["reservation"] == reserva
    assert administrador_http.get("/api/reservations", params={"origin": "csv"}).json() == [reserva]
