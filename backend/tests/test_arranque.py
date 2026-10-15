import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError

from rentalab import arranque
from rentalab.autenticacion.esquemas import SolicitudRegistro
from rentalab.configuracion import Configuracion
from rentalab.principal import crear_aplicacion


@pytest.fixture
def arranque_configuracion(ajustes: Configuracion, tmp_path: Path) -> Configuracion:
    compilacion = tmp_path / "frontend" / "dist"
    compilacion.mkdir(parents=True)
    (compilacion / "index.html").write_text(
        "<!doctype html><title>RentaLab</title>", encoding="utf-8"
    )
    return ajustes.model_copy(update={"interfaz_compilada": compilacion})


def test_arranque_valida_autenticacion_antes_creando_o_migrando_base_datos(
    arranque_configuracion: Configuracion, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base_datos = tmp_path / "not-created" / "rentalab.db"
    invalido = arranque_configuracion.model_copy(
        update={"secreto_sesion": SecretStr("invalid"), "url_base_datos": f"sqlite:///{base_datos}"}
    )
    migrada: list[str] = []
    monkeypatch.setattr(arranque.command, "upgrade", lambda *_argumentos: migrada.append("upgrade"))
    with pytest.raises(ValueError, match="configuración de acceso"):
        arranque.preparar_arranque(invalido)
    assert migrada == []
    assert not base_datos.parent.exists()


def test_arranque_aplica_real_migraciones_sin_cargando_demostracion_datos(
    arranque_configuracion: Configuracion,
) -> None:
    arranque.preparar_arranque(arranque_configuracion)
    base_datos = Path(arranque_configuracion.url_base_datos.removeprefix("sqlite:///"))
    with sqlite3.connect(base_datos) as conexion:
        assert conexion.execute("SELECT version_num FROM alembic_version").fetchone() == (
            "0011_booking_requests",
        )
        for tabla in (
            "equipment",
            "users",
            "reservations",
            "incidents",
            "auth_sessions",
            "booking_requests",
            "booking_request_reservations",
        ):
            assert conexion.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone() == (0,)
        conexion.execute(
            "INSERT INTO equipment (code, name, category, description, active) "
            "VALUES ('PERSIST-001', 'Equipo previo', 'Pruebas', '', 1)"
        )
    arranque.preparar_arranque(arranque_configuracion)
    with sqlite3.connect(base_datos) as conexion:
        assert conexion.execute("SELECT code FROM equipment").fetchall() == [("PERSIST-001",)]


def test_reinicio_preserva_cuentas_sesiones_propiedad_y_cliente_informa(
    arranque_configuracion: Configuracion,
) -> None:
    """
    Recrea la aplicación y el motor sobre un archivo migrado, conservando las sesiones con
    cookies firmadas.
    """
    arranque.preparar_arranque(arranque_configuracion)
    base_datos = Path(arranque_configuracion.url_base_datos.removeprefix("sqlite:///"))
    contrasena = "restart-only-fictitious-password"
    aplicacion = crear_aplicacion(arranque_configuracion)
    administrador = aplicacion.state.autenticacion_servicio.registrar(
        SolicitudRegistro(
            nombre="Administración", correo="admin@example.test", contrasena=contrasena
        ),
        rol="admin",
    )

    def iniciar_sesion(navegador: TestClient, correo: str) -> None:
        token = navegador.get("/api/auth/csrf").json()["csrf_token"]
        respuesta = navegador.post(
            "/api/auth/login",
            json={"username": correo, "password": contrasena},
            headers={"X-CSRF-Token": token},
        )
        assert respuesta.status_code == 200
        navegador.headers["X-CSRF-Token"] = navegador.get("/api/auth/csrf").json()["csrf_token"]

    with TestClient(aplicacion) as administrador_http, TestClient(aplicacion) as cliente:
        iniciar_sesion(administrador_http, administrador.correo)
        token = cliente.get("/api/auth/csrf").json()["csrf_token"]
        respuesta = cliente.post(
            "/api/auth/register",
            json={"name": "Cliente", "email": "customer@example.test", "password": contrasena},
            headers={"X-CSRF-Token": token},
        )
        assert respuesta.status_code == 201
        propietario_id = respuesta.json()["id"]
        iniciar_sesion(cliente, "customer@example.test")
        unidad = administrador_http.post(
            "/api/equipment", json={"code": "PERSIST", "name": "Cámara", "category": "Vídeo"}
        )
        assert unidad.status_code == 201
        primero_dia = date.today() + timedelta(days=20)
        reserva = cliente.post(
            "/api/me/reservations",
            json={
                "equipment_id": unidad.json()["id"],
                "start_date": primero_dia.isoformat(),
                "end_date": (primero_dia + timedelta(days=2)).isoformat(),
            },
        )
        assert reserva.status_code == 201
        id_reserva = reserva.json()["id"]
        informe = cliente.post(
            f"/api/me/reservations/{id_reserva}/incidents",
            json={"title": "Aviso persistente", "description": "Descripción del cliente"},
        )
        assert informe.status_code == 201
        id_incidencia = informe.json()["id"]
        gestionado = administrador_http.patch(
            f"/api/incidents/{id_incidencia}",
            json={
                "blocking": True,
                "public_response": "Revisaremos el equipo",
                "internal_notes": "Sólo administración",
            },
        )
        assert gestionado.status_code == 200
        administrador_cookies = dict(administrador_http.cookies)
        cliente_cookies = dict(cliente.cookies)
        tablas = ("equipment", "users", "reservations", "incidents", "auth_sessions")
        with sqlite3.connect(base_datos) as conexion:
            antes = {
                tabla: conexion.execute(f"SELECT * FROM {tabla} ORDER BY id").fetchall()
                for tabla in tablas
            }
    # preparar_arranque es el punto de entrada que usa el contenedor antes de cada inicio HTTP.
    arranque.preparar_arranque(arranque_configuracion)
    reiniciado = crear_aplicacion(arranque_configuracion)
    with (
        TestClient(reiniciado, cookies=administrador_cookies) as administrador_http,
        TestClient(reiniciado, cookies=cliente_cookies) as cliente,
    ):
        with sqlite3.connect(base_datos) as conexion:
            for tabla, esperado in antes.items():
                assert conexion.execute(f"SELECT * FROM {tabla} ORDER BY id").fetchall() == esperado
            assert conexion.execute("PRAGMA integrity_check").fetchone() == ("ok",)
            assert conexion.execute("PRAGMA foreign_key_check").fetchall() == []
        assert administrador_http.get("/api/auth/session").json()["role"] == "admin"
        assert cliente.get("/api/auth/session").json()["user"]["id"] == propietario_id
        propia = cliente.get(f"/api/me/reservations/{id_reserva}")
        assert propia.status_code == 200
        assert propia.json() == reserva.json()
        global_reserva = administrador_http.get(f"/api/reservations/{id_reserva}").json()
        assert global_reserva["customer_user_id"] == propietario_id
        assert global_reserva["origin"] == "portal"
        propia_informe = cliente.get(f"/api/me/incidents/{id_incidencia}")
        assert propia_informe.status_code == 200
        assert propia_informe.json()["public_response"] == "Revisaremos el equipo"
        assert "internal_notes" not in propia_informe.json()
        incidencia = administrador_http.get(f"/api/incidents/{id_incidencia}").json()
        assert incidencia["blocking"] is True
        assert incidencia["internal_notes"] == "Sólo administración"
        # Un acceso nuevo también comprueba que se conservaron los hashes de las contraseñas.
        iniciar_sesion(cliente, "customer@example.test")
        assert cliente.get("/api/auth/session").json()["user"]["id"] == propietario_id


@pytest.mark.parametrize(
    "url_base_datos",
    ["sqlite:///:memory:", "postgresql://localhost/rentalab", "invalid-private-database-setting"],
)
def test_arranque_requiere_a_persistente_sqlite_archivo_antes_migrando(
    arranque_configuracion: Configuracion, monkeypatch: pytest.MonkeyPatch, url_base_datos: str
) -> None:
    migrada: list[str] = []
    monkeypatch.setattr(arranque.command, "upgrade", lambda *_argumentos: migrada.append("upgrade"))
    invalido = arranque_configuracion.model_copy(update={"url_base_datos": url_base_datos})
    with pytest.raises(arranque.ArranqueError, match="SQLite"):
        arranque.preparar_arranque(invalido)
    assert migrada == []


def test_arranque_requiere_interfaz_compilacion_antes_migrando(
    arranque_configuracion: Configuracion, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    migrada: list[str] = []
    monkeypatch.setattr(arranque.command, "upgrade", lambda *_argumentos: migrada.append("upgrade"))
    ausente = arranque_configuracion.model_copy(update={"interfaz_compilada": tmp_path / "missing"})
    with pytest.raises(arranque.ArranqueError, match="frontend"):
        arranque.preparar_arranque(ausente)
    assert migrada == []


def test_no_escribible_datos_directorio_detiene_antes_migraciones(
    arranque_configuracion: Configuracion, monkeypatch: pytest.MonkeyPatch
) -> None:
    migrada: list[str] = []

    def denegado(*_argumentos: object, **_argumentos_clave: object) -> None:
        raise PermissionError("sensitive internal path")

    monkeypatch.setattr(arranque.tempfile, "NamedTemporaryFile", denegado)
    monkeypatch.setattr(arranque.command, "upgrade", lambda *_argumentos: migrada.append("upgrade"))
    with pytest.raises(arranque.ArranqueError, match="permisos") as error:
        arranque.preparar_arranque(arranque_configuracion)
    assert "sensitive internal path" not in str(error.value)
    assert migrada == []


def test_principal_migra_antes_reemplazando_procesar_con_exactamente_una_trabajador(
    arranque_configuracion: Configuracion, monkeypatch: pytest.MonkeyPatch
) -> None:
    ajustes = arranque_configuracion.model_copy(
        update={"puerto": 8123, "ips_reenviadas_permitidas": "10.0.0.1"}
    )
    eventos: list[object] = []
    monkeypatch.setattr(arranque, "Configuracion", lambda: ajustes)
    monkeypatch.setattr(
        arranque, "preparar_arranque", lambda _configuracion: eventos.append("migrated")
    )
    monkeypatch.setenv("WEB_CONCURRENCY", "8")

    def reemplazar_procesar(executable: str, argumentos: list[str]) -> None:
        assert eventos == ["migrated"]
        eventos.append((executable, argumentos))

    monkeypatch.setattr(arranque.os, "execv", reemplazar_procesar)
    assert arranque.principal() == 0
    executable, argumentos = eventos[1]
    assert executable == sys.executable
    assert argumentos[:4] == [sys.executable, "-m", "uvicorn", "rentalab.principal:aplicacion"]
    assert argumentos[argumentos.index("--host") + 1] == "0.0.0.0"
    assert argumentos[argumentos.index("--port") + 1] == "8123"
    assert argumentos[argumentos.index("--workers") + 1] == "1"
    assert argumentos[argumentos.index("--forwarded-allow-ips") + 1] == "10.0.0.1"
    assert "--reload" not in argumentos
    assert "--proxy-headers" in argumentos


def test_migracion_fallida_no_inicia_http_ni_imprime_detalles_internos(
    arranque_configuracion: Configuracion,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fallar(*_argumentos: object) -> None:
        raise RuntimeError("secret-internal-database-diagnostic")

    ejecutado: list[object] = []
    monkeypatch.setattr(arranque, "Configuracion", lambda: arranque_configuracion)
    monkeypatch.setattr(arranque.command, "upgrade", fallar)
    monkeypatch.setattr(arranque.os, "execv", lambda *_argumentos: ejecutado.append("started"))
    assert arranque.principal() == 1
    salida = capsys.readouterr()
    assert "migraciones" in salida.err
    assert "secret-internal" not in salida.out + salida.err
    assert "Traceback" not in salida.err
    assert ejecutado == []


def test_principal_ausente_configuracion_tiene_a_generico_fallo_antes_lateral_efectos(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    base_datos = tmp_path / "missing" / "rentalab.db"
    monkeypatch.setattr(
        arranque,
        "Configuracion",
        lambda: Configuracion(
            _env_file=None,
            usuario_operador=None,
            hash_contrasena_operador=None,
            secreto_sesion=None,
            url_base_datos=f"sqlite:///{base_datos}",
        ),
    )
    assert arranque.principal() == 1
    assert "configuración de acceso" in capsys.readouterr().err
    assert not base_datos.parent.exists()


@pytest.mark.parametrize("puerto", [0, 65536])
def test_puerto_de_ejecucion_rechaza_valores_fuera_del_intervalo_tcp(puerto: int) -> None:
    with pytest.raises(ValidationError):
        Configuracion(_env_file=None, puerto=puerto)


def test_configuracion_de_ejecucion_se_lee_del_entorno(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RENTALAB_PORT", "8123")
    monkeypatch.setenv("RENTALAB_FORWARDED_ALLOW_IPS", "127.0.0.1,172.20.0.1")
    ajustes = Configuracion(_env_file=None)
    assert ajustes.puerto == 8123
    assert ajustes.ips_reenviadas_permitidas == "127.0.0.1,172.20.0.1"
