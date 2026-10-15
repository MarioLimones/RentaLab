from pathlib import Path

import pytest
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from alembic import command
from rentalab.autenticacion.esquemas import SolicitudRegistro
from rentalab.base_datos import crear_base_datos_motor
from rentalab.reservas.modelos import Reserva


def test_administrativa_filtros_son_combinados_literal_y_normalizado(
    aplicacion: FastAPI, cliente_http: TestClient, equipo_contenido_envio: dict
) -> None:
    unidad = cliente_http.post("/api/equipment", json=equipo_contenido_envio).json()
    usuario = aplicacion.state.autenticacion_servicio.registrar(
        SolicitudRegistro(
            nombre="María", correo="maria@example.test", contrasena="isolated-admin-test"
        )
    )
    reservas = []
    for indice, nombre in enumerate(("MARÍA Prueba", "Usuario_100%", "Otra persona")):
        respuesta = cliente_http.post(
            "/api/reservations",
            json={
                "equipment_id": unidad["id"],
                "customer_name": nombre,
                "customer_email": f"persona{indice}@example.test",
                "start_date": f"2030-11-{10 + indice:02}",
                "end_date": f"2030-11-{11 + indice:02}",
            },
        )
        assert respuesta.status_code == 201, respuesta.text
        reservas.append(respuesta.json())
    with aplicacion.state.fabrica_sesiones.begin() as sesion:
        fila = sesion.get(Reserva, reservas[0]["id"])
        fila.id_usuario_cliente = usuario.id
        fila.origen = "portal"
    reservas[0].update(customer_user_id=usuario.id, origin="portal")
    assert cliente_http.get("/api/reservations", params={"customer": "  maría  "}).json() == [
        reservas[0]
    ]
    assert cliente_http.get(
        "/api/reservations", params={"customer": "PERSONA1@EXAMPLE.TEST"}
    ).json() == [reservas[1]]
    for literal in ("_", "%", "100%"):
        assert cliente_http.get("/api/reservations", params={"customer": literal}).json() == [
            reservas[1]
        ]
    filtros = {
        "customer": "María",
        "customer_user_id": usuario.id,
        "origin": "portal",
        "equipment_id": unidad["id"],
        "status": "confirmed",
        "start_date": "2030-11-09",
        "end_date": "2030-11-11",
    }
    assert cliente_http.get("/api/reservations", params=filtros).json() == [reservas[0]]
    assert cliente_http.get("/api/reservations", params={**filtros, "origin": "csv"}).json() == []
    assert cliente_http.get("/api/reservations", params={"customer_user_id": 999}).json() == []
    assert cliente_http.get("/api/reservations", params={"origin": "admin"}).json() == reservas[1:]


@pytest.mark.parametrize(
    "filtros",
    [
        {"customer": ""},
        {"customer": "   "},
        {"customer": "a" * 255},
        {"customer": "private\x00name"},
        {"customer_user_id": 0},
        {"customer_user_id": str(2**63)},
        {"origin": "guessed"},
    ],
)
def test_administrador_reserva_filtro_contrato_rechaza_invalido_valores(
    cliente_http: TestClient, filtros: dict
) -> None:
    assert cliente_http.get("/api/reservations", params=filtros).status_code == 422


@pytest.mark.parametrize("prohibido", ["customer_user_id", "origin", "status"])
def test_administrador_crear_nunca_acepta_servidor_asignado_propiedad_o_origen(
    cliente_http: TestClient, equipo_contenido_envio: dict, prohibido: str
) -> None:
    id_equipo = cliente_http.post("/api/equipment", json=equipo_contenido_envio).json()["id"]
    respuesta = cliente_http.post(
        "/api/reservations",
        json={
            "equipment_id": id_equipo,
            "customer_name": "Nombre",
            "customer_email": "nombre@example.test",
            "start_date": "2030-11-10",
            "end_date": "2030-11-12",
            prohibido: 1 if prohibido == "customer_user_id" else "portal",
        },
    )
    assert respuesta.status_code == 422
    assert cliente_http.get("/api/reservations").json() == []


def test_administrativa_openapi_documenta_origen_propietario_y_filtros(
    cliente_http: TestClient,
) -> None:
    documento = cliente_http.get("/api/openapi.json").json()
    esquemas = documento["components"]["schemas"]
    assert esquemas["LecturaReserva"]["properties"]["origin"]["enum"] == [
        "portal",
        "admin",
        "csv",
        "legacy",
    ]
    assert {"customer_user_id", "origin"} <= set(esquemas["LecturaReserva"]["required"])
    assert not {"customer_user_id", "origin"} & set(esquemas["CrearReserva"]["properties"])
    assert not {"customer_user_id", "origin"} & set(esquemas["ClienteReservaLectura"]["properties"])
    operacion = documento["paths"]["/api/reservations"]["get"]
    assert {"customer", "customer_user_id", "origin"} <= {
        p["name"] for p in operacion["parameters"]
    }
    assert operacion["security"] == [{"SessionCookie": []}]
    assert {"401", "403"} <= set(operacion["responses"])


def test_origen_migracion_preserva_propia_desconocido_y_vinculada_incidencia_filas(
    tmp_path: Path,
) -> None:
    servidor = Path(__file__).resolve().parents[1]
    configuracion = Config(str(servidor / "alembic.ini"))
    configuracion.set_main_option("script_location", str(servidor / "alembic"))
    url = f"sqlite:///{(tmp_path / 'before-origin.db').as_posix()}"
    configuracion.set_main_option("sqlalchemy.url", url)
    motor = crear_base_datos_motor(url)
    try:
        with motor.begin() as conexion:
            configuracion.attributes["connection"] = conexion
            command.upgrade(configuracion, "0008_customer_incidents")
            conexion.execute(
                text(
                    "INSERT INTO equipment(id,code,name,category,technical_specs) "
                    "VALUES (41,'HISTORIC','Equipo histórico','Audio','{}')"
                )
            )
            conexion.execute(
                text(
                    "INSERT INTO users(id,name,email,password_hash,role,active) "
                    "VALUES(51,'Cuenta','cuenta@example.test','unusable-placeholder','customer',1)"
                )
            )
            conexion.execute(
                text(
                    "INSERT INTO reservations(id,equipment_id,customer_name,customer_email,"
                    "start_date,"
                    "end_date,status,external_reference,customer_user_id) VALUES"
                    "(61,41,'Cuenta','cuenta@example.test','2030-11-10','2030-11-12','confirmed',NULL,51),"
                    "(62,41,'Histórico','cuenta@example.test','2030-11-13','2030-11-15','cancelled','CSV-OLD',NULL)"
                )
            )
            conexion.execute(
                text(
                    "INSERT INTO incidents(id,equipment_id,title,blocking,status,reservation_id,"
                    "author_user_id,public_response,internal_notes) VALUES "
                    "(71,41,'Aviso',0,'open',61,51,'Respuesta pública','Nota interna')"
                )
            )
            tablas = ("equipment", "users", "reservations", "incidents", "auth_sessions")
            antes = {
                tabla: list(conexion.execute(text(f"SELECT * FROM {tabla}")).mappings())
                for tabla in tablas
            }
            # Reconstruir la tabla activaría esta traza. La migración solo debe
            # ejecutar ALTER sobre reservations.
            statements: list[str] = []
            conexion.connection.driver_connection.set_trace_callback(statements.append)
            command.upgrade(configuracion, "head")
            conexion.connection.driver_connection.set_trace_callback(None)
            assert not any("DROP TABLE" in sentencia.upper() for sentencia in statements)
            for tabla, filas in antes.items():
                despues = list(conexion.execute(text(f"SELECT * FROM {tabla}")).mappings())
                for real, esperado in zip(despues, filas, strict=True):
                    assert {clave: real[clave] for clave in esperado} == dict(esperado)
            assert conexion.execute(
                text("SELECT origin FROM reservations ORDER BY id")
            ).scalars().all() == ["legacy", "legacy"]
            assert conexion.execute(text("PRAGMA foreign_key_check")).all() == []
            assert conexion.scalar(text("PRAGMA integrity_check")) == "ok"
            command.check(configuracion)
        with pytest.raises(IntegrityError), motor.begin() as conexion:
            conexion.execute(text("UPDATE reservations SET origin='guessed' WHERE id=61"))
        with pytest.raises(IntegrityError), motor.begin() as conexion:
            conexion.execute(text("UPDATE incidents SET reservation_id=999 WHERE id=71"))
    finally:
        motor.dispose()
