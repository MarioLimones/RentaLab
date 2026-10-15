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


@pytest.mark.parametrize("incidencia_primero", [True, False])
def test_incidencia_y_reserva_uso_la_mismo_sqlite_escritura_serializacion(
    aplicacion: FastAPI,
    cliente_http: TestClient,
    ajustes: Configuracion,
    equipo_contenido_envio: dict[str, object],
    incidencia_primero: bool,
) -> None:
    """
    Los dos órdenes de escritura producen un resultado observable y coherente entre
    conexiones reales.
    """
    equipo = cliente_http.post("/api/equipment", json=equipo_contenido_envio).json()
    incidencia_contenido_envio = {
        "equipment_id": equipo["id"],
        "title": "Incidencia bloqueante ficticia",
        "blocking": True,
    }
    reserva_contenido_envio = {
        "equipment_id": equipo["id"],
        "customer_name": "Cliente ficticio",
        "customer_email": "concurrency@example.test",
        "start_date": "2026-11-10",
        "end_date": "2026-11-12",
    }
    primero_url = "/api/incidents" if incidencia_primero else "/api/reservations"
    segundo_url = "/api/reservations" if incidencia_primero else "/api/incidents"
    primero_contenido_envio = (
        incidencia_contenido_envio if incidencia_primero else reserva_contenido_envio
    )
    segundo_contenido_envio = (
        reserva_contenido_envio if incidencia_primero else incidencia_contenido_envio
    )
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
                "The other writer never attempted SQL"
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
            primero = ejecutor.submit(cliente_http.post, primero_url, json=primero_contenido_envio)
            assert primero_tiene_bloqueo.wait(timeout=5), (
                "The first writer did not acquire its lock"
            )
            segundo = ejecutor.submit(
                segundo_cliente.post, segundo_url, json=segundo_contenido_envio
            )
            primero_respuesta = primero.result(timeout=10)
            segundo_respuesta = segundo.result(timeout=10)
        assert primero_respuesta.status_code == 201
        assert primero_conexiones and segundo_conexiones
        assert primero_conexiones.isdisjoint(segundo_conexiones)
        with aplicacion.state.motor.connect() as conexion:
            incidencia_contar = conexion.scalar(text("SELECT COUNT(*) FROM incidents"))
            reserva_contar = conexion.scalar(text("SELECT COUNT(*) FROM reservations"))
        assert incidencia_contar == 1
        if incidencia_primero:
            assert segundo_respuesta.status_code == 409
            assert "retry-after" not in segundo_respuesta.headers
            assert reserva_contar == 0
            assert cliente_http.get("/api/reservations").json() == []
        else:
            assert segundo_respuesta.status_code == 201
            assert reserva_contar == 1
            assert segundo_respuesta.json()["confirmed_reservation_ids"] == [
                primero_respuesta.json()["id"]
            ]
            assert isinstance(segundo_respuesta.json()["warning"], str)
            assert cliente_http.get("/api/reservations").json() == [primero_respuesta.json()]
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


@pytest.mark.parametrize("operacion", ["create", "status"])
def test_ocupado_incidencia_escrituras_devolver_a_temporal_fallo_y_dejar_sin_parcial_cambios(
    aplicacion: FastAPI,
    cliente_http: TestClient,
    ajustes: Configuracion,
    equipo_contenido_envio: dict[str, object],
    operacion: str,
) -> None:
    equipo = cliente_http.post("/api/equipment", json=equipo_contenido_envio).json()
    incidencia_contenido_envio = {
        "equipment_id": equipo["id"],
        "title": "Incidencia ficticia",
        "blocking": True,
    }
    original: dict[str, object] | None = None
    if operacion == "status":
        respuesta = cliente_http.post("/api/incidents", json=incidencia_contenido_envio)
        assert respuesta.status_code == 201
        original = respuesta.json()
        url = f"/api/incidents/{original['id']}/status"
        cuerpo = {"status": "resolved", "resolution": "Reparación ficticia"}
        metodo = "patch"
    else:
        url = "/api/incidents"
        cuerpo = incidencia_contenido_envio
        metodo = "post"

    segundo_aplicacion = crear_aplicacion(
        ajustes.model_copy(update={"espera_sqlite_ocupado_ms": 25})
    )
    try:
        with TestClient(segundo_aplicacion) as segundo_cliente:
            autenticar(segundo_cliente)
            with aplicacion.state.motor.connect() as bloqueo_propietario:
                bloqueo_propietario.exec_driver_sql("BEGIN IMMEDIATE")
                respuesta = segundo_cliente.request(metodo, url, json=cuerpo)
                assert respuesta.status_code == 503
                assert respuesta.headers["retry-after"] == "1"
                assert isinstance(respuesta.json()["detail"], str)
                assert cliente_http.get("/api/incidents").json() == (
                    [original] if original is not None else []
                )
                bloqueo_propietario.rollback()
            reintentado = segundo_cliente.request(metodo, url, json=cuerpo)
            assert reintentado.status_code == (201 if operacion == "create" else 200)
            assert reintentado.json()["status"] == ("open" if operacion == "create" else "resolved")
            assert len(cliente_http.get("/api/incidents").json()) == 1
    finally:
        segundo_aplicacion.state.motor.dispose()


@pytest.mark.parametrize("operacion", ["create", "status"])
def test_lector_bloqueado_confirmar_revierte_regreso_incidencia_creacion_o_estado_cambiar(
    aplicacion: FastAPI,
    cliente_http: TestClient,
    ajustes: Configuracion,
    equipo_contenido_envio: dict[str, object],
    operacion: str,
) -> None:
    equipo = cliente_http.post("/api/equipment", json=equipo_contenido_envio).json()
    incidencia_contenido_envio = {"equipment_id": equipo["id"], "title": "Incidencia ficticia"}
    original: dict[str, object] | None = None
    if operacion == "status":
        respuesta = cliente_http.post("/api/incidents", json=incidencia_contenido_envio)
        assert respuesta.status_code == 201
        original = respuesta.json()
        url = f"/api/incidents/{original['id']}/status"
        cuerpo = {"status": "resolved", "resolution": "Reparación ficticia"}
        metodo = "patch"
    else:
        url = "/api/incidents"
        cuerpo = incidencia_contenido_envio
        metodo = "post"
    segundo_aplicacion = crear_aplicacion(
        ajustes.model_copy(update={"espera_sqlite_ocupado_ms": 25})
    )
    try:
        with TestClient(segundo_aplicacion) as segundo_cliente:
            autenticar(segundo_cliente)
            with aplicacion.state.motor.connect() as lector:
                lector.exec_driver_sql("BEGIN")
                lector.exec_driver_sql("SELECT id FROM equipment").all()
                respuesta = segundo_cliente.request(metodo, url, json=cuerpo)
                assert respuesta.status_code == 503
                assert respuesta.headers["retry-after"] == "1"
                assert cliente_http.get("/api/incidents").json() == (
                    [original] if original is not None else []
                )
                lector.rollback()
            reintentado = segundo_cliente.request(metodo, url, json=cuerpo)
            assert reintentado.status_code == (201 if operacion == "create" else 200)
            assert len(cliente_http.get("/api/incidents").json()) == 1
    finally:
        segundo_aplicacion.state.motor.dispose()
