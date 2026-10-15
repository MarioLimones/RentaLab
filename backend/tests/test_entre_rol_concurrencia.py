"""El portal, la administración y el CSV deben compartir un único bloqueo definitivo de reservas."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event, select
from sqlalchemy.engine import Connection, ExecutionContext
from test_administrador_conectado import FECHAS, acceder_en
from test_administrador_conectado import conectado_escenario as conectado_escenario

from rentalab.configuracion import Configuracion
from rentalab.principal import crear_aplicacion
from rentalab.reloj import obtener_hoy_proveedor
from rentalab.reservas.modelos import Reserva


@pytest.mark.parametrize("gestion_origen", ["admin", "csv"])
@pytest.mark.parametrize("portal_primero", [True, False])
def test_portal_y_gestion_no_puede_confirmar_incompatibles_reservas(
    aplicacion: FastAPI,
    ajustes: Configuracion,
    conectado_escenario: tuple,
    gestion_origen: str,
    portal_primero: bool,
) -> None:
    cliente, otro_cliente, administrador_http, propietario_id, id_equipo = conectado_escenario
    segundo_aplicacion = crear_aplicacion(ajustes)
    segundo_aplicacion.dependency_overrides[obtener_hoy_proveedor] = (
        aplicacion.dependency_overrides[obtener_hoy_proveedor]
    )
    primero_tiene_bloqueo = Event()
    segundo_intentado_escritura = Event()
    primero_conexiones: set[int] = set()
    segundo_conexiones: set[int] = set()

    def observar_primero_conexion(conexion: object, _registro: object, _proxy: object) -> None:
        primero_conexiones.add(id(conexion))

    def observar_segundo_conexion(conexion: object, _registro: object, _proxy: object) -> None:
        segundo_conexiones.add(id(conexion))

    def mantener_primero_escritura_bloqueo(
        _conexion: Connection,
        _cursor: object,
        sentencia: str,
        _parametros: object,
        _context: ExecutionContext,
        _executemany: bool,
    ) -> None:
        if sentencia.strip().upper() == "BEGIN IMMEDIATE":
            primero_tiene_bloqueo.set()
            assert segundo_intentado_escritura.wait(timeout=5), "Second writer never attempted SQL"

    def observar_segundo_escritura_intento(
        _conexion: Connection,
        _cursor: object,
        sentencia: str,
        _parametros: object,
        _context: ExecutionContext,
        _executemany: bool,
    ) -> None:
        if sentencia.strip().upper() == "BEGIN IMMEDIATE":
            segundo_intentado_escritura.set()

    def portal_solicitud(navegador: TestClient):
        return navegador.post("/api/me/reservations", json={"equipment_id": id_equipo, **FECHAS})

    def gestion_solicitud(navegador: TestClient):
        if gestion_origen == "admin":
            return navegador.post(
                "/api/reservations",
                json={
                    "equipment_id": id_equipo,
                    "customer_name": "PRIVATE-MANAGEMENT-RACE-CANARY",
                    "customer_email": "management-race@example.test",
                    **FECHAS,
                },
            )
        contenido = (
            "external_reference,customer_name,customer_email,equipment_code,starts_on,ends_on\n"
            "F-RACE,PRIVATE-MANAGEMENT-RACE-CANARY,management-race@example.test,"
            f"CAM-001,{FECHAS['start_date']},{FECHAS['end_date']}\n"
        ).encode()
        return navegador.post("/api/imports", files={"file": ("race.csv", contenido, "text/csv")})

    try:
        with TestClient(segundo_aplicacion) as segundo_navegador:
            acceder_en(
                segundo_navegador,
                "admin-phase-e@example.test" if portal_primero else "one-phase-e@example.test",
            )
            # Autentica antes de observar SQL, para sincronizar únicamente la
            # competencia por la reserva.
            event.listen(aplicacion.state.motor, "checkout", observar_primero_conexion)
            event.listen(segundo_aplicacion.state.motor, "checkout", observar_segundo_conexion)
            event.listen(
                aplicacion.state.motor, "after_cursor_execute", mantener_primero_escritura_bloqueo
            )
            event.listen(
                segundo_aplicacion.state.motor,
                "before_cursor_execute",
                observar_segundo_escritura_intento,
            )
            try:
                with ThreadPoolExecutor(max_workers=2) as ejecutor:
                    primero = ejecutor.submit(
                        portal_solicitud if portal_primero else gestion_solicitud,
                        cliente if portal_primero else administrador_http,
                    )
                    assert primero_tiene_bloqueo.wait(timeout=5), (
                        "First writer did not acquire SQL lock"
                    )
                    segundo = ejecutor.submit(
                        gestion_solicitud if portal_primero else portal_solicitud, segundo_navegador
                    )
                    primero_respuesta = primero.result(timeout=10)
                    segundo_respuesta = segundo.result(timeout=10)
            finally:
                event.remove(aplicacion.state.motor, "checkout", observar_primero_conexion)
                event.remove(segundo_aplicacion.state.motor, "checkout", observar_segundo_conexion)
                event.remove(
                    aplicacion.state.motor,
                    "after_cursor_execute",
                    mantener_primero_escritura_bloqueo,
                )
                event.remove(
                    segundo_aplicacion.state.motor,
                    "before_cursor_execute",
                    observar_segundo_escritura_intento,
                )
        portal = primero_respuesta if portal_primero else segundo_respuesta
        gestion = segundo_respuesta if portal_primero else primero_respuesta
        assert portal.status_code == (201 if portal_primero else 409)
        if not portal_primero:
            assert "consulta la disponibilidad" in portal.json()["detail"]
            assert "PRIVATE-MANAGEMENT-RACE-CANARY" not in portal.text
            assert "management-race@example.test" not in portal.text
            assert "retry-after" not in portal.headers
        if gestion_origen == "admin":
            assert gestion.status_code == (409 if portal_primero else 201)
            assert "retry-after" not in gestion.headers
        else:
            # El CSV conserva su contrato de informe parcial: rechaza las filas en conflicto
            # dentro de una respuesta HTTP 200, sin guardar reservas ni referencias adicionales.
            assert gestion.status_code == 200
            informe = gestion.json()
            assert informe["totals"] == {
                "total": 1,
                "accepted": 0 if portal_primero else 1,
                "already_imported": 0,
                "rejected": 1 if portal_primero else 0,
            }
            assert informe["rows"][0]["status"] == ("rejected" if portal_primero else "accepted")
            if portal_primero:
                assert informe["rows"][0]["reservation"] is None
        assert primero_conexiones and segundo_conexiones
        assert primero_conexiones.isdisjoint(segundo_conexiones)
        with aplicacion.state.fabrica_sesiones() as sesion:
            persistidos = sesion.scalars(select(Reserva)).all()
            assert len(persistidos) == 1
            reserva = persistidos[0]
            assert reserva.estado == "confirmed"
            assert reserva.origen == ("portal" if portal_primero else gestion_origen)
            assert reserva.id_usuario_cliente == (propietario_id if portal_primero else None)
            assert reserva.referencia_externa == (
                "F-RACE" if not portal_primero and gestion_origen == "csv" else None
            )
        assert cliente.get("/api/me/reservations").json() == (
            [portal.json()] if portal_primero else []
        )
        assert otro_cliente.get("/api/me/reservations").json() == []
        assert len(administrador_http.get("/api/reservations").json()) == 1
        disponibilidad = cliente.get(
            f"/api/public/equipment/{id_equipo}/availability", params=FECHAS
        )
        assert disponibilidad.json()["available"] is False
    finally:
        segundo_aplicacion.state.motor.dispose()
