from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from threading import Event

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event, select
from test_cuenta_reservas import HOY, ClienteEscenario, iniciar_sesion_cliente
from test_cuenta_reservas import cliente_escenario as cliente_escenario
from test_importaciones import hacer_csv, importacion_csv, orden_fila

from rentalab.compatibilidad import alias_json
from rentalab.configuracion import Configuracion
from rentalab.principal import crear_aplicacion
from rentalab.reloj import obtener_hoy_proveedor
from rentalab.reservas.esquemas import CrearReserva
from rentalab.reservas.modelos import Reserva
from rentalab.reservas.repositorio import RepositorioReservas
from rentalab.reservas.servicio import ConflictoReserva, ServicioReservas


@pytest.fixture
def segundo_unidad(cliente_escenario: ClienteEscenario, equipo_contenido_envio: dict) -> int:
    respuesta = cliente_escenario.administrador_http.post(
        "/api/equipment", json={**equipo_contenido_envio, "code": "CAM-002"}
    )
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()["id"]


def administrador_reservar(escenario: ClienteEscenario, **cambios: object) -> dict:
    respuesta = escenario.administrador_http.post(
        "/api/reservations",
        json={
            **escenario.contenido_envio(**cambios),
            "customer_name": "Cliente administrativo",
            "customer_email": "admin-booking@example.test",
        },
    )
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()


def test_producto_reserva_dos_unidades_independientemente_y_cancelacion_restaura_capacidad(
    aplicacion: FastAPI, cliente_escenario: ClienteEscenario, segundo_unidad: int
) -> None:
    escenario = cliente_escenario
    primero = escenario.crear()
    segundo = escenario.crear(escenario.segundo)
    assert [primero["equipment_id"], segundo["equipment_id"]] == [
        escenario.id_equipo,
        segundo_unidad,
    ]
    agotado = escenario.primero.post("/api/me/reservations", json=escenario.contenido_envio())
    assert agotado.status_code == 409
    assert escenario.primero.get("/api/me/reservations").json() == [primero]
    assert escenario.segundo.get("/api/me/reservations").json() == [segundo]
    assert escenario.primero.post(f"/api/me/reservations/{segundo['id']}/cancel").status_code == 404
    assert escenario.primero.post(f"/api/me/reservations/{primero['id']}/cancel").status_code == 200
    reemplazo = escenario.crear()
    assert reemplazo["equipment_id"] == escenario.id_equipo
    with aplicacion.state.fabrica_sesiones() as sesion:
        reservas = sesion.scalars(select(Reserva).order_by(Reserva.id)).all()
        assert len(reservas) == 3
        assert [fila.estado for fila in reservas] == ["cancelled", "confirmed", "confirmed"]
        assert [fila.id_usuario_cliente for fila in reservas] == [
            escenario.primero_id,
            escenario.segundo_id,
            escenario.primero_id,
        ]
        assert all(fila.origen == "portal" for fila in reservas)


@pytest.mark.parametrize("no_disponible", ["inactive", "blocking_incident"])
def test_no_disponible_unidades_hacer_no_agregar_capacidad_y_recuperar_cuando_reactivado(
    cliente_escenario: ClienteEscenario, segundo_unidad: int, no_disponible: str
) -> None:
    escenario = cliente_escenario
    escenario.crear()
    id_incidencia = None
    if no_disponible == "inactive":
        assert (
            escenario.administrador_http.patch(
                f"/api/equipment/{segundo_unidad}", json={"active": False}
            ).status_code
            == 200
        )
    else:
        incidencia = escenario.administrador_http.post(
            "/api/incidents",
            json={"equipment_id": segundo_unidad, "title": "PRIVATE-MAINTENANCE", "blocking": True},
        )
        assert incidencia.status_code == 201, incidencia.text
        id_incidencia = incidencia.json()["id"]
    no_disponible_respuesta = escenario.segundo.post(
        "/api/me/reservations", json=escenario.contenido_envio()
    )
    assert no_disponible_respuesta.status_code == 409
    assert "PRIVATE" not in no_disponible_respuesta.text
    assert "blocking" not in no_disponible_respuesta.text
    if no_disponible == "inactive":
        assert (
            escenario.administrador_http.patch(
                f"/api/equipment/{segundo_unidad}", json={"active": True}
            ).status_code
            == 200
        )
    else:
        assert (
            escenario.administrador_http.patch(
                f"/api/incidents/{id_incidencia}", json={"blocking": False}
            ).status_code
            == 200
        )
    assert escenario.crear(escenario.segundo)["equipment_id"] == segundo_unidad


def test_bloqueado_representante_puede_asignar_sana_hermana(
    cliente_escenario: ClienteEscenario, segundo_unidad: int
) -> None:
    escenario = cliente_escenario
    bloqueado = escenario.administrador_http.post(
        "/api/incidents",
        json={"equipment_id": escenario.id_equipo, "title": "En reparación", "blocking": True},
    )
    assert bloqueado.status_code == 201, bloqueado.text
    assert escenario.crear()["equipment_id"] == segundo_unidad
    assert (
        escenario.segundo.post("/api/me/reservations", json=escenario.contenido_envio()).status_code
        == 409
    )


def test_inactivo_solicitado_unidad_hace_no_permitir_a_ocultos_producto_enlace(
    cliente_escenario: ClienteEscenario, segundo_unidad: int
) -> None:
    escenario = cliente_escenario
    assert (
        escenario.administrador_http.patch(
            f"/api/equipment/{escenario.id_equipo}", json={"active": False}
        ).status_code
        == 200
    )
    assert (
        escenario.primero.post("/api/me/reservations", json=escenario.contenido_envio()).status_code
        == 409
    )
    assert escenario.crear(equipment_id=segundo_unidad)["equipment_id"] == segundo_unidad


def test_fragmentada_capacidad_no_puede_cambiar_unidades_mitad_mediante_a_reserva(
    cliente_escenario: ClienteEscenario, segundo_unidad: int
) -> None:
    escenario = cliente_escenario
    administrador_reservar(escenario, fecha_fin="2026-11-11")
    administrador_reservar(escenario, id_equipo=segundo_unidad, fecha_inicio="2026-11-11")
    respuesta = escenario.primero.post("/api/me/reservations", json=escenario.contenido_envio())
    assert respuesta.status_code == 409
    assert escenario.primero.get("/api/me/reservations").json() == []
    assert len(escenario.administrador_http.get("/api/reservations").json()) == 2
    # El día de fin sigue excluido para cada unidad física.
    primero = escenario.crear(start_date="2026-11-11")
    segundo = escenario.crear(escenario.segundo, end_date="2026-11-11")
    assert [primero["equipment_id"], segundo["equipment_id"]] == [
        escenario.id_equipo,
        segundo_unidad,
    ]


@pytest.mark.parametrize(
    "cambios",
    [{"name": "Otro modelo"}, {"category": "Ópticas"}],
)
def test_asignacion_hace_no_tomar_a_distinto_producto_o_categoria(
    cliente_escenario: ClienteEscenario, equipo_contenido_envio: dict, cambios: dict
) -> None:
    escenario = cliente_escenario
    otro = escenario.administrador_http.post(
        "/api/equipment",
        json={
            **equipo_contenido_envio,
            "code": "CAM-OTHER",
            **{alias_json(clave): valor for clave, valor in cambios.items()},
        },
    )
    assert otro.status_code == 201, otro.text
    escenario.crear()
    assert (
        escenario.segundo.post("/api/me/reservations", json=escenario.contenido_envio()).status_code
        == 409
    )
    assert (
        escenario.crear(escenario.segundo, equipment_id=otro.json()["id"])["equipment_id"]
        == (otro.json()["id"])
    )


def test_normalizado_producto_nombre_y_categoria_comparten_capacidad(
    cliente_escenario: ClienteEscenario, segundo_unidad: int
) -> None:
    escenario = cliente_escenario
    updated = escenario.administrador_http.patch(
        f"/api/equipment/{segundo_unidad}",
        json={"name": "  CÁMARA DE PRUEBA  ", "category": "  CÁMARAS  "},
    )
    assert updated.status_code == 200, updated.text
    escenario.crear()
    assert escenario.crear(escenario.segundo)["equipment_id"] == segundo_unidad


def test_administracion_csv_y_demostracion_conservan_unidad_fisica_solicitada(
    aplicacion: FastAPI, cliente_escenario: ClienteEscenario, segundo_unidad: int
) -> None:
    escenario = cliente_escenario
    escenario.crear()
    administrador_http = escenario.administrador_http.post(
        "/api/reservations",
        json={
            **escenario.contenido_envio(),
            "customer_name": "Cliente administrativo",
            "customer_email": "admin-booking@example.test",
        },
    )
    assert administrador_http.status_code == 409
    informe = importacion_csv(
        escenario.administrador_http, hacer_csv([orden_fila("EXACT-UNIT-CSV")])
    )
    assert informe["totals"]["rejected"] == 1
    with aplicacion.state.fabrica_sesiones() as sesion:
        servicio = ServicioReservas(RepositorioReservas(sesion))
        with pytest.raises(ConflictoReserva):
            servicio.crear_para_cliente(
                CrearReserva(
                    **escenario.contenido_envio(),
                    nombre_cliente="Alicia Prueba",
                    correo_cliente="alicia@example.test",
                ),
                id_usuario_cliente=escenario.primero_id,
                hoy=lambda: HOY,
            )
    assert escenario.crear(escenario.segundo)["equipment_id"] == segundo_unidad


def test_paralelas_reservas_nunca_sobrerreservar_dos_unidades(
    aplicacion: FastAPI,
    ajustes: Configuracion,
    cliente_escenario: ClienteEscenario,
    segundo_unidad: int,
) -> None:
    escenario = cliente_escenario
    otro_aplicaciones = [crear_aplicacion(ajustes), crear_aplicacion(ajustes)]
    for otro_aplicacion in otro_aplicaciones:
        otro_aplicacion.dependency_overrides[obtener_hoy_proveedor] = lambda: lambda: HOY
    primero_tiene_bloqueo = Event()
    esperando_escritores = [Event(), Event()]

    def mantener_primero_escritura(
        _conexion, _cursor, sentencia, _parametros, _context, _executemany
    ):
        if sentencia.strip().upper() == "BEGIN IMMEDIATE":
            primero_tiene_bloqueo.set()
            for esperando_escritor in esperando_escritores:
                assert esperando_escritor.wait(timeout=5), (
                    "Competing request did not attempt its write"
                )

    def observar_escritura(esperando_escritor: Event):
        def observar(_conexion, _cursor, sentencia, _parametros, _context, _executemany):
            if sentencia.strip().upper() == "BEGIN IMMEDIATE":
                esperando_escritor.set()

        return observar

    observadores = [observar_escritura(escritor) for escritor in esperando_escritores]
    try:
        with ExitStack() as pila:
            navegadores = [
                pila.enter_context(TestClient(otro_aplicacion))
                for otro_aplicacion in otro_aplicaciones
            ]
            iniciar_sesion_cliente(navegadores[0], "bruno@example.test")
            iniciar_sesion_cliente(navegadores[1], "alicia@example.test")
            event.listen(aplicacion.state.motor, "after_cursor_execute", mantener_primero_escritura)
            for otro_aplicacion, observador in zip(otro_aplicaciones, observadores, strict=True):
                event.listen(otro_aplicacion.state.motor, "before_cursor_execute", observador)
            try:
                with ThreadPoolExecutor(max_workers=3) as ejecutor:
                    primero = ejecutor.submit(
                        escenario.primero.post,
                        "/api/me/reservations",
                        json=escenario.contenido_envio(),
                    )
                    assert primero_tiene_bloqueo.wait(timeout=5), (
                        "First request did not acquire its lock"
                    )
                    otros = [
                        ejecutor.submit(
                            navegador.post, "/api/me/reservations", json=escenario.contenido_envio()
                        )
                        for navegador in navegadores
                    ]
                    respuestas = [primero.result(timeout=10)] + [
                        futuro.result(timeout=10) for futuro in otros
                    ]
            finally:
                event.remove(
                    aplicacion.state.motor, "after_cursor_execute", mantener_primero_escritura
                )
                for otro_aplicacion, observador in zip(
                    otro_aplicaciones, observadores, strict=True
                ):
                    event.remove(otro_aplicacion.state.motor, "before_cursor_execute", observador)
        assert sorted(respuesta.status_code for respuesta in respuestas) == [201, 201, 409]
        confirmadas = [respuesta.json() for respuesta in respuestas if respuesta.status_code == 201]
        assert {reserva["equipment_id"] for reserva in confirmadas} == {
            escenario.id_equipo,
            segundo_unidad,
        }
        with aplicacion.state.fabrica_sesiones() as sesion:
            reservas = sesion.scalars(select(Reserva)).all()
            assert len(reservas) == 2
            assert {reserva.id_equipo for reserva in reservas} == {
                escenario.id_equipo,
                segundo_unidad,
            }
            assert all(reserva.estado == "confirmed" for reserva in reservas)
    finally:
        for otro_aplicacion in otro_aplicaciones:
            otro_aplicacion.state.motor.dispose()
