"""Pruebas de regresión de seguridad HTTP del espacio de clientes.

Estas solicitudes acceden directamente a HTTP y usan dos cookies independientes de cliente.
Todas las cuentas, credenciales y registros pertenecen a la base de datos de prueba desechable."""

from collections.abc import Iterator
from contextlib import ExitStack
from dataclasses import dataclass
from datetime import date

import pytest
from conftest import PRUEBA_CONTRASENA, PRUEBA_CONTRASENA_HASH
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from rentalab.autenticacion.modelos import Usuario
from rentalab.incidencias.modelos import Incidencia
from rentalab.reservas.modelos import Reserva

RESERVA_CAMPOS = {"id", "equipment_id", "start_date", "end_date", "status"}
INCIDENCIA_CAMPOS = {"id", "reservation_id", "title", "description", "status", "public_response"}


def acceder_en(navegador: TestClient, correo: str) -> None:
    csrf = navegador.get("/api/auth/csrf")
    assert csrf.status_code == 200
    respuesta = navegador.post(
        "/api/auth/login",
        json={"username": correo, "password": PRUEBA_CONTRASENA},
        headers={"X-CSRF-Token": csrf.json()["csrf_token"]},
    )
    assert respuesta.status_code == 200, respuesta.text
    navegador.headers["X-CSRF-Token"] = navegador.get("/api/auth/csrf").json()["csrf_token"]


@dataclass
class Clientes:
    alicia: TestClient
    bruno: TestClient
    administrador_http: TestClient
    alicia_id: int
    bruno_id: int
    administrador_id: int
    id_equipo: int

    def reservar(instancia, navegador: TestClient, arranque: str = "2026-11-10") -> dict:
        respuesta = navegador.post(
            "/api/me/reservations",
            json={
                "equipment_id": instancia.id_equipo,
                "start_date": arranque,
                "end_date": "2026-11-12",
            },
        )
        assert respuesta.status_code == 201, respuesta.text
        return respuesta.json()

    def informe(instancia, navegador: TestClient, id_reserva: int) -> dict:
        respuesta = navegador.post(
            f"/api/me/reservations/{id_reserva}/incidents",
            json={"title": "Aviso propio", "description": "Descripción aportada por el cliente"},
        )
        assert respuesta.status_code == 201, respuesta.text
        return respuesta.json()


@pytest.fixture
def clientes(aplicacion: FastAPI) -> Iterator[Clientes]:
    from rentalab.reloj import obtener_hoy_proveedor

    aplicacion.dependency_overrides[obtener_hoy_proveedor] = lambda: lambda: date(2026, 11, 1)
    with aplicacion.state.fabrica_sesiones() as base_datos_sesion:
        registros = [
            Usuario(
                nombre=nombre,
                correo=correo,
                hash_contrasena=PRUEBA_CONTRASENA_HASH,
                rol=rol,
                activo=True,
            )
            for nombre, correo, rol in [
                ("Alice privada", "alice@example.test", "customer"),
                ("Bob privado", "bob@example.test", "customer"),
                ("Administradora", "admin@example.test", "admin"),
            ]
        ]
        base_datos_sesion.add_all(registros)
        base_datos_sesion.commit()
        ids = [registro.id for registro in registros]
    with ExitStack() as pila:
        alicia, bruno, administrador_http = [
            pila.enter_context(TestClient(aplicacion)) for _ in range(3)
        ]
        for navegador, correo in [
            (alicia, "alice@example.test"),
            (bruno, "bob@example.test"),
            (administrador_http, "admin@example.test"),
        ]:
            acceder_en(navegador, correo)
        equipo = administrador_http.post(
            "/api/equipment",
            json={
                "code": "PRIVATE-CODE-CANARY",
                "name": "Cámara de pruebas",
                "category": "Cámaras",
                "description": "INTERNAL-EQUIPMENT-CANARY",
            },
        )
        assert equipo.status_code == 201, equipo.text
        yield Clientes(alicia, bruno, administrador_http, *ids, equipo.json()["id"])
    aplicacion.dependency_overrides.clear()


@pytest.mark.parametrize(
    ("metodo", "ruta"),
    [
        ("GET", "/api/me/reservations"),
        ("POST", "/api/me/reservations"),
        ("GET", "/api/me/reservations/1"),
        ("POST", "/api/me/reservations/1/cancel"),
        ("POST", "/api/me/reservations/1/incidents"),
        ("GET", "/api/me/incidents"),
        ("GET", "/api/me/incidents/1"),
    ],
)
def test_cliente_espacio_nombres_requiere_a_sesion_antes_validando_cuerpo(
    aplicacion: FastAPI, metodo: str, ruta: str
) -> None:
    with TestClient(aplicacion) as anonimo:
        respuesta = anonimo.request(metodo, ruta, content=b"invalid-json")
        assert respuesta.status_code == 401
        assert set(respuesta.json()) == {"detail"}
        assert respuesta.headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize(
    ("metodo", "ruta"),
    [
        ("GET", "/api/me/reservations"),
        ("POST", "/api/me/reservations"),
        ("GET", "/api/me/reservations/1"),
        ("POST", "/api/me/reservations/1/cancel"),
        ("POST", "/api/me/reservations/1/incidents"),
        ("GET", "/api/me/incidents"),
        ("GET", "/api/me/incidents/1"),
    ],
)
def test_persistidos_administrador_usa_gestion_rutas(
    clientes: Clientes, metodo: str, ruta: str
) -> None:
    respuesta = clientes.administrador_http.request(metodo, ruta, json={})
    assert respuesta.status_code == 403


def test_reserva_lista_y_directa_ids_son_aislado(aplicacion: FastAPI, clientes: Clientes) -> None:
    reserva = clientes.reservar(clientes.alicia)
    assert set(reserva) == RESERVA_CAMPOS
    assert clientes.alicia.get("/api/me/reservations").json() == [reserva]
    assert clientes.bruno.get("/api/me/reservations").json() == []
    assert clientes.alicia.get(f"/api/me/reservations/{reserva['id']}").json() == reserva
    for suffix in ["", "/cancel", "/incidents"]:
        metodo = "GET" if not suffix else "POST"
        cuerpo = (
            {"title": "Ataque", "description": "No es su reserva"}
            if suffix == "/incidents"
            else None
        )
        ruta = f"/api/me/reservations/{reserva['id']}{suffix}"
        respuesta = clientes.bruno.request(metodo, ruta, json=cuerpo)
        inexistente = clientes.bruno.request(
            metodo, f"/api/me/reservations/999999{suffix}", json=cuerpo
        )
        assert respuesta.status_code == inexistente.status_code == 404
        assert respuesta.json() == inexistente.json()
        assert "Alice" not in respuesta.text
    with aplicacion.state.fabrica_sesiones() as base_datos_sesion:
        registro = base_datos_sesion.get(Reserva, reserva["id"])
        assert registro.estado == "confirmed"
        assert registro.id_usuario_cliente == clientes.alicia_id
        assert registro.nombre_cliente == "Alice privada"
        assert registro.correo_cliente == "alice@example.test"
        assert registro.referencia_externa is None
        assert base_datos_sesion.scalar(select(Incidencia.id)) is None


@pytest.mark.parametrize(
    ("clave", "valor"),
    [
        ("id", 999),
        ("customer_id", 2),
        ("customer_user_id", 2),
        ("user_id", 2),
        ("customer_name", "Identidad falsificada"),
        ("customer_email", "bob@example.test"),
        ("status", "cancelled"),
        ("origin", "csv"),
        ("source", "admin"),
        ("external_reference", "PRIVATE-REFERENCE-CANARY"),
        ("role", "admin"),
    ],
)
def test_cliente_reserva_creacion_rechaza_identidad_y_administrativa_campos(
    aplicacion: FastAPI, clientes: Clientes, clave: str, valor: object
) -> None:
    respuesta = clientes.alicia.post(
        "/api/me/reservations",
        json={
            "equipment_id": clientes.id_equipo,
            "start_date": "2026-11-10",
            "end_date": "2026-11-12",
            clave: valor,
        },
    )
    assert respuesta.status_code == 422
    with aplicacion.state.fabrica_sesiones() as base_datos_sesion:
        assert base_datos_sesion.scalar(select(Reserva.id)) is None


@pytest.mark.parametrize("clave", ["status", "customer_user_id", "equipment_id", "role"])
def test_cliente_cancelacion_rechaza_a_no_vacio_cuerpo(
    aplicacion: FastAPI, clientes: Clientes, clave: str
) -> None:
    reserva = clientes.reservar(clientes.alicia)
    respuesta = clientes.alicia.post(
        f"/api/me/reservations/{reserva['id']}/cancel", json={clave: 1}
    )
    assert respuesta.status_code == 422
    with aplicacion.state.fabrica_sesiones() as base_datos_sesion:
        assert base_datos_sesion.get(Reserva, reserva["id"]).estado == "confirmed"


@pytest.mark.parametrize(
    ("clave", "valor"),
    [
        ("id", 999),
        ("reservation_id", 999),
        ("equipment_id", 999),
        ("customer_user_id", 2),
        ("author_user_id", 2),
        ("customer_id", 2),
        ("priority", "high"),
        ("blocking", True),
        ("status", "resolved"),
        ("resolution", "Resolución falsificada"),
        ("public_response", "Respuesta falsificada"),
        ("internal_notes", "Notas falsificadas"),
    ],
)
def test_cliente_incidencia_rechaza_identidad_y_administrativa_campos(
    aplicacion: FastAPI, clientes: Clientes, clave: str, valor: object
) -> None:
    reserva = clientes.reservar(clientes.alicia)
    respuesta = clientes.alicia.post(
        f"/api/me/reservations/{reserva['id']}/incidents",
        json={"title": "Aviso", "description": "Descripción", clave: valor},
    )
    assert respuesta.status_code == 422
    with aplicacion.state.fabrica_sesiones() as base_datos_sesion:
        assert base_datos_sesion.scalar(select(Incidencia.id)) is None


def test_incidencia_propiedad_y_respuesta_proyeccion_excluir_internas_administracion(
    aplicacion: FastAPI, clientes: Clientes
) -> None:
    reserva = clientes.reservar(clientes.alicia)
    incidencia = clientes.informe(clientes.alicia, reserva["id"])
    assert set(incidencia) == INCIDENCIA_CAMPOS
    assert incidencia["status"] == "open"
    assert incidencia["public_response"] == ""
    assert clientes.alicia.get("/api/me/incidents").json() == [incidencia]
    assert clientes.bruno.get("/api/me/incidents").json() == []
    ausente = clientes.bruno.get("/api/me/incidents/999999")
    ajena = clientes.bruno.get(f"/api/me/incidents/{incidencia['id']}")
    assert ausente.status_code == ajena.status_code == 404
    assert ausente.json() == ajena.json()
    with aplicacion.state.fabrica_sesiones() as base_datos_sesion:
        registro = base_datos_sesion.get(Incidencia, incidencia["id"])
        assert registro.id_usuario_autor == clientes.alicia_id
        assert registro.id_equipo == clientes.id_equipo
        assert registro.id_reserva == reserva["id"]
        assert registro.bloqueante is False
        assert registro.prioridad == "medium"
    updated = clientes.administrador_http.patch(
        f"/api/incidents/{incidencia['id']}",
        json={
            "priority": "high",
            "blocking": True,
            "public_response": "Hemos atendido su aviso.",
            "internal_notes": "INTERNAL-NOTES-CANARY",
        },
    )
    assert updated.status_code == 200, updated.text
    resuelta = clientes.administrador_http.patch(
        f"/api/incidents/{incidencia['id']}/status",
        json={"status": "resolved", "resolution": "INTERNAL-RESOLUTION-CANARY"},
    )
    assert resuelta.status_code == 200, resuelta.text
    propia = clientes.alicia.get(f"/api/me/incidents/{incidencia['id']}")
    assert propia.status_code == 200
    assert set(propia.json()) == INCIDENCIA_CAMPOS
    assert propia.json()["status"] == "resolved"
    assert propia.json()["public_response"] == "Hemos atendido su aviso."
    for respuesta in [propia, clientes.alicia.get("/api/me/incidents")]:
        assert "INTERNAL-" not in respuesta.text
        assert "PRIVATE-" not in respuesta.text
        assert "bob@example.test" not in respuesta.text
        assert respuesta.headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize("token_kind", ["missing", "invalid", "other_customer"])
def test_cliente_escrituras_exigir_sus_propia_real_csrf_token(
    aplicacion: FastAPI, clientes: Clientes, token_kind: str
) -> None:
    reserva = clientes.reservar(clientes.alicia)
    csrf = {
        "missing": "",
        "invalid": "incorrect",
        "other_customer": clientes.bruno.headers["X-CSRF-Token"],
    }[token_kind]
    for ruta, cuerpo in [
        (
            "/api/me/reservations",
            {
                "equipment_id": clientes.id_equipo,
                "start_date": "2026-11-15",
                "end_date": "2026-11-17",
            },
        ),
        (f"/api/me/reservations/{reserva['id']}/cancel", {}),
        (
            f"/api/me/reservations/{reserva['id']}/incidents",
            {"title": "Aviso sin CSRF", "description": "No debe crearse"},
        ),
    ]:
        respuesta = clientes.alicia.post(ruta, json=cuerpo, headers={"X-CSRF-Token": csrf})
        assert respuesta.status_code == 403
    with aplicacion.state.fabrica_sesiones() as base_datos_sesion:
        assert len(base_datos_sesion.scalars(select(Reserva)).all()) == 1
        assert base_datos_sesion.get(Reserva, reserva["id"]).estado == "confirmed"
        assert base_datos_sesion.scalar(select(Incidencia.id)) is None


def test_real_perfil_es_lectura_desde_base_datos_cuando_creando_reserva(
    aplicacion: FastAPI, clientes: Clientes
) -> None:
    with aplicacion.state.fabrica_sesiones() as base_datos_sesion:
        usuario = base_datos_sesion.get(Usuario, clientes.alicia_id)
        usuario.nombre = "Nombre actualizado"
        usuario.correo = "updated@example.test"
        base_datos_sesion.commit()
    reserva = clientes.reservar(clientes.alicia)
    with aplicacion.state.fabrica_sesiones() as base_datos_sesion:
        registro = base_datos_sesion.get(Reserva, reserva["id"])
        assert registro.id_usuario_cliente == clientes.alicia_id
        assert registro.nombre_cliente == "Nombre actualizado"
        assert registro.correo_cliente == "updated@example.test"


@pytest.mark.parametrize("cambiar", ["inactive", "role", "expired"])
def test_cliente_acceso_usa_real_cuenta_y_sesion_estado(
    aplicacion: FastAPI, clientes: Clientes, cambiar: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    if cambiar == "expired":
        monkeypatch.setattr(
            "rentalab.autenticacion.servicio.actual_marca_temporal", lambda: 4_000_000_000
        )
    else:
        with aplicacion.state.fabrica_sesiones() as base_datos_sesion:
            usuario = base_datos_sesion.get(Usuario, clientes.alicia_id)
            if cambiar == "inactive":
                usuario.activo = False
            else:
                usuario.rol = "admin"
            base_datos_sesion.commit()
    esperado = 403 if cambiar == "role" else 401
    assert clientes.alicia.get("/api/me/reservations").status_code == esperado
    assert clientes.alicia.get("/api/me/incidents").status_code == esperado
    assert (
        clientes.alicia.post(
            "/api/me/reservations",
            json={
                "equipment_id": clientes.id_equipo,
                "start_date": "2026-11-10",
                "end_date": "2026-11-12",
            },
        ).status_code
        == esperado
    )


def test_heredado_gestion_no_puede_filtrar_cliente_internas_campos(clientes: Clientes) -> None:
    reserva = clientes.reservar(clientes.alicia)
    incidencia = clientes.informe(clientes.alicia, reserva["id"])
    for ruta in [
        "/api/reservations",
        f"/api/reservations/{reserva['id']}",
        f"/api/reservations/{reserva['id']}/",
        "/api/incidents",
        f"/api/incidents/{incidencia['id']}",
        f"/api/incidents/{incidencia['id']}/",
        "/api/equipment",
        f"/api/equipment/{clientes.id_equipo}",
    ]:
        for navegador in [clientes.alicia, clientes.bruno]:
            respuesta = navegador.get(ruta)
            assert respuesta.status_code == 403, (ruta, respuesta.text)
            assert "INTERNAL-" not in respuesta.text
            assert "PRIVATE-" not in respuesta.text
    for navegador in [clientes.alicia, clientes.bruno]:
        for metodo, ruta, cuerpo in [
            ("POST", f"/api/reservations/{reserva['id']}/cancel", {}),
            ("PATCH", f"/api/incidents/{incidencia['id']}", {"blocking": True}),
            (
                "PATCH",
                f"/api/incidents/{incidencia['id']}/status",
                {"status": "resolved", "resolution": "Resolución falsificada"},
            ),
            ("PATCH", f"/api/me/incidents/{incidencia['id']}", {"blocking": True}),
        ]:
            respuesta = navegador.request(metodo, ruta, json=cuerpo)
            assert respuesta.status_code in {403, 405}, (ruta, respuesta.text)


def test_historico_correo_coincidencia_permanece_sin_propietario_y_visible_a_administrador(
    aplicacion: FastAPI, clientes: Clientes
) -> None:
    respuesta = clientes.administrador_http.post(
        "/api/reservations",
        json={
            "equipment_id": clientes.id_equipo,
            "customer_name": "Alice privada",
            "customer_email": "alice@example.test",
            "start_date": "2026-11-10",
            "end_date": "2026-11-12",
            "external_reference": "PRIVATE-REFERENCE-CANARY",
        },
    )
    assert respuesta.status_code == 201
    id_reserva = respuesta.json()["id"]
    with aplicacion.state.fabrica_sesiones() as base_datos_sesion:
        historico = Incidencia(
            id_equipo=clientes.id_equipo,
            titulo="Aviso histórico",
            descripcion="INTERNAL-OLD-INCIDENT-CANARY",
            id_usuario_autor=None,
        )
        base_datos_sesion.add(historico)
        base_datos_sesion.commit()
        id_incidencia = historico.id
        assert base_datos_sesion.get(Reserva, id_reserva).id_usuario_cliente is None
    for navegador in [clientes.alicia, clientes.bruno]:
        assert navegador.get("/api/me/reservations").json() == []
        assert navegador.get("/api/me/incidents").json() == []
        assert navegador.get(f"/api/me/reservations/{id_reserva}").status_code == 404
        assert navegador.get(f"/api/me/incidents/{id_incidencia}").status_code == 404
        assert navegador.post(f"/api/me/reservations/{id_reserva}/cancel").status_code == 404
    assert id_reserva in [
        fila["id"] for fila in clientes.administrador_http.get("/api/reservations").json()
    ]
    assert id_incidencia in [
        fila["id"] for fila in clientes.administrador_http.get("/api/incidents").json()
    ]
    assert clientes.administrador_http.get(f"/api/reservations/{id_reserva}").status_code == 200
    assert clientes.administrador_http.get(f"/api/incidents/{id_incidencia}").status_code == 200


def test_conflicto_despues_publico_consulta_nunca_expone_otro_cliente_identidad(
    aplicacion: FastAPI, clientes: Clientes
) -> None:
    disponibilidad = clientes.alicia.get(
        f"/api/public/equipment/{clientes.id_equipo}/availability",
        params={"start_date": "2026-11-10", "end_date": "2026-11-12"},
    )
    assert disponibilidad.status_code == 200
    assert disponibilidad.json()["available"] is True
    clientes.reservar(clientes.bruno)
    respuesta = clientes.alicia.post(
        "/api/me/reservations",
        json={
            "equipment_id": clientes.id_equipo,
            "start_date": "2026-11-10",
            "end_date": "2026-11-12",
        },
    )
    assert respuesta.status_code == 409
    assert isinstance(respuesta.json()["detail"], str)
    assert "Bob" not in respuesta.text
    assert "bob@example.test" not in respuesta.text
    assert "PRIVATE-" not in respuesta.text
    with aplicacion.state.fabrica_sesiones() as base_datos_sesion:
        assert len(base_datos_sesion.scalars(select(Reserva)).all()) == 1


def test_autoria_hace_no_conceder_acceso_a_sin_vincular_o_ajena_reserva_informa(
    aplicacion: FastAPI, clientes: Clientes
) -> None:
    reserva = clientes.reservar(clientes.bruno)
    with aplicacion.state.fabrica_sesiones() as base_datos_sesion:
        registros = [
            Incidencia(
                id_equipo=clientes.id_equipo,
                titulo="Aviso de autoría histórica",
                descripcion="INTERNAL-UNLINKED-OR-FOREIGN-CANARY",
                id_usuario_autor=clientes.alicia_id,
                id_reserva=id_reserva,
            )
            for id_reserva in [None, reserva["id"]]
        ]
        base_datos_sesion.add_all(registros)
        base_datos_sesion.commit()
        ids = [registro.id for registro in registros]
    for navegador in [clientes.alicia, clientes.bruno]:
        assert navegador.get("/api/me/incidents").json() == []
        for id_incidencia in ids:
            respuesta = navegador.get(f"/api/me/incidents/{id_incidencia}")
            assert respuesta.status_code == 404
            assert "INTERNAL-" not in respuesta.text
    assert set(ids) <= {
        fila["id"] for fila in clientes.administrador_http.get("/api/incidents").json()
    }


def test_cliente_no_puede_elegir_otra_propietario_mediante_consulta_parametros(
    clientes: Clientes,
) -> None:
    reserva = clientes.reservar(clientes.alicia)
    incidencia = clientes.informe(clientes.alicia, reserva["id"])
    for punto_acceso in ["reservations", "incidents"]:
        respuesta = clientes.bruno.get(
            f"/api/me/{punto_acceso}",
            params={"customer_user_id": clientes.alicia_id, "author_user_id": clientes.alicia_id},
        )
        # Un filtro desconocido puede rechazarse o ignorarse, pero nunca cambiar el ámbito.
        assert respuesta.status_code in {200, 422}
        if respuesta.status_code == 200:
            assert respuesta.json() == []
        assert "Alice privada" not in respuesta.text
        assert "Descripción aportada por el cliente" not in respuesta.text
    assert clientes.bruno.get(f"/api/me/incidents/{incidencia['id']}").status_code == 404
