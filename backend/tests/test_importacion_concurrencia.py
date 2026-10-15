from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from conftest import autenticar
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event, text
from sqlalchemy.engine import Connection, ExceptionContext, ExecutionContext

from rentalab.configuracion import Configuracion
from rentalab.principal import crear_aplicacion

CABECERA = "external_reference,customer_name,customer_email,equipment_code,starts_on,ends_on\n"


@pytest.mark.parametrize("cambiados_datos", [False, True])
def test_simultaneos_importaciones_con_la_mismo_referencia_son_atomico_y_idempotente(
    aplicacion: FastAPI,
    cliente_http: TestClient,
    ajustes: Configuracion,
    equipo_contenido_envio: dict[str, object],
    cambiados_datos: bool,
) -> None:
    assert cliente_http.post("/api/equipment", json=equipo_contenido_envio).status_code == 201
    primero_contenido = (
        CABECERA + "ORDER-1,Cliente ficticio,cliente@example.test,CAM-001,2026-11-10,2026-11-12\n"
    ).encode()
    segundo_contenido = (
        CABECERA
        + (
            "ORDER-1,Otro cliente,cliente@example.test,CAM-001,2026-11-10,2026-11-12\n"
            if cambiados_datos
            else "ORDER-1,Cliente ficticio,cliente@example.test,CAM-001,2026-11-10,2026-11-12\n"
        )
    ).encode()
    segundo_aplicacion = crear_aplicacion(ajustes)
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
                "Second importer never attempted SQL"
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

    segundo_cliente = TestClient(segundo_aplicacion)
    autenticar(segundo_cliente)
    event.listen(aplicacion.state.motor, "checkout", observar_primero_conexion)
    event.listen(segundo_aplicacion.state.motor, "checkout", observar_segundo_conexion)
    event.listen(aplicacion.state.motor, "after_cursor_execute", mantener_primero_escritura_bloqueo)
    event.listen(
        segundo_aplicacion.state.motor, "before_cursor_execute", observar_segundo_escritura_intento
    )
    try:
        with segundo_cliente, ThreadPoolExecutor(max_workers=2) as ejecutor:
            primero = ejecutor.submit(
                cliente_http.post,
                "/api/imports",
                files={"file": ("orders.csv", primero_contenido, "text/csv")},
            )
            assert primero_tiene_bloqueo.wait(timeout=5), "Import did not acquire SQLite write lock"
            segundo = ejecutor.submit(
                segundo_cliente.post,
                "/api/imports",
                files={"file": ("orders.csv", segundo_contenido, "text/csv")},
            )
            primero_respuesta = primero.result(timeout=10)
            segundo_respuesta = segundo.result(timeout=10)
        assert primero_respuesta.status_code == segundo_respuesta.status_code == 200
        primero_informe = primero_respuesta.json()
        segundo_informe = segundo_respuesta.json()
        assert primero_informe["totals"] == {
            "total": 1,
            "accepted": 1,
            "already_imported": 0,
            "rejected": 0,
        }
        if cambiados_datos:
            assert segundo_informe["totals"] == {
                "total": 1,
                "accepted": 0,
                "already_imported": 0,
                "rejected": 1,
            }
            assert segundo_informe["rows"][0]["reservation"] is None
        else:
            assert segundo_informe["totals"] == {
                "total": 1,
                "accepted": 0,
                "already_imported": 1,
                "rejected": 0,
            }
            assert (
                primero_informe["rows"][0]["reservation"]
                == segundo_informe["rows"][0]["reservation"]
            )
        assert primero_conexiones and segundo_conexiones
        assert primero_conexiones.isdisjoint(segundo_conexiones)
        assert cliente_http.get("/api/reservations").json() == [
            primero_informe["rows"][0]["reservation"]
        ]
        with aplicacion.state.motor.connect() as conexion:
            contar = conexion.scalar(text("SELECT COUNT(*) FROM reservations"))
        assert contar == 1
    finally:
        event.remove(aplicacion.state.motor, "checkout", observar_primero_conexion)
        event.remove(segundo_aplicacion.state.motor, "checkout", observar_segundo_conexion)
        event.remove(
            aplicacion.state.motor, "after_cursor_execute", mantener_primero_escritura_bloqueo
        )
        event.remove(
            segundo_aplicacion.state.motor,
            "before_cursor_execute",
            observar_segundo_escritura_intento,
        )
        segundo_aplicacion.state.motor.dispose()


def test_a_ocupado_fila_es_rechazadas_y_la_siguiente_fila_usa_a_limpia_transaccion(
    aplicacion: FastAPI,
    cliente_http: TestClient,
    ajustes: Configuracion,
    equipo_contenido_envio: dict[str, object],
) -> None:
    assert cliente_http.post("/api/equipment", json=equipo_contenido_envio).status_code == 201
    contenido = (
        CABECERA
        + "BUSY-ROW,Cliente ficticio,cliente@example.test,CAM-001,2026-11-10,2026-11-12\n"
        + "NEXT-ROW,Cliente ficticio,cliente@example.test,CAM-001,2026-11-10,2026-11-12\n"
    ).encode()
    segundo_aplicacion = crear_aplicacion(
        ajustes.model_copy(update={"espera_sqlite_ocupado_ms": 25})
    )
    primero_fallido = Event()
    try:
        with (
            TestClient(segundo_aplicacion) as segundo_cliente,
            aplicacion.state.motor.connect() as bloqueo_propietario,
        ):
            autenticar(segundo_cliente)
            bloqueo_propietario.exec_driver_sql("BEGIN IMMEDIATE")

            def liberar_bloqueo_despues_primero_ocupado(context: ExceptionContext) -> None:
                if (context.statement or "").strip().upper() == "BEGIN IMMEDIATE":
                    assert not primero_fallido.is_set()
                    assert getattr(context.original_exception, "sqlite_errorcode", 0) & 0xFF == 5
                    bloqueo_propietario.rollback()
                    primero_fallido.set()

            event.listen(
                segundo_aplicacion.state.motor,
                "handle_error",
                liberar_bloqueo_despues_primero_ocupado,
            )
            try:
                respuesta = segundo_cliente.post(
                    "/api/imports", files={"file": ("orders.csv", contenido, "text/csv")}
                )
            finally:
                event.remove(
                    segundo_aplicacion.state.motor,
                    "handle_error",
                    liberar_bloqueo_despues_primero_ocupado,
                )
            assert primero_fallido.is_set(), "No real SQLite busy error was observed"
            assert respuesta.status_code == 200
            informe = respuesta.json()
            assert informe["totals"] == {
                "total": 2,
                "accepted": 1,
                "already_imported": 0,
                "rejected": 1,
            }
            assert [fila["status"] for fila in informe["rows"]] == ["rejected", "accepted"]
            assert informe["rows"][0]["reservation"] is None
            assert isinstance(informe["rows"][0]["message"], str)
            reservas = cliente_http.get("/api/reservations").json()
            assert len(reservas) == 1
            assert reservas[0]["external_reference"] == "NEXT-ROW"
    finally:
        segundo_aplicacion.state.motor.dispose()
