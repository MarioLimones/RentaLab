from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from threading import Barrier

import pytest
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from alembic import command
from rentalab.autenticacion.esquemas import SolicitudRegistro
from rentalab.autenticacion.modelos import Usuario
from rentalab.base_datos import crear_base_datos_motor
from rentalab.compatibilidad import alias_json
from rentalab.cuenta.modelos import GuardadosProducto

BASE_URL = "/api/me/saved-products"
CLIENTE_CONTRASENA = "isolated-saved-products-password"


def iniciar_sesion(navegador: TestClient, correo: str) -> None:
    token = navegador.get("/api/auth/csrf").json()["csrf_token"]
    respuesta = navegador.post(
        "/api/auth/login",
        json={"username": correo, "password": CLIENTE_CONTRASENA},
        headers={"X-CSRF-Token": token},
    )
    assert respuesta.status_code == 200, respuesta.text
    navegador.headers["X-CSRF-Token"] = navegador.get("/api/auth/csrf").json()["csrf_token"]


@dataclass
class GuardadosEscenario:
    primero: TestClient
    segundo: TestClient
    administrador_http: TestClient
    primero_id: int
    segundo_id: int
    id_equipo: int


@pytest.fixture
def escenario(aplicacion: FastAPI, equipo_contenido_envio: dict) -> Iterator[GuardadosEscenario]:
    identidades = [
        ("Primera cuenta", "saved-first@example.test", "customer"),
        ("Segunda cuenta", "saved-second@example.test", "customer"),
        ("Administración", "saved-admin@example.test", "admin"),
    ]
    usuarios = [
        aplicacion.state.autenticacion_servicio.registrar(
            SolicitudRegistro(nombre=nombre, correo=correo, contrasena=CLIENTE_CONTRASENA), rol=rol
        )
        for nombre, correo, rol in identidades
    ]
    with ExitStack() as pila:
        navegadores = [pila.enter_context(TestClient(aplicacion)) for _identidad in identidades]
        for navegador, (_nombre, correo, _rol) in zip(navegadores, identidades, strict=True):
            iniciar_sesion(navegador, correo)
        primero, segundo, administrador_http = navegadores
        respuesta = administrador_http.post("/api/equipment", json=equipo_contenido_envio)
        assert respuesta.status_code == 201, respuesta.text
        yield GuardadosEscenario(
            primero,
            segundo,
            administrador_http,
            usuarios[0].id,
            usuarios[1].id,
            respuesta.json()["id"],
        )


def crear_unidad(escenario: GuardadosEscenario, **cambios: object) -> int:
    respuesta = escenario.administrador_http.post(
        "/api/equipment",
        json={
            "code": "CAM-ALIAS",
            "name": "Cámara de prueba",
            "category": "Cámaras",
            "description": "INTERNAL-PRIVATE-INVENTORY-NOTE",
            **{alias_json(clave): valor for clave, valor in cambios.items()},
        },
    )
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()["id"]


def test_guardados_productos_persiste_entre_sesiones_y_aislar_cuentas(
    aplicacion: FastAPI, escenario: GuardadosEscenario
) -> None:
    esperado = {"equipment_ids": [escenario.id_equipo]}
    assert escenario.primero.get(BASE_URL).json() == {"equipment_ids": []}
    respuesta = escenario.primero.put(f"{BASE_URL}/{escenario.id_equipo}")
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json() == esperado
    assert respuesta.headers["Cache-Control"] == "no-store"
    assert escenario.segundo.get(BASE_URL).json() == {"equipment_ids": []}
    assert escenario.segundo.delete(f"{BASE_URL}/{escenario.id_equipo}").json() == {
        "equipment_ids": []
    }
    with TestClient(aplicacion) as nuevo_navegador:
        iniciar_sesion(nuevo_navegador, "saved-first@example.test")
        lectura = nuevo_navegador.get(BASE_URL)
        assert lectura.json() == esperado
        assert lectura.headers["Cache-Control"] == "no-store"
        assert "PRIVATE" not in lectura.text
        assert "customer" not in lectura.text
    with aplicacion.state.fabrica_sesiones() as sesion:
        filas = sesion.scalars(select(GuardadosProducto)).all()
        assert [(fila.id_usuario_cliente, fila.id_equipo) for fila in filas] == [
            (escenario.primero_id, escenario.id_equipo)
        ]
    assert escenario.primero.delete(f"{BASE_URL}/{escenario.id_equipo}").json() == {
        "equipment_ids": []
    }
    assert escenario.primero.delete(f"{BASE_URL}/{escenario.id_equipo}").json() == {
        "equipment_ids": []
    }
    assert escenario.primero.delete(f"{BASE_URL}/999999").json() == {"equipment_ids": []}


def test_alias_guardar_una_canonico_modelo_y_archivar_mantiene_eliminable_favorito(
    aplicacion: FastAPI, escenario: GuardadosEscenario
) -> None:
    alias = crear_unidad(escenario, nombre="CA\u0301MARA DE PRUEBA", categoria="CA\u0301MARAS")
    otro_categoria = crear_unidad(escenario, codigo="ACCESSORY", categoria="Accesorios")
    esperado = {"equipment_ids": [escenario.id_equipo]}
    for id_equipo in [alias, escenario.id_equipo, alias]:
        respuesta = escenario.primero.put(f"{BASE_URL}/{id_equipo}")
        assert respuesta.status_code == 200, respuesta.text
        assert respuesta.json() == esperado
    assert escenario.primero.put(f"{BASE_URL}/{otro_categoria}").json() == {
        "equipment_ids": [escenario.id_equipo, otro_categoria]
    }
    with aplicacion.state.fabrica_sesiones() as sesion:
        assert len(sesion.scalars(select(GuardadosProducto)).all()) == 2
    assert (
        escenario.administrador_http.patch(
            f"/api/equipment/{escenario.id_equipo}", json={"active": False}
        ).status_code
        == 200
    )
    assert escenario.primero.get(BASE_URL).json() == {"equipment_ids": [alias, otro_categoria]}
    assert escenario.primero.put(f"{BASE_URL}/{alias}").json() == {
        "equipment_ids": [alias, otro_categoria]
    }
    assert escenario.primero.delete(f"{BASE_URL}/{alias}").json() == {
        "equipment_ids": [otro_categoria]
    }
    assert escenario.primero.put(f"{BASE_URL}/{alias}").json() == {
        "equipment_ids": [alias, otro_categoria]
    }
    assert (
        escenario.administrador_http.patch(
            f"/api/equipment/{alias}", json={"active": False}
        ).status_code
        == 200
    )
    assert escenario.primero.get(BASE_URL).json() == {"equipment_ids": [alias, otro_categoria]}
    assert escenario.primero.put(f"{BASE_URL}/{alias}").status_code == 404
    # Un alias archivado permite eliminar el mismo modelo guardado mediante otra unidad.
    assert escenario.primero.delete(f"{BASE_URL}/{escenario.id_equipo}").json() == {
        "equipment_ids": [otro_categoria]
    }


def test_ausente_y_inactivo_productos_no_puede_ser_guardados(escenario: GuardadosEscenario) -> None:
    inactivo = crear_unidad(escenario, activo=False)
    ausente = escenario.primero.put(f"{BASE_URL}/999999")
    assert ausente.status_code == 404
    archivados = escenario.primero.put(f"{BASE_URL}/{inactivo}")
    assert archivados.status_code == 404
    assert archivados.json() == ausente.json() == {"detail": "El equipo no existe"}
    assert escenario.primero.get(BASE_URL).json() == {"equipment_ids": []}


@pytest.mark.parametrize("metodo", ["GET", "PUT", "DELETE"])
def test_guardados_productos_exigir_cliente_sesion_y_ocultar_datos(
    aplicacion: FastAPI, escenario: GuardadosEscenario, metodo: str
) -> None:
    ruta = BASE_URL if metodo == "GET" else f"{BASE_URL}/{escenario.id_equipo}"
    with TestClient(aplicacion) as anonimo:
        assert anonimo.request(metodo, ruta).status_code == 401
    prohibido = escenario.administrador_http.request(metodo, ruta)
    assert prohibido.status_code == 403
    assert "equipment_ids" not in prohibido.text
    assert prohibido.headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize("metodo", ["PUT", "DELETE"])
def test_escrituras_exigir_csrf_y_rechazar_propietario_inyeccion(
    escenario: GuardadosEscenario, metodo: str
) -> None:
    ruta = f"{BASE_URL}/{escenario.id_equipo}"
    respuesta = escenario.primero.request(metodo, ruta, headers={"X-CSRF-Token": "invalid"})
    assert respuesta.status_code == 403
    respuesta = escenario.primero.request(
        metodo, ruta, json={"customer_user_id": escenario.segundo_id}
    )
    assert respuesta.status_code == 422
    respuesta = escenario.primero.request(
        metodo, ruta, params={"customer_user_id": escenario.segundo_id}
    )
    assert respuesta.status_code == 422
    assert escenario.primero.get(BASE_URL).json() == {"equipment_ids": []}
    assert escenario.segundo.get(BASE_URL).json() == {"equipment_ids": []}


def test_lecturas_rechazar_propietario_consulta_parametro(escenario: GuardadosEscenario) -> None:
    assert escenario.primero.put(f"{BASE_URL}/{escenario.id_equipo}").status_code == 200
    respuesta = escenario.segundo.get(BASE_URL, params={"customer_user_id": escenario.primero_id})
    assert respuesta.status_code == 422
    assert escenario.segundo.get(BASE_URL).json() == {"equipment_ids": []}


@pytest.mark.parametrize("id_equipo", ["0", "-1", str(2**63), "not-an-id"])
@pytest.mark.parametrize("metodo", ["PUT", "DELETE"])
def test_guardados_producto_ids_son_limitado(
    escenario: GuardadosEscenario, id_equipo: str, metodo: str
) -> None:
    assert escenario.primero.request(metodo, f"{BASE_URL}/{id_equipo}").status_code == 422


@pytest.mark.parametrize("cambiar", ["deactivated", "changed_role"])
def test_guardados_productos_recomprobar_real_cuenta_acceso(
    aplicacion: FastAPI, escenario: GuardadosEscenario, cambiar: str
) -> None:
    assert escenario.primero.put(f"{BASE_URL}/{escenario.id_equipo}").status_code == 200
    with aplicacion.state.fabrica_sesiones() as sesion, sesion.begin():
        usuario = sesion.get(Usuario, escenario.primero_id)
        assert usuario is not None
        if cambiar == "deactivated":
            usuario.activo = False
        else:
            usuario.rol = "admin"
    esperado = 401 if cambiar == "deactivated" else 403
    assert escenario.primero.get(BASE_URL).status_code == esperado
    assert escenario.primero.put(f"{BASE_URL}/{escenario.id_equipo}").status_code == esperado
    assert escenario.primero.delete(f"{BASE_URL}/{escenario.id_equipo}").status_code == esperado


def test_simultaneos_alias_incorporaciones_son_idempotente(
    aplicacion: FastAPI, escenario: GuardadosEscenario
) -> None:
    alias = crear_unidad(escenario)
    barrera = Barrier(2)
    with TestClient(aplicacion) as otro_sesion:
        iniciar_sesion(otro_sesion, "saved-first@example.test")

        def guardar(navegador: TestClient, id_equipo: int) -> dict:
            barrera.wait(timeout=10)
            respuesta = navegador.put(f"{BASE_URL}/{id_equipo}")
            assert respuesta.status_code == 200, respuesta.text
            return respuesta.json()

        with ThreadPoolExecutor(max_workers=2) as ejecutor:
            primero = ejecutor.submit(guardar, escenario.primero, escenario.id_equipo)
            segundo = ejecutor.submit(guardar, otro_sesion, alias)
            assert (
                primero.result(timeout=15)
                == segundo.result(timeout=15)
                == {"equipment_ids": [escenario.id_equipo]}
            )
    with aplicacion.state.fabrica_sesiones() as sesion:
        assert len(sesion.scalars(select(GuardadosProducto)).all()) == 1
    with aplicacion.state.fabrica_sesiones() as sesion:
        sesion.add(
            GuardadosProducto(
                id_usuario_cliente=escenario.primero_id, id_equipo=escenario.id_equipo
            )
        )
        with pytest.raises(IntegrityError):
            sesion.commit()


def test_guardados_productos_migracion_preserva_existentes_datos_y_revierte_correctamente(
    tmp_path: Path,
) -> None:
    servidor = Path(__file__).resolve().parents[1]
    configuracion = Config(str(servidor / "alembic.ini"))
    configuracion.set_main_option("script_location", str(servidor / "alembic"))
    url_base_datos = f"sqlite:///{(tmp_path / 'saved-products-migration.sqlite3').as_posix()}"
    configuracion.set_main_option("sqlalchemy.url", url_base_datos)
    motor = crear_base_datos_motor(url_base_datos)
    try:
        with motor.begin() as conexion:
            configuracion.attributes["connection"] = conexion
            command.upgrade(configuracion, "0009_reservation_origin")
            for sentencia in (
                "INSERT INTO users (id,name,email,password_hash,role,active) "
                "VALUES (7,'Cliente previo','previous@example.test','test-hash','customer',1)",
                "INSERT INTO equipment (id,code,name,category,description,active) "
                "VALUES (41,'OLD-CAM','Equipo previo','Cámaras','Nota interna privada',0)",
                "INSERT INTO reservations (id,equipment_id,customer_user_id,customer_name,"
                "customer_email,start_date,end_date,status,external_reference,origin) "
                "VALUES (52,41,7,'Cliente previo','previous@example.test','2026-11-10',"
                "'2026-11-12','confirmed','HISTORICAL','portal')",
                "INSERT INTO incidents (id,equipment_id,author_user_id,title,description,"
                "blocking,status,resolution,reservation_id) "
                "VALUES (63,41,7,'Aviso previo','Información sensible',0,'resolved','Reparada',52)",
                "INSERT INTO auth_sessions (id,expires_at,credential_version,user_id) "
                "VALUES ('" + "a" * 64 + "',2000000000,'" + "b" * 64 + "',7)",
            ):
                conexion.execute(text(sentencia))
            tablas = ("users", "equipment", "reservations", "incidents", "auth_sessions")

            def instantanea() -> dict:
                return {
                    tabla: list(conexion.execute(text(f"SELECT * FROM {tabla}")).mappings())
                    for tabla in tablas
                }

            antes = instantanea()
            command.upgrade(configuracion, "head")
            assert instantanea() == antes
            conexion.execute(
                text("INSERT INTO saved_products (customer_user_id,equipment_id) VALUES (7,41)")
            )
            assert conexion.execute(text("SELECT * FROM saved_products")).one() == (7, 41)
            assert conexion.scalar(text("PRAGMA integrity_check")) == "ok"
            assert conexion.execute(text("PRAGMA foreign_key_check")).all() == []
            command.check(configuracion)
            command.downgrade(configuracion, "0009_reservation_origin")
            assert instantanea() == antes
            command.upgrade(configuracion, "head")
            assert conexion.execute(text("SELECT * FROM saved_products")).all() == []
            assert instantanea() == antes
            assert conexion.execute(text("PRAGMA foreign_key_check")).all() == []
    finally:
        motor.dispose()
