from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event

from rentalab.compatibilidad import alias_json

PUBLICO_CAMPOS = {
    "id",
    "name",
    "category",
    "public_description",
    "technical_specs",
    "image_url",
    "image_fallback_url",
    "active_reservations_count",
}
DISPONIBILIDAD_CAMPOS = {"equipment_id", "start_date", "end_date", "available", "status"}
FECHAS = {"start_date": "2026-11-10", "end_date": "2026-11-12"}


@pytest.fixture
def visitante(aplicacion: FastAPI) -> Iterator[TestClient]:
    with TestClient(aplicacion) as navegador:
        yield navegador


def crear_equipo(administrador_http: TestClient, **cambios: object) -> dict[str, Any]:
    respuesta = administrador_http.post(
        "/api/equipment",
        json={
            "code": "PRIVATE-CODE-001",
            "name": "Cámara de prueba",
            "category": "Cámaras",
            "description": "PRIVATE-INTERNAL-NOTE",
            **{alias_json(clave): valor for clave, valor in cambios.items()},
        },
    )
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()


def reservar_equipo(administrador_http: TestClient, id_equipo: object) -> dict[str, Any]:
    respuesta = administrador_http.post(
        "/api/reservations",
        json={
            "equipment_id": id_equipo,
            "customer_name": "PRIVATE-CUSTOMER-NAME",
            "customer_email": "private-customer@example.test",
            "external_reference": "PRIVATE-BOOKING-REFERENCE",
            **FECHAS,
        },
    )
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()


def informe_problema(
    administrador_http: TestClient, id_equipo: object, bloqueante: bool
) -> dict[str, Any]:
    respuesta = administrador_http.post(
        "/api/incidents",
        json={
            "equipment_id": id_equipo,
            "title": "PRIVATE-FAULT-TITLE",
            "description": "PRIVATE-FAULT-DESCRIPTION",
            "priority": "high",
            "blocking": bloqueante,
        },
    )
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()


def obtener_disponibilidad(
    visitante: TestClient, id_equipo: object, **fechas: str
) -> dict[str, Any]:
    respuesta = visitante.get(
        f"/api/public/equipment/{id_equipo}/availability",
        params={alias_json(clave): valor for clave, valor in (fechas or FECHAS).items()},
    )
    assert respuesta.status_code == 200, respuesta.text
    assert set(respuesta.json()) == DISPONIBILIDAD_CAMPOS
    return respuesta.json()


def test_vacio_catalogo_es_publico(visitante: TestClient) -> None:
    respuesta = visitante.get("/api/public/equipment")
    assert respuesta.status_code == 200
    assert respuesta.json() == []


def test_catalogo_proyecta_solo_publico_campos_y_local_imagen_alternativa(
    cliente_http: TestClient, visitante: TestClient
) -> None:
    equipo = crear_equipo(
        cliente_http,
        descripcion_publica="Cámara ficticia compacta para entrevistas y eventos.",
        caracteristicas_tecnicas={"Resolución": "4K UHD", "Conexiones": "HDMI, USB-C"},
    )
    esperado = {
        "id": equipo["id"],
        "name": "Cámara de prueba",
        "category": "Cámaras",
        "public_description": "Cámara ficticia compacta para entrevistas y eventos.",
        "technical_specs": {"Resolución": "4K UHD", "Conexiones": "HDMI, USB-C"},
        "image_url": None,
        "image_fallback_url": "/api/public/images/equipment-placeholder.svg",
        "active_reservations_count": 0,
    }
    for navegador in (visitante, cliente_http):
        listado = navegador.get("/api/public/equipment")
        detalle = navegador.get(f"/api/public/equipment/{equipo['id']}")
        assert listado.status_code == detalle.status_code == 200
        assert listado.json() == [esperado]
        assert detalle.json() == esperado
        assert set(detalle.json()) == PUBLICO_CAMPOS
        assert "PRIVATE-" not in listado.text + detalle.text
    imagen = visitante.get(esperado["image_fallback_url"])
    assert imagen.status_code == 200
    assert imagen.headers["content-type"].startswith("image/svg+xml")
    assert "<svg" in imagen.text
    assert "http://" not in imagen.text.replace("http://www.w3.org/2000/svg", "")
    assert "https://" not in imagen.text


def test_catalogo_excluye_inactivo_grupos_modelos_y_ordenes_por_nombre_despues_id(
    cliente_http: TestClient, visitante: TestClient
) -> None:
    ultimo = crear_equipo(cliente_http, codigo="EQUIP-01", nombre="Zeta")
    primero = crear_equipo(cliente_http, codigo="EQUIP-02", nombre="Alfa")
    crear_equipo(cliente_http, codigo="EQUIP-03", nombre="Alfa")
    crear_equipo(cliente_http, codigo="EQUIP-04", nombre="A oculto", activo=False)
    respuesta = visitante.get("/api/public/equipment")
    assert respuesta.status_code == 200
    assert [elemento["id"] for elemento in respuesta.json()] == [primero["id"], ultimo["id"]]


@pytest.mark.parametrize("consulta", ["CÁMARA", "cámara", "  CÁMARA  ", "mara de pru"])
def test_busqueda_coincidencias_nombre_subcadenas_con_unicode_normalizacion_mayusculas(
    cliente_http: TestClient, visitante: TestClient, consulta: str
) -> None:
    coincidencia = crear_equipo(cliente_http)
    crear_equipo(cliente_http, codigo="LIGHT-02", nombre="Foco LED", descripcion="Cámara interna")
    respuesta = visitante.get("/api/public/equipment", params={"q": consulta})
    assert respuesta.status_code == 200
    assert [elemento["id"] for elemento in respuesta.json()] == [coincidencia["id"]]


@pytest.mark.parametrize("consulta", ["%", "_", "' OR 1=1 --"])
def test_busqueda_trata_sql_comodines_y_sintaxis_como_literal_texto(
    cliente_http: TestClient, visitante: TestClient, consulta: str
) -> None:
    coincidencia = crear_equipo(cliente_http, nombre=f"Equipo {consulta}")
    crear_equipo(cliente_http, codigo="OTHER-02", nombre="Equipo diferente")
    respuesta = visitante.get("/api/public/equipment", params={"q": consulta})
    assert respuesta.status_code == 200
    assert [elemento["id"] for elemento in respuesta.json()] == [coincidencia["id"]]


@pytest.mark.parametrize("categoria", ["CÁMARAS", "cámaras", "  CáMaRaS  "])
def test_categoria_filtro_es_exacto_y_caso_indiferente(
    cliente_http: TestClient, visitante: TestClient, categoria: str
) -> None:
    coincidencia = crear_equipo(cliente_http)
    crear_equipo(cliente_http, codigo="OTHER-02", categoria="Cámaras de acción")
    respuesta = visitante.get("/api/public/equipment", params={"category": categoria})
    assert respuesta.status_code == 200
    assert [elemento["id"] for elemento in respuesta.json()] == [coincidencia["id"]]


def test_busqueda_y_categoria_combinar_y_desconocido_valores_devolver_vacio_listar(
    cliente_http: TestClient, visitante: TestClient
) -> None:
    coincidencia = crear_equipo(cliente_http, nombre="Compacta 4K")
    crear_equipo(cliente_http, codigo="OTHER-02", nombre="Compacta LED", categoria="Iluminación")
    crear_equipo(cliente_http, codigo="OTHER-03", nombre="Profesional", categoria="Cámaras")
    respuesta = visitante.get(
        "/api/public/equipment", params={"q": "compacta", "category": "cámaras"}
    )
    assert respuesta.status_code == 200
    assert [elemento["id"] for elemento in respuesta.json()] == [coincidencia["id"]]
    assert visitante.get("/api/public/equipment", params={"q": "ausente"}).json() == []
    assert visitante.get("/api/public/equipment", params={"category": "ausente"}).json() == []


def test_filtros_uso_completa_unicode_normalizacion_mayusculas_y_ignorar_vacio_valores(
    cliente_http: TestClient, visitante: TestClient
) -> None:
    equipo = crear_equipo(cliente_http, nombre="Straße cámara", categoria="Maße")
    respuesta = visitante.get("/api/public/equipment", params={"q": "STRASSE", "category": "MASSE"})
    assert respuesta.status_code == 200
    assert [elemento["id"] for elemento in respuesta.json()] == [equipo["id"]]
    sin_filtrar = visitante.get("/api/public/equipment", params={"q": "  ", "category": ""})
    assert sin_filtrar.status_code == 200
    assert [elemento["id"] for elemento in sin_filtrar.json()] == [equipo["id"]]


@pytest.mark.parametrize(
    "filtros",
    [{"q": "x" * 121}, {"category": "x" * 81}, {"q": "bad\x00text"}, {"active": "false"}],
)
def test_catalogo_rechaza_invalido_o_administrativa_filtros(
    visitante: TestClient, filtros: dict[str, str]
) -> None:
    assert visitante.get("/api/public/equipment", params=filtros).status_code == 422


@pytest.mark.parametrize("suffix", ["", "/availability"])
def test_inactivo_y_ausente_equipo_tienen_identico_publico_404(
    cliente_http: TestClient, visitante: TestClient, suffix: str
) -> None:
    equipo = crear_equipo(cliente_http, activo=False)
    inactivo = visitante.get(f"/api/public/equipment/{equipo['id']}{suffix}")
    ausente = visitante.get(f"/api/public/equipment/999999{suffix}")
    assert inactivo.status_code == ausente.status_code == 404
    assert inactivo.json() == ausente.json() == {"detail": "El equipo no existe"}


def test_sin_fechas_requiere_seleccion_y_hace_no_consulta_privado_historial(
    aplicacion: FastAPI, cliente_http: TestClient, visitante: TestClient
) -> None:
    equipo = crear_equipo(cliente_http)
    reservar_equipo(cliente_http, equipo["id"])
    informe_problema(cliente_http, equipo["id"], bloqueante=True)
    consultas: list[str] = []

    def registro_consulta(_conexion: Any, _cursor: Any, sentencia: str, *_argumentos: Any) -> None:
        consultas.append(sentencia)

    event.listen(aplicacion.state.motor, "before_cursor_execute", registro_consulta)
    try:
        respuesta = visitante.get(f"/api/public/equipment/{equipo['id']}/availability")
    finally:
        event.remove(aplicacion.state.motor, "before_cursor_execute", registro_consulta)
    assert respuesta.status_code == 200
    assert respuesta.json() == {
        "equipment_id": equipo["id"],
        "start_date": None,
        "end_date": None,
        "available": None,
        "status": "select_dates",
    }
    assert not any("reservations" in consulta or "incidents" in consulta for consulta in consultas)


@pytest.mark.parametrize(
    "fechas",
    [
        {"start_date": "2026-11-10"},
        {"end_date": "2026-11-12"},
        {"start_date": "2026-11-10", "end_date": "2026-11-10"},
        {"start_date": "2026-11-12", "end_date": "2026-11-10"},
        {"start_date": "2026-02-30", "end_date": "2026-11-12"},
        {"start_date": "2026-11-10T00:00:00", "end_date": "2026-11-12"},
        {"start_date": "2026-1-01", "end_date": "2026-11-12"},
        {"start_date": "1794268800", "end_date": "2026-11-12"},
        {"start_date": "", "end_date": "2026-11-12"},
    ],
)
def test_invalido_y_parcial_fecha_intervalos_son_422(
    cliente_http: TestClient, visitante: TestClient, fechas: dict[str, str]
) -> None:
    equipo = crear_equipo(cliente_http)
    respuesta = visitante.get(f"/api/public/equipment/{equipo['id']}/availability", params=fechas)
    assert respuesta.status_code == 422


def test_libre_equipo_devuelve_fechas_y_disponible_estado(
    cliente_http: TestClient, visitante: TestClient
) -> None:
    equipo = crear_equipo(cliente_http)
    assert obtener_disponibilidad(visitante, equipo["id"]) == {
        "equipment_id": equipo["id"],
        **FECHAS,
        "available": True,
        "status": "available",
    }


@pytest.mark.parametrize(
    ("fecha_inicio", "fecha_fin", "esperado"),
    [
        ("2026-11-09", "2026-11-10", True),
        ("2026-11-12", "2026-11-13", True),
        ("2026-11-09", "2026-11-11", False),
        ("2026-11-11", "2026-11-13", False),
        ("2026-11-10", "2026-11-12", False),
        ("2026-11-09", "2026-11-13", False),
        ("2026-11-10", "2026-11-11", False),
    ],
)
def test_publico_y_administrativa_disponibilidad_comparten_dia_solapamiento_reglas(
    cliente_http: TestClient,
    visitante: TestClient,
    fecha_inicio: str,
    fecha_fin: str,
    esperado: bool,
) -> None:
    equipo = crear_equipo(cliente_http)
    reservar_equipo(cliente_http, equipo["id"])
    fechas = {"start_date": fecha_inicio, "end_date": fecha_fin}
    publico = obtener_disponibilidad(visitante, equipo["id"], **fechas)
    administrativa = cliente_http.get(f"/api/equipment/{equipo['id']}/availability", params=fechas)
    assert administrativa.status_code == 200
    assert publico["available"] is administrativa.json()["available"] is esperado
    assert publico["status"] == ("available" if esperado else "unavailable")


def test_canceladas_reserva_libera_su_dias_y_otra_producto_es_no_afectado(
    cliente_http: TestClient, visitante: TestClient
) -> None:
    equipo = crear_equipo(cliente_http)
    otro = crear_equipo(cliente_http, codigo="OTHER-02", nombre="Otro modelo")
    reserva = reservar_equipo(cliente_http, equipo["id"])
    assert obtener_disponibilidad(visitante, equipo["id"])["available"] is False
    assert obtener_disponibilidad(visitante, otro["id"])["available"] is True
    assert cliente_http.post(f"/api/reservations/{reserva['id']}/cancel").status_code == 200
    assert obtener_disponibilidad(visitante, equipo["id"])["available"] is True


@pytest.mark.parametrize("bloqueante", [False, True])
@pytest.mark.parametrize("estado", ["open", "in_progress", "resolved"])
def test_incidencia_reglas_son_compartido_sin_revelando_fallos(
    cliente_http: TestClient, visitante: TestClient, bloqueante: bool, estado: str
) -> None:
    equipo = crear_equipo(cliente_http)
    incidencia = informe_problema(cliente_http, equipo["id"], bloqueante)
    if estado != "open":
        cambiar: dict[str, object] = {"status": estado}
        if estado == "resolved":
            cambiar["resolution"] = "PRIVATE-FAULT-RESOLUTION"
        assert (
            cliente_http.patch(
                f"/api/incidents/{incidencia['id']}/status", json=cambiar
            ).status_code
            == 200
        )
    esperado = not (bloqueante and estado != "resolved")
    for navegador in (visitante, cliente_http):
        publico = obtener_disponibilidad(navegador, equipo["id"])
        assert publico["available"] is esperado
        assert publico["status"] == ("available" if esperado else "unavailable")
        assert "PRIVATE-" not in str(publico)
    administrativa = cliente_http.get(f"/api/equipment/{equipo['id']}/availability", params=FECHAS)
    assert administrativa.status_code == 200
    assert administrativa.json()["available"] is esperado


def test_privado_cliente_y_reserva_datos_hacer_no_aparecen_en_cualquier_publico_respuesta(
    cliente_http: TestClient, visitante: TestClient
) -> None:
    equipo = crear_equipo(cliente_http)
    reservar_equipo(cliente_http, equipo["id"])
    informe_problema(cliente_http, equipo["id"], bloqueante=True)
    rutas = [
        "/api/public/equipment",
        f"/api/public/equipment/{equipo['id']}",
        f"/api/public/equipment/{equipo['id']}/availability",
    ]
    for navegador in (visitante, cliente_http):
        for ruta in rutas:
            respuesta = navegador.get(
                ruta, params=FECHAS if ruta.endswith("availability") else None
            )
            assert respuesta.status_code == 200
            assert "PRIVATE-" not in respuesta.text
            assert "private-customer@example.test" not in respuesta.text
            filas = respuesta.json() if isinstance(respuesta.json(), list) else [respuesta.json()]
            for fila in filas:
                esperado_claves = (
                    DISPONIBILIDAD_CAMPOS if ruta.endswith("availability") else PUBLICO_CAMPOS
                )
                assert set(fila) == esperado_claves
