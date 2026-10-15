from typing import Any

import pytest
from conftest import autenticar
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from rentalab.compatibilidad import alias_json
from rentalab.configuracion import Configuracion
from rentalab.principal import crear_aplicacion


@pytest.fixture
def incidencia_contenido_envio(
    cliente_http: TestClient, equipo_contenido_envio: dict[str, object]
) -> dict[str, object]:
    equipo = cliente_http.post("/api/equipment", json=equipo_contenido_envio)
    assert equipo.status_code == 201
    return {"equipment_id": equipo.json()["id"], "title": "Conector de audio defectuoso"}


def crear_incidencia(
    cliente_http: TestClient, contenido_envio: dict[str, object], **cambios: object
) -> dict[str, Any]:
    respuesta = cliente_http.post(
        "/api/incidents",
        json={**contenido_envio, **{alias_json(clave): valor for clave, valor in cambios.items()}},
    )
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()


def reservar_equipo(
    cliente_http: TestClient, id_equipo: object, **cambios: object
) -> dict[str, Any]:
    respuesta = cliente_http.post(
        "/api/reservations",
        json={
            "equipment_id": id_equipo,
            "customer_name": "Cliente ficticio",
            "customer_email": "incidents@example.test",
            "start_date": "2026-11-10",
            "end_date": "2026-11-12",
            **{alias_json(clave): valor for clave, valor in cambios.items()},
        },
    )
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()


def disponibilidad(cliente_http: TestClient, id_equipo: object) -> dict[str, Any]:
    respuesta = cliente_http.get(
        f"/api/equipment/{id_equipo}/availability",
        params={"start_date": "2026-11-10", "end_date": "2026-11-12"},
    )
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()


def test_crear_normaliza_predeterminados_y_recupera_un_abrir_incidencia(
    cliente_http: TestClient, incidencia_contenido_envio: dict[str, object]
) -> None:
    respuesta = cliente_http.post(
        "/api/incidents",
        json={**incidencia_contenido_envio, "title": "  Conector de audio defectuoso  "},
    )
    assert respuesta.status_code == 201
    incidencia = respuesta.json()
    assert isinstance(incidencia["id"], int)
    assert incidencia == {
        **incidencia_contenido_envio,
        "id": incidencia["id"],
        "reservation_id": None,
        "author_user_id": None,
        "description": "",
        "priority": "medium",
        "blocking": False,
        "status": "open",
        "resolution": "",
        "public_response": "",
        "internal_notes": "",
        "confirmed_reservation_ids": [],
        "warning": None,
    }
    assert respuesta.headers["location"] == f"/api/incidents/{incidencia['id']}"
    assert cliente_http.get(respuesta.headers["location"]).json() == incidencia
    assert cliente_http.get("/api/incidents").json() == [incidencia]


@pytest.mark.parametrize("prioridad", ["low", "medium", "high"])
@pytest.mark.parametrize("bloqueante", [False, True])
def test_crear_acepta_cada_prioridad_y_explicito_bloqueante_modo(
    cliente_http: TestClient,
    incidencia_contenido_envio: dict[str, object],
    prioridad: str,
    bloqueante: bool,
) -> None:
    incidencia = crear_incidencia(
        cliente_http,
        incidencia_contenido_envio,
        descripcion="  Inspección técnica ficticia  ",
        prioridad=prioridad,
        bloqueante=bloqueante,
    )
    assert incidencia["description"] == "Inspección técnica ficticia"
    assert incidencia["priority"] == prioridad
    assert incidencia["blocking"] is bloqueante


def test_incidencias_puede_ser_registrado_para_un_inactivo_unidad(
    cliente_http: TestClient, incidencia_contenido_envio: dict[str, object]
) -> None:
    id_equipo = incidencia_contenido_envio["equipment_id"]
    cliente_http.patch(f"/api/equipment/{id_equipo}", json={"active": False})
    incidencia = crear_incidencia(cliente_http, incidencia_contenido_envio, bloqueante=True)
    assert incidencia["equipment_id"] == id_equipo
    assert incidencia["status"] == "open"


@pytest.mark.parametrize("ruta", [["in_progress"], ["resolved"], ["in_progress", "resolved"]])
def test_permitidos_transiciones_preservar_la_incidencia_y_recortar_resolucion(
    cliente_http: TestClient, incidencia_contenido_envio: dict[str, object], ruta: list[str]
) -> None:
    original = crear_incidencia(
        cliente_http, incidencia_contenido_envio, bloqueante=True, prioridad="high"
    )
    real = original
    for estado in ruta:
        cuerpo = {"status": estado}
        if estado == "resolved":
            cuerpo["resolution"] = "  Conector sustituido en taller ficticio  "
        respuesta = cliente_http.patch(f"/api/incidents/{original['id']}/status", json=cuerpo)
        assert respuesta.status_code == 200
        real = respuesta.json()
        assert real == {
            **original,
            "status": estado,
            "resolution": "Conector sustituido en taller ficticio" if estado == "resolved" else "",
        }
    assert cliente_http.get(f"/api/incidents/{original['id']}").json() == real
    assert cliente_http.get("/api/incidents").json() == [real]


@pytest.mark.parametrize(
    ("inicial", "objetivo"),
    [
        ("open", "open"),
        ("in_progress", "in_progress"),
        ("in_progress", "open"),
        ("resolved", "resolved"),
        ("resolved", "open"),
        ("resolved", "in_progress"),
    ],
)
def test_repetidas_retroceso_y_terminal_transiciones_son_conflictos_sin_cambios(
    cliente_http: TestClient,
    incidencia_contenido_envio: dict[str, object],
    inicial: str,
    objetivo: str,
) -> None:
    incidencia = crear_incidencia(cliente_http, incidencia_contenido_envio)
    url = f"/api/incidents/{incidencia['id']}/status"
    if inicial != "open":
        cuerpo = {"status": inicial}
        if inicial == "resolved":
            cuerpo["resolution"] = "Reparación original"
        respuesta = cliente_http.patch(url, json=cuerpo)
        assert respuesta.status_code == 200
        incidencia = respuesta.json()
    cuerpo = {"status": objetivo}
    if objetivo == "resolved":
        cuerpo["resolution"] = "Intento de reemplazar el historial"
    respuesta = cliente_http.patch(url, json=cuerpo)
    assert respuesta.status_code == 409
    assert isinstance(respuesta.json()["detail"], str)
    assert cliente_http.get(f"/api/incidents/{incidencia['id']}").json() == incidencia


@pytest.mark.parametrize(
    "cuerpo",
    [
        {},
        {"status": "invalid"},
        {"status": None},
        {"status": "resolved"},
        {"status": "resolved", "resolution": None},
        {"status": "resolved", "resolution": ""},
        {"status": "resolved", "resolution": "   "},
        {"status": "resolved", "resolution": "X" * 2001},
        {"status": "resolved", "resolution": "Repair\x00bad"},
        {"status": "resolved", "resolution": 12},
        {"status": "in_progress", "resolution": ""},
        {"status": "in_progress", "resolution": "Premature repair"},
        {"status": "in_progress", "blocking": False},
        {"status": "in_progress", "unknown": True},
    ],
)
def test_invalido_estado_cambios_son_422_y_preservar_la_original(
    cliente_http: TestClient,
    incidencia_contenido_envio: dict[str, object],
    cuerpo: dict[str, object],
) -> None:
    incidencia = crear_incidencia(cliente_http, incidencia_contenido_envio)
    respuesta = cliente_http.patch(f"/api/incidents/{incidencia['id']}/status", json=cuerpo)
    assert respuesta.status_code == 422
    assert cliente_http.get(f"/api/incidents/{incidencia['id']}").json() == incidencia


def test_nulo_resolucion_es_permitidos_para_la_en_progreso_transicion(
    cliente_http: TestClient, incidencia_contenido_envio: dict[str, object]
) -> None:
    incidencia = crear_incidencia(cliente_http, incidencia_contenido_envio)
    respuesta = cliente_http.patch(
        f"/api/incidents/{incidencia['id']}/status",
        json={"status": "in_progress", "resolution": None},
    )
    assert respuesta.status_code == 200
    assert respuesta.json()["resolution"] == ""


def test_bloqueante_incidencia_impide_reserva_hasta_resuelta(
    cliente_http: TestClient, incidencia_contenido_envio: dict[str, object]
) -> None:
    id_equipo = incidencia_contenido_envio["equipment_id"]
    incidencia = crear_incidencia(cliente_http, incidencia_contenido_envio, bloqueante=True)
    esperado = {
        "equipment_id": id_equipo,
        "start_date": "2026-11-10",
        "end_date": "2026-11-12",
        "available": False,
        "reason": "blocking_incident",
        "conflicting_reservation_ids": [],
    }
    assert disponibilidad(cliente_http, id_equipo) == esperado
    reserva = {
        "equipment_id": id_equipo,
        "customer_name": "Cliente ficticio",
        "customer_email": "blocked@example.test",
        "start_date": "2026-11-10",
        "end_date": "2026-11-12",
    }
    assert cliente_http.post("/api/reservations", json=reserva).status_code == 409
    assert cliente_http.get("/api/reservations").json() == []
    url = f"/api/incidents/{incidencia['id']}/status"
    assert cliente_http.patch(url, json={"status": "in_progress"}).status_code == 200
    assert disponibilidad(cliente_http, id_equipo) == esperado
    assert cliente_http.post("/api/reservations", json=reserva).status_code == 409
    assert (
        cliente_http.patch(url, json={"status": "resolved", "resolution": "Reparación"}).status_code
        == 200
    )
    assert disponibilidad(cliente_http, id_equipo) == {
        **esperado,
        "available": True,
        "reason": None,
    }
    assert cliente_http.post("/api/reservations", json=reserva).status_code == 201
    assert cliente_http.get(f"/api/incidents/{incidencia['id']}").json()["status"] == "resolved"


def test_multiples_bloqueante_incidencias_exigir_resolviendo_la_ultimo_una(
    cliente_http: TestClient, incidencia_contenido_envio: dict[str, object]
) -> None:
    id_equipo = incidencia_contenido_envio["equipment_id"]
    primero = crear_incidencia(cliente_http, incidencia_contenido_envio, bloqueante=True)
    segundo = crear_incidencia(cliente_http, incidencia_contenido_envio, bloqueante=True)
    crear_incidencia(cliente_http, incidencia_contenido_envio, bloqueante=False)
    for incidencia in (primero, segundo):
        respuesta = cliente_http.patch(
            f"/api/incidents/{incidencia['id']}/status",
            json={"status": "resolved", "resolution": "Reparación ficticia"},
        )
        assert respuesta.status_code == 200
        assert disponibilidad(cliente_http, id_equipo)["available"] is (incidencia == segundo)
    assert len(cliente_http.get("/api/incidents").json()) == 3
    reservar_equipo(cliente_http, id_equipo)


@pytest.mark.parametrize("estado", ["open", "in_progress"])
def test_no_bloqueante_sin_resolver_incidencias_hacer_no_bloqueo_reservas(
    cliente_http: TestClient, incidencia_contenido_envio: dict[str, object], estado: str
) -> None:
    incidencia = crear_incidencia(cliente_http, incidencia_contenido_envio, bloqueante=False)
    if estado == "in_progress":
        assert (
            cliente_http.patch(
                f"/api/incidents/{incidencia['id']}/status", json={"status": estado}
            ).status_code
            == 200
        )
    assert (
        disponibilidad(cliente_http, incidencia_contenido_envio["equipment_id"])["available"]
        is True
    )
    reservar_equipo(cliente_http, incidencia_contenido_envio["equipment_id"])


def test_indisponibilidad_motivo_prioridad_y_reservas_son_conservado(
    cliente_http: TestClient, incidencia_contenido_envio: dict[str, object]
) -> None:
    id_equipo = incidencia_contenido_envio["equipment_id"]
    reserva = reservar_equipo(cliente_http, id_equipo)
    incidencia = crear_incidencia(cliente_http, incidencia_contenido_envio, bloqueante=True)
    assert disponibilidad(cliente_http, id_equipo)["reason"] == "blocking_incident"
    assert disponibilidad(cliente_http, id_equipo)["conflicting_reservation_ids"] == []
    cliente_http.patch(f"/api/equipment/{id_equipo}", json={"active": False})
    assert disponibilidad(cliente_http, id_equipo)["reason"] == "equipment_inactive"
    assert (
        cliente_http.patch(
            f"/api/incidents/{incidencia['id']}/status",
            json={"status": "resolved", "resolution": "Reparación"},
        ).status_code
        == 200
    )
    assert disponibilidad(cliente_http, id_equipo)["reason"] == "equipment_inactive"
    cliente_http.patch(f"/api/equipment/{id_equipo}", json={"active": True})
    assert disponibilidad(cliente_http, id_equipo)["reason"] == "reservation_overlap"
    assert disponibilidad(cliente_http, id_equipo)["conflicting_reservation_ids"] == [reserva["id"]]
    assert cliente_http.get(f"/api/reservations/{reserva['id']}").json() == reserva


def test_bloqueante_incidencias_solo_afectar_sus_fisica_unidad(
    cliente_http: TestClient,
    incidencia_contenido_envio: dict[str, object],
    equipo_contenido_envio: dict[str, object],
) -> None:
    crear_incidencia(cliente_http, incidencia_contenido_envio, bloqueante=True)
    otro_equipo = cliente_http.post(
        "/api/equipment", json={**equipo_contenido_envio, "code": "OTHER-001"}
    ).json()
    assert disponibilidad(cliente_http, otro_equipo["id"])["available"] is True
    reservar_equipo(cliente_http, otro_equipo["id"])


@pytest.mark.parametrize("bloqueante", [False, True])
def test_incidencia_advierte_sobre_todos_confirmadas_reservas_sin_modificando_ellos(
    cliente_http: TestClient, incidencia_contenido_envio: dict[str, object], bloqueante: bool
) -> None:
    id_equipo = incidencia_contenido_envio["equipment_id"]
    antiguo = reservar_equipo(
        cliente_http,
        id_equipo,
        fecha_inicio="2020-01-10",
        fecha_fin="2020-01-12",
        referencia_externa="OLD",
    )
    futuro = reservar_equipo(
        cliente_http,
        id_equipo,
        fecha_inicio="2030-01-10",
        fecha_fin="2030-01-12",
        referencia_externa="NEW",
    )
    canceladas = reservar_equipo(cliente_http, id_equipo)
    assert cliente_http.post(f"/api/reservations/{canceladas['id']}/cancel").status_code == 200
    antes = cliente_http.get("/api/reservations").json()
    incidencia = crear_incidencia(cliente_http, incidencia_contenido_envio, bloqueante=bloqueante)
    assert incidencia["confirmed_reservation_ids"] == [antiguo["id"], futuro["id"]]
    assert isinstance(incidencia["warning"], str) and incidencia["warning"].strip()
    assert "customer_email" not in incidencia
    assert "customer_name" not in incidencia
    assert cliente_http.get("/api/reservations").json() == antes
    assert cliente_http.get(f"/api/incidents/{incidencia['id']}").json() == incidencia
    assert cliente_http.get("/api/incidents").json() == [incidencia]
    assert (
        cliente_http.patch(
            f"/api/incidents/{incidencia['id']}/status",
            json={"status": "resolved", "resolution": "Reparación"},
        ).status_code
        == 200
    )
    assert cliente_http.get("/api/reservations").json() == antes


def test_aviso_es_derivado_desde_real_confirmadas_reservas(
    cliente_http: TestClient, incidencia_contenido_envio: dict[str, object]
) -> None:
    incidencia = crear_incidencia(cliente_http, incidencia_contenido_envio, bloqueante=False)
    assert incidencia["warning"] is None
    reserva = reservar_equipo(cliente_http, incidencia_contenido_envio["equipment_id"])
    respuesta = cliente_http.get(f"/api/incidents/{incidencia['id']}").json()
    assert respuesta["confirmed_reservation_ids"] == [reserva["id"]]
    assert isinstance(respuesta["warning"], str)
    assert cliente_http.get("/api/incidents").json() == [respuesta]
    cliente_http.post(f"/api/reservations/{reserva['id']}/cancel")
    assert cliente_http.get(f"/api/incidents/{incidencia['id']}").json() == incidencia


def test_listar_filtros_son_combinable_y_ordenadas_por_id(
    cliente_http: TestClient,
    incidencia_contenido_envio: dict[str, object],
    equipo_contenido_envio: dict[str, object],
) -> None:
    assert cliente_http.get("/api/incidents").json() == []
    primero = crear_incidencia(
        cliente_http, incidencia_contenido_envio, bloqueante=True, prioridad="high"
    )
    segundo = crear_incidencia(
        cliente_http, incidencia_contenido_envio, bloqueante=False, prioridad="low"
    )
    otro_equipo = cliente_http.post(
        "/api/equipment", json={**equipo_contenido_envio, "code": "OTHER-001"}
    ).json()
    tercero = crear_incidencia(
        cliente_http, incidencia_contenido_envio, id_equipo=otro_equipo["id"], prioridad="high"
    )
    segundo = cliente_http.patch(
        f"/api/incidents/{segundo['id']}/status", json={"status": "in_progress"}
    ).json()
    tercero = cliente_http.patch(
        f"/api/incidents/{tercero['id']}/status",
        json={"status": "resolved", "resolution": "Reparación"},
    ).json()
    assert cliente_http.get("/api/incidents").json() == [primero, segundo, tercero]
    for filtros, esperado in [
        ({"equipment_id": incidencia_contenido_envio["equipment_id"]}, [primero, segundo]),
        ({"status": "open"}, [primero]),
        ({"status": "in_progress"}, [segundo]),
        ({"status": "resolved"}, [tercero]),
        ({"priority": "high"}, [primero, tercero]),
        ({"blocking": "true"}, [primero]),
        ({"blocking": "false"}, [segundo, tercero]),
        (
            {
                "equipment_id": incidencia_contenido_envio["equipment_id"],
                "status": "open",
                "priority": "high",
                "blocking": "true",
            },
            [primero],
        ),
        ({"status": "resolved", "blocking": "true"}, []),
    ]:
        assert cliente_http.get("/api/incidents", params=filtros).json() == esperado


@pytest.mark.parametrize(
    ("campo", "valor"),
    [
        ("equipment_id", 0),
        ("equipment_id", -1),
        ("equipment_id", 2**63),
        ("equipment_id", True),
        ("equipment_id", "1"),
        ("equipment_id", 1.0),
        ("equipment_id", None),
        ("title", ""),
        ("title", "   "),
        ("title", "X" * 161),
        ("title", "Fault\x00bad"),
        ("title", 12),
        ("title", None),
        ("description", "X" * 2001),
        ("description", "Fault\x00bad"),
        ("description", None),
        ("priority", "critical"),
        ("priority", "HIGH"),
        ("priority", None),
        ("blocking", "false"),
        ("blocking", 0),
        ("blocking", 1),
        ("blocking", None),
        ("status", "open"),
        ("resolution", "Repaired"),
        ("confirmed_reservation_ids", []),
        ("unknown", True),
    ],
)
def test_invalido_incidencia_creacion_es_422_sin_escribiendo(
    cliente_http: TestClient,
    incidencia_contenido_envio: dict[str, object],
    campo: str,
    valor: object,
) -> None:
    respuesta = cliente_http.post(
        "/api/incidents", json={**incidencia_contenido_envio, campo: valor}
    )
    assert respuesta.status_code == 422
    assert cliente_http.get("/api/incidents").json() == []


@pytest.mark.parametrize("campo", ["equipment_id", "title"])
def test_incidencia_creacion_requiere_obligatorios_campos(
    cliente_http: TestClient, incidencia_contenido_envio: dict[str, object], campo: str
) -> None:
    del incidencia_contenido_envio[campo]
    assert cliente_http.post("/api/incidents", json=incidencia_contenido_envio).status_code == 422


@pytest.mark.parametrize(
    "filtros",
    [
        {"equipment_id": "0"},
        {"equipment_id": "-1"},
        {"equipment_id": str(2**63)},
        {"equipment_id": "invalid"},
        {"status": "cancelled"},
        {"priority": "critical"},
        {"blocking": "perhaps"},
    ],
)
def test_invalido_listar_filtros_son_422(cliente_http: TestClient, filtros: dict[str, str]) -> None:
    assert cliente_http.get("/api/incidents", params=filtros).status_code == 422


def test_ausente_incidencia_equipo_y_estado_objetivo_devolver_404(
    cliente_http: TestClient, incidencia_contenido_envio: dict[str, object]
) -> None:
    assert cliente_http.get("/api/incidents/99999").status_code == 404
    assert (
        cliente_http.patch(
            "/api/incidents/99999/status", json={"status": "in_progress"}
        ).status_code
        == 404
    )
    assert cliente_http.get("/api/incidents?equipment_id=99999").status_code == 404
    assert (
        cliente_http.post(
            "/api/incidents", json={**incidencia_contenido_envio, "equipment_id": 99999}
        ).status_code
        == 404
    )
    assert cliente_http.get("/api/incidents").json() == []


def test_resuelta_incidencia_y_su_historial_persiste_entre_aplicacion_recreacion(
    cliente_http: TestClient, incidencia_contenido_envio: dict[str, object], ajustes: Configuracion
) -> None:
    incidencia = crear_incidencia(cliente_http, incidencia_contenido_envio, bloqueante=True)
    resuelta = cliente_http.patch(
        f"/api/incidents/{incidencia['id']}/status",
        json={"status": "resolved", "resolution": "Sustitución ficticia"},
    )
    assert resuelta.status_code == 200
    aplicacion = crear_aplicacion(ajustes)
    try:
        with TestClient(aplicacion) as recreada:
            autenticar(recreada)
            assert recreada.get("/api/incidents").json() == [resuelta.json()]
            assert (
                disponibilidad(recreada, incidencia_contenido_envio["equipment_id"])["available"]
                is True
            )
    finally:
        aplicacion.state.motor.dispose()


@pytest.mark.parametrize(
    "cambios",
    [
        {"equipment_id": 99999},
        {"status": "cancelled"},
        {"priority": "critical"},
        {"status": "resolved", "resolution": ""},
        {"status": "open", "resolution": "Repaired"},
    ],
)
def test_sqlite_exige_incidencia_ajena_clave_y_estado_restricciones(
    aplicacion: FastAPI, incidencia_contenido_envio: dict[str, object], cambios: dict[str, object]
) -> None:
    parametros = {
        **incidencia_contenido_envio,
        "description": "",
        "priority": "medium",
        "blocking": False,
        "status": "open",
        "resolution": "",
        **{alias_json(clave): valor for clave, valor in cambios.items()},
    }
    with pytest.raises(IntegrityError), aplicacion.state.motor.begin() as conexion:
        conexion.execute(
            text(
                "INSERT INTO incidents (equipment_id, title, description, priority, blocking, "
                "status, resolution) VALUES (:equipment_id, :title, :description, :priority, "
                ":blocking, :status, :resolution)"
            ),
            parametros,
        )
