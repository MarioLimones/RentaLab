from datetime import datetime

import pytest
from conftest import PRUEBA_CONTRASENA, PRUEBA_NOMBRE_USUARIO, autenticar
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import Response

from rentalab.compatibilidad import alias_json
from rentalab.configuracion import Configuracion
from rentalab.principal import crear_aplicacion


def csrf(cliente_http: TestClient) -> str:
    respuesta = cliente_http.get("/api/auth/csrf")
    assert respuesta.status_code == 200
    return respuesta.json()["csrf_token"]


def iniciar_sesion(cliente_http: TestClient, token: str, **cambios: str) -> Response:
    return cliente_http.post(
        "/api/auth/login",
        json={
            "username": PRUEBA_NOMBRE_USUARIO,
            "password": PRUEBA_CONTRASENA,
            **{alias_json(clave): valor for clave, valor in cambios.items()},
        },
        headers={"X-CSRF-Token": token},
    )


@pytest.mark.parametrize(
    "metodo,ruta",
    [
        ("get", "/api/equipment"),
        ("get", "/api/equipment/1"),
        ("get", "/api/equipment/1/availability"),
        ("post", "/api/equipment"),
        ("get", "/api/reservations"),
        ("post", "/api/reservations"),
        ("post", "/api/reservations/1/cancel"),
        ("get", "/api/incidents"),
        ("post", "/api/incidents"),
        ("patch", "/api/incidents/1/status"),
        ("post", "/api/imports"),
        ("get", "/api/imports/example"),
        ("get", "/api/docs"),
        ("get", "/api/redoc"),
        ("get", "/api/openapi.json"),
    ],
)
def test_negocio_y_documentacion_exigir_a_sesion(
    aplicacion: FastAPI, metodo: str, ruta: str
) -> None:
    with TestClient(aplicacion) as anonimo:
        respuesta = anonimo.request(metodo, ruta)
    assert respuesta.status_code == 401
    assert set(respuesta.json()) == {"detail"}


def test_anonimo_sesion_es_401_pero_salud_y_csrf_son_publico(aplicacion: FastAPI) -> None:
    with TestClient(aplicacion) as anonimo:
        assert anonimo.get("/api/auth/session").status_code == 401
        assert anonimo.get("/health").json() == {"status": "ok"}
        respuesta = anonimo.get("/api/auth/csrf")
        assert respuesta.status_code == 200
        assert isinstance(respuesta.json()["csrf_token"], str)
        assert len(respuesta.json()["csrf_token"]) >= 32
        assert anonimo.get("/api/public/equipment").status_code == 200


def test_iniciar_sesion_requiere_a_sesion_vinculado_csrf_token(aplicacion: FastAPI) -> None:
    with TestClient(aplicacion) as anonimo:
        respuesta = anonimo.post(
            "/api/auth/login", json={"username": "operator", "password": "test"}
        )
        assert respuesta.status_code == 403
        assert set(respuesta.json()) == {"detail"}


def test_cookie_es_httponly_mismo_sitio_y_csrf_es_estable(aplicacion: FastAPI) -> None:
    with TestClient(aplicacion) as anonimo:
        primero = anonimo.get("/api/auth/csrf")
        assert primero.status_code == 200
        cookie = primero.headers["set-cookie"].lower()
        assert "rentalab_session=" in cookie
        assert "httponly" in cookie
        assert "samesite=lax" in cookie
        assert anonimo.get("/api/auth/csrf").json() == primero.json()


def test_correcto_iniciar_sesion_devuelve_la_real_operador(cliente_http: TestClient) -> None:
    respuesta = cliente_http.get("/api/auth/session")
    assert respuesta.status_code == 200
    sesion = respuesta.json()
    assert sesion["authenticated"] is True
    assert sesion["username"] == PRUEBA_NOMBRE_USUARIO
    assert datetime.fromisoformat(sesion["expires_at"]).tzinfo is not None


@pytest.mark.parametrize("cambios", [{"username": "unknown"}, {"password": "incorrect"}])
def test_incorrecto_credenciales_son_generico_y_hacer_no_autenticar(
    aplicacion: FastAPI, cambios: dict[str, str]
) -> None:
    with TestClient(aplicacion) as anonimo:
        respuesta = iniciar_sesion(anonimo, csrf(anonimo), **cambios)
        assert respuesta.status_code == 401
        detalle = respuesta.json()["detail"]
        assert isinstance(detalle, str)
        assert PRUEBA_NOMBRE_USUARIO not in detalle
        assert PRUEBA_CONTRASENA not in respuesta.text
        assert "argon2" not in respuesta.text.lower()
        assert anonimo.get("/api/auth/session").status_code == 401


def test_incorrecto_nombre_usuario_y_incorrecto_contrasena_recibir_la_mismo_error(
    aplicacion: FastAPI,
) -> None:
    with TestClient(aplicacion) as anonimo:
        token = csrf(anonimo)
        incorrecto_nombre_usuario = iniciar_sesion(anonimo, token, nombre_usuario="unknown")
        incorrecto_contrasena = iniciar_sesion(anonimo, token, contrasena="incorrect")
        assert incorrecto_nombre_usuario.status_code == incorrecto_contrasena.status_code == 401
        assert incorrecto_nombre_usuario.json() == incorrecto_contrasena.json()


def test_invalido_iniciar_sesion_contenido_envio_nunca_repite_la_contrasena(
    aplicacion: FastAPI,
) -> None:
    contrasena = "sensitive-password-never-reflected-" * 40
    with TestClient(aplicacion) as anonimo:
        respuesta = iniciar_sesion(anonimo, csrf(anonimo), contrasena=contrasena)
        assert respuesta.status_code == 422
        assert contrasena not in respuesta.text
        assert "input" not in respuesta.json()["detail"][0]


def test_iniciar_sesion_renueva_la_anonimo_cookie_y_csrf_token(aplicacion: FastAPI) -> None:
    with TestClient(aplicacion) as anonimo:
        original_token = csrf(anonimo)
        original_cookie = anonimo.cookies.get("rentalab_session")
        respuesta = iniciar_sesion(anonimo, original_token)
        assert respuesta.status_code == 200
        assert respuesta.json()["authenticated"] is True
        assert anonimo.cookies.get("rentalab_session") != original_cookie
        assert csrf(anonimo) != original_token
        rechazadas = anonimo.post("/api/auth/logout", headers={"X-CSRF-Token": original_token})
        assert rechazadas.status_code == 403
        assert anonimo.get("/api/auth/session").status_code == 200


def test_iniciar_sesion_rechaza_a_csrf_token_sin_su_cookie_o_desde_otra_navegador(
    aplicacion: FastAPI,
) -> None:
    with TestClient(aplicacion) as primero, TestClient(aplicacion) as segundo:
        token = csrf(primero)
        assert iniciar_sesion(segundo, token).status_code == 403
        csrf(segundo)
        assert iniciar_sesion(segundo, token).status_code == 403
        assert iniciar_sesion(primero, token).status_code == 200


@pytest.mark.parametrize("token", [None, "invalid-csrf-token"])
@pytest.mark.parametrize(
    "metodo,ruta",
    [
        ("post", "/api/equipment"),
        ("put", "/api/equipment/1"),
        ("patch", "/api/equipment/1"),
        ("post", "/api/reservations"),
        ("post", "/api/reservations/1/cancel"),
        ("post", "/api/incidents"),
        ("patch", "/api/incidents/1/status"),
        ("post", "/api/imports"),
        ("post", "/api/auth/logout"),
    ],
)
def test_autenticado_escrituras_exigir_csrf_antes_procesamiento_la_cuerpo(
    cliente_http: TestClient, token: str | None, metodo: str, ruta: str
) -> None:
    cliente_http.headers.pop("X-CSRF-Token")
    respuesta = cliente_http.request(
        metodo, ruta, headers={"X-CSRF-Token": token} if token is not None else {}
    )
    assert respuesta.status_code == 403
    assert set(respuesta.json()) == {"detail"}
    assert cliente_http.get("/api/equipment").json() == []


def test_lecturas_hacer_no_exigir_csrf_y_hacer_no_cambiar_negocio_datos(
    cliente_http: TestClient,
) -> None:
    cliente_http.headers.pop("X-CSRF-Token")
    for ruta in [
        "/api/equipment",
        "/api/reservations",
        "/api/incidents",
        "/api/imports/example",
        "/api/docs",
        "/api/redoc",
        "/api/openapi.json",
    ]:
        assert cliente_http.get(ruta).status_code == 200
    assert cliente_http.get("/api/equipment").json() == []
    assert cliente_http.get("/api/reservations").json() == []
    assert cliente_http.get("/api/incidents").json() == []


def test_cerrar_sesion_revoca_copiada_cookies_y_limpia_la_navegador_cookie(
    aplicacion: FastAPI, cliente_http: TestClient
) -> None:
    original_cookie = cliente_http.cookies.get("rentalab_session")
    respuesta = cliente_http.post("/api/auth/logout")
    assert respuesta.status_code == 200
    assert respuesta.json() == {"authenticated": False}
    assert "expires=thu, 01 jan 1970" in respuesta.headers["set-cookie"].lower()
    assert cliente_http.cookies.get("rentalab_session") is None
    assert cliente_http.get("/api/auth/session").status_code == 401
    with TestClient(aplicacion) as repetir:
        repetir.cookies.set("rentalab_session", original_cookie)
        assert repetir.get("/api/auth/session").status_code == 401
        assert repetir.get("/api/reservations").status_code == 401


def test_manipulada_sesion_cookie_no_puede_autenticar(aplicacion: FastAPI) -> None:
    with TestClient(aplicacion) as navegador:
        autenticar(navegador)
        original = navegador.cookies.get("rentalab_session")
        navegador.cookies.clear()
        navegador.cookies.set("rentalab_session", f"{original}tampered")
        assert navegador.get("/api/auth/session").status_code == 401
        assert navegador.get("/api/reservations").status_code == 401


def test_sesion_tiene_absoluto_servidor_caducidad_sin_extendiendo_al_actividad(
    aplicacion: FastAPI, cliente_http: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = cliente_http.get("/api/auth/session").json()
    caducidad = int(datetime.fromisoformat(original["expires_at"]).timestamp())
    monkeypatch.setattr(
        "rentalab.autenticacion.servicio.actual_marca_temporal", lambda: caducidad - 1
    )
    assert cliente_http.get("/api/auth/session").json() == original
    csrf(cliente_http)
    assert cliente_http.get("/api/equipment").status_code == 200
    assert cliente_http.get("/api/auth/session").json() == original
    monkeypatch.setattr("rentalab.autenticacion.servicio.actual_marca_temporal", lambda: caducidad)
    assert cliente_http.get("/api/auth/session").status_code == 401
    assert cliente_http.get("/api/reservations").status_code == 401
    assert cliente_http.post("/api/incidents", json={}).status_code == 401


def test_produccion_cookie_es_segura_y_la_spa_puede_permanecer_publico(
    aplicacion: FastAPI, ajustes: Configuracion
) -> None:
    produccion = crear_aplicacion(ajustes.model_copy(update={"entorno": "production"}))
    try:
        with TestClient(produccion, base_url="https://testserver") as navegador:
            respuesta = navegador.get("/api/auth/csrf")
            cookie = respuesta.headers["set-cookie"].lower()
            assert "secure" in cookie
            assert "httponly" in cookie
            assert "samesite=lax" in cookie
            autenticar(navegador)
            assert navegador.get("/api/equipment").status_code == 200
    finally:
        produccion.state.motor.dispose()


def test_unicode_nombre_usuario_y_exacto_contrasena_son_compatible(
    aplicacion: FastAPI, ajustes: Configuracion
) -> None:
    nombre_usuario = "Operador demostración 日本語"
    aplicacion = crear_aplicacion(
        ajustes.model_copy(update={"usuario_operador": f"  {nombre_usuario}  "})
    )
    try:
        with TestClient(aplicacion) as navegador:
            respuesta = iniciar_sesion(
                navegador, csrf(navegador), nombre_usuario=f"  {nombre_usuario}  "
            )
            assert respuesta.status_code == 200
            assert respuesta.json()["username"] == nombre_usuario
            assert navegador.get("/api/auth/session").json()["username"] == nombre_usuario
    finally:
        aplicacion.state.motor.dispose()


def test_cambiados_operador_credenciales_revocar_existentes_servidor_sesiones(
    aplicacion: FastAPI, ajustes: Configuracion, cliente_http: TestClient
) -> None:
    anterior_cookie = cliente_http.cookies.get("rentalab_session")
    cambiados = crear_aplicacion(
        ajustes.model_copy(update={"usuario_operador": "different-operator"})
    )
    try:
        with TestClient(cambiados) as navegador:
            navegador.cookies.set("rentalab_session", anterior_cookie)
            assert navegador.get("/api/auth/session").status_code == 401
            assert navegador.get("/api/reservations").status_code == 401
    finally:
        cambiados.state.motor.dispose()


def test_sin_autenticar_carga_es_rechazadas_antes_leyendo_su_cuerpo(aplicacion: FastAPI) -> None:
    consumido = False

    def carga():
        nonlocal consumido
        consumido = True
        yield b"This body must not be read without a valid session"

    with TestClient(aplicacion) as anonimo:
        solicitud = anonimo.build_request(
            "POST",
            "/api/imports",
            content=carga(),
            headers={"Content-Type": "multipart/form-data; boundary=missing"},
        )
        assert anonimo.send(solicitud).status_code == 401
        assert consumido is False


def test_autenticacion_respuestas_no_puede_ser_en_cache(
    aplicacion: FastAPI, cliente_http: TestClient
) -> None:
    assert cliente_http.get("/api/auth/session").headers["cache-control"] == "no-store"
    assert cliente_http.get("/api/auth/csrf").headers["cache-control"] == "no-store"
    with TestClient(aplicacion) as anonimo:
        assert anonimo.get("/api/auth/session").headers["cache-control"] == "no-store"
        assert anonimo.get("/api/equipment").headers["cache-control"] == "no-store"


def test_exclusivo_base_datos_bloqueo_durante_sesion_busqueda_es_a_controlados_temporal_fallo(
    aplicacion: FastAPI, ajustes: Configuracion
) -> None:
    segundo = crear_aplicacion(ajustes.model_copy(update={"espera_sqlite_ocupado_ms": 25}))
    try:
        with TestClient(segundo, raise_server_exceptions=False) as navegador:
            autenticar(navegador)
            with aplicacion.state.motor.connect() as bloqueo_propietario:
                bloqueo_propietario.exec_driver_sql("BEGIN EXCLUSIVE")
                respuesta = navegador.get("/api/equipment")
                assert respuesta.status_code == 503
                assert respuesta.headers["retry-after"] == "1"
                assert isinstance(respuesta.json()["detail"], str)
                assert "SELECT" not in respuesta.text
                assert "auth_sessions" not in respuesta.text
                bloqueo_propietario.rollback()
            assert navegador.get("/api/equipment").json() == []
    finally:
        segundo.state.motor.dispose()
