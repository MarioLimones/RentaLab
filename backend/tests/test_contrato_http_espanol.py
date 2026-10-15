from datetime import date
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from rentalab.autenticacion.esquemas import LecturaUsuario, SolicitudRegistro
from rentalab.reloj import obtener_hoy_proveedor


def test_constructores_y_lectura_orm_conservan_nombres_internos_espanoles() -> None:
    registro = SolicitudRegistro(
        nombre="Persona de prueba",
        correo="contrato@example.test",
        contrasena="valor-sintetico-de-prueba",
    )
    assert registro.nombre == "Persona de prueba"
    usuario = LecturaUsuario.model_validate(
        SimpleNamespace(
            id=7, nombre=registro.nombre, correo=registro.correo, rol="customer", activo=True
        )
    )
    assert usuario.model_dump(by_alias=True) == {
        "id": 7,
        "name": "Persona de prueba",
        "email": "contrato@example.test",
        "role": "customer",
        "active": True,
    }


@pytest.mark.parametrize(
    "contenido",
    [
        {
            "nombre": "Persona de prueba",
            "correo": "contrato@example.test",
            "contrasena": "valor-sintetico-de-prueba",
        },
        {
            "name": "Persona de prueba",
            "email": "contrato@example.test",
            "password": "valor-sintetico-de-prueba",
            "nombre": "Campo adicional",
        },
    ],
)
def test_registro_http_rechaza_nombres_internos_y_campos_adicionales(
    aplicacion: FastAPI, contenido: dict[str, str]
) -> None:
    with TestClient(aplicacion) as anonimo:
        token = anonimo.get("/api/auth/csrf").json()["csrf_token"]
        respuesta = anonimo.post(
            "/api/auth/register", json=contenido, headers={"X-CSRF-Token": token}
        )
        assert respuesta.status_code == 422
        assert any(error["type"] == "extra_forbidden" for error in respuesta.json()["detail"])
        assert "valor-sintetico-de-prueba" not in respuesta.text
        assert anonimo.get("/api/auth/session").status_code == 401


def test_registro_http_conserva_payload_y_respuesta_publicos(aplicacion: FastAPI) -> None:
    with TestClient(aplicacion) as anonimo:
        token = anonimo.get("/api/auth/csrf").json()["csrf_token"]
        respuesta = anonimo.post(
            "/api/auth/register",
            json={
                "name": "Persona de prueba",
                "email": "contrato@example.test",
                "password": "valor-sintetico-de-prueba",
            },
            headers={"X-CSRF-Token": token},
        )
        assert respuesta.status_code == 201
        assert set(respuesta.json()) == {"id", "name", "email", "role", "active"}
        assert respuesta.json()["role"] == "customer"
        assert anonimo.get("/api/auth/session").status_code == 401


def test_acceso_http_rechaza_alias_internos_sin_reflejar_contrasena(
    aplicacion: FastAPI,
) -> None:
    with TestClient(aplicacion) as anonimo:
        token = anonimo.get("/api/auth/csrf").json()["csrf_token"]
        respuesta = anonimo.post(
            "/api/auth/login",
            json={"nombre_usuario": "persona@example.test", "contrasena": "dato-de-prueba"},
            headers={"X-CSRF-Token": token},
        )
        assert respuesta.status_code == 422
        assert "dato-de-prueba" not in respuesta.text


def test_edicion_http_rechaza_nombre_interno_y_conserva_alias_publico(
    cliente_http: TestClient, equipo_contenido_envio: dict[str, object]
) -> None:
    creado = cliente_http.post("/api/equipment", json=equipo_contenido_envio)
    assert creado.status_code == 201
    ruta = f"/api/equipment/{creado.json()['id']}"
    rechazado = cliente_http.patch(ruta, json={"nombre": "Cambio rechazado"})
    assert rechazado.status_code == 422
    assert cliente_http.get(ruta).json()["name"] == equipo_contenido_envio["name"]
    guardado = cliente_http.patch(ruta, json={"name": "Cambio público permitido"})
    assert guardado.status_code == 200
    assert guardado.json()["name"] == "Cambio público permitido"


def test_reserva_http_rechaza_nombres_internos_sin_crear_otra_reserva(
    cliente_http: TestClient, equipo_contenido_envio: dict[str, object]
) -> None:
    creado = cliente_http.post("/api/equipment", json=equipo_contenido_envio)
    assert creado.status_code == 201
    id_equipo = creado.json()["id"]
    rechazado = cliente_http.post(
        "/api/reservations",
        json={
            "id_equipo": id_equipo,
            "nombre_cliente": "Persona de prueba",
            "correo_cliente": "contrato@example.test",
            "fecha_inicio": "2030-01-10",
            "fecha_fin": "2030-01-12",
        },
    )
    assert rechazado.status_code == 422
    assert cliente_http.get("/api/reservations").json() == []
    guardado = cliente_http.post(
        "/api/reservations",
        json={
            "equipment_id": id_equipo,
            "customer_name": "Persona de prueba",
            "customer_email": "contrato@example.test",
            "start_date": "2030-01-10",
            "end_date": "2030-01-12",
        },
    )
    assert guardado.status_code == 201
    assert guardado.json()["status"] == "confirmed"
    assert guardado.json()["equipment_id"] == id_equipo
    assert len(cliente_http.get("/api/reservations").json()) == 1


@pytest.mark.parametrize(
    "ruta",
    [
        "/api/public/equipment?categoria=Cámaras",
        "/api/reservations?estado=confirmed",
        "/api/incidents?prioridad=high",
    ],
)
def test_consultas_http_rechazan_filtros_internos(cliente_http: TestClient, ruta: str) -> None:
    respuesta = cliente_http.get(ruta)
    assert respuesta.status_code == 422
    assert any(error["type"] == "extra_forbidden" for error in respuesta.json()["detail"])


def test_reserva_propia_acepta_solo_campos_publicos(
    aplicacion: FastAPI,
    cliente_http: TestClient,
    equipo_contenido_envio: dict[str, object],
) -> None:
    aplicacion.dependency_overrides[obtener_hoy_proveedor] = lambda: lambda: date(2030, 1, 1)
    creado = cliente_http.post("/api/equipment", json=equipo_contenido_envio)
    assert creado.status_code == 201
    with TestClient(aplicacion) as cliente:
        token = cliente.get("/api/auth/csrf").json()["csrf_token"]
        cabeceras = {"X-CSRF-Token": token}
        assert (
            cliente.post(
                "/api/auth/register",
                json={
                    "name": "Cliente de prueba",
                    "email": "cliente-contrato@example.test",
                    "password": "valor-sintetico-de-prueba",
                },
                headers=cabeceras,
            ).status_code
            == 201
        )
        assert (
            cliente.post(
                "/api/auth/login",
                json={
                    "username": "cliente-contrato@example.test",
                    "password": "valor-sintetico-de-prueba",
                },
                headers=cabeceras,
            ).status_code
            == 200
        )
        cabeceras = {"X-CSRF-Token": cliente.get("/api/auth/csrf").json()["csrf_token"]}
        rechazado = cliente.post(
            "/api/me/reservations",
            json={
                "id_equipo": creado.json()["id"],
                "fecha_inicio": "2030-01-10",
                "fecha_fin": "2030-01-12",
            },
            headers=cabeceras,
        )
        assert rechazado.status_code == 422
        assert cliente.get("/api/me/reservations").json() == []
        guardado = cliente.post(
            "/api/me/reservations",
            json={
                "equipment_id": creado.json()["id"],
                "start_date": "2030-01-10",
                "end_date": "2030-01-12",
            },
            headers=cabeceras,
        )
        assert guardado.status_code == 201
        assert set(guardado.json()) == {"id", "equipment_id", "start_date", "end_date", "status"}
        assert guardado.json()["status"] == "confirmed"
