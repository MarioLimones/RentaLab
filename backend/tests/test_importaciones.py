import csv
from datetime import date, timedelta
from io import StringIO
from pathlib import Path
from typing import Any

import pytest
from conftest import autenticar
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event

from rentalab.compatibilidad import alias_json
from rentalab.configuracion import Configuracion
from rentalab.principal import crear_aplicacion

CABECERA = [
    "external_reference",
    "customer_name",
    "customer_email",
    "equipment_code",
    "starts_on",
    "ends_on",
]
FIXTURES = Path(__file__).parent / "fixtures" / "imports"
MAXIMO_ARCHIVO_BYTES = 1_048_576


@pytest.fixture
def importacion_equipo(
    cliente_http: TestClient, equipo_contenido_envio: dict[str, object]
) -> list[dict[str, Any]]:
    equipo = []
    for codigo in ("CAM-001", "CAM-002"):
        respuesta = cliente_http.post(
            "/api/equipment", json={**equipo_contenido_envio, "code": codigo}
        )
        assert respuesta.status_code == 201
        equipo.append(respuesta.json())
    return equipo


def hacer_csv(filas: list[list[str]], cabecera: list[str] = CABECERA) -> bytes:
    flujo = StringIO(newline="")
    escritor = csv.writer(flujo, lineterminator="\n")
    escritor.writerow(cabecera)
    escritor.writerows(filas)
    return flujo.getvalue().encode("utf-8")


def orden_fila(referencia: str = "ORDER-001", **cambios: str) -> list[str]:
    valores = {
        "external_reference": referencia,
        "customer_name": "Cliente ficticio",
        "customer_email": "cliente@example.test",
        "equipment_code": "CAM-001",
        "starts_on": "2026-11-10",
        "ends_on": "2026-11-12",
        **{alias_json(clave): valor for clave, valor in cambios.items()},
    }
    return [valores[clave] for clave in CABECERA]


def importacion_csv(cliente_http: TestClient, contenido: bytes) -> dict[str, Any]:
    respuesta = cliente_http.post(
        "/api/imports", files={"file": ("orders.csv", contenido, "text/csv")}
    )
    assert respuesta.status_code == 200, respuesta.text
    informe = respuesta.json()
    assert set(informe) == {"totals", "rows"}
    assert set(informe["totals"]) == {"total", "accepted", "already_imported", "rejected"}
    assert informe["totals"]["total"] == len(informe["rows"])
    assert (
        sum(informe["totals"][estado] for estado in ("accepted", "already_imported", "rejected"))
        == informe["totals"]["total"]
    )
    for fila in informe["rows"]:
        assert set(fila) == {"line", "external_reference", "status", "reservation", "message"}
        assert isinstance(fila["message"], str) and fila["message"].strip()
        assert "Traceback" not in fila["message"]
        assert "INSERT INTO" not in fila["message"]
        assert fila["status"] in {"accepted", "already_imported", "rejected"}
        assert (fila["reservation"] is None) is (fila["status"] == "rejected")
    return informe


def test_importacion_valido_csv_crea_normalizado_reservas_en_archivo_orden(
    cliente_http: TestClient, importacion_equipo: list[dict[str, Any]]
) -> None:
    informe = importacion_csv(cliente_http, (FIXTURES / "valid.csv").read_bytes())
    assert informe["totals"] == {"total": 3, "accepted": 3, "already_imported": 0, "rejected": 0}
    assert [fila["line"] for fila in informe["rows"]] == [2, 3, 4]
    primero = informe["rows"][0]
    assert primero["external_reference"] == "ORDER-001"
    assert primero["reservation"] == {
        "id": primero["reservation"]["id"],
        "equipment_id": importacion_equipo[0]["id"],
        "customer_name": "Luz, Norte",
        "customer_email": "luz@example.test",
        "start_date": "2026-11-10",
        "end_date": "2026-11-12",
        "status": "confirmed",
        "external_reference": "ORDER-001",
        "customer_user_id": None,
        "origin": "csv",
    }
    for fila in informe["rows"]:
        reserva = fila["reservation"]
        assert cliente_http.get(f"/api/reservations/{reserva['id']}").json() == reserva
    assert len(cliente_http.get("/api/reservations").json()) == 3


def test_mezclado_csv_confirmaciones_valido_filas_y_rechaza_otro_filas_individualmente(
    cliente_http: TestClient, importacion_equipo: list[dict[str, Any]]
) -> None:
    informe = importacion_csv(cliente_http, (FIXTURES / "mixed.csv").read_bytes())
    assert informe["totals"] == {"total": 5, "accepted": 2, "already_imported": 0, "rejected": 3}
    assert [fila["status"] for fila in informe["rows"]] == [
        "accepted",
        "rejected",
        "rejected",
        "rejected",
        "accepted",
    ]
    assert [fila["line"] for fila in informe["rows"]] == [2, 3, 4, 5, 6]
    assert [fila["external_reference"] for fila in informe["rows"]] == [
        "ORDER-A",
        "ORDER-B",
        "ORDER-C",
        "ORDER-D",
        "ORDER-E",
    ]
    assert len(cliente_http.get("/api/reservations").json()) == 2


def test_reimportar_devuelve_original_reservas_sin_duplicados(
    cliente_http: TestClient, importacion_equipo: list[dict[str, Any]]
) -> None:
    contenido = (FIXTURES / "valid.csv").read_bytes()
    primero = importacion_csv(cliente_http, contenido)
    original = cliente_http.get("/api/reservations").json()
    segundo = importacion_csv(cliente_http, contenido)
    assert segundo["totals"] == {"total": 3, "accepted": 0, "already_imported": 3, "rejected": 0}
    assert [fila["reservation"] for fila in segundo["rows"]] == [
        fila["reservation"] for fila in primero["rows"]
    ]
    assert cliente_http.get("/api/reservations").json() == original


def test_normalizado_duplicado_referencias_en_a_archivo_son_idempotente(
    cliente_http: TestClient, importacion_equipo: list[dict[str, Any]]
) -> None:
    informe = importacion_csv(
        cliente_http,
        hacer_csv(
            [
                orden_fila(
                    " ORDER-001 ",
                    nombre_cliente="  Cliente ficticio  ",
                    correo_cliente="cliente@EXAMPLE.TEST",
                    codigo_equipo=" cam-001 ",
                ),
                orden_fila(),
                orden_fila(nombre_cliente="Otro cliente"),
            ]
        ),
    )
    assert informe["totals"] == {"total": 3, "accepted": 1, "already_imported": 1, "rejected": 1}
    assert [fila["status"] for fila in informe["rows"]] == [
        "accepted",
        "already_imported",
        "rejected",
    ]
    assert informe["rows"][0]["reservation"] == informe["rows"][1]["reservation"]
    assert len(cliente_http.get("/api/reservations").json()) == 1


@pytest.mark.parametrize(
    "cambios",
    [
        {"customer_name": "Otro cliente"},
        {"customer_email": "otro@example.test"},
        {"equipment_code": "CAM-002"},
        {"starts_on": "2026-11-09"},
        {"ends_on": "2026-11-13"},
    ],
)
def test_a_referencia_con_cambiados_datos_es_rechazadas_sin_sobrescribir_historial(
    cliente_http: TestClient, importacion_equipo: list[dict[str, Any]], cambios: dict[str, str]
) -> None:
    importacion_csv(cliente_http, hacer_csv([orden_fila()]))
    antes = cliente_http.get("/api/reservations").json()
    informe = importacion_csv(cliente_http, hacer_csv([orden_fila(**cambios)]))
    assert informe["totals"]["rejected"] == 1
    assert informe["rows"][0]["external_reference"] == "ORDER-001"
    assert cliente_http.get("/api/reservations").json() == antes


@pytest.mark.parametrize("obstaculo", ["inactive", "incident", "later_booking"])
def test_canceladas_identico_importacion_permanece_idempotente_pese_real_indisponibilidad(
    cliente_http: TestClient, importacion_equipo: list[dict[str, Any]], obstaculo: str
) -> None:
    id_equipo = importacion_equipo[0]["id"]
    importadas = importacion_csv(cliente_http, hacer_csv([orden_fila()]))["rows"][0]["reservation"]
    canceladas = cliente_http.post(f"/api/reservations/{importadas['id']}/cancel").json()
    if obstaculo == "inactive":
        assert (
            cliente_http.patch(f"/api/equipment/{id_equipo}", json={"active": False}).status_code
            == 200
        )
    elif obstaculo == "incident":
        assert (
            cliente_http.post(
                "/api/incidents",
                json={
                    "equipment_id": id_equipo,
                    "title": "Incidencia ficticia",
                    "blocking": True,
                },
            ).status_code
            == 201
        )
    else:
        assert (
            cliente_http.post(
                "/api/reservations",
                json={
                    **{
                        clave: valor
                        for clave, valor in importadas.items()
                        if clave not in {"id", "status", "customer_user_id", "origin"}
                    },
                    "external_reference": "LATER-BOOKING",
                },
            ).status_code
            == 201
        )
    antes = cliente_http.get("/api/reservations").json()
    informe = importacion_csv(cliente_http, hacer_csv([orden_fila()]))
    assert informe["totals"] == {"total": 1, "accepted": 0, "already_imported": 1, "rejected": 0}
    assert informe["rows"][0]["reservation"] == canceladas
    assert cliente_http.get("/api/reservations").json() == antes


def test_referencia_comparacion_es_caso_confidencial(
    cliente_http: TestClient, importacion_equipo: list[dict[str, Any]]
) -> None:
    informe = importacion_csv(
        cliente_http,
        hacer_csv(
            [
                orden_fila("ORDER-001"),
                orden_fila("order-001", starts_on="2026-11-12", ends_on="2026-11-13"),
            ]
        ),
    )
    assert informe["totals"]["accepted"] == 2


@pytest.mark.parametrize("obstaculo", ["inactive", "incident", "overlap"])
def test_importacion_usa_la_existentes_reserva_politica_y_continua_despues_rechazo(
    cliente_http: TestClient, importacion_equipo: list[dict[str, Any]], obstaculo: str
) -> None:
    id_equipo = importacion_equipo[0]["id"]
    if obstaculo == "inactive":
        cliente_http.patch(f"/api/equipment/{id_equipo}", json={"active": False})
    elif obstaculo == "incident":
        cliente_http.post(
            "/api/incidents",
            json={"equipment_id": id_equipo, "title": "Incidencia ficticia", "blocking": True},
        )
    else:
        importacion_csv(cliente_http, hacer_csv([orden_fila("EXISTING")]))
    antes = cliente_http.get("/api/reservations").json()
    informe = importacion_csv(
        cliente_http,
        hacer_csv([orden_fila("BLOCKED"), orden_fila("FREE", codigo_equipo="CAM-002")]),
    )
    assert informe["totals"] == {"total": 2, "accepted": 1, "already_imported": 0, "rejected": 1}
    assert [fila["status"] for fila in informe["rows"]] == ["rejected", "accepted"]
    despues = cliente_http.get("/api/reservations").json()
    assert len(despues) == len(antes) + 1
    for original in antes:
        assert cliente_http.get(f"/api/reservations/{original['id']}").json() == original


@pytest.mark.parametrize(
    ("campo", "valor"),
    [
        ("external_reference", ""),
        ("external_reference", "   "),
        ("external_reference", "X" * 121),
        ("external_reference", "REF\x00bad"),
        ("customer_name", ""),
        ("customer_name", "  "),
        ("customer_name", "X" * 121),
        ("customer_name", "Bad\x00name"),
        ("customer_email", "invalid-email"),
        ("customer_email", ""),
        ("equipment_code", ""),
        ("equipment_code", "UNKNOWN"),
        ("equipment_code", "CAM\x00bad"),
        ("starts_on", "2026-11-12"),
        ("starts_on", "2026-11-13"),
        ("starts_on", "2026-02-30"),
        ("starts_on", "2026-1-10"),
        ("starts_on", "2026-11-10T00:00:00"),
        ("starts_on", " 2026-11-10 "),
        ("ends_on", "2026-11-10"),
        ("ends_on", ""),
        ("ends_on", "2026-11-12T00:00:00Z"),
    ],
)
def test_invalido_fila_campos_son_rechazadas_sin_perdiendo_la_siguiente_valido_fila(
    cliente_http: TestClient, importacion_equipo: list[dict[str, Any]], campo: str, valor: str
) -> None:
    informe = importacion_csv(
        cliente_http, hacer_csv([orden_fila(**{campo: valor}), orden_fila("VALID-SECOND")])
    )
    assert informe["totals"] == {"total": 2, "accepted": 1, "already_imported": 0, "rejected": 1}
    assert [fila["status"] for fila in informe["rows"]] == ["rejected", "accepted"]
    assert informe["rows"][1]["line"] == 3
    assert len(cliente_http.get("/api/reservations").json()) == 1


@pytest.mark.parametrize("bad_fila", [[], ["ONLY-REF"], orden_fila() + ["extra"]])
def test_vacio_y_incorrecto_celda_recuentos_son_rechazadas_y_procesamiento_continua(
    cliente_http: TestClient, importacion_equipo: list[dict[str, Any]], bad_fila: list[str]
) -> None:
    informe = importacion_csv(cliente_http, hacer_csv([bad_fila, orden_fila("VALID-SECOND")]))
    assert informe["totals"]["rejected"] == 1
    assert informe["totals"]["accepted"] == 1
    assert [fila["line"] for fila in informe["rows"]] == [2, 3]


def test_entrecomillado_comas_multilinea_registros_y_fisica_arranque_linea_numeros(
    cliente_http: TestClient, importacion_equipo: list[dict[str, Any]]
) -> None:
    informe = importacion_csv(
        cliente_http,
        hacer_csv(
            [
                orden_fila(nombre_cliente='Estudio "Norte",\nProducción'),
                orden_fila("SECOND", codigo_equipo="CAM-002"),
            ]
        ),
    )
    assert informe["totals"]["accepted"] == 2
    assert [fila["line"] for fila in informe["rows"]] == [2, 4]
    assert informe["rows"][0]["reservation"]["customer_name"] == 'Estudio "Norte",\nProducción'


@pytest.mark.parametrize("bom", [False, True])
@pytest.mark.parametrize("crlf", [False, True])
def test_utf8_con_opcionales_bom_y_windows_saltos_linea_es_compatible(
    cliente_http: TestClient, importacion_equipo: list[dict[str, Any]], bom: bool, crlf: bool
) -> None:
    contenido = hacer_csv([orden_fila(nombre_cliente="Producción Ñandú")])
    if crlf:
        contenido = contenido.replace(b"\n", b"\r\n")
    if bom:
        contenido = b"\xef\xbb\xbf" + contenido
    informe = importacion_csv(cliente_http, contenido)
    assert informe["totals"]["accepted"] == 1
    assert informe["rows"][0]["reservation"]["customer_name"] == "Producción Ñandú"


def test_cabecera_solo_es_un_vacio_correcto_importacion(cliente_http: TestClient) -> None:
    assert importacion_csv(cliente_http, hacer_csv([])) == {
        "totals": {"total": 0, "accepted": 0, "already_imported": 0, "rejected": 0},
        "rows": [],
    }


@pytest.mark.parametrize(
    "cabecera",
    [
        CABECERA[:-1],
        CABECERA + ["extra"],
        [CABECERA[1], CABECERA[0], *CABECERA[2:]],
        ["EXTERNAL_REFERENCE", *CABECERA[1:]],
        [" external_reference", *CABECERA[1:]],
        ["external_reference ", *CABECERA[1:]],
        [*CABECERA[:-1], "starts_on"],
    ],
)
def test_cabecera_es_exacto_ordenadas_y_caso_confidencial(
    cliente_http: TestClient, importacion_equipo: list[dict[str, Any]], cabecera: list[str]
) -> None:
    respuesta = cliente_http.post(
        "/api/imports",
        files={"file": ("orders.csv", hacer_csv([orden_fila()], cabecera=cabecera), "text/csv")},
    )
    assert respuesta.status_code == 422
    assert cliente_http.get("/api/reservations").json() == []


def test_invalido_cabecera_fixture_es_rechazadas_sin_creando_reservas(
    cliente_http: TestClient, importacion_equipo: list[dict[str, Any]]
) -> None:
    respuesta = cliente_http.post(
        "/api/imports",
        files={"file": ("orders.csv", (FIXTURES / "invalid_header.csv").read_bytes(), "text/csv")},
    )
    assert respuesta.status_code == 422
    assert cliente_http.get("/api/reservations").json() == []


@pytest.mark.parametrize("contenido", [b"", b"\xef\xbb\xbf", b"\xff\xfeinvalid-utf8"])
def test_vacio_o_no_utf8_archivos_son_422(cliente_http: TestClient, contenido: bytes) -> None:
    respuesta = cliente_http.post(
        "/api/imports", files={"file": ("orders.csv", contenido, "text/csv")}
    )
    assert respuesta.status_code == 422


@pytest.mark.parametrize("suffix", [b'"unclosed\n', b'"bad"unexpected,value\n'])
def test_estructuralmente_roto_csv_es_rechazadas_antes_cualquier_insertar(
    aplicacion: FastAPI,
    cliente_http: TestClient,
    importacion_equipo: list[dict[str, Any]],
    suffix: bytes,
) -> None:
    statements: list[str] = []

    def observar_sql(
        _conexion: object, _cursor: object, sentencia: str, *_argumentos: object
    ) -> None:
        statements.append(sentencia)

    event.listen(aplicacion.state.motor, "before_cursor_execute", observar_sql)
    try:
        respuesta = cliente_http.post(
            "/api/imports",
            files={"file": ("orders.csv", hacer_csv([orden_fila()]) + suffix, "text/csv")},
        )
    finally:
        event.remove(aplicacion.state.motor, "before_cursor_execute", observar_sql)
    assert respuesta.status_code == 422
    assert not any(sentencia.lstrip().upper().startswith("INSERT") for sentencia in statements)
    assert cliente_http.get("/api/reservations").json() == []


@pytest.mark.parametrize("too_grande", ["bytes", "rows"])
def test_limites_son_comprobado_para_la_completo_archivo_antes_cualquier_insertar(
    aplicacion: FastAPI,
    cliente_http: TestClient,
    importacion_equipo: list[dict[str, Any]],
    too_grande: str,
) -> None:
    if too_grande == "bytes":
        contenido = hacer_csv([orden_fila()]) + b"X" * MAXIMO_ARCHIVO_BYTES
    else:
        contenido = hacer_csv([orden_fila(str(indice)) for indice in range(501)])
    statements: list[str] = []

    def observar_sql(
        _conexion: object, _cursor: object, sentencia: str, *_argumentos: object
    ) -> None:
        statements.append(sentencia)

    event.listen(aplicacion.state.motor, "before_cursor_execute", observar_sql)
    try:
        respuesta = cliente_http.post(
            "/api/imports", files={"file": ("orders.csv", contenido, "text/csv")}
        )
    finally:
        event.remove(aplicacion.state.motor, "before_cursor_execute", observar_sql)
    assert respuesta.status_code == 413
    assert not any(sentencia.lstrip().upper().startswith("INSERT") for sentencia in statements)
    assert cliente_http.get("/api/reservations").json() == []


def test_exactamente_500_filas_son_permitidos(
    cliente_http: TestClient, importacion_equipo: list[dict[str, Any]]
) -> None:
    arranque = date(2027, 1, 1)
    filas = [
        orden_fila(
            f"ORDER-{indice}",
            starts_on=(arranque + timedelta(days=indice)).isoformat(),
            ends_on=(arranque + timedelta(days=indice + 1)).isoformat(),
        )
        for indice in range(500)
    ]
    informe = importacion_csv(cliente_http, hacer_csv(filas))
    assert informe["totals"] == {
        "total": 500,
        "accepted": 500,
        "already_imported": 0,
        "rejected": 0,
    }
    assert len(cliente_http.get("/api/reservations").json()) == 500


def test_exacto_byte_limitar_es_permitidos_y_grande_campos_son_fila_errores(
    cliente_http: TestClient, importacion_equipo: list[dict[str, Any]]
) -> None:
    base = hacer_csv([orden_fila(nombre_cliente="")])
    contenido = hacer_csv([orden_fila(nombre_cliente="X" * (MAXIMO_ARCHIVO_BYTES - len(base)))])
    assert len(contenido) == MAXIMO_ARCHIVO_BYTES
    informe = importacion_csv(cliente_http, contenido)
    assert informe["totals"] == {"total": 1, "accepted": 0, "already_imported": 0, "rejected": 1}


def test_campos_superior_csv_predeterminado_tamano_limitar_hacer_no_abortar_otro_filas(
    cliente_http: TestClient, importacion_equipo: list[dict[str, Any]]
) -> None:
    informe = importacion_csv(
        cliente_http,
        hacer_csv([orden_fila("HUGE", nombre_cliente="X" * 150_000), orden_fila("VALID-SECOND")]),
    )
    assert informe["totals"] == {"total": 2, "accepted": 1, "already_imported": 0, "rejected": 1}


@pytest.mark.parametrize("kind", ["missing", "wrong_field", "json", "duplicate_file", "extra"])
def test_invalido_multipart_contrato_es_422(cliente_http: TestClient, kind: str) -> None:
    archivo = ("orders.csv", hacer_csv([]), "text/csv")
    if kind == "missing":
        respuesta = cliente_http.post("/api/imports")
    elif kind == "wrong_field":
        respuesta = cliente_http.post("/api/imports", files={"upload": archivo})
    elif kind == "json":
        respuesta = cliente_http.post("/api/imports", json={"file": "orders.csv"})
    elif kind == "duplicate_file":
        respuesta = cliente_http.post("/api/imports", files=[("file", archivo), ("file", archivo)])
    else:
        respuesta = cliente_http.post(
            "/api/imports", files={"file": archivo}, data={"extra": "unexpected"}
        )
    assert respuesta.status_code == 422


def test_ejemplo_descargar_es_csv_con_la_exacto_contrato_y_ficticio_datos(
    cliente_http: TestClient,
) -> None:
    respuesta = cliente_http.get("/api/imports/example")
    assert respuesta.status_code == 200
    assert respuesta.headers["content-type"].startswith("text/csv")
    assert "attachment" in respuesta.headers["content-disposition"]
    assert ".csv" in respuesta.headers["content-disposition"]
    filas = list(csv.reader(StringIO(respuesta.content.decode("utf-8-sig"))))
    assert filas[0] == CABECERA
    assert len(filas) > 1
    assert all(len(fila) == len(CABECERA) for fila in filas)
    assert all(fila[2].endswith(".test") for fila in filas[1:])
    assert all(fila[3] in {"CAM-001", "CAM-002", "AUD-001", "LGT-001"} for fila in filas[1:])


def test_importadas_reservas_persiste_y_reimportar_despues_aplicacion_recreacion(
    cliente_http: TestClient, importacion_equipo: list[dict[str, Any]], ajustes: Configuracion
) -> None:
    contenido = hacer_csv([orden_fila()])
    original = importacion_csv(cliente_http, contenido)["rows"][0]["reservation"]
    aplicacion = crear_aplicacion(ajustes)
    try:
        with TestClient(aplicacion) as recreada:
            autenticar(recreada)
            informe = importacion_csv(recreada, contenido)
            assert informe["totals"]["already_imported"] == 1
            assert informe["rows"][0]["reservation"] == original
            assert recreada.get("/api/reservations").json() == [original]
    finally:
        aplicacion.state.motor.dispose()


def test_truncado_multipart_es_rechazadas_antes_cualquier_reserva_es_creados(
    cliente_http: TestClient, importacion_equipo: list[dict[str, Any]]
) -> None:
    contenido = (
        b'--test-boundary\r\nContent-Disposition: form-data; name="file"; filename="orders.csv"\r\n'
        b"Content-Type: text/csv\r\n\r\n" + hacer_csv([orden_fila()])
    )
    respuesta = cliente_http.post(
        "/api/imports",
        content=contenido,
        headers={"Content-Type": "multipart/form-data; boundary=test-boundary"},
    )
    assert respuesta.status_code == 422
    assert cliente_http.get("/api/reservations").json() == []


def test_archivo_tamano_es_aplicado_sin_a_contenido_longitud_cabecera(
    cliente_http: TestClient, importacion_equipo: list[dict[str, Any]]
) -> None:
    contenido = (
        b'--test-boundary\r\nContent-Disposition: form-data; name="file"; filename="orders.csv"\r\n'
        b"Content-Type: text/csv\r\n\r\n"
        + hacer_csv([orden_fila()])
        + b"X" * MAXIMO_ARCHIVO_BYTES
        + b"\r\n--test-boundary--\r\n"
    )
    solicitud = cliente_http.build_request(
        "POST",
        "/api/imports",
        content=iter([contenido]),
        headers={"Content-Type": "multipart/form-data; boundary=test-boundary"},
    )
    assert "content-length" not in solicitud.headers
    assert cliente_http.send(solicitud).status_code == 413
    assert cliente_http.get("/api/reservations").json() == []
