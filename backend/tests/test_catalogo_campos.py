from pathlib import Path

import pytest
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from alembic import command
from rentalab.base_datos import crear_base_datos_motor
from rentalab.cargar_datos import DEMOSTRACION_EQUIPO, cargar_datos_equipo
from rentalab.equipo.modelos import Equipo


def test_administrador_edita_campos_publicos_separados_de_descripcion_interna(
    cliente_http: TestClient, equipo_contenido_envio: dict[str, object]
) -> None:
    creados = cliente_http.post(
        "/api/equipment",
        json={
            **equipo_contenido_envio,
            "public_description": "  Cámara ligera para entrevistas.  ",
            "technical_specs": {"  Resolución  ": "  4K UHD  ", "Peso": "1,2 kg"},
            "image_url": "  /api/public/images/camera.svg  ",
        },
    )
    assert creados.status_code == 201
    equipo = creados.json()
    assert equipo["description"] == equipo_contenido_envio["description"]
    assert equipo["public_description"] == "Cámara ligera para entrevistas."
    assert equipo["technical_specs"] == {"Resolución": "4K UHD", "Peso": "1,2 kg"}
    assert equipo["image_url"] == "/api/public/images/camera.svg"
    url = f"/api/equipment/{equipo['id']}"
    editados = cliente_http.patch(url, json={"technical_specs": {"Óptica": "24–70 mm"}})
    assert editados.status_code == 200
    assert editados.json() == {**equipo, "technical_specs": {"Óptica": "24–70 mm"}}
    eliminados = cliente_http.patch(url, json={"image_url": None})
    assert eliminados.status_code == 200
    assert eliminados.json() == {**editados.json(), "image_url": None}
    assert cliente_http.get(url).json() == eliminados.json()


def test_reemplazar_restablece_publico_campos_a_predeterminados(
    cliente_http: TestClient, equipo_contenido_envio: dict[str, object]
) -> None:
    equipo = cliente_http.post(
        "/api/equipment",
        json={
            **equipo_contenido_envio,
            "public_description": "Descripción para clientes",
            "technical_specs": {"Audio": "48 kHz"},
            "image_url": "https://images.example.test/microphone.webp",
        },
    ).json()
    reemplazo = cliente_http.put(f"/api/equipment/{equipo['id']}", json=equipo_contenido_envio)
    assert reemplazo.status_code == 200
    assert reemplazo.json()["public_description"] == ""
    assert reemplazo.json()["technical_specs"] == {}
    assert reemplazo.json()["image_url"] is None


@pytest.mark.parametrize(
    ("campo", "valor"),
    [
        ("public_description", None),
        ("public_description", 123),
        ("public_description", "X" * 2001),
        ("public_description", "Visible\x00privado"),
        ("technical_specs", None),
        ("technical_specs", []),
        ("technical_specs", {str(indice): "Dato" for indice in range(21)}),
        ("technical_specs", {" ": "Dato"}),
        ("technical_specs", {"X" * 81: "Dato"}),
        ("technical_specs", {"Peso": " "}),
        ("technical_specs", {"Peso": "X" * 301}),
        ("technical_specs", {"Peso": 123}),
        ("technical_specs", {"Peso\x00": "Dato"}),
        ("technical_specs", {"Peso": "Dato\x00"}),
        ("technical_specs", {" Peso ": "1 kg", "Peso": "2 kg"}),
        ("image_url", ""),
        ("image_url", 123),
        ("image_url", "http://example.test/image.png"),
        ("image_url", "javascript:alert(1)"),
        ("image_url", "//example.test/image.png"),
        ("image_url", "https://user:password@example.test/image.png"),
        ("image_url", "https://example.test/image.png?token=private"),
        ("image_url", "https://example.test/image.png#fragment"),
        ("image_url", "https:///image.png"),
        ("image_url", "https://example.test:99999/image.png"),
        ("image_url", "https://example.test/ima\nge.png"),
        ("image_url", "/other/image.png"),
        ("image_url", "/api/public/images/../private.png"),
        ("image_url", "/api/public/images/%2e%2e/private.png"),
        ("image_url", "/api/public/images/..\\private.png"),
        ("image_url", "/api/public/images/image.png?private=true"),
        ("image_url", "/api/public/images/image.png#fragment"),
    ],
)
def test_invalido_publico_campos_son_rechazadas_para_creacion_y_modificacion_sin_cambios(
    cliente_http: TestClient,
    equipo_contenido_envio: dict[str, object],
    campo: str,
    valor: object,
) -> None:
    rechazadas = cliente_http.post("/api/equipment", json={**equipo_contenido_envio, campo: valor})
    assert rechazadas.status_code == 422
    assert cliente_http.get("/api/equipment").json() == []
    equipo = cliente_http.post("/api/equipment", json=equipo_contenido_envio).json()
    url = f"/api/equipment/{equipo['id']}"
    assert cliente_http.patch(url, json={campo: valor}).status_code == 422
    assert cliente_http.get(url).json() == equipo


def test_maximo_publico_caracteristicas_y_vacio_publico_descripcion_son_aceptadas(
    cliente_http: TestClient, equipo_contenido_envio: dict[str, object]
) -> None:
    caracteristicas = {f"{indice:02d}" + "X" * 78: "V" * 300 for indice in range(20)}
    respuesta = cliente_http.post(
        "/api/equipment",
        json={
            **equipo_contenido_envio,
            "public_description": "  ",
            "technical_specs": caracteristicas,
        },
    )
    assert respuesta.status_code == 201
    assert respuesta.json()["public_description"] == ""
    assert respuesta.json()["technical_specs"] == caracteristicas
    assert respuesta.json()["image_url"] is None


def test_catalogo_demostracion_funciona_sin_imagenes_remotas_y_conserva_campos(
    aplicacion: FastAPI,
) -> None:
    assert len(DEMOSTRACION_EQUIPO) == 4
    with aplicacion.state.fabrica_sesiones() as sesion, sesion.begin():
        assert cargar_datos_equipo(sesion) == 4
        equipo = list(sesion.scalars(select(Equipo).order_by(Equipo.id)))
        assert all(
            elemento.descripcion_publica and elemento.caracteristicas_tecnicas
            for elemento in equipo
        )
        assert {elemento.url_imagen for elemento in equipo} == {
            "/api/public/images/demo-camera.jpg",
            "/api/public/images/demo-microphone.jpg",
            "/api/public/images/demo-light.jpg",
        }
        primero = equipo[0]
        primero.descripcion_publica = "Contenido revisado por administración"
        primero.caracteristicas_tecnicas = {"Accesorios": "Trípode propio"}
        primero.url_imagen = "/api/public/images/custom-camera.svg"
        sesion.flush()
        antes = [
            dict(fila)
            for fila in sesion.execute(text("SELECT * FROM equipment ORDER BY id")).mappings()
        ]
        assert cargar_datos_equipo(sesion) == 0
        despues = [
            dict(fila)
            for fila in sesion.execute(text("SELECT * FROM equipment ORDER BY id")).mappings()
        ]
        assert despues == antes


def test_catalogo_migracion_preserva_cada_anterior_columna_sin_publicando_internas_notas(
    tmp_path: Path,
) -> None:
    servidor = Path(__file__).resolve().parents[1]
    configuracion = Config(str(servidor / "alembic.ini"))
    configuracion.set_main_option("script_location", str(servidor / "alembic"))
    url_base_datos = f"sqlite:///{(tmp_path / 'catalogue-migration.sqlite3').as_posix()}"
    configuracion.set_main_option("sqlalchemy.url", url_base_datos)
    motor = crear_base_datos_motor(url_base_datos)
    try:
        with motor.begin() as conexion:
            configuracion.attributes["connection"] = conexion
            command.upgrade(configuracion, "0006_users_ownership")
            for sentencia in (
                "INSERT INTO users (id,name,email,password_hash,role,active) "
                "VALUES (7,'Cliente previo','previous@example.test','test-hash','customer',1)",
                "INSERT INTO equipment (id,code,name,category,description,active) "
                "VALUES (41,'OLD-CAM','Equipo previo','Cámaras','Nota interna privada',0)",
                "INSERT INTO reservations (id,equipment_id,customer_user_id,customer_name,"
                "customer_email,start_date,end_date,status,external_reference) "
                "VALUES (52,41,7,'Cliente previo','previous@example.test','2026-11-10',"
                "'2026-11-12','confirmed','HISTORICAL')",
                "INSERT INTO incidents (id,equipment_id,author_user_id,title,description,"
                "blocking,status,resolution) VALUES (63,41,7,'Avería privada','Información "
                "sensible',1,'resolved','Reparada')",
                "INSERT INTO auth_sessions (id,expires_at,credential_version,user_id) "
                "VALUES ('" + "a" * 64 + "',2000000000,'" + "b" * 64 + "',7)",
            ):
                conexion.execute(text(sentencia))
            tablas = ("users", "equipment", "reservations", "incidents", "auth_sessions")
            antes = {
                tabla: [
                    dict(fila)
                    for fila in conexion.execute(
                        text(f"SELECT * FROM {tabla} ORDER BY id")
                    ).mappings()
                ]
                for tabla in tablas
            }
            command.upgrade(configuracion, "head")
            for tabla, esperado_filas in antes.items():
                real_filas = list(
                    conexion.execute(text(f"SELECT * FROM {tabla} ORDER BY id")).mappings()
                )
                for esperado, real in zip(esperado_filas, real_filas, strict=True):
                    assert {clave: real[clave] for clave in esperado} == esperado
            migrada = conexion.execute(text("SELECT * FROM equipment WHERE id=41")).mappings().one()
            assert migrada["public_description"] == ""
            assert migrada["technical_specs"] == "{}"
            assert migrada["image_url"] is None
            assert conexion.scalar(text("PRAGMA integrity_check")) == "ok"
            assert conexion.execute(text("PRAGMA foreign_key_check")).all() == []
            command.check(configuracion)
    finally:
        motor.dispose()
