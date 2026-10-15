from collections.abc import Iterator
from contextlib import ExitStack
from dataclasses import dataclass
from datetime import UTC, date, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event, select

from rentalab.autenticacion.esquemas import SolicitudRegistro
from rentalab.compatibilidad import alias_json
from rentalab.reloj import obtener_hoy_proveedor
from rentalab.reservas.modelos import Reserva

HOY = date(2026, 10, 15)
CLIENTE_CONTRASENA = "isolated-phase-c-customer-password"


def iniciar_sesion_cliente(navegador: TestClient, correo: str) -> None:
    token = navegador.get("/api/auth/csrf").json()["csrf_token"]
    respuesta = navegador.post(
        "/api/auth/login",
        json={"username": correo, "password": CLIENTE_CONTRASENA},
        headers={"X-CSRF-Token": token},
    )
    assert respuesta.status_code == 200, respuesta.text
    navegador.headers["X-CSRF-Token"] = navegador.get("/api/auth/csrf").json()["csrf_token"]


@dataclass
class ClienteEscenario:
    primero: TestClient
    segundo: TestClient
    administrador_http: TestClient
    primero_id: int
    segundo_id: int
    id_equipo: int

    def contenido_envio(instancia, **cambios: object) -> dict[str, object]:
        return {
            "equipment_id": instancia.id_equipo,
            "start_date": "2026-11-10",
            "end_date": "2026-11-12",
            **{alias_json(clave): valor for clave, valor in cambios.items()},
        }

    def crear(instancia, navegador: TestClient | None = None, **cambios: object) -> dict:
        respuesta = (navegador or instancia.primero).post(
            "/api/me/reservations", json=instancia.contenido_envio(**cambios)
        )
        assert respuesta.status_code == 201, respuesta.text
        return respuesta.json()


@pytest.fixture
def cliente_escenario(
    aplicacion: FastAPI, equipo_contenido_envio: dict
) -> Iterator[ClienteEscenario]:
    aplicacion.dependency_overrides[obtener_hoy_proveedor] = lambda: lambda: HOY
    identidades = [
        ("Alicia Prueba", "alicia@example.test", "customer"),
        ("Bruno Prueba", "bruno@example.test", "customer"),
        ("Administración Prueba", "admin-phase-c@example.test", "admin"),
    ]
    usuarios = [
        aplicacion.state.autenticacion_servicio.registrar(
            SolicitudRegistro(nombre=nombre, correo=correo, contrasena=CLIENTE_CONTRASENA), rol=rol
        )
        for nombre, correo, rol in identidades
    ]
    with ExitStack() as pila:
        navegadores = [pila.enter_context(TestClient(aplicacion)) for _identidad in identidades]
        for navegador, (_nombre, correo, _rol) in zip(navegadores, identidades, strict=True):
            iniciar_sesion_cliente(navegador, correo)
        primero, segundo, administrador_http = navegadores
        equipo = administrador_http.post("/api/equipment", json=equipo_contenido_envio)
        assert equipo.status_code == 201, equipo.text
        yield ClienteEscenario(
            primero,
            segundo,
            administrador_http,
            usuarios[0].id,
            usuarios[1].id,
            equipo.json()["id"],
        )
    aplicacion.dependency_overrides.pop(obtener_hoy_proveedor, None)


def test_crear_usa_real_cuenta_y_devuelve_explicito_minimo_esquema(
    aplicacion: FastAPI, cliente_escenario: ClienteEscenario
) -> None:
    escenario = cliente_escenario
    respuesta = escenario.primero.post("/api/me/reservations", json=escenario.contenido_envio())
    assert respuesta.status_code == 201, respuesta.text
    real = respuesta.json()
    assert real == {"id": real["id"], **escenario.contenido_envio(), "status": "confirmed"}
    assert respuesta.headers["location"] == f"/api/me/reservations/{real['id']}"
    assert respuesta.headers["cache-control"] == "no-store"
    assert escenario.primero.get(respuesta.headers["location"]).json() == real
    with aplicacion.state.fabrica_sesiones() as sesion:
        fila = sesion.get(Reserva, real["id"])
        assert fila.id_usuario_cliente == escenario.primero_id
        assert fila.nombre_cliente == "Alicia Prueba"
        assert fila.correo_cliente == "alicia@example.test"
        assert fila.referencia_externa is None
        assert fila.estado == "confirmed"
    assert escenario.administrador_http.get(f"/api/reservations/{real['id']}").status_code == 200


def test_lista_y_identificadores_aislar_dos_clientes_y_preservar_sin_propietario_historial(
    aplicacion: FastAPI, cliente_escenario: ClienteEscenario
) -> None:
    escenario = cliente_escenario
    primero = escenario.crear()
    segundo = escenario.crear(escenario.segundo, start_date="2026-11-12", end_date="2026-11-13")
    historico = escenario.administrador_http.post(
        "/api/reservations",
        json={
            **escenario.contenido_envio(fecha_inicio="2026-11-13", fecha_fin="2026-11-14"),
            "customer_name": "Histórico del CSV",
            "customer_email": "alicia@example.test",
            "external_reference": "PRIVATE-HISTORICAL-REFERENCE",
        },
    )
    assert historico.status_code == 201
    canceladas = escenario.primero.post(f"/api/me/reservations/{primero['id']}/cancel").json()
    assert escenario.primero.get("/api/me/reservations").json() == [canceladas]
    assert escenario.segundo.get("/api/me/reservations").json() == [segundo]
    for navegador, inaccesible in [
        (escenario.primero, [segundo["id"], historico.json()["id"], 999999]),
        (escenario.segundo, [primero["id"], historico.json()["id"], 999999]),
    ]:
        ausente = navegador.get("/api/me/reservations/999999")
        for id_reserva in inaccesible:
            detalle = navegador.get(f"/api/me/reservations/{id_reserva}")
            cancelar = navegador.post(f"/api/me/reservations/{id_reserva}/cancel")
            assert detalle.status_code == cancelar.status_code == 404
            assert detalle.json() == cancelar.json() == ausente.json()
    assert len(escenario.administrador_http.get("/api/reservations").json()) == 3
    with aplicacion.state.fabrica_sesiones() as sesion:
        assert sesion.get(Reserva, historico.json()["id"]).id_usuario_cliente is None
        assert sesion.get(Reserva, segundo["id"]).estado == "confirmed"


@pytest.mark.parametrize(
    "adicional",
    [
        {"customer_user_id": 2},
        {"customer_id": 2},
        {"customer_name": "Falsa identidad"},
        {"customer_email": "bruno@example.test"},
        {"user_id": 2},
        {"id": 4},
        {"status": "cancelled"},
        {"origin": "csv"},
        {"external_reference": "PRIVATE-REFERENCE"},
        {"role": "admin"},
    ],
)
def test_creacion_rechaza_identidad_y_administrativa_campos_sin_escribiendo(
    aplicacion: FastAPI, cliente_escenario: ClienteEscenario, adicional: dict
) -> None:
    escenario = cliente_escenario
    respuesta = escenario.primero.post(
        "/api/me/reservations", json={**escenario.contenido_envio(), **adicional}
    )
    assert respuesta.status_code == 422, respuesta.text
    with aplicacion.state.fabrica_sesiones() as sesion:
        assert sesion.scalar(select(Reserva.id)) is None


@pytest.mark.parametrize(
    "adicional",
    [{"status": "confirmed"}, {"customer_user_id": 2}, {"origin": "csv"}, {"equipment_id": 2}],
)
def test_cancelacion_rechaza_adicional_campos_sin_modificando(
    aplicacion: FastAPI, cliente_escenario: ClienteEscenario, adicional: dict
) -> None:
    escenario = cliente_escenario
    reserva = escenario.crear()
    respuesta = escenario.primero.post(
        f"/api/me/reservations/{reserva['id']}/cancel", json=adicional
    )
    assert respuesta.status_code == 422
    with aplicacion.state.fabrica_sesiones() as sesion:
        assert sesion.get(Reserva, reserva["id"]).estado == "confirmed"


@pytest.mark.parametrize(
    "cambios",
    [
        {"start_date": "2026-11-12", "end_date": "2026-11-12"},
        {"start_date": "2026-11-13", "end_date": "2026-11-12"},
        {"start_date": "2026-02-30"},
        {"start_date": "2026-11-10T00:00:00"},
        {"start_date": 0},
        {"equipment_id": True},
        {"equipment_id": 0},
    ],
)
def test_nuevo_reservas_validar_fechas_y_equipo(
    cliente_escenario: ClienteEscenario, cambios: dict
) -> None:
    escenario = cliente_escenario
    assert (
        escenario.primero.post(
            "/api/me/reservations", json=escenario.contenido_envio(**cambios)
        ).status_code
        == 422
    )
    assert escenario.primero.get("/api/me/reservations").json() == []


def test_rechaza_pasado_arranque_pero_permite_hoy(cliente_escenario: ClienteEscenario) -> None:
    escenario = cliente_escenario
    pasado = escenario.primero.post(
        "/api/me/reservations",
        json=escenario.contenido_envio(fecha_inicio="2026-10-14", fecha_fin="2026-10-16"),
    )
    assert pasado.status_code == 409
    assert "anterior a hoy" in pasado.json()["detail"]
    reserva = escenario.crear(start_date="2026-10-15", end_date="2026-10-16")
    assert reserva["start_date"] == HOY.isoformat()


@pytest.mark.parametrize("hoy", [date(2026, 11, 10), date(2026, 11, 11), date(2026, 12, 1)])
def test_no_puede_cancelar_al_o_despues_arranque(
    aplicacion: FastAPI, cliente_escenario: ClienteEscenario, hoy: date
) -> None:
    escenario = cliente_escenario
    reserva = escenario.crear()
    aplicacion.dependency_overrides[obtener_hoy_proveedor] = lambda: lambda: hoy
    respuesta = escenario.primero.post(f"/api/me/reservations/{reserva['id']}/cancel")
    assert respuesta.status_code == 409
    assert "antes de su fecha de inicio" in respuesta.json()["detail"]
    assert escenario.primero.get(f"/api/me/reservations/{reserva['id']}").json() == reserva


def test_cancelar_es_idempotente_despues_arranque_y_hace_no_escritura_otra_vez(
    aplicacion: FastAPI, cliente_escenario: ClienteEscenario
) -> None:
    escenario = cliente_escenario
    reserva = escenario.crear()
    url = f"/api/me/reservations/{reserva['id']}/cancel"
    primero = escenario.primero.post(url, json={})
    assert primero.status_code == 200
    assert primero.json()["status"] == "cancelled"
    aplicacion.dependency_overrides[obtener_hoy_proveedor] = lambda: lambda: date(2026, 12, 1)
    statements = []

    def observar(_conexion, _cursor, sentencia, _parametros, _context, _executemany):
        statements.append(sentencia.strip().upper())

    event.listen(aplicacion.state.motor, "before_cursor_execute", observar)
    try:
        repetidas = escenario.primero.post(url)
    finally:
        event.remove(aplicacion.state.motor, "before_cursor_execute", observar)
    assert repetidas.status_code == 200
    assert repetidas.json() == primero.json()
    assert not any(sentencia.startswith("UPDATE") for sentencia in statements)
    assert escenario.primero.get("/api/me/reservations").json() == [primero.json()]


def test_negocio_dia_usa_madrid_incluso_cuando_utc_es_anterior_dia(
    aplicacion: FastAPI, cliente_escenario: ClienteEscenario, monkeypatch: pytest.MonkeyPatch
) -> None:
    escenario = cliente_escenario
    aplicacion.dependency_overrides.pop(obtener_hoy_proveedor)
    monkeypatch.setattr(
        "rentalab.reloj.utc_ahora", lambda: datetime(2026, 10, 14, 22, 30, tzinfo=UTC)
    )
    anterior_utc_dia = escenario.primero.post(
        "/api/me/reservations",
        json=escenario.contenido_envio(fecha_inicio="2026-10-14", fecha_fin="2026-10-16"),
    )
    assert anterior_utc_dia.status_code == 409
    hoy = escenario.crear(start_date="2026-10-15", end_date="2026-10-16")
    assert escenario.primero.post(f"/api/me/reservations/{hoy['id']}/cancel").status_code == 409


def test_compartido_disponibilidad_aplica_solapamiento_adyacencia_cancelacion_y_bloquea(
    cliente_escenario: ClienteEscenario,
) -> None:
    escenario = cliente_escenario
    publico = f"/api/public/equipment/{escenario.id_equipo}/availability"
    intervalo = {"start_date": "2026-11-10", "end_date": "2026-11-12"}
    assert escenario.primero.get(publico, params=intervalo).json()["available"] is True
    primero = escenario.crear()
    solapamiento = escenario.segundo.post("/api/me/reservations", json=escenario.contenido_envio())
    assert solapamiento.status_code == 409
    assert "consulta la disponibilidad" in solapamiento.json()["detail"]
    escenario.crear(escenario.segundo, start_date="2026-11-12", end_date="2026-11-13")
    assert escenario.primero.post(f"/api/me/reservations/{primero['id']}/cancel").status_code == 200
    assert escenario.primero.get(publico, params=intervalo).json()["available"] is True
    incidencia = escenario.administrador_http.post(
        "/api/incidents",
        json={
            "equipment_id": escenario.id_equipo,
            "title": "PRIVATE-BLOCK-TITLE",
            "description": "PRIVATE-BLOCK-DESCRIPTION",
            "blocking": True,
        },
    )
    assert incidencia.status_code == 201, incidencia.text
    bloqueado = escenario.primero.post("/api/me/reservations", json=escenario.contenido_envio())
    assert bloqueado.status_code == 409
    assert bloqueado.json() == solapamiento.json()
    assert "PRIVATE" not in bloqueado.text
    assert escenario.primero.get(publico, params=intervalo).json()["available"] is False


@pytest.mark.parametrize("activo", [False, None])
def test_inactivo_o_ausente_equipo_no_puede_ser_reservado(
    cliente_escenario: ClienteEscenario, activo: bool | None
) -> None:
    escenario = cliente_escenario
    id_equipo = 999999
    if activo is not None:
        id_equipo = escenario.id_equipo
        assert (
            escenario.administrador_http.patch(
                f"/api/equipment/{id_equipo}", json={"active": False}
            ).status_code
            == 200
        )
    respuesta = escenario.primero.post(
        "/api/me/reservations", json=escenario.contenido_envio(id_equipo=id_equipo)
    )
    assert respuesta.status_code == (404 if activo is None else 409)
    assert escenario.primero.get("/api/me/reservations").json() == []


@pytest.mark.parametrize("adicional_consulta", [{"customer_user_id": 2}, {"status": "confirmed"}])
def test_listar_hace_no_aceptar_propietario_o_administrativa_consulta_filtros(
    cliente_escenario: ClienteEscenario, adicional_consulta: dict
) -> None:
    assert (
        cliente_escenario.primero.get("/api/me/reservations", params=adicional_consulta).status_code
        == 422
    )


def test_ausente_sesion_y_administrador_rol_tienen_distintos_respuestas_http_contratos(
    aplicacion: FastAPI, cliente_escenario: ClienteEscenario
) -> None:
    escenario = cliente_escenario
    with TestClient(aplicacion) as visitante:
        for navegador, esperado in [(visitante, 401), (escenario.administrador_http, 403)]:
            assert navegador.get("/api/me/reservations").status_code == esperado
            assert navegador.get("/api/me/reservations/999999").status_code == esperado
            assert (
                navegador.post("/api/me/reservations", json=escenario.contenido_envio()).status_code
                == esperado
            )
            assert navegador.post("/api/me/reservations/999999/cancel").status_code == esperado


@pytest.mark.parametrize("proporcionado_csrf", [None, "wrong-csrf"])
def test_cliente_escrituras_exigir_csrf_sin_mutacion(
    cliente_escenario: ClienteEscenario, proporcionado_csrf: str | None
) -> None:
    escenario = cliente_escenario
    reserva = escenario.crear()
    original_csrf = escenario.primero.headers.pop("X-CSRF-Token")
    if proporcionado_csrf is not None:
        escenario.primero.headers["X-CSRF-Token"] = proporcionado_csrf
    try:
        creacion = escenario.primero.post(
            "/api/me/reservations",
            json=escenario.contenido_envio(fecha_inicio="2026-11-12", fecha_fin="2026-11-13"),
        )
        cancelacion = escenario.primero.post(f"/api/me/reservations/{reserva['id']}/cancel")
    finally:
        escenario.primero.headers["X-CSRF-Token"] = original_csrf
    assert creacion.status_code == cancelacion.status_code == 403
    assert escenario.primero.get("/api/me/reservations").json() == [reserva]
