import pytest
from conftest import autenticar
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from rentalab.compatibilidad import alias_json
from rentalab.configuracion import Configuracion
from rentalab.principal import crear_aplicacion


def test_crear_normaliza_y_devuelve_equipo(
    cliente_http: TestClient, equipo_contenido_envio: dict[str, object]
) -> None:
    equipo_contenido_envio.update(
        code="  cam-001  ",
        name="  Cámara de prueba  ",
        category="  Cámaras  ",
        description="  Unidad ficticia para las pruebas  ",
    )
    respuesta = cliente_http.post("/api/equipment", json=equipo_contenido_envio)

    assert respuesta.status_code == 201
    equipo = respuesta.json()
    assert isinstance(equipo["id"], int)
    assert equipo == {
        "id": equipo["id"],
        "code": "CAM-001",
        "name": "Cámara de prueba",
        "category": "Cámaras",
        "description": "Unidad ficticia para las pruebas",
        "public_description": "",
        "technical_specs": {},
        "image_url": None,
        "active": True,
    }
    assert respuesta.headers["location"] == f"/api/equipment/{equipo['id']}"
    assert cliente_http.get(respuesta.headers["location"]).json() == equipo


def test_crear_usa_opcionales_campo_predeterminados(cliente_http: TestClient) -> None:
    respuesta = cliente_http.post(
        "/api/equipment", json={"code": "CAM-1", "name": "Cámara", "category": "Vídeo"}
    )
    assert respuesta.status_code == 201
    assert respuesta.json()["description"] == ""
    assert respuesta.json()["active"] is True


def test_listar_es_ordenadas_y_puede_filtro_activo_equipo(
    cliente_http: TestClient, equipo_contenido_envio: dict[str, object]
) -> None:
    assert cliente_http.get("/api/equipment").json() == []
    for codigo, activo in [("Z-1", True), ("A-1", False), ("M-1", True)]:
        respuesta = cliente_http.post(
            "/api/equipment", json={**equipo_contenido_envio, "code": codigo, "active": activo}
        )
        assert respuesta.status_code == 201

    assert [elemento["code"] for elemento in cliente_http.get("/api/equipment").json()] == [
        "A-1",
        "M-1",
        "Z-1",
    ]
    assert [
        elemento["code"] for elemento in cliente_http.get("/api/equipment?active=true").json()
    ] == [
        "M-1",
        "Z-1",
    ]
    assert [
        elemento["code"] for elemento in cliente_http.get("/api/equipment?active=false").json()
    ] == ["A-1"]


def test_reemplazar_y_modificacion_preservar_la_fisica_unidad_id(
    cliente_http: TestClient, equipo_contenido_envio: dict[str, object]
) -> None:
    equipo = cliente_http.post("/api/equipment", json=equipo_contenido_envio).json()
    url = f"/api/equipment/{equipo['id']}"

    reemplazado = cliente_http.put(
        url,
        json={
            "code": "  cam_002 ",
            "name": "Nueva cámara",
            "category": "Vídeo",
            "description": "Descripción revisada",
            "active": False,
        },
    )
    assert reemplazado.status_code == 200
    assert reemplazado.json() == {
        "id": equipo["id"],
        "code": "CAM_002",
        "name": "Nueva cámara",
        "category": "Vídeo",
        "description": "Descripción revisada",
        "public_description": "",
        "technical_specs": {},
        "image_url": None,
        "active": False,
    }

    activated = cliente_http.patch(url, json={"active": True})
    assert activated.status_code == 200
    assert activated.json() == {**reemplazado.json(), "active": True}
    editado = cliente_http.patch(url, json={"name": "  Nombre corregido  "})
    assert editado.status_code == 200
    assert editado.json() == {**activated.json(), "name": "Nombre corregido"}
    assert cliente_http.get(url).json() == editado.json()
    assert cliente_http.patch(url, json={"active": False}).json()["active"] is False
    assert len(cliente_http.get("/api/equipment").json()) == 1


def test_reemplazar_restablece_opcionales_campos_a_predeterminados(
    cliente_http: TestClient, equipo_contenido_envio: dict[str, object]
) -> None:
    equipo = cliente_http.post(
        "/api/equipment", json={**equipo_contenido_envio, "active": False}
    ).json()
    respuesta = cliente_http.put(
        f"/api/equipment/{equipo['id']}",
        json={"code": "CAM-2", "name": "Cámara", "category": "Vídeo"},
    )
    assert respuesta.status_code == 200
    assert respuesta.json()["description"] == ""
    assert respuesta.json()["active"] is True


def test_duplicado_codigo_es_conflicto_despues_normalizacion(
    cliente_http: TestClient, equipo_contenido_envio: dict[str, object]
) -> None:
    assert cliente_http.post("/api/equipment", json=equipo_contenido_envio).status_code == 201
    respuesta = cliente_http.post(
        "/api/equipment", json={**equipo_contenido_envio, "code": "  cam-001 "}
    )
    assert respuesta.status_code == 409
    assert len(cliente_http.get("/api/equipment").json()) == 1


@pytest.mark.parametrize("metodo", ["put", "patch"])
def test_editar_no_puede_reutilizar_otra_unidades_codigo(
    cliente_http: TestClient, equipo_contenido_envio: dict[str, object], metodo: str
) -> None:
    primero = cliente_http.post("/api/equipment", json=equipo_contenido_envio).json()
    segundo = cliente_http.post(
        "/api/equipment", json={**equipo_contenido_envio, "code": "CAM-002"}
    ).json()
    contenido_envio = (
        {**equipo_contenido_envio, "code": " cam-001 "}
        if metodo == "put"
        else {"code": " cam-001 "}
    )
    respuesta = cliente_http.request(
        metodo, f"/api/equipment/{segundo['id']}", json=contenido_envio
    )
    assert respuesta.status_code == 409
    assert cliente_http.get(f"/api/equipment/{primero['id']}").json()["code"] == "CAM-001"
    assert cliente_http.get(f"/api/equipment/{segundo['id']}").json()["code"] == "CAM-002"


def test_editar_puede_mantener_su_propia_codigo(
    cliente_http: TestClient, equipo_contenido_envio: dict[str, object]
) -> None:
    equipo = cliente_http.post("/api/equipment", json=equipo_contenido_envio).json()
    respuesta = cliente_http.patch(f"/api/equipment/{equipo['id']}", json={"code": " cam-001 "})
    assert respuesta.status_code == 200
    assert respuesta.json() == equipo


@pytest.mark.parametrize("metodo", ["get", "put", "patch"])
def test_ausente_equipo_es_404(
    cliente_http: TestClient, equipo_contenido_envio: dict[str, object], metodo: str
) -> None:
    argumentos_clave = {} if metodo == "get" else {"json": equipo_contenido_envio}
    assert (
        cliente_http.request(metodo, "/api/equipment/99999", **argumentos_clave).status_code == 404
    )


@pytest.mark.parametrize(
    ("campo", "valor"),
    [
        ("code", ""),
        ("code", "   "),
        ("code", "X" * 41),
        ("code", "CAM 001"),
        ("code", "-CAM"),
        ("code", "CÁM-1"),
        ("code", "CAM/1"),
        ("code", None),
        ("code", 123),
        ("name", ""),
        ("name", "   "),
        ("name", "X" * 121),
        ("name", None),
        ("category", ""),
        ("category", "  "),
        ("category", "X" * 81),
        ("category", None),
        ("description", "X" * 2001),
        ("description", None),
        ("active", "false"),
        ("active", 0),
        ("active", 1),
        ("active", None),
        ("unknown", "unexpected"),
    ],
)
def test_invalido_creacion_es_rechazadas_sin_escribiendo(
    cliente_http: TestClient, equipo_contenido_envio: dict[str, object], campo: str, valor: object
) -> None:
    respuesta = cliente_http.post("/api/equipment", json={**equipo_contenido_envio, campo: valor})
    assert respuesta.status_code == 422
    assert cliente_http.get("/api/equipment").json() == []


@pytest.mark.parametrize("campo", ["name", "category", "description"])
@pytest.mark.parametrize("valor", ["\x00Texto", "Tex\x00to", "Texto\x00"])
def test_nul_creacion_es_rechazadas_sin_escrituras_y_siguiente_guardar_funciona(
    cliente_http: TestClient, equipo_contenido_envio: dict[str, object], campo: str, valor: str
) -> None:
    existentes = cliente_http.post("/api/equipment", json=equipo_contenido_envio)
    assert existentes.status_code == 201
    antes = cliente_http.get("/api/equipment").json()
    valido_contenido_envio = {**equipo_contenido_envio, "code": "CAM-002"}

    respuesta = cliente_http.post("/api/equipment", json={**valido_contenido_envio, campo: valor})

    assert respuesta.status_code == 422
    assert any(
        error["loc"][:2] == ["body", campo] and "NUL" in error["msg"]
        for error in respuesta.json()["detail"]
    )
    assert cliente_http.get("/api/equipment").json() == antes
    guardados = cliente_http.post("/api/equipment", json=valido_contenido_envio)
    assert guardados.status_code == 201
    assert len(cliente_http.get("/api/equipment").json()) == 2


@pytest.mark.parametrize("metodo", ["put", "patch"])
@pytest.mark.parametrize("campo", ["name", "category", "description"])
@pytest.mark.parametrize("valor", ["\x00Texto", "Tex\x00to", "Texto\x00"])
def test_nul_editar_no_puede_parcialmente_actualizar_y_siguiente_guardar_funciona(
    cliente_http: TestClient,
    equipo_contenido_envio: dict[str, object],
    metodo: str,
    campo: str,
    valor: str,
) -> None:
    equipo = cliente_http.post("/api/equipment", json=equipo_contenido_envio).json()
    antes = cliente_http.get("/api/equipment").json()
    url = f"/api/equipment/{equipo['id']}"
    cambios = {**equipo_contenido_envio, "code": "CAM-002", "active": False, campo: valor}

    respuesta = cliente_http.request(metodo, url, json=cambios)

    assert respuesta.status_code == 422
    assert any(
        error["loc"][:2] == ["body", campo] and "NUL" in error["msg"]
        for error in respuesta.json()["detail"]
    )
    assert cliente_http.get(url).json() == equipo
    assert cliente_http.get("/api/equipment").json() == antes
    guardados = cliente_http.request(
        metodo,
        url,
        json={
            **{alias_json(clave): valor for clave, valor in cambios.items()},
            campo: "Texto válido",
        },
    )
    assert guardados.status_code == 200
    assert guardados.json()[campo] == "Texto válido"
    assert guardados.json()["code"] == "CAM-002"
    assert guardados.json()["active"] is False
    assert len(cliente_http.get("/api/equipment").json()) == 1


@pytest.mark.parametrize("metodo", ["post", "put", "patch"])
def test_equipo_texto_preserva_unicode_y_recorta_exterior_espacios(
    cliente_http: TestClient, equipo_contenido_envio: dict[str, object], metodo: str
) -> None:
    url = "/api/equipment"
    if metodo != "post":
        equipo = cliente_http.post(url, json=equipo_contenido_envio).json()
        url = f"{url}/{equipo['id']}"
    respuesta = cliente_http.request(
        metodo,
        url,
        json={
            **equipo_contenido_envio,
            "name": "\u00a0Cámara Straße 東京\u00a0",
            "category": "\tVídeo e iluminación\u2003",
            "description": "\nÓptica útil — espacios  interiores.\u2003",
        },
    )

    assert respuesta.status_code == (201 if metodo == "post" else 200)
    assert respuesta.json()["name"] == "Cámara Straße 東京"
    assert respuesta.json()["category"] == "Vídeo e iluminación"
    assert respuesta.json()["description"] == "Óptica útil — espacios  interiores."


@pytest.mark.parametrize("campo", ["code", "name", "category"])
def test_creacion_requiere_obligatorios_campos(
    cliente_http: TestClient, equipo_contenido_envio: dict[str, object], campo: str
) -> None:
    del equipo_contenido_envio[campo]
    assert cliente_http.post("/api/equipment", json=equipo_contenido_envio).status_code == 422


@pytest.mark.parametrize(
    "contenido_envio",
    [
        {},
        {"active": None},
        {"active": "false"},
        {"name": "  "},
        {"code": "BAD CODE"},
        {"description": None},
        {"unknown": True},
    ],
)
def test_invalido_modificacion_es_rechazadas_sin_cambios(
    cliente_http: TestClient,
    equipo_contenido_envio: dict[str, object],
    contenido_envio: dict[str, object],
) -> None:
    equipo = cliente_http.post("/api/equipment", json=equipo_contenido_envio).json()
    url = f"/api/equipment/{equipo['id']}"
    assert cliente_http.patch(url, json=contenido_envio).status_code == 422
    assert cliente_http.get(url).json() == equipo


def test_put_requiere_la_completo_obligatorios_representacion(
    cliente_http: TestClient, equipo_contenido_envio: dict[str, object]
) -> None:
    equipo = cliente_http.post("/api/equipment", json=equipo_contenido_envio).json()
    url = f"/api/equipment/{equipo['id']}"
    assert cliente_http.put(url, json={"name": "Otro nombre"}).status_code == 422
    assert cliente_http.get(url).json() == equipo


def test_equipo_persiste_cuando_aplicacion_es_recreada(
    cliente_http: TestClient, equipo_contenido_envio: dict[str, object], ajustes: Configuracion
) -> None:
    original = cliente_http.post("/api/equipment", json=equipo_contenido_envio).json()
    aplicacion = crear_aplicacion(ajustes)
    try:
        with TestClient(aplicacion) as recreada_cliente:
            autenticar(recreada_cliente)
            assert recreada_cliente.get(f"/api/equipment/{original['id']}").json() == original
            assert recreada_cliente.get("/api/equipment").json() == [original]
    finally:
        aplicacion.state.motor.dispose()


@pytest.mark.parametrize(
    "bruto_codigo", ["CAM-001", "cam-002", " CAM-002 ", "CÁM-002", "BAD CODE", "CAM\x00bad"]
)
def test_sqlite_exige_unico_canonico_codigos(
    aplicacion: FastAPI,
    cliente_http: TestClient,
    equipo_contenido_envio: dict[str, object],
    bruto_codigo: str,
) -> None:
    assert cliente_http.post("/api/equipment", json=equipo_contenido_envio).status_code == 201
    with pytest.raises(IntegrityError), aplicacion.state.motor.begin() as conexion:
        conexion.execute(
            text(
                "INSERT INTO equipment (code, name, category, description, active) "
                "VALUES (:code, 'Direct unit', 'Test', '', 1)"
            ),
            {"code": bruto_codigo},
        )
