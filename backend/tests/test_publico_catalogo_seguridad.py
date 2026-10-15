import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

PUBLICO_EQUIPO_CAMPOS = {
    "id",
    "name",
    "category",
    "public_description",
    "technical_specs",
    "image_url",
    "image_fallback_url",
    "active_reservations_count",
}
PUBLICO_DISPONIBILIDAD_CAMPOS = {
    "equipment_id",
    "start_date",
    "end_date",
    "available",
    "status",
}


def crear_privado_equipo(cliente_http: TestClient, activo: bool = True) -> dict:
    respuesta = cliente_http.post(
        "/api/equipment",
        json={
            "code": "PRIVATE-CODE-CANARY",
            "name": "Cámara pública",
            "category": "Cámaras",
            "description": "INTERNAL-NOTE-CANARY",
            "public_description": "Cámara para proyectos audiovisuales",
            "technical_specs": {"Resolución": "4K"},
            "active": activo,
        },
    )
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()


def test_publico_esquema_hace_no_ampliar_cuando_un_administrador_es_autenticado(
    aplicacion: FastAPI, cliente_http: TestClient
) -> None:
    equipo = crear_privado_equipo(cliente_http)
    incidencia = cliente_http.post(
        "/api/incidents",
        json={
            "equipment_id": equipo["id"],
            "title": "PRIVATE-FAULT-TITLE-CANARY",
            "description": "PRIVATE-FAULT-DESCRIPTION-CANARY",
            "blocking": True,
        },
    )
    assert incidencia.status_code == 201
    rutas = [
        "/api/public/equipment",
        f"/api/public/equipment/{equipo['id']}",
        f"/api/public/equipment/{equipo['id']}/availability"
        "?start_date=2026-11-10&end_date=2026-11-12",
    ]
    with TestClient(aplicacion) as anonimo:
        for ruta in rutas:
            respuesta_publica = anonimo.get(ruta)
            administrativa_respuesta = cliente_http.get(ruta)
            assert respuesta_publica.status_code == administrativa_respuesta.status_code == 200
            assert respuesta_publica.json() == administrativa_respuesta.json()
            assert "PRIVATE-" not in respuesta_publica.text
            assert "INTERNAL-" not in respuesta_publica.text


@pytest.mark.parametrize("metodo", ["POST", "PUT", "PATCH", "DELETE"])
@pytest.mark.parametrize("suffix", ["", "/1"])
def test_publico_catalogo_nunca_acepta_gestion_escrituras(
    aplicacion: FastAPI, cliente_http: TestClient, metodo: str, suffix: str
) -> None:
    equipo = crear_privado_equipo(cliente_http)
    antes = cliente_http.get(f"/api/equipment/{equipo['id']}").json()
    # El administrador ya tiene el token CSRF vigente: incluso una sesión
    # administrativa válida debe usar el espacio protegido de gestión.
    with TestClient(aplicacion) as anonimo:
        ruta = f"/api/public/equipment{suffix}"
        for navegador in [anonimo, cliente_http]:
            respuesta = navegador.request(metodo, ruta, json={"name": "Mutated name"})
            assert respuesta.status_code in {401, 403, 405}
            assert "PRIVATE-CODE-CANARY" not in respuesta.text
            assert "INTERNAL-NOTE-CANARY" not in respuesta.text
    assert cliente_http.get(f"/api/equipment/{equipo['id']}").json() == antes
    assert len(cliente_http.get("/api/equipment").json()) == 1


def test_publico_error_respuestas_hacer_no_revelar_inactivo_equipo_o_privado_notas(
    aplicacion: FastAPI, cliente_http: TestClient
) -> None:
    equipo = crear_privado_equipo(cliente_http, activo=False)
    with TestClient(aplicacion) as anonimo:
        ausente = anonimo.get("/api/public/equipment/999999")
        inactivo = anonimo.get(f"/api/public/equipment/{equipo['id']}")
        no_disponible = anonimo.get(
            f"/api/public/equipment/{equipo['id']}/availability",
            params={"start_date": "2026-11-10", "end_date": "2026-11-12"},
        )
        assert ausente.status_code == inactivo.status_code == no_disponible.status_code == 404
        assert ausente.json() == inactivo.json() == no_disponible.json()
        invalido_fechas = anonimo.get(
            f"/api/public/equipment/{equipo['id']}/availability",
            params={"start_date": "2026-11-10"},
        )
        assert invalido_fechas.status_code == 422
        for respuesta in [ausente, inactivo, no_disponible, invalido_fechas]:
            assert "PRIVATE-CODE-CANARY" not in respuesta.text
            assert "INTERNAL-NOTE-CANARY" not in respuesta.text
            assert "Cámara pública" not in respuesta.text


def test_openapi_separa_explicito_publico_respuestas_desde_administrador_gestion(
    cliente_http: TestClient,
) -> None:
    respuesta = cliente_http.get("/api/openapi.json")
    assert respuesta.status_code == 200
    esquema = respuesta.json()
    publico_rutas = {
        "/api/public/equipment",
        "/api/public/equipment/{equipment_id}",
        "/api/public/equipment/{equipment_id}/availability",
    }
    for ruta in publico_rutas:
        operacion = esquema["paths"][ruta]["get"]
        assert operacion["security"] == []
        resultado = operacion["responses"]["200"]["content"]["application/json"]["schema"]
        if ruta == "/api/public/equipment":
            resultado = resultado["items"]
        modelo = esquema["components"]["schemas"][resultado["$ref"].split("/")[-1]]
        esperado = (
            PUBLICO_DISPONIBILIDAD_CAMPOS
            if ruta.endswith("/availability")
            else PUBLICO_EQUIPO_CAMPOS
        )
        assert set(modelo["properties"]) == esperado
    for ruta in [
        "/api/equipment",
        "/api/equipment/{equipment_id}",
        "/api/equipment/{equipment_id}/availability",
    ]:
        operacion = esquema["paths"][ruta]["get"]
        assert operacion["security"] == [{"SessionCookie": []}]
        assert "admin" in operacion["description"]
        assert {"401", "403"} <= set(operacion["responses"])
