"""Recorridos HTTP completos sobre una base de datos SQLite migrada y desechable."""

from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_administrador_conectado import CONTRASENA, FECHAS, acceder_en
from test_administrador_conectado import conectado_escenario as conectado_escenario

from rentalab.reloj import obtener_hoy_proveedor


def test_visitante_registra_firma_en_y_explicitamente_confirma_a_publico_equipo(
    aplicacion: FastAPI, conectado_escenario: tuple
) -> None:
    _, otro_cliente, administrador_http, _, id_equipo = conectado_escenario
    cambiados = administrador_http.patch(
        f"/api/equipment/{id_equipo}",
        json={
            "description": "PRIVATE-INVENTORY-CANARY",
            "public_description": "Cámara para grabaciones en interiores y exteriores.",
            "technical_specs": {"Resolución": "4K", "Autonomía": "120 minutos"},
        },
    )
    assert cambiados.status_code == 200
    with TestClient(aplicacion) as visitante:
        catalogo = visitante.get("/api/public/equipment", params={"q": "CÁMARA"})
        assert catalogo.status_code == 200
        assert [elemento["id"] for elemento in catalogo.json()] == [id_equipo]
        equipo = visitante.get(f"/api/public/equipment/{id_equipo}")
        assert equipo.status_code == 200
        assert equipo.json()["technical_specs"] == {
            "Resolución": "4K",
            "Autonomía": "120 minutos",
        }
        assert "PRIVATE-INVENTORY-CANARY" not in equipo.text
        alternativa = visitante.get(equipo.json()["image_fallback_url"])
        assert alternativa.status_code == 200
        assert alternativa.headers["content-type"].startswith("image/svg+xml")
        disponibilidad = f"/api/public/equipment/{id_equipo}/availability"
        sin_fechas = visitante.get(disponibilidad).json()
        assert sin_fechas["status"] == "select_dates"
        assert sin_fechas["available"] is None
        assert visitante.get(disponibilidad, params=FECHAS).json()["available"] is True

        token = visitante.get("/api/auth/csrf").json()["csrf_token"]
        registrado = visitante.post(
            "/api/auth/register",
            json={
                "name": "Cliente del recorrido completo",
                "email": "  FULL-JOURNEY@Example.TEST  ",
                "password": CONTRASENA,
            },
            headers={"X-CSRF-Token": token},
        )
        assert registrado.status_code == 201
        assert registrado.json()["role"] == "customer"
        assert registrado.json()["email"] == "full-journey@example.test"
        # El registro y el acceso nunca crean una reserva en nombre del usuario.
        assert visitante.get("/api/auth/session").status_code == 401
        assert administrador_http.get("/api/reservations").json() == []
        acceder_en(visitante, "FULL-JOURNEY@EXAMPLE.TEST")
        sesion = visitante.get("/api/auth/session")
        assert sesion.status_code == 200
        assert sesion.json()["user"] == registrado.json()
        assert visitante.get("/api/me/reservations").json() == []

        creados = visitante.post("/api/me/reservations", json={"equipment_id": id_equipo, **FECHAS})
        assert creados.status_code == 201
        reserva = creados.json()
        privado_ruta = f"/api/me/reservations/{reserva['id']}"
        assert visitante.get(privado_ruta).json() == reserva
        assert visitante.get("/api/me/reservations").json() == [reserva]
        gestion = administrador_http.get(f"/api/reservations/{reserva['id']}").json()
        assert gestion["customer_user_id"] == registrado.json()["id"]
        assert gestion["customer_name"] == "Cliente del recorrido completo"
        assert gestion["customer_email"] == "full-journey@example.test"
        assert gestion["origin"] == "portal"
        assert otro_cliente.get(privado_ruta).status_code == 404
        assert visitante.get(disponibilidad, params=FECHAS).json()["available"] is False


@pytest.mark.parametrize(
    ("rol", "hoy", "esperado_estado"),
    [
        ("customer", date(2030, 11, 19), 200),
        ("customer", date(2030, 11, 20), 409),
        ("admin", date(2030, 11, 20), 200),
        ("admin", date(2030, 11, 23), 200),
    ],
)
def test_cancelacion_libera_solo_su_intervalo_bajo_cada_roles_politica(
    aplicacion: FastAPI,
    conectado_escenario: tuple,
    rol: str,
    hoy: date,
    esperado_estado: int,
) -> None:
    cliente, segundo, administrador_http, propietario_id, id_equipo = conectado_escenario
    creados = cliente.post("/api/me/reservations", json={"equipment_id": id_equipo, **FECHAS})
    assert creados.status_code == 201
    reserva = creados.json()
    adyacentes_fechas = {"start_date": FECHAS["end_date"], "end_date": "2030-11-23"}
    adyacentes = segundo.post(
        "/api/me/reservations", json={"equipment_id": id_equipo, **adyacentes_fechas}
    )
    assert adyacentes.status_code == 201
    aplicacion.dependency_overrides[obtener_hoy_proveedor] = lambda: lambda: hoy
    navegador = cliente if rol == "customer" else administrador_http
    espacio_nombres = "/api/me/reservations" if rol == "customer" else "/api/reservations"
    canceladas = navegador.post(f"{espacio_nombres}/{reserva['id']}/cancel")
    assert canceladas.status_code == esperado_estado
    estado = "cancelled" if esperado_estado == 200 else "confirmed"
    esperado = {**reserva, "status": estado}
    assert cliente.get(f"/api/me/reservations/{reserva['id']}").json() == esperado
    assert cliente.get("/api/me/reservations").json() == [esperado]
    gestion = administrador_http.get(f"/api/reservations/{reserva['id']}").json()
    assert gestion["customer_user_id"] == propietario_id
    assert gestion["origin"] == "portal"
    assert gestion["status"] == estado
    disponibilidad = f"/api/public/equipment/{id_equipo}/availability"
    assert cliente.get(disponibilidad, params=FECHAS).json()["available"] is (
        esperado_estado == 200
    )
    assert cliente.get(disponibilidad, params=adyacentes_fechas).json()["available"] is False
    assert (
        segundo.get(f"/api/me/reservations/{adyacentes.json()['id']}").json() == adyacentes.json()
    )
    if esperado_estado == 200:
        # Una cancelación correcta sigue siendo idempotente después del día de inicio original,
        # incluso si la canceló el administrador.
        aplicacion.dependency_overrides[obtener_hoy_proveedor] = lambda: lambda: date(2030, 11, 23)
        assert cliente.post(f"/api/me/reservations/{reserva['id']}/cancel").json() == esperado
        assert cliente.get(disponibilidad, params=FECHAS).json()["available"] is True
