"""Repetir un intento de reserva individual nunca consume otra unidad tras perderse la respuesta."""

from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from threading import Event
from uuid import uuid4

import pytest
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event, inspect, select, text
from test_cuenta_reservas import HOY, ClienteEscenario, iniciar_sesion_cliente
from test_cuenta_reservas import cliente_escenario as cliente_escenario
from test_producto_reservas import segundo_unidad as segundo_unidad

from alembic import command
from rentalab.base_datos import crear_base_datos_motor
from rentalab.configuracion import Configuracion
from rentalab.principal import crear_aplicacion
from rentalab.reloj import obtener_hoy_proveedor
from rentalab.reservas.modelos import (
    ClienteReservaSolicitud,
    Reserva,
    ReservaSolicitudReserva,
)

URL = "/api/me/reservations"


def intencion() -> dict[str, str]:
    return {"Idempotency-Key": str(uuid4())}


def test_reintento_tras_perder_respuesta_y_reiniciar_recupera_unidad_original(
    aplicacion: FastAPI,
    ajustes: Configuracion,
    cliente_escenario: ClienteEscenario,
    segundo_unidad: int,
) -> None:
    escenario = cliente_escenario
    cabeceras = intencion()
    original = escenario.primero.post(URL, json=escenario.contenido_envio(), headers=cabeceras)
    assert original.status_code == 201, original.text
    # El primer cliente puede perder el resultado tras confirmar la transacción. Una nueva
    # aplicación o sesión debe recuperarlo
    # desde SQLite, sin depender de una caché en memoria ni de la unidad física que esté libre.
    recreada = crear_aplicacion(ajustes)
    recreada.dependency_overrides[obtener_hoy_proveedor] = lambda: lambda: HOY
    try:
        with TestClient(recreada) as navegador:
            iniciar_sesion_cliente(navegador, "alicia@example.test")
            recuperado = navegador.post(URL, json=escenario.contenido_envio(), headers=cabeceras)
            assert recuperado.status_code == 201, recuperado.text
            assert recuperado.json() == original.json()
            assert recuperado.headers["location"] == original.headers["location"]
            assert set(recuperado.json()) == {
                "id",
                "equipment_id",
                "start_date",
                "end_date",
                "status",
            }
            assert cabeceras["Idempotency-Key"] not in recuperado.text
        with aplicacion.state.fabrica_sesiones() as sesion:
            reservas = sesion.scalars(select(Reserva)).all()
            solicitudes = sesion.scalars(select(ClienteReservaSolicitud)).all()
            assert len(reservas) == len(solicitudes) == 1
            assert reservas[0].id_equipo == escenario.id_equipo
            assert solicitudes[0].elementos[0].id_equipo_solicitado == escenario.id_equipo
        assert segundo_unidad != original.json()["equipment_id"]
    finally:
        recreada.state.motor.dispose()


def test_original_solicitado_modelo_es_conservado_cuando_otra_fisica_unidad_es_asignado(
    aplicacion: FastAPI, cliente_escenario: ClienteEscenario, segundo_unidad: int
) -> None:
    escenario = cliente_escenario
    escenario.crear(escenario.segundo)
    cabeceras = intencion()
    respuesta = escenario.primero.post(URL, json=escenario.contenido_envio(), headers=cabeceras)
    assert respuesta.status_code == 201, respuesta.text
    assert respuesta.json()["equipment_id"] == segundo_unidad
    repetir = escenario.primero.post(URL, json=escenario.contenido_envio(), headers=cabeceras)
    assert repetir.status_code == 201
    assert repetir.json() == respuesta.json()
    # Un producto o alias distinto en la URL constituye otra solicitud aunque pertenezca al
    # mismo modelo.
    colision = escenario.primero.post(
        URL, json=escenario.contenido_envio(id_equipo=segundo_unidad), headers=cabeceras
    )
    assert colision.status_code == 409
    with aplicacion.state.fabrica_sesiones() as sesion:
        solicitud = sesion.scalars(select(ClienteReservaSolicitud)).one()
        assert solicitud.elementos[0].id_equipo_solicitado == escenario.id_equipo
        assert solicitud.elementos[0].id_reserva == respuesta.json()["id"]


@pytest.mark.parametrize("cambios", [{"start_date": "2026-11-09"}, {"end_date": "2026-11-13"}])
def test_reutilizando_cliente_clave_con_otro_fechas_es_a_conflicto_sin_adicional_escrituras(
    aplicacion: FastAPI, cliente_escenario: ClienteEscenario, cambios: dict[str, str]
) -> None:
    escenario = cliente_escenario
    cabeceras = intencion()
    original = escenario.primero.post(URL, json=escenario.contenido_envio(), headers=cabeceras)
    assert original.status_code == 201
    respuesta = escenario.primero.post(
        URL, json=escenario.contenido_envio(**cambios), headers=cabeceras
    )
    assert respuesta.status_code == 409
    assert "otros datos" in respuesta.json()["detail"]
    assert escenario.primero.get(URL).json() == [original.json()]
    with aplicacion.state.fabrica_sesiones() as sesion:
        assert len(sesion.scalars(select(ClienteReservaSolicitud)).all()) == 1


def test_claves_pertenecen_al_cliente_autenticado_y_son_independientes(
    aplicacion: FastAPI, cliente_escenario: ClienteEscenario, segundo_unidad: int
) -> None:
    escenario = cliente_escenario
    cabeceras = intencion()
    primero = escenario.primero.post(URL, json=escenario.contenido_envio(), headers=cabeceras)
    segundo = escenario.segundo.post(URL, json=escenario.contenido_envio(), headers=cabeceras)
    assert primero.status_code == segundo.status_code == 201
    assert primero.json()["id"] != segundo.json()["id"]
    assert segundo.json()["equipment_id"] == segundo_unidad
    for navegador, esperado in ((escenario.primero, primero), (escenario.segundo, segundo)):
        repetir = navegador.post(URL, json=escenario.contenido_envio(), headers=cabeceras)
        assert repetir.status_code == 201
        assert repetir.json() == esperado.json()
        assert navegador.get(URL).json() == [esperado.json()]
    assert escenario.primero.get(f"{URL}/{segundo.json()['id']}").status_code == 404
    with aplicacion.state.fabrica_sesiones() as sesion:
        assert len(sesion.scalars(select(ClienteReservaSolicitud)).all()) == 2


def test_explicito_nuevo_clave_puede_crear_a_separados_reserva_cuando_otra_unidad_es_libre(
    cliente_escenario: ClienteEscenario, segundo_unidad: int
) -> None:
    escenario = cliente_escenario
    primero = escenario.primero.post(URL, json=escenario.contenido_envio(), headers=intencion())
    segundo = escenario.primero.post(URL, json=escenario.contenido_envio(), headers=intencion())
    assert primero.status_code == segundo.status_code == 201
    assert primero.json()["id"] != segundo.json()["id"]
    assert segundo.json()["equipment_id"] == segundo_unidad


def test_solicitudes_sin_clave_conservan_comportamiento_sin_registrar_intentos(
    aplicacion: FastAPI, cliente_escenario: ClienteEscenario, segundo_unidad: int
) -> None:
    escenario = cliente_escenario
    primero = escenario.primero.post(URL, json=escenario.contenido_envio())
    segundo = escenario.primero.post(URL, json=escenario.contenido_envio())
    assert primero.status_code == segundo.status_code == 201
    assert primero.json()["id"] != segundo.json()["id"]
    assert segundo.json()["equipment_id"] == segundo_unidad
    with aplicacion.state.fabrica_sesiones() as sesion:
        assert sesion.scalars(select(ClienteReservaSolicitud)).all() == []


def test_repetir_preserva_real_canceladas_estado_incluso_despues_arranque_y_desactivacion(
    aplicacion: FastAPI, cliente_escenario: ClienteEscenario
) -> None:
    escenario = cliente_escenario
    cabeceras = intencion()
    original = escenario.primero.post(URL, json=escenario.contenido_envio(), headers=cabeceras)
    assert original.status_code == 201
    canceladas = escenario.primero.post(f"{URL}/{original.json()['id']}/cancel")
    assert canceladas.status_code == 200
    inactivo = escenario.administrador_http.patch(
        f"/api/equipment/{escenario.id_equipo}", json={"active": False}
    )
    assert inactivo.status_code == 200
    aplicacion.dependency_overrides[obtener_hoy_proveedor] = lambda: lambda: date(2026, 12, 1)
    repetir = escenario.primero.post(URL, json=escenario.contenido_envio(), headers=cabeceras)
    assert repetir.status_code == 201, repetir.text
    assert repetir.json() == canceladas.json()
    assert escenario.primero.get(URL).json() == [canceladas.json()]


def test_rechazadas_intento_hace_no_consumir_clave_y_posterior_reintentar_puede_tienen_exito(
    aplicacion: FastAPI, cliente_escenario: ClienteEscenario
) -> None:
    escenario = cliente_escenario
    ocupados = escenario.crear(escenario.segundo)
    cabeceras = intencion()
    assert (
        escenario.primero.post(URL, json=escenario.contenido_envio(), headers=cabeceras).status_code
        == 409
    )
    with aplicacion.state.fabrica_sesiones() as sesion:
        assert sesion.scalars(select(ClienteReservaSolicitud)).all() == []
    assert escenario.segundo.post(f"{URL}/{ocupados['id']}/cancel").status_code == 200
    respuesta = escenario.primero.post(URL, json=escenario.contenido_envio(), headers=cabeceras)
    assert respuesta.status_code == 201, respuesta.text
    assert (
        escenario.primero.post(URL, json=escenario.contenido_envio(), headers=cabeceras).json()
        == respuesta.json()
    )


@pytest.mark.parametrize(
    "clave", ["", "not-a-uuid", "x" * 100, "00000000-0000-0000-0000-00000000000z"]
)
def test_invalido_idempotencia_cabecera_es_422_sin_creando_registros(
    aplicacion: FastAPI, cliente_escenario: ClienteEscenario, clave: str
) -> None:
    escenario = cliente_escenario
    respuesta = escenario.primero.post(
        URL, json=escenario.contenido_envio(), headers={"Idempotency-Key": clave}
    )
    assert respuesta.status_code == 422
    assert escenario.primero.get(URL).json() == []
    with aplicacion.state.fabrica_sesiones() as sesion:
        assert sesion.scalars(select(ClienteReservaSolicitud)).all() == []


def test_cabecera_hace_no_reemplazar_autenticacion_autorizacion_o_csrf(
    aplicacion: FastAPI, cliente_escenario: ClienteEscenario
) -> None:
    escenario = cliente_escenario
    cabeceras = intencion()
    with TestClient(aplicacion) as visitante:
        assert (
            visitante.post(URL, json=escenario.contenido_envio(), headers=cabeceras).status_code
            == 401
        )
    assert (
        escenario.administrador_http.post(
            URL, json=escenario.contenido_envio(), headers=cabeceras
        ).status_code
        == 403
    )
    assert (
        escenario.primero.post(
            URL, json=escenario.contenido_envio(), headers={**cabeceras, "X-CSRF-Token": "wrong"}
        ).status_code
        == 403
    )
    assert escenario.primero.get(URL).json() == []


@pytest.mark.parametrize("operacion", ["single", "batch_one", "batch_multiple"])
def test_simultaneos_mismo_cliente_intentos_comparten_original_reservas_entre_aplicaciones(
    aplicacion: FastAPI,
    ajustes: Configuracion,
    cliente_escenario: ClienteEscenario,
    segundo_unidad: int,
    operacion: str,
) -> None:
    escenario = cliente_escenario
    solicitado_ids = [escenario.id_equipo]
    if operacion == "batch_multiple":
        for indice in range(2):
            equipo = escenario.administrador_http.post(
                "/api/equipment",
                json={"code": f"OTHER-{indice}", "name": "Otro modelo", "category": "Audio"},
            )
            assert equipo.status_code == 201
            if indice == 0:
                solicitado_ids.insert(0, equipo.json()["id"])
    url = URL if operacion == "single" else f"{URL}/batch"
    contenido_envio = (
        escenario.contenido_envio()
        if operacion == "single"
        else {
            "equipment_ids": solicitado_ids,
            "start_date": escenario.contenido_envio()["start_date"],
            "end_date": escenario.contenido_envio()["end_date"],
        }
    )
    otro_aplicacion = crear_aplicacion(ajustes)
    otro_aplicacion.dependency_overrides[obtener_hoy_proveedor] = lambda: lambda: HOY
    primero_tiene_bloqueo = Event()
    segundo_intentado = Event()
    cabeceras = intencion()

    def mantener_primero(_conexion, _cursor, sentencia, *_argumentos):
        if sentencia.strip().upper() == "BEGIN IMMEDIATE":
            primero_tiene_bloqueo.set()
            assert segundo_intentado.wait(timeout=5), "Second request did not attempt its write"

    def observar_segundo(_conexion, _cursor, sentencia, *_argumentos):
        if sentencia.strip().upper() == "BEGIN IMMEDIATE":
            segundo_intentado.set()

    try:
        with TestClient(otro_aplicacion) as navegador:
            iniciar_sesion_cliente(navegador, "alicia@example.test")
            event.listen(aplicacion.state.motor, "after_cursor_execute", mantener_primero)
            event.listen(otro_aplicacion.state.motor, "before_cursor_execute", observar_segundo)
            try:
                with ThreadPoolExecutor(max_workers=2) as ejecutor:
                    primero = ejecutor.submit(
                        escenario.primero.post, url, json=contenido_envio, headers=cabeceras
                    )
                    assert primero_tiene_bloqueo.wait(timeout=5)
                    segundo = ejecutor.submit(
                        navegador.post, url, json=contenido_envio, headers=cabeceras
                    )
                    respuestas = [primero.result(timeout=10), segundo.result(timeout=10)]
            finally:
                event.remove(aplicacion.state.motor, "after_cursor_execute", mantener_primero)
                event.remove(otro_aplicacion.state.motor, "before_cursor_execute", observar_segundo)
        assert [respuesta.status_code for respuesta in respuestas] == [201, 201]
        assert respuestas[0].json() == respuestas[1].json()
        with aplicacion.state.fabrica_sesiones() as sesion:
            assert len(sesion.scalars(select(Reserva)).all()) == len(solicitado_ids)
            assert len(sesion.scalars(select(ClienteReservaSolicitud)).all()) == 1
            assert len(sesion.scalars(select(ReservaSolicitudReserva)).all()) == len(solicitado_ids)
        resultado = respuestas[0].json()
        filas = [resultado] if isinstance(resultado, dict) else resultado
        assert [fila["equipment_id"] for fila in filas] == solicitado_ids
        assert all(fila["equipment_id"] != segundo_unidad for fila in filas)
    finally:
        otro_aplicacion.state.motor.dispose()


def test_reserva_solicitud_migracion_preserva_existentes_datos_y_revierte_correctamente(
    tmp_path: Path,
) -> None:
    servidor = Path(__file__).resolve().parents[1]
    configuracion = Config(str(servidor / "alembic.ini"))
    configuracion.set_main_option("script_location", str(servidor / "alembic"))
    url_base_datos = f"sqlite:///{(tmp_path / 'booking-requests-migration.sqlite3').as_posix()}"
    configuracion.set_main_option("sqlalchemy.url", url_base_datos)
    motor = crear_base_datos_motor(url_base_datos)
    try:
        with motor.begin() as conexion:
            configuracion.attributes["connection"] = conexion
            command.upgrade(configuracion, "0010_saved_products")
            for sentencia in (
                "INSERT INTO users (id,name,email,password_hash,role,active) "
                "VALUES (7,'Cliente previo','previous@example.test','test-hash','customer',1)",
                "INSERT INTO equipment (id,code,name,category,description,active) "
                "VALUES (41,'OLD-CAM','Equipo previo','Cámaras','Nota interna',0)",
                "INSERT INTO reservations (id,equipment_id,customer_user_id,customer_name,"
                "customer_email,start_date,end_date,status,external_reference,origin) "
                "VALUES (52,41,7,'Cliente previo','previous@example.test','2026-11-10',"
                "'2026-11-12','confirmed','HISTORICAL','portal')",
                "INSERT INTO incidents (id,equipment_id,author_user_id,title,description,"
                "blocking,status,resolution,reservation_id) "
                "VALUES (63,41,7,'Aviso previo','Prueba',0,'resolved','Reparada',52)",
                "INSERT INTO saved_products (customer_user_id,equipment_id) VALUES (7,41)",
            ):
                conexion.execute(text(sentencia))
            tablas = ("users", "equipment", "reservations", "incidents", "saved_products")

            def instantanea() -> dict:
                return {
                    tabla: list(conexion.execute(text(f"SELECT * FROM {tabla}")).mappings())
                    for tabla in tablas
                }

            antes = instantanea()
            command.upgrade(configuracion, "head")
            assert instantanea() == antes
            assert conexion.execute(text("SELECT * FROM booking_requests")).all() == []
            assert conexion.execute(text("SELECT * FROM booking_request_reservations")).all() == []
            conexion.execute(
                text(
                    "INSERT INTO booking_requests (customer_user_id,idempotency_key,"
                    "operation,start_date,end_date) "
                    "VALUES (7,:key,'single','2026-11-10','2026-11-12')"
                ),
                {"key": "49917cb0-8d1a-4d8c-aa46-59959a7e797a"},
            )
            conexion.execute(
                text(
                    "INSERT INTO booking_request_reservations (customer_user_id,idempotency_key,"
                    "position,requested_equipment_id,reservation_id) VALUES (7,:key,0,41,52)"
                ),
                {"key": "49917cb0-8d1a-4d8c-aa46-59959a7e797a"},
            )
            assert conexion.scalar(text("PRAGMA integrity_check")) == "ok"
            assert conexion.execute(text("PRAGMA foreign_key_check")).all() == []
            command.check(configuracion)
            command.downgrade(configuracion, "0010_saved_products")
            assert not inspect(conexion).has_table("booking_requests")
            assert not inspect(conexion).has_table("booking_request_reservations")
            assert instantanea() == antes
            command.upgrade(configuracion, "head")
            assert conexion.execute(text("SELECT * FROM booking_requests")).all() == []
            assert instantanea() == antes
    finally:
        motor.dispose()
