from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from pathlib import Path
from threading import Event
from typing import Any

import pytest
from alembic.config import Config
from conftest import PRUEBA_CONTRASENA, PRUEBA_CONTRASENA_HASH
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event, text
from sqlalchemy.engine import Connection, ExecutionContext
from sqlalchemy.exc import IntegrityError

from alembic import command
from rentalab.autenticacion.modelos import Usuario
from rentalab.base_datos import crear_base_datos_motor
from rentalab.configuracion import Configuracion
from rentalab.incidencias.modelos import Incidencia
from rentalab.principal import crear_aplicacion
from rentalab.reservas.modelos import Reserva

INFORME = {"title": "  Conector suelto  ", "description": "  Se desconecta al mover el cable.  "}
CLIENTE_CAMPOS = {"id", "reservation_id", "title", "description", "status", "public_response"}


def iniciar_sesion(navegador: TestClient, correo: str) -> None:
    csrf = navegador.get("/api/auth/csrf").json()["csrf_token"]
    respuesta = navegador.post(
        "/api/auth/login",
        json={"username": correo, "password": PRUEBA_CONTRASENA},
        headers={"X-CSRF-Token": csrf},
    )
    assert respuesta.status_code == 200, respuesta.text
    navegador.headers["X-CSRF-Token"] = navegador.get("/api/auth/csrf").json()["csrf_token"]


@pytest.fixture
def actores(aplicacion: FastAPI) -> Iterator[dict[str, Any]]:
    with aplicacion.state.fabrica_sesiones.begin() as sesion:
        cuentas = [
            Usuario(
                nombre=nombre,
                correo=correo,
                hash_contrasena=PRUEBA_CONTRASENA_HASH,
                rol=rol,
                activo=True,
            )
            for nombre, correo, rol in (
                ("Alicia Ficticia", "alicia@example.test", "customer"),
                ("Bruno Ficticio", "bruno@example.test", "customer"),
                ("Administración Ficticia", "admin@example.test", "admin"),
            )
        ]
        sesion.add_all(cuentas)
        sesion.flush()
        identificadores = [cuenta.id for cuenta in cuentas]
    with ExitStack() as pila:
        navegadores = [pila.enter_context(TestClient(aplicacion)) for _ in cuentas]
        for navegador, cuenta in zip(navegadores, cuentas, strict=True):
            iniciar_sesion(navegador, cuenta.correo)
        yield {
            "first": navegadores[0],
            "second": navegadores[1],
            "admin": navegadores[2],
            "first_id": identificadores[0],
            "second_id": identificadores[1],
            "admin_id": identificadores[2],
        }


@pytest.fixture
def propia_reserva(
    aplicacion: FastAPI, actores: dict[str, Any], equipo_contenido_envio: dict[str, object]
) -> dict[str, Any]:
    equipo = actores["admin"].post("/api/equipment", json=equipo_contenido_envio)
    assert equipo.status_code == 201
    respuesta = actores["admin"].post(
        "/api/reservations",
        json={
            "equipment_id": equipo.json()["id"],
            "customer_name": "Alicia Ficticia",
            "customer_email": "alicia@example.test",
            "start_date": "2030-11-10",
            "end_date": "2030-11-12",
        },
    )
    assert respuesta.status_code == 201, respuesta.text
    reserva = respuesta.json()
    # La preparación asigna un propietario histórico sin depender de la creación mediante /api/me.
    with aplicacion.state.fabrica_sesiones.begin() as sesion:
        sesion.get(Reserva, reserva["id"]).id_usuario_cliente = actores["first_id"]
    return reserva


def informe(actores: dict[str, Any], reserva: dict[str, Any]) -> dict[str, Any]:
    respuesta = actores["first"].post(
        f"/api/me/reservations/{reserva['id']}/incidents", json=INFORME
    )
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()


def test_cliente_informe_deduce_identidad_equipo_y_seguro_predeterminados(
    aplicacion: FastAPI, actores: dict[str, Any], propia_reserva: dict[str, Any]
) -> None:
    respuesta = actores["first"].post(
        f"/api/me/reservations/{propia_reserva['id']}/incidents", json=INFORME
    )
    assert respuesta.status_code == 201, respuesta.text
    incidencia = respuesta.json()
    assert incidencia == {
        "id": incidencia["id"],
        "reservation_id": propia_reserva["id"],
        "title": "Conector suelto",
        "description": "Se desconecta al mover el cable.",
        "status": "open",
        "public_response": "",
    }
    assert respuesta.headers["location"] == f"/api/me/incidents/{incidencia['id']}"
    assert actores["first"].get(respuesta.headers["location"]).json() == incidencia
    assert actores["first"].get("/api/me/incidents").json() == [incidencia]
    with aplicacion.state.fabrica_sesiones() as sesion:
        almacenado = sesion.get(Incidencia, incidencia["id"])
        assert almacenado.id_usuario_autor == actores["first_id"]
        assert almacenado.id_reserva == propia_reserva["id"]
        assert almacenado.id_equipo == propia_reserva["equipment_id"]
        assert almacenado.prioridad == "medium"
        assert almacenado.bloqueante is False
        assert (
            almacenado.resolucion == almacenado.respuesta_publica == almacenado.notas_internas == ""
        )


def test_identificador_manipulacion_no_puede_lectura_o_informe_otra_clientes_reserva(
    actores: dict[str, Any], propia_reserva: dict[str, Any]
) -> None:
    incidencia = informe(actores, propia_reserva)
    assert actores["second"].get("/api/me/incidents").json() == []
    ocultos = actores["second"].get(f"/api/me/incidents/{incidencia['id']}")
    ausente = actores["second"].get("/api/me/incidents/99999")
    assert ocultos.status_code == ausente.status_code == 404
    assert ocultos.json() == ausente.json()
    for id_reserva in (propia_reserva["id"], 99999):
        respuesta = actores["second"].post(
            f"/api/me/reservations/{id_reserva}/incidents", json=INFORME
        )
        assert respuesta.status_code == 404
    assert len(actores["admin"].get("/api/incidents").json()) == 1


@pytest.mark.parametrize(
    "prohibido",
    [
        {"equipment_id": 1},
        {"reservation_id": 1},
        {"author_user_id": 2},
        {"customer_user_id": 2},
        {"customer_id": 2},
        {"customer_name": "Otra persona"},
        {"customer_email": "otra@example.test"},
        {"status": "resolved"},
        {"priority": "high"},
        {"blocking": True},
        {"resolution": "Resuelta por cliente"},
        {"public_response": "Autorizado"},
        {"internal_notes": "Forjado"},
    ],
)
def test_informe_rechaza_todos_identidad_y_gestion_campos(
    actores: dict[str, Any], propia_reserva: dict[str, Any], prohibido: dict[str, object]
) -> None:
    respuesta = actores["first"].post(
        f"/api/me/reservations/{propia_reserva['id']}/incidents", json={**INFORME, **prohibido}
    )
    assert respuesta.status_code == 422, respuesta.text
    assert actores["admin"].get("/api/incidents").json() == []


@pytest.mark.parametrize(
    "cuerpo",
    [
        {},
        {"title": "Problema"},
        {"description": "Descripción"},
        {"title": " ", "description": "Descripción"},
        {"title": "X" * 161, "description": "Descripción"},
        {"title": "Problema", "description": " "},
        {"title": "Problema", "description": "X" * 2001},
        {"title": "Problema", "description": "NUL\x00"},
        {"title": "Problema", "description": None},
    ],
)
def test_cliente_informa_exigir_utiles_limitado_texto(
    actores: dict[str, Any], propia_reserva: dict[str, Any], cuerpo: dict[str, object]
) -> None:
    respuesta = actores["first"].post(
        f"/api/me/reservations/{propia_reserva['id']}/incidents", json=cuerpo
    )
    assert respuesta.status_code == 422
    assert actores["first"].get("/api/me/incidents").json() == []


def test_canceladas_reserva_no_puede_crear_informa_y_existentes_informa_permanecen(
    actores: dict[str, Any], propia_reserva: dict[str, Any]
) -> None:
    incidencia = informe(actores, propia_reserva)
    assert (
        actores["admin"].post(f"/api/reservations/{propia_reserva['id']}/cancel").status_code == 200
    )
    respuesta = actores["first"].post(
        f"/api/me/reservations/{propia_reserva['id']}/incidents", json=INFORME
    )
    assert respuesta.status_code == 409
    assert "confirmada" in respuesta.json()["detail"]
    assert actores["first"].get("/api/me/incidents").json() == [incidencia]


def test_historicos_sin_propietario_solo_son_visibles_para_administrador(
    aplicacion: FastAPI, actores: dict[str, Any], propia_reserva: dict[str, Any]
) -> None:
    incidencia = informe(actores, propia_reserva)
    with aplicacion.state.fabrica_sesiones.begin() as sesion:
        sesion.get(Reserva, propia_reserva["id"]).id_usuario_cliente = None
    assert actores["first"].get("/api/me/incidents").json() == []
    assert actores["first"].get(f"/api/me/incidents/{incidencia['id']}").status_code == 404
    assert (
        actores["first"]
        .post(f"/api/me/reservations/{propia_reserva['id']}/incidents", json=INFORME)
        .status_code
        == 404
    )
    assert actores["admin"].get(f"/api/reservations/{propia_reserva['id']}").status_code == 200
    historico = actores["admin"].get(f"/api/incidents/{incidencia['id']}")
    assert historico.status_code == 200
    assert historico.json()["author_user_id"] == actores["first_id"]


def test_autoria_solo_hace_no_exponer_otra_propietarios_reserva(
    aplicacion: FastAPI, actores: dict[str, Any], propia_reserva: dict[str, Any]
) -> None:
    incidencia = informe(actores, propia_reserva)
    with aplicacion.state.fabrica_sesiones.begin() as sesion:
        sesion.get(Reserva, propia_reserva["id"]).id_usuario_cliente = actores["second_id"]
    for navegador in (actores["first"], actores["second"]):
        assert navegador.get("/api/me/incidents").json() == []
        assert navegador.get(f"/api/me/incidents/{incidencia['id']}").status_code == 404


def test_publico_respuesta_es_separados_desde_internas_notas_y_resolucion(
    actores: dict[str, Any], propia_reserva: dict[str, Any]
) -> None:
    incidencia = informe(actores, propia_reserva)
    url = f"/api/incidents/{incidencia['id']}"
    updated = actores["admin"].patch(
        url,
        json={
            "public_response": "  Hemos recibido tu aviso y te contactaremos.  ",
            "internal_notes": "PRIVATE-NOTES: enviar a taller interno",
            "priority": "high",
            "blocking": True,
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["priority"] == "high"
    assert updated.json()["blocking"] is True
    assert updated.json()["internal_notes"] == "PRIVATE-NOTES: enviar a taller interno"
    assert updated.json()["author_user_id"] == actores["first_id"]
    assert updated.json()["reservation_id"] == propia_reserva["id"]
    resuelta = actores["admin"].patch(
        f"{url}/status", json={"status": "resolved", "resolution": "PRIVATE-REPAIR: coste 120"}
    )
    assert resuelta.status_code == 200
    for respuesta in (
        actores["first"].get(f"/api/me/incidents/{incidencia['id']}"),
        actores["first"].get("/api/me/incidents"),
    ):
        assert respuesta.status_code == 200
        assert "PRIVATE-" not in respuesta.text
        valor = respuesta.json()
        if isinstance(valor, list):
            valor = valor[0]
        assert set(valor) == CLIENTE_CAMPOS
        assert valor["status"] == "resolved"
        assert valor["public_response"] == "Hemos recibido tu aviso y te contactaremos."
    # Solicitar directamente la URL antigua nunca debe revelar la resolución ni las notas internas.
    assert actores["first"].get(url).status_code == 403
    assert actores["second"].get(url).status_code == 403


def test_cliente_no_puede_gestionar_incidencias_o_uso_administrativa_urls(
    actores: dict[str, Any], propia_reserva: dict[str, Any]
) -> None:
    incidencia = informe(actores, propia_reserva)
    for navegador in (actores["first"], actores["second"]):
        for metodo, url, cuerpo in (
            ("GET", "/api/incidents", None),
            ("GET", f"/api/incidents/{incidencia['id']}", None),
            ("PATCH", f"/api/incidents/{incidencia['id']}", {"blocking": True}),
            (
                "PATCH",
                f"/api/incidents/{incidencia['id']}/status",
                {"status": "resolved", "resolution": "Forjada"},
            ),
            ("POST", "/api/incidents", {"equipment_id": 1, "title": "Forjada"}),
        ):
            assert navegador.request(metodo, url, json=cuerpo).status_code == 403
    almacenado = actores["admin"].get(f"/api/incidents/{incidencia['id']}").json()
    assert almacenado["blocking"] is False
    assert almacenado["status"] == "open"


def test_informa_y_gestion_exigir_csrf_y_sesion(
    aplicacion: FastAPI, actores: dict[str, Any], propia_reserva: dict[str, Any]
) -> None:
    incidencia = informe(actores, propia_reserva)
    del actores["first"].headers["X-CSRF-Token"]
    assert (
        actores["first"]
        .post(f"/api/me/reservations/{propia_reserva['id']}/incidents", json=INFORME)
        .status_code
        == 403
    )
    del actores["admin"].headers["X-CSRF-Token"]
    assert (
        actores["admin"]
        .patch(
            f"/api/incidents/{incidencia['id']}", json={"public_response": "Revisaremos el aviso"}
        )
        .status_code
        == 403
    )
    with TestClient(aplicacion) as anonimo:
        for metodo, ruta in (
            ("GET", "/api/me/incidents"),
            ("GET", f"/api/me/incidents/{incidencia['id']}"),
            ("POST", f"/api/me/reservations/{propia_reserva['id']}/incidents"),
        ):
            assert anonimo.request(metodo, ruta, json=INFORME).status_code == 401
    assert len(actores["first"].get("/api/me/incidents").json()) == 1


def test_administrador_no_puede_suplantar_a_cliente_mediante_cuenta_rutas(
    actores: dict[str, Any], propia_reserva: dict[str, Any]
) -> None:
    for metodo, ruta in (
        ("GET", "/api/me/incidents"),
        ("GET", "/api/me/incidents/1"),
        ("POST", f"/api/me/reservations/{propia_reserva['id']}/incidents"),
    ):
        assert actores["admin"].request(metodo, ruta, json=INFORME).status_code == 403


def test_informe_cliente_no_bloquea_disponibilidad_y_administrador_controla_bloqueo(
    actores: dict[str, Any], propia_reserva: dict[str, Any]
) -> None:
    incidencia = informe(actores, propia_reserva)
    url = f"/api/public/equipment/{propia_reserva['equipment_id']}/availability"
    fechas = {"start_date": "2030-11-12", "end_date": "2030-11-15"}
    assert actores["first"].get(url, params=fechas).json()["available"] is True
    assert (
        actores["admin"]
        .patch(f"/api/incidents/{incidencia['id']}", json={"blocking": True, "priority": "high"})
        .status_code
        == 200
    )
    no_disponible = actores["first"].get(url, params=fechas)
    assert no_disponible.json()["available"] is False
    assert "Conector" not in no_disponible.text
    assert "incident" not in no_disponible.text
    assert (
        actores["admin"]
        .patch(f"/api/incidents/{incidencia['id']}", json={"blocking": False})
        .status_code
        == 200
    )
    assert actores["first"].get(url, params=fechas).json()["available"] is True


@pytest.mark.parametrize(
    "cambios",
    [
        {},
        {"priority": None},
        {"blocking": None},
        {"blocking": 1},
        {"priority": "critical"},
        {"public_response": None},
        {"internal_notes": None},
        {"public_response": "X" * 2001},
        {"internal_notes": "X" * 2001},
        {"public_response": "bad\x00value"},
        {"internal_notes": "bad\x00value"},
        {"status": "resolved"},
        {"resolution": "Repair"},
        {"author_user_id": 2},
        {"reservation_id": 2},
        {"equipment_id": 2},
        {"title": "Changed"},
    ],
)
def test_administrador_modificacion_valida_campos_sin_cambiando_historial(
    actores: dict[str, Any], propia_reserva: dict[str, Any], cambios: dict[str, object]
) -> None:
    incidencia = informe(actores, propia_reserva)
    url = f"/api/incidents/{incidencia['id']}"
    original = actores["admin"].get(url).json()
    assert actores["admin"].patch(url, json=cambios).status_code == 422
    assert actores["admin"].get(url).json() == original


def test_edicion_administrativa_conserva_campos_omitidos_y_permite_borrar_comunicacion(
    actores: dict[str, Any], propia_reserva: dict[str, Any]
) -> None:
    incidencia = informe(actores, propia_reserva)
    url = f"/api/incidents/{incidencia['id']}"
    primero = actores["admin"].patch(
        url, json={"public_response": "Recibido", "internal_notes": "Pendiente de taller"}
    )
    assert primero.status_code == 200
    segundo = actores["admin"].patch(url, json={"public_response": ""})
    assert segundo.status_code == 200
    assert segundo.json() == {**primero.json(), "public_response": ""}
    assert (
        actores["admin"].patch("/api/incidents/99999", json={"priority": "high"}).status_code == 404
    )


def test_migracion_conserva_filas_antiguas_y_privacidad_de_resolucion_interna(
    tmp_path: Path,
) -> None:
    servidor = Path(__file__).resolve().parents[1]
    configuracion = Config(str(servidor / "alembic.ini"))
    configuracion.set_main_option("script_location", str(servidor / "alembic"))
    url_base_datos = f"sqlite:///{(tmp_path / 'previous.sqlite3').as_posix()}"
    configuracion.set_main_option("sqlalchemy.url", url_base_datos)
    motor = crear_base_datos_motor(url_base_datos)
    try:
        with motor.begin() as conexion:
            configuracion.attributes["connection"] = conexion
            command.upgrade(configuracion, "0007_public_catalogue")
            conexion.execute(
                text(
                    "INSERT INTO equipment(id,code,name,category,"
                    "public_description,technical_specs) "
                    "VALUES(41,'OLD-CAM','Cámara previa','Cámaras','Ficha pública','{}')"
                )
            )
            conexion.execute(
                text(
                    "INSERT INTO reservations(id,equipment_id,customer_name,customer_email,"
                    "start_date,end_date,status,external_reference) VALUES"
                    "(52,41,'Cliente previo','alicia@example.test','2030-11-10','2030-11-12',"
                    "'confirmed','CSV-OLD'),"
                    "(53,41,'Cliente previo','alicia@example.test','2030-11-13','2030-11-15',"
                    "'cancelled',NULL)"
                )
            )
            conexion.execute(
                text(
                    "INSERT INTO incidents(id,equipment_id,title,blocking,status,resolution) "
                    "VALUES(63,41,'Avería previa',1,'resolved','PRIVATE-REPAIR histórico')"
                )
            )
            antes = {
                tabla: [
                    dict(fila)
                    for fila in conexion.execute(text(f"SELECT * FROM {tabla}")).mappings()
                ]
                for tabla in ("equipment", "reservations", "incidents", "users", "auth_sessions")
            }
            command.upgrade(configuracion, "head")
            for tabla, filas in antes.items():
                despues = [
                    dict(fila)
                    for fila in conexion.execute(text(f"SELECT * FROM {tabla}")).mappings()
                ]
                for real, esperado in zip(despues, filas, strict=True):
                    assert {clave: real[clave] for clave in esperado} == esperado
            historico = (
                conexion.execute(text("SELECT * FROM incidents WHERE id=63")).mappings().one()
            )
            assert historico["reservation_id"] is None
            assert historico["author_user_id"] is None
            assert historico["public_response"] == historico["internal_notes"] == ""
            assert historico["resolution"] == "PRIVATE-REPAIR histórico"
            assert conexion.execute(
                text("SELECT customer_user_id FROM reservations")
            ).scalars().all() == [None, None]
            assert conexion.execute(text("PRAGMA foreign_key_check")).all() == []
            assert conexion.scalar(text("PRAGMA integrity_check")) == "ok"
            command.check(configuracion)
        with pytest.raises(IntegrityError), motor.begin() as conexion:
            conexion.execute(text("UPDATE incidents SET reservation_id=99999 WHERE id=63"))
    finally:
        motor.dispose()


def test_cliente_openapi_esquemas_solo_publicar_aprobado_campos(actores: dict[str, Any]) -> None:
    esquema = actores["admin"].get("/api/openapi.json").json()
    lectura = esquema["components"]["schemas"]["ClienteIncidenciaLectura"]
    crear = esquema["components"]["schemas"]["ClienteIncidenciaCrear"]
    assert set(lectura["properties"]) == CLIENTE_CAMPOS
    assert set(crear["properties"]) == {"title", "description"}
    assert crear["additionalProperties"] is False
    operacion = esquema["paths"]["/api/me/incidents/{incident_id}"]["get"]
    assert operacion["security"] == [{"SessionCookie": []}]
    assert "403" in operacion["responses"]
    assert "404" in operacion["responses"]


@pytest.mark.parametrize("informe_primero", [True, False])
def test_cliente_informe_y_cancelacion_hacer_sus_decision_bajo_la_mismo_escritor_bloqueo(
    aplicacion: FastAPI,
    ajustes: Configuracion,
    actores: dict[str, Any],
    propia_reserva: dict[str, Any],
    informe_primero: bool,
) -> None:
    informe_url = f"/api/me/reservations/{propia_reserva['id']}/incidents"
    cancelar_url = f"/api/reservations/{propia_reserva['id']}/cancel"
    primero_tiene_bloqueo = Event()
    segundo_intentado_escritura = Event()
    segundo_aplicacion = crear_aplicacion(ajustes)

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
            assert segundo_intentado_escritura.wait(timeout=5)

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
        with (
            TestClient(segundo_aplicacion) as segundo,
            ThreadPoolExecutor(max_workers=2) as ejecutor,
        ):
            iniciar_sesion(
                segundo, "admin@example.test" if informe_primero else "alicia@example.test"
            )
            event.listen(
                aplicacion.state.motor, "after_cursor_execute", mantener_primero_escritura_bloqueo
            )
            event.listen(
                segundo_aplicacion.state.motor,
                "before_cursor_execute",
                observar_segundo_escritura_intento,
            )
            try:
                primero = ejecutor.submit(
                    actores["first" if informe_primero else "admin"].post,
                    informe_url if informe_primero else cancelar_url,
                    json=INFORME if informe_primero else None,
                )
                assert primero_tiene_bloqueo.wait(timeout=5)
                siguiente = ejecutor.submit(
                    segundo.post,
                    cancelar_url if informe_primero else informe_url,
                    json=None if informe_primero else INFORME,
                )
                primero_respuesta = primero.result(timeout=10)
                segundo_respuesta = siguiente.result(timeout=10)
            finally:
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
            assert primero_respuesta.status_code == (201 if informe_primero else 200)
            assert segundo_respuesta.status_code == (200 if informe_primero else 409)
        assert len(actores["admin"].get("/api/incidents").json()) == (1 if informe_primero else 0)
        assert (
            actores["admin"].get(f"/api/reservations/{propia_reserva['id']}").json()["status"]
            == "cancelled"
        )
    finally:
        segundo_aplicacion.state.motor.dispose()


@pytest.mark.parametrize("operacion", ["report", "management"])
def test_ocupado_cliente_informe_o_administrador_gestion_deja_sin_parcial_cambios(
    aplicacion: FastAPI,
    ajustes: Configuracion,
    actores: dict[str, Any],
    propia_reserva: dict[str, Any],
    operacion: str,
) -> None:
    original = informe(actores, propia_reserva) if operacion == "management" else None
    url = (
        f"/api/incidents/{original['id']}"
        if original
        else f"/api/me/reservations/{propia_reserva['id']}/incidents"
    )
    metodo = "PATCH" if original else "POST"
    cuerpo = {"blocking": True, "public_response": "Revisaremos el aviso"} if original else INFORME
    segundo_aplicacion = crear_aplicacion(
        ajustes.model_copy(update={"espera_sqlite_ocupado_ms": 25})
    )
    try:
        with TestClient(segundo_aplicacion) as navegador:
            iniciar_sesion(navegador, "admin@example.test" if original else "alicia@example.test")
            with aplicacion.state.motor.connect() as escritor:
                escritor.exec_driver_sql("BEGIN IMMEDIATE")
                fallido = navegador.request(metodo, url, json=cuerpo)
                assert fallido.status_code == 503
                assert fallido.headers["Retry-After"] == "1"
                escritor.rollback()
            assert actores["first"].get("/api/me/incidents").json() == (
                [original] if original else []
            )
            reintentado = navegador.request(metodo, url, json=cuerpo)
            assert reintentado.status_code == (200 if original else 201)
    finally:
        segundo_aplicacion.state.motor.dispose()
