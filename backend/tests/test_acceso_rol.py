from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from rentalab.incidencias.modelos import Incidencia
from rentalab.reservas.modelos import Reserva

CLIENTE_CORREO = "customer-access@example.test"
CLIENTE_CONTRASENA = "customer-access-password"


def registrar_cliente(navegador: TestClient, correo: str = CLIENTE_CORREO) -> dict[str, object]:
    token = navegador.get("/api/auth/csrf").json()["csrf_token"]
    respuesta = navegador.post(
        "/api/auth/register",
        json={"name": "Cliente ficticio", "email": correo, "password": CLIENTE_CONTRASENA},
        headers={"X-CSRF-Token": token},
    )
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()


@pytest.fixture
def cliente(aplicacion: FastAPI) -> Iterator[TestClient]:
    with TestClient(aplicacion) as navegador:
        registrar_cliente(navegador)
        token = navegador.get("/api/auth/csrf").json()["csrf_token"]
        respuesta = navegador.post(
            "/api/auth/login",
            json={"username": CLIENTE_CORREO, "password": CLIENTE_CONTRASENA},
            headers={"X-CSRF-Token": token},
        )
        assert respuesta.status_code == 200, respuesta.text
        navegador.headers["X-CSRF-Token"] = navegador.get("/api/auth/csrf").json()["csrf_token"]
        yield navegador


ADMINISTRADOR_PUNTOS_ACCESO = [
    ("GET", "/api/equipment"),
    ("GET", "/api/equipment/1"),
    ("GET", "/api/equipment/1/availability"),
    ("POST", "/api/equipment"),
    ("PUT", "/api/equipment/1"),
    ("PATCH", "/api/equipment/1"),
    ("GET", "/api/reservations"),
    ("GET", "/api/reservations/1"),
    ("POST", "/api/reservations"),
    ("POST", "/api/reservations/1/cancel"),
    ("GET", "/api/incidents"),
    ("GET", "/api/incidents/1"),
    ("POST", "/api/incidents"),
    ("PATCH", "/api/incidents/1/status"),
    ("PATCH", "/api/incidents/1"),
    ("POST", "/api/imports"),
    ("GET", "/api/imports/example"),
    ("GET", "/api/docs"),
    ("GET", "/api/docs/oauth2-redirect"),
    ("GET", "/api/redoc"),
    ("GET", "/api/openapi.json"),
]


@pytest.mark.parametrize("metodo,ruta", ADMINISTRADOR_PUNTOS_ACCESO)
def test_cliente_no_puede_uso_existentes_gestion_puntos_acceso(
    cliente: TestClient, metodo: str, ruta: str
) -> None:
    # Los cuerpos ausentes o inválidos no deben eludir la comprobación del rol ni revelar
    # detalles de validación.
    respuesta = cliente.request(metodo, ruta)
    assert respuesta.status_code == 403
    assert set(respuesta.json()) == {"detail"}


@pytest.mark.parametrize("metodo,ruta", ADMINISTRADOR_PUNTOS_ACCESO)
def test_existentes_gestion_puntos_acceso_exigir_a_sesion(
    aplicacion: FastAPI, metodo: str, ruta: str
) -> None:
    with TestClient(aplicacion) as anonimo:
        respuesta = anonimo.request(metodo, ruta)
        assert respuesta.status_code == 401
        assert set(respuesta.json()) == {"detail"}


def test_cliente_importacion_es_denegado_antes_consumiendo_multipart(cliente: TestClient) -> None:
    consumido = False

    def carga() -> Iterator[bytes]:
        nonlocal consumido
        consumido = True
        yield b"This multipart body must not be read by a customer"

    solicitud = cliente.build_request(
        "POST",
        "/api/imports",
        content=carga(),
        headers={"Content-Type": "multipart/form-data; boundary=missing"},
    )
    assert cliente.send(solicitud).status_code == 403
    assert consumido is False


def crear_privado_historial(
    administrador_http: TestClient,
    equipo_contenido_envio: dict[str, object],
    correo: str = CLIENTE_CORREO,
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    equipo_respuesta = administrador_http.post("/api/equipment", json=equipo_contenido_envio)
    assert equipo_respuesta.status_code == 201
    equipo = equipo_respuesta.json()
    reserva_respuesta = administrador_http.post(
        "/api/reservations",
        json={
            "equipment_id": equipo["id"],
            "customer_name": "Nombre privado",
            "customer_email": correo,
            "start_date": "2026-11-10",
            "end_date": "2026-11-12",
            "external_reference": "PRIVATE-REFERENCE",
        },
    )
    assert reserva_respuesta.status_code == 201
    incidencia_respuesta = administrador_http.post(
        "/api/incidents",
        json={
            "equipment_id": equipo["id"],
            "title": "Informe privado",
            "description": "Descripción de uso privada",
            "blocking": False,
        },
    )
    assert incidencia_respuesta.status_code == 201
    return equipo, reserva_respuesta.json(), incidencia_respuesta.json()


def test_catalogo_y_fecha_disponibilidad_son_publico_sin_privado_reserva_ids(
    aplicacion: FastAPI, cliente_http: TestClient, equipo_contenido_envio: dict[str, object]
) -> None:
    equipo, reserva, _incidencia = crear_privado_historial(cliente_http, equipo_contenido_envio)
    ruta = f"/api/public/equipment/{equipo['id']}/availability"
    fechas = {"start_date": "2026-11-10", "end_date": "2026-11-12"}
    administrativa = cliente_http.get(f"/api/equipment/{equipo['id']}/availability", params=fechas)
    assert administrativa.status_code == 200
    assert administrativa.json()["conflicting_reservation_ids"] == [reserva["id"]]

    with TestClient(aplicacion) as anonimo:
        catalogo = anonimo.get("/api/public/equipment")
        detalle = anonimo.get(f"/api/public/equipment/{equipo['id']}")
        disponibilidad = anonimo.get(ruta, params=fechas)
        assert catalogo.status_code == detalle.status_code == disponibilidad.status_code == 200
        resultado = disponibilidad.json()
        assert resultado["available"] is False
        assert resultado["status"] == "unavailable"
        assert "reason" not in resultado
        assert resultado.get("conflicting_reservation_ids", []) == []
        for privado_valor in ["Nombre privado", CLIENTE_CORREO, "PRIVATE-REFERENCE"]:
            assert privado_valor not in catalogo.text + detalle.text + disponibilidad.text
        for privado_ruta in [
            f"/api/reservations/{reserva['id']}",
            "/api/reservations/999999",
            "/api/incidents/999999",
        ]:
            assert anonimo.get(privado_ruta).status_code == 401


def test_cliente_no_ve_historicos_sin_propietario_aunque_coincida_correo(
    aplicacion: FastAPI,
    cliente_http: TestClient,
    cliente: TestClient,
    equipo_contenido_envio: dict[str, object],
) -> None:
    _equipo, reserva, incidencia = crear_privado_historial(cliente_http, equipo_contenido_envio)
    reserva_ruta = f"/api/reservations/{reserva['id']}"
    incidencia_ruta = f"/api/incidents/{incidencia['id']}"
    assert cliente_http.get(reserva_ruta).status_code == 200
    assert cliente_http.get(incidencia_ruta).status_code == 200
    assert cliente.get(f"/api/me/reservations/{reserva['id']}").status_code == 404
    assert cliente.get(f"/api/me/incidents/{incidencia['id']}").status_code == 404
    assert cliente.get("/api/me/reservations/999999").status_code == 404
    assert cliente.get("/api/me/incidents/999999").status_code == 404

    # Crear una reserva como administrador o coincidir con su correo de contacto no otorga su
    # propiedad.
    with aplicacion.state.fabrica_sesiones() as base_datos_sesion:
        registro = base_datos_sesion.get(Reserva, reserva["id"])
        assert registro is not None
        assert registro.id_usuario_cliente is None


def test_detalle_permisos_seguir_persistidos_propiedad_sin_exponer_otro_reservas(
    aplicacion: FastAPI,
    cliente_http: TestClient,
    cliente: TestClient,
    equipo_contenido_envio: dict[str, object],
) -> None:
    from rentalab.autenticacion.modelos import Usuario

    equipo, reserva, incidencia = crear_privado_historial(cliente_http, equipo_contenido_envio)
    with aplicacion.state.fabrica_sesiones.begin() as base_datos_sesion:
        usuario = base_datos_sesion.scalar(select(Usuario).where(Usuario.correo == CLIENTE_CORREO))
        assert usuario is not None
        registro = base_datos_sesion.get(Reserva, reserva["id"])
        informe = base_datos_sesion.get(Incidencia, incidencia["id"])
        assert registro is not None and informe is not None
        registro.id_usuario_cliente = usuario.id
        informe.id_usuario_autor = usuario.id
        informe.id_reserva = registro.id

    reserva_ruta = f"/api/me/reservations/{reserva['id']}"
    incidencia_ruta = f"/api/me/incidents/{incidencia['id']}"
    assert cliente.get(reserva_ruta).status_code == 200
    # Existe otra reserva sin propietario en la misma unidad y su identificador sigue siendo
    # privado.
    otro = cliente_http.post(
        "/api/reservations",
        json={
            "equipment_id": equipo["id"],
            "customer_name": "Otro cliente",
            "customer_email": "other@example.test",
            "start_date": "2026-12-10",
            "end_date": "2026-12-12",
        },
    )
    assert otro.status_code == 201
    propia_informe = cliente.get(incidencia_ruta)
    assert propia_informe.status_code == 200
    assert otro.json()["id"] not in propia_informe.json().get("confirmed_reservation_ids", [])
    assert cliente.get(f"/api/me/reservations/{otro.json()['id']}").status_code == 404

    with aplicacion.state.fabrica_sesiones.begin() as base_datos_sesion:
        registro = base_datos_sesion.get(Reserva, reserva["id"])
        informe = base_datos_sesion.get(Incidencia, incidencia["id"])
        assert registro is not None and informe is not None
        registro.id_usuario_cliente = None
        informe.id_usuario_autor = None
    assert cliente.get(reserva_ruta).status_code == 404
    assert cliente.get(incidencia_ruta).status_code == 404


def test_cliente_disponibilidad_oculta_en_conflicto_reserva_ids(
    cliente_http: TestClient, cliente: TestClient, equipo_contenido_envio: dict[str, object]
) -> None:
    equipo, _reserva, _incidencia = crear_privado_historial(cliente_http, equipo_contenido_envio)
    respuesta = cliente.get(
        f"/api/public/equipment/{equipo['id']}/availability",
        params={"start_date": "2026-11-10", "end_date": "2026-11-12"},
    )
    assert respuesta.status_code == 200
    assert respuesta.json()["available"] is False
    assert respuesta.json().get("conflicting_reservation_ids", []) == []


def test_registrar_hace_no_apropiarse_historial_por_coincidente_correo(
    aplicacion: FastAPI, cliente_http: TestClient, equipo_contenido_envio: dict[str, object]
) -> None:
    _equipo, reserva, _incidencia = crear_privado_historial(cliente_http, equipo_contenido_envio)
    with TestClient(aplicacion) as navegador:
        usuario = registrar_cliente(navegador)
        assert isinstance(usuario["id"], int)

    with aplicacion.state.fabrica_sesiones() as base_datos_sesion:
        registro = base_datos_sesion.get(Reserva, reserva["id"])
        assert registro is not None
        assert registro.correo_cliente == CLIENTE_CORREO
        assert registro.id_usuario_cliente is None


def test_rol_vigente_controla_acceso_administrativo_y_registra_autor_de_incidencia(
    aplicacion: FastAPI,
    cliente_http: TestClient,
    cliente: TestClient,
    equipo_contenido_envio: dict[str, object],
) -> None:
    from rentalab.autenticacion.modelos import Usuario

    equipo_respuesta = cliente_http.post("/api/equipment", json=equipo_contenido_envio)
    assert equipo_respuesta.status_code == 201
    id_equipo = equipo_respuesta.json()["id"]
    with aplicacion.state.fabrica_sesiones.begin() as base_datos_sesion:
        usuario = base_datos_sesion.scalar(select(Usuario).where(Usuario.correo == CLIENTE_CORREO))
        assert usuario is not None
        id_usuario = usuario.id
        usuario.rol = "admin"

    # La misma cookie debe usar el rol vigente en la base de datos en cada solicitud.
    assert cliente.get("/api/reservations").status_code == 200
    informe_respuesta = cliente.post(
        "/api/incidents", json={"equipment_id": id_equipo, "title": "Informe del administrador"}
    )
    assert informe_respuesta.status_code == 201
    with aplicacion.state.fabrica_sesiones.begin() as base_datos_sesion:
        informe = base_datos_sesion.get(Incidencia, informe_respuesta.json()["id"])
        assert informe is not None
        assert informe.id_usuario_autor == id_usuario
        usuario = base_datos_sesion.get(Usuario, id_usuario)
        assert usuario is not None
        usuario.rol = "customer"

    assert cliente.get("/api/reservations").status_code == 403
    assert cliente.post("/api/incidents", json={}).status_code == 403
    # Un informe administrativo no tiene reserva de cliente; perder el rol no concede acceso.
    assert cliente.get(f"/api/incidents/{informe_respuesta.json()['id']}").status_code == 403
    assert cliente.get(f"/api/me/incidents/{informe_respuesta.json()['id']}").status_code == 404


def test_csv_hace_no_asignar_un_propietario_desde_un_existentes_usuarios_correo(
    aplicacion: FastAPI,
    cliente_http: TestClient,
    cliente: TestClient,
    equipo_contenido_envio: dict[str, object],
) -> None:
    equipo_respuesta = cliente_http.post("/api/equipment", json=equipo_contenido_envio)
    assert equipo_respuesta.status_code == 201
    contenido = (
        "external_reference,customer_name,customer_email,equipment_code,starts_on,ends_on\n"
        f"CSV-UNKNOWN-OWNER,Cliente importado,{CLIENTE_CORREO},CAM-001,2026-11-10,2026-11-12\n"
    ).encode()
    respuesta = cliente_http.post(
        "/api/imports", files={"file": ("orders.csv", contenido, "text/csv")}
    )
    assert respuesta.status_code == 200
    assert respuesta.json()["totals"]["accepted"] == 1
    id_reserva = respuesta.json()["rows"][0]["reservation"]["id"]
    with aplicacion.state.fabrica_sesiones() as base_datos_sesion:
        registro = base_datos_sesion.get(Reserva, id_reserva)
        assert registro is not None
        assert registro.correo_cliente == CLIENTE_CORREO
        assert registro.id_usuario_cliente is None
    assert cliente.get(f"/api/me/reservations/{id_reserva}").status_code == 404


@pytest.mark.parametrize("correo", ["de\u0301mo@example.test", "demo@ＥＸＡＭＰＬＥ.test"])
def test_iniciar_sesion_acepta_la_mismo_correo_escritura_aceptadas_durante_registro(
    aplicacion: FastAPI, correo: str
) -> None:
    with TestClient(aplicacion) as navegador:
        usuario = registrar_cliente(navegador, correo)
        token = navegador.get("/api/auth/csrf").json()["csrf_token"]
        respuesta = navegador.post(
            "/api/auth/login",
            json={"username": correo, "password": CLIENTE_CONTRASENA},
            headers={"X-CSRF-Token": token},
        )
        assert respuesta.status_code == 200
        assert respuesta.json()["role"] == "customer"
        assert respuesta.json()["user"]["id"] == usuario["id"]
