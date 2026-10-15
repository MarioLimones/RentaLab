from concurrent.futures import ThreadPoolExecutor
from datetime import date
from threading import Event

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event, select
from test_cuenta_reservas import HOY, ClienteEscenario, iniciar_sesion_cliente
from test_cuenta_reservas import cliente_escenario as cliente_escenario

from rentalab.base_datos import SQLITE_ENTERO_MAXIMO
from rentalab.compatibilidad import alias_json
from rentalab.configuracion import Configuracion
from rentalab.principal import crear_aplicacion
from rentalab.reloj import obtener_hoy_proveedor
from rentalab.reservas.modelos import Reserva

CONJUNTO_URL = "/api/me/reservations/batch"


@pytest.fixture
def productos(cliente_escenario: ClienteEscenario, equipo_contenido_envio: dict) -> list[int]:
    ids = [cliente_escenario.id_equipo]
    for numero, nombre in [(2, "Trípode de prueba"), (3, "Micrófono de prueba")]:
        creados = cliente_escenario.administrador_http.post(
            "/api/equipment",
            json={**equipo_contenido_envio, "code": f"PROD-{numero}", "name": nombre},
        )
        assert creados.status_code == 201, creados.text
        ids.append(creados.json()["id"])
    return ids


def conjunto_contenido_envio(productos: list[int], **cambios: object) -> dict:
    return {
        "equipment_ids": productos,
        "start_date": "2026-11-10",
        "end_date": "2026-11-12",
        **{alias_json(clave): valor for clave, valor in cambios.items()},
    }


def test_conjunto_asigna_unidades_y_servidor_identidad_con_una_escritura_transaccion(
    aplicacion: FastAPI,
    cliente_escenario: ClienteEscenario,
    productos: list[int],
    equipo_contenido_envio: dict,
) -> None:
    escenario = cliente_escenario
    hermana = escenario.administrador_http.post(
        "/api/equipment", json={**equipo_contenido_envio, "code": "CAM-002"}
    ).json()["id"]
    escenario.crear(escenario.segundo)
    statements = []

    def observar(_conexion, _cursor, sentencia, _parametros, _context, _executemany):
        statements.append(sentencia.strip().upper())

    event.listen(aplicacion.state.motor, "before_cursor_execute", observar)
    try:
        respuesta = escenario.primero.post(CONJUNTO_URL, json=conjunto_contenido_envio(productos))
    finally:
        event.remove(aplicacion.state.motor, "before_cursor_execute", observar)
    assert respuesta.status_code == 201, respuesta.text
    real = respuesta.json()
    assert statements.count("BEGIN IMMEDIATE") == 1
    assert respuesta.headers["location"] == "/api/me/reservations"
    assert respuesta.headers["cache-control"] == "no-store"
    assert [fila["equipment_id"] for fila in real] == [hermana, *productos[1:]]
    for fila in real:
        assert fila == {
            "id": fila["id"],
            "equipment_id": fila["equipment_id"],
            "start_date": "2026-11-10",
            "end_date": "2026-11-12",
            "status": "confirmed",
        }
    assert escenario.primero.get("/api/me/reservations").json() == real
    with aplicacion.state.fabrica_sesiones() as sesion:
        filas = sesion.scalars(
            select(Reserva).where(Reserva.id_usuario_cliente == escenario.primero_id)
        ).all()
        assert len(filas) == 3
        assert all(fila.origen == "portal" for fila in filas)
        assert all(fila.nombre_cliente == "Alicia Prueba" for fila in filas)
        assert all(fila.correo_cliente == "alicia@example.test" for fila in filas)
        assert all(fila.referencia_externa is None for fila in filas)


@pytest.mark.parametrize("no_disponible", ["overlap", "blocking_incident", "inactive", "missing"])
def test_no_disponible_intermedio_producto_nunca_deja_parcial_reservas(
    aplicacion: FastAPI,
    cliente_escenario: ClienteEscenario,
    productos: list[int],
    no_disponible: str,
) -> None:
    escenario = cliente_escenario
    if no_disponible == "overlap":
        escenario.crear(escenario.segundo, equipment_id=productos[1])
    elif no_disponible == "blocking_incident":
        incidencia = escenario.administrador_http.post(
            "/api/incidents",
            json={"equipment_id": productos[1], "title": "PRIVATE-MAINTENANCE", "blocking": True},
        )
        assert incidencia.status_code == 201, incidencia.text
    elif no_disponible == "inactive":
        assert (
            escenario.administrador_http.patch(
                f"/api/equipment/{productos[1]}", json={"active": False}
            ).status_code
            == 200
        )
    else:
        productos[1] = 999999
    antes = escenario.administrador_http.get("/api/reservations").json()
    respuesta = escenario.primero.post(CONJUNTO_URL, json=conjunto_contenido_envio(productos))
    assert respuesta.status_code == (404 if no_disponible == "missing" else 409), respuesta.text
    assert "PRIVATE" not in respuesta.text
    assert "blocking" not in respuesta.text
    if no_disponible != "missing":
        assert "no se ha creado ninguna reserva" in respuesta.json()["detail"]
    assert escenario.primero.get("/api/me/reservations").json() == []
    assert escenario.administrador_http.get("/api/reservations").json() == antes
    with aplicacion.state.fabrica_sesiones() as sesion:
        assert len(sesion.scalars(select(Reserva)).all()) == len(antes)


def test_producto_alias_son_rechazadas_antes_escribiendo(
    cliente_escenario: ClienteEscenario, equipo_contenido_envio: dict
) -> None:
    escenario = cliente_escenario
    alias = escenario.administrador_http.post(
        "/api/equipment",
        json={
            **equipo_contenido_envio,
            "code": "CAM-ALIAS",
            "name": "  CÁMARA DE PRUEBA  ",
            "category": "  CÁMARAS  ",
        },
    ).json()["id"]
    respuesta = escenario.primero.post(
        CONJUNTO_URL, json=conjunto_contenido_envio([escenario.id_equipo, alias])
    )
    assert respuesta.status_code == 409, respuesta.text
    assert "una sola vez" in respuesta.json()["detail"]
    assert escenario.administrador_http.get("/api/reservations").json() == []


@pytest.mark.parametrize(
    "invalido_ids",
    [
        [],
        [0],
        [-1],
        [True],
        [1.0],
        ["1"],
        [None],
        [SQLITE_ENTERO_MAXIMO + 1],
        [1, 1],
        list(range(1, 52)),
    ],
)
def test_conjunto_requiere_una_a_cincuenta_distintos_estrictos_positivo_ids(
    cliente_escenario: ClienteEscenario, invalido_ids: list
) -> None:
    escenario = cliente_escenario
    respuesta = escenario.primero.post(CONJUNTO_URL, json=conjunto_contenido_envio(invalido_ids))
    assert respuesta.status_code == 422, respuesta.text
    assert escenario.administrador_http.get("/api/reservations").json() == []


@pytest.mark.parametrize(
    "adicional",
    [
        {"customer_user_id": 2},
        {"customer_name": "Falsa identidad"},
        {"customer_email": "bruno@example.test"},
        {"status": "cancelled"},
        {"origin": "csv"},
        {"external_reference": "PRIVATE-REFERENCE"},
        {"equipment_id": 1},
    ],
)
def test_conjunto_rechaza_identidad_y_administrativa_campos(
    cliente_escenario: ClienteEscenario, productos: list[int], adicional: dict
) -> None:
    escenario = cliente_escenario
    respuesta = escenario.primero.post(
        CONJUNTO_URL, json=conjunto_contenido_envio(productos, **adicional)
    )
    assert respuesta.status_code == 422, respuesta.text
    assert escenario.administrador_http.get("/api/reservations").json() == []


@pytest.mark.parametrize(
    "cambios,esperado",
    [
        ({"start_date": "2026-10-14", "end_date": "2026-10-16"}, 409),
        ({"end_date": "2026-11-10"}, 422),
        ({"start_date": "2026-11-10T00:00:00"}, 422),
        ({"start_date": 0}, 422),
        ({"end_date": "2026-02-30"}, 422),
    ],
)
def test_conjunto_rechaza_pasado_o_invalido_compartido_fechas(
    cliente_escenario: ClienteEscenario, productos: list[int], cambios: dict, esperado: int
) -> None:
    respuesta = cliente_escenario.primero.post(
        CONJUNTO_URL, json=conjunto_contenido_envio(productos, **cambios)
    )
    assert respuesta.status_code == esperado, respuesta.text
    assert cliente_escenario.administrador_http.get("/api/reservations").json() == []


def test_conjunto_permite_hoy_y_adyacentes_reservas(
    cliente_escenario: ClienteEscenario, productos: list[int]
) -> None:
    escenario = cliente_escenario
    primero = escenario.primero.post(
        CONJUNTO_URL,
        json=conjunto_contenido_envio(
            productos, fecha_inicio=HOY.isoformat(), fecha_fin="2026-11-10"
        ),
    )
    assert primero.status_code == 201, primero.text
    adyacentes = escenario.segundo.post(CONJUNTO_URL, json=conjunto_contenido_envio(productos))
    assert adyacentes.status_code == 201, adyacentes.text


def test_conjunto_requiere_cliente_sesion_y_csrf(
    aplicacion: FastAPI, cliente_escenario: ClienteEscenario, productos: list[int]
) -> None:
    escenario = cliente_escenario
    with TestClient(aplicacion) as visitante:
        assert (
            visitante.post(CONJUNTO_URL, json=conjunto_contenido_envio(productos)).status_code
            == 401
        )
    assert (
        escenario.administrador_http.post(
            CONJUNTO_URL, json=conjunto_contenido_envio(productos)
        ).status_code
        == 403
    )
    original = escenario.primero.headers.pop("X-CSRF-Token")
    try:
        assert (
            escenario.primero.post(
                CONJUNTO_URL, json=conjunto_contenido_envio(productos)
            ).status_code
            == 403
        )
        escenario.primero.headers["X-CSRF-Token"] = "wrong-csrf"
        assert (
            escenario.primero.post(
                CONJUNTO_URL, json=conjunto_contenido_envio(productos)
            ).status_code
            == 403
        )
    finally:
        escenario.primero.headers["X-CSRF-Token"] = original
    assert escenario.administrador_http.get("/api/reservations").json() == []


@pytest.mark.parametrize("competidor", ["customer", "admin"])
@pytest.mark.parametrize("conjunto_primero", [False, True])
def test_solicitudes_conjuntas_e_individuales_se_serializan_sin_escrituras_parciales(
    aplicacion: FastAPI,
    ajustes: Configuracion,
    cliente_escenario: ClienteEscenario,
    productos: list[int],
    competidor: str,
    conjunto_primero: bool,
) -> None:
    escenario = cliente_escenario
    segundo_aplicacion = crear_aplicacion(ajustes)
    segundo_aplicacion.dependency_overrides[obtener_hoy_proveedor] = lambda: lambda: HOY
    primero_tiene_bloqueo, segundo_intentado_escritura = Event(), Event()

    def mantener_primero_escritura(
        _conexion, _cursor, sentencia, _parametros, _context, _executemany
    ):
        if sentencia.strip().upper() == "BEGIN IMMEDIATE":
            primero_tiene_bloqueo.set()
            assert segundo_intentado_escritura.wait(timeout=5), (
                "Competing write did not attempt SQL"
            )

    def observar_segundo_escritura(
        _conexion, _cursor, sentencia, _parametros, _context, _executemany
    ):
        if sentencia.strip().upper() == "BEGIN IMMEDIATE":
            segundo_intentado_escritura.set()

    individual_url = "/api/me/reservations" if competidor == "customer" else "/api/reservations"
    individual_datos = escenario.contenido_envio(id_equipo=productos[1])
    if competidor == "admin":
        individual_datos.update(
            customer_name="Cliente administrativo", customer_email="booking@example.test"
        )
    primero_navegador = (
        escenario.primero
        if conjunto_primero or competidor == "customer"
        else escenario.administrador_http
    )
    try:
        with TestClient(segundo_aplicacion) as segundo_navegador:
            iniciar_sesion_cliente(
                segundo_navegador,
                "admin-phase-c@example.test"
                if conjunto_primero and competidor == "admin"
                else "bruno@example.test",
            )
            event.listen(aplicacion.state.motor, "after_cursor_execute", mantener_primero_escritura)
            event.listen(
                segundo_aplicacion.state.motor, "before_cursor_execute", observar_segundo_escritura
            )
            try:
                with ThreadPoolExecutor(max_workers=2) as ejecutor:
                    primero = ejecutor.submit(
                        primero_navegador.post,
                        CONJUNTO_URL if conjunto_primero else individual_url,
                        json=conjunto_contenido_envio(productos)
                        if conjunto_primero
                        else individual_datos,
                    )
                    assert primero_tiene_bloqueo.wait(timeout=5), (
                        "First request did not acquire lock"
                    )
                    segundo = ejecutor.submit(
                        segundo_navegador.post,
                        individual_url if conjunto_primero else CONJUNTO_URL,
                        json=individual_datos
                        if conjunto_primero
                        else conjunto_contenido_envio(productos),
                    )
                    respuestas = [primero.result(timeout=10), segundo.result(timeout=10)]
            finally:
                event.remove(
                    aplicacion.state.motor, "after_cursor_execute", mantener_primero_escritura
                )
                event.remove(
                    segundo_aplicacion.state.motor,
                    "before_cursor_execute",
                    observar_segundo_escritura,
                )
        assert [respuesta.status_code for respuesta in respuestas] == [201, 409]
        with aplicacion.state.fabrica_sesiones() as sesion:
            filas = sesion.scalars(select(Reserva)).all()
            assert len(filas) == (3 if conjunto_primero else 1)
            assert {fila.id_equipo for fila in filas} == (
                set(productos) if conjunto_primero else {productos[1]}
            )
            assert all(fila.estado == "confirmed" for fila in filas)
    finally:
        segundo_aplicacion.state.motor.dispose()


def test_conjunto_lecturas_negocio_dia_despues_adquiriendo_bloqueo(
    aplicacion: FastAPI,
    ajustes: Configuracion,
    cliente_escenario: ClienteEscenario,
    productos: list[int],
) -> None:
    segundo_aplicacion = crear_aplicacion(ajustes)
    dia = [date(2026, 11, 9)]
    solicitado_dias: list[date] = []
    intentado_escritura = Event()

    def negocio_dia() -> date:
        solicitado_dias.append(dia[0])
        return dia[0]

    def observar_escritura(_conexion, _cursor, sentencia, _parametros, _context, _executemany):
        if sentencia.strip().upper() == "BEGIN IMMEDIATE":
            intentado_escritura.set()

    segundo_aplicacion.dependency_overrides[obtener_hoy_proveedor] = lambda: negocio_dia
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
                            navegador.post, CONJUNTO_URL, json=conjunto_contenido_envio(productos)
                        )
                        assert intentado_escritura.wait(timeout=5), "Batch did not attempt SQL"
                        assert solicitado_dias == []
                        dia[0] = date(2026, 11, 11)
                        bloqueo_propietario.rollback()
                        respuesta = pendiente.result(timeout=10)
                finally:
                    event.remove(
                        segundo_aplicacion.state.motor, "before_cursor_execute", observar_escritura
                    )
        assert respuesta.status_code == 409, respuesta.text
        assert solicitado_dias == [date(2026, 11, 11)]
        assert cliente_escenario.administrador_http.get("/api/reservations").json() == []
    finally:
        segundo_aplicacion.state.motor.dispose()
