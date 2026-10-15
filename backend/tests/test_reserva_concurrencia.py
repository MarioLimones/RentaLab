from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from conftest import autenticar
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event, text
from sqlalchemy.engine import Connection, ExecutionContext

from rentalab.configuracion import Configuracion
from rentalab.principal import crear_aplicacion


def test_dos_conexiones_no_puede_confirmar_incompatibles_reservas(
    aplicacion: FastAPI,
    cliente_http: TestClient,
    ajustes: Configuracion,
    equipo_contenido_envio: dict[str, object],
) -> None:
    """Fuerza a la segunda conexión a intentar escribir mientras la primera mantiene el bloqueo."""
    equipo = cliente_http.post("/api/equipment", json=equipo_contenido_envio).json()
    contenido_envio = {
        "equipment_id": equipo["id"],
        "customer_name": "Cliente de concurrencia ficticio",
        "customer_email": "concurrency@example.test",
        "start_date": "2026-11-10",
        "end_date": "2026-11-12",
    }
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
                "The second writer never attempted SQL"
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
            primero = ejecutor.submit(cliente_http.post, "/api/reservations", json=contenido_envio)
            assert primero_tiene_bloqueo.wait(timeout=5), (
                "Creation did not acquire a SQLite write lock"
            )
            segundo = ejecutor.submit(
                segundo_cliente.post, "/api/reservations", json=contenido_envio
            )
            respuestas = [primero.result(timeout=10), segundo.result(timeout=10)]
        assert sorted(respuesta.status_code for respuesta in respuestas) == [201, 409]
        conflicto = next(respuesta for respuesta in respuestas if respuesta.status_code == 409)
        assert "retry-after" not in conflicto.headers
        assert "reserva confirmada" in conflicto.json()["detail"]
        assert primero_conexiones and segundo_conexiones
        assert primero_conexiones.isdisjoint(segundo_conexiones)
        with aplicacion.state.motor.connect() as conexion:
            confirmadas = conexion.scalar(
                text("SELECT COUNT(*) FROM reservations WHERE status = 'confirmed'")
            )
        assert confirmadas == 1
        reservas = cliente_http.get("/api/reservations").json()
        assert len(reservas) == 1
        assert reservas[0]["status"] == "confirmed"
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


@pytest.mark.parametrize("operacion", ["create", "cancel"])
def test_sqlite_ocupado_responde_controladamente_y_permite_reintentar_tras_desbloqueo(
    aplicacion: FastAPI,
    cliente_http: TestClient,
    ajustes: Configuracion,
    equipo_contenido_envio: dict[str, object],
    operacion: str,
) -> None:
    equipo = cliente_http.post("/api/equipment", json=equipo_contenido_envio).json()
    contenido_envio = {
        "equipment_id": equipo["id"],
        "customer_name": "Cliente ficticio",
        "customer_email": "busy@example.test",
        "start_date": "2026-11-10",
        "end_date": "2026-11-12",
    }
    original: dict[str, object] | None = None
    if operacion == "cancel":
        creados = cliente_http.post("/api/reservations", json=contenido_envio)
        assert creados.status_code == 201
        original = creados.json()
        url = f"/api/reservations/{original['id']}/cancel"
        solicitud_json = None
    else:
        url = "/api/reservations"
        solicitud_json = contenido_envio

    segundo_aplicacion = crear_aplicacion(
        ajustes.model_copy(update={"espera_sqlite_ocupado_ms": 25})
    )
    try:
        with TestClient(segundo_aplicacion) as segundo_cliente:
            autenticar(segundo_cliente)
            with aplicacion.state.motor.connect() as bloqueo_propietario:
                bloqueo_propietario.exec_driver_sql("BEGIN IMMEDIATE")
                respuesta = segundo_cliente.post(url, json=solicitud_json)
                assert respuesta.status_code == 503
                assert respuesta.headers["retry-after"] == "1"
                assert isinstance(respuesta.json()["detail"], str)
                assert cliente_http.get("/api/reservations").json() == (
                    [original] if original is not None else []
                )
                bloqueo_propietario.rollback()

            reintentado = segundo_cliente.post(url, json=solicitud_json)
            assert reintentado.status_code == (201 if operacion == "create" else 200)
            assert reintentado.json()["status"] == (
                "confirmed" if operacion == "create" else "cancelled"
            )
            assert len(cliente_http.get("/api/reservations").json()) == 1
    finally:
        segundo_aplicacion.state.motor.dispose()


def test_a_confirmar_bloqueado_por_a_lector_revierte_regreso_sin_creando_a_reserva(
    aplicacion: FastAPI,
    cliente_http: TestClient,
    ajustes: Configuracion,
    equipo_contenido_envio: dict[str, object],
) -> None:
    equipo = cliente_http.post("/api/equipment", json=equipo_contenido_envio).json()
    contenido_envio = {
        "equipment_id": equipo["id"],
        "customer_name": "Cliente ficticio",
        "customer_email": "reader@example.test",
        "start_date": "2026-11-10",
        "end_date": "2026-11-12",
    }
    segundo_aplicacion = crear_aplicacion(
        ajustes.model_copy(update={"espera_sqlite_ocupado_ms": 25})
    )
    try:
        with TestClient(segundo_aplicacion) as segundo_cliente:
            autenticar(segundo_cliente)
            with aplicacion.state.motor.connect() as lector:
                lector.exec_driver_sql("BEGIN")
                lector.exec_driver_sql("SELECT id FROM equipment").all()
                bloqueado = segundo_cliente.post("/api/reservations", json=contenido_envio)
                assert bloqueado.status_code == 503
                assert bloqueado.headers["retry-after"] == "1"
                assert cliente_http.get("/api/reservations").json() == []
                lector.rollback()
            reintentado = segundo_cliente.post("/api/reservations", json=contenido_envio)
            assert reintentado.status_code == 201
            assert len(cliente_http.get("/api/reservations").json()) == 1
    finally:
        segundo_aplicacion.state.motor.dispose()
