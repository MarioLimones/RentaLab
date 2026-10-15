from concurrent.futures import ThreadPoolExecutor
from datetime import date
from threading import Event

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event, select
from sqlalchemy.engine import Connection, ExecutionContext
from test_cuenta_reservas import HOY, ClienteEscenario, iniciar_sesion_cliente
from test_cuenta_reservas import cliente_escenario as cliente_escenario

from rentalab.configuracion import Configuracion
from rentalab.principal import crear_aplicacion
from rentalab.reloj import obtener_hoy_proveedor
from rentalab.reservas.modelos import Reserva


def test_dos_clientes_usando_distintos_conexiones_no_puede_doble_reservar(
    aplicacion: FastAPI, ajustes: Configuracion, cliente_escenario: ClienteEscenario
) -> None:
    escenario = cliente_escenario
    segundo_aplicacion = crear_aplicacion(ajustes)
    segundo_aplicacion.dependency_overrides[obtener_hoy_proveedor] = lambda: lambda: HOY
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
            assert segundo_intentado_escritura.wait(timeout=5), (
                "Second customer did not attempt SQL"
            )

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

    try:
        with TestClient(segundo_aplicacion) as segundo_navegador:
            iniciar_sesion_cliente(segundo_navegador, "bruno@example.test")
            # Observa el SQL real después de que la autenticación haya emitido las dos
            # sesiones de cliente.
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
                        escenario.primero.post,
                        "/api/me/reservations",
                        json=escenario.contenido_envio(),
                    )
                    assert primero_tiene_bloqueo.wait(timeout=5), (
                        "First customer did not acquire lock"
                    )
                    segundo = ejecutor.submit(
                        segundo_navegador.post,
                        "/api/me/reservations",
                        json=escenario.contenido_envio(),
                    )
                    respuestas = [primero.result(timeout=10), segundo.result(timeout=10)]
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
        assert [respuesta.status_code for respuesta in respuestas] == [201, 409]
        assert "consulta la disponibilidad" in respuestas[1].json()["detail"]
        assert "retry-after" not in respuestas[1].headers
        assert primero_conexiones and segundo_conexiones
        assert primero_conexiones.isdisjoint(segundo_conexiones)
        with aplicacion.state.fabrica_sesiones() as sesion:
            reservas = sesion.scalars(select(Reserva)).all()
            assert len(reservas) == 1
            reserva = reservas[0]
            assert reserva.estado == "confirmed"
            assert reserva.id_usuario_cliente == escenario.primero_id
            assert reserva.nombre_cliente == "Alicia Prueba"
            assert reserva.correo_cliente == "alicia@example.test"
        assert escenario.segundo.get("/api/me/reservations").json() == []
    finally:
        segundo_aplicacion.state.motor.dispose()


@pytest.mark.parametrize("operacion", ["create", "cancel"])
def test_negocio_dia_es_lectura_despues_esperando_para_la_sqlite_escritura_bloqueo(
    aplicacion: FastAPI, ajustes: Configuracion, cliente_escenario: ClienteEscenario, operacion: str
) -> None:
    escenario = cliente_escenario
    existentes = escenario.crear() if operacion == "cancel" else None
    url = (
        f"/api/me/reservations/{existentes['id']}/cancel"
        if existentes is not None
        else "/api/me/reservations"
    )
    segundo_aplicacion = crear_aplicacion(ajustes)
    dia = [date(2026, 11, 9)]
    solicitado_dias: list[date] = []

    def negocio_dia() -> date:
        solicitado_dias.append(dia[0])
        return dia[0]

    segundo_aplicacion.dependency_overrides[obtener_hoy_proveedor] = lambda: negocio_dia
    intentado_escritura = Event()

    def observar_escritura(_conexion, _cursor, sentencia, _parametros, _context, _executemany):
        if sentencia.strip().upper() == "BEGIN IMMEDIATE":
            intentado_escritura.set()

    try:
        with TestClient(segundo_aplicacion) as navegador:
            iniciar_sesion_cliente(navegador, "alicia@example.test")
            with aplicacion.state.motor.connect() as bloqueo_propietario:
                bloqueo_propietario.exec_driver_sql("BEGIN IMMEDIATE")
                event.listen(
                    segundo_aplicacion.state.motor, "before_cursor_execute", observar_escritura
                )
                try:
                    with ThreadPoolExecutor(max_workers=1) as ejecutor:
                        pendiente = ejecutor.submit(
                            navegador.post,
                            url,
                            json=escenario.contenido_envio() if operacion == "create" else {},
                        )
                        assert intentado_escritura.wait(timeout=5), "Customer did not attempt SQL"
                        assert solicitado_dias == []
                        # Comienza un nuevo día en Madrid mientras la
                        # solicitud HTTP espera a SQLite.
                        dia[0] = date(2026, 11, 11)
                        bloqueo_propietario.rollback()
                        respuesta = pendiente.result(timeout=10)
                finally:
                    event.remove(
                        segundo_aplicacion.state.motor, "before_cursor_execute", observar_escritura
                    )
        assert respuesta.status_code == 409, respuesta.text
        assert solicitado_dias == [date(2026, 11, 11)]
        with aplicacion.state.fabrica_sesiones() as sesion:
            reservas = sesion.scalars(select(Reserva)).all()
            assert len(reservas) == (1 if operacion == "cancel" else 0)
            if reservas:
                assert reservas[0].estado == "confirmed"
    finally:
        segundo_aplicacion.state.motor.dispose()
