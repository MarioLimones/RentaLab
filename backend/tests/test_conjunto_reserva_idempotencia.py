"""
El mismo intento persistente protege las reservas conjuntas de la lista guardada, incluso con un
solo producto.
"""

from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from test_cuenta_reservas import ClienteEscenario, iniciar_sesion_cliente
from test_cuenta_reservas import cliente_escenario as cliente_escenario
from test_producto_reservas import segundo_unidad as segundo_unidad
from test_reserva_idempotencia import intencion

from rentalab.compatibilidad import alias_json
from rentalab.configuracion import Configuracion
from rentalab.principal import crear_aplicacion
from rentalab.reloj import obtener_hoy_proveedor
from rentalab.reservas.modelos import (
    ClienteReservaSolicitud,
    Reserva,
    ReservaSolicitudReserva,
)

INDIVIDUAL_URL = "/api/me/reservations"
URL = f"{INDIVIDUAL_URL}/batch"


def contenido_envio(escenario: ClienteEscenario, ids: list[int], **cambios: object) -> dict:
    return {
        "equipment_ids": ids,
        "start_date": escenario.contenido_envio()["start_date"],
        "end_date": escenario.contenido_envio()["end_date"],
        **{alias_json(clave): valor for clave, valor in cambios.items()},
    }


def otro_modelo(escenario: ClienteEscenario, indice: int = 0) -> int:
    respuesta = escenario.administrador_http.post(
        "/api/equipment",
        json={"code": f"OTHER-{indice}", "name": "Otro modelo", "category": "Audio"},
    )
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()["id"]


def test_una_producto_conjunto_perdida_respuesta_reintentar_hace_no_consumir_segundo_unidad(
    aplicacion: FastAPI, cliente_escenario: ClienteEscenario, segundo_unidad: int
) -> None:
    escenario = cliente_escenario
    cabeceras = intencion()
    cuerpo = contenido_envio(escenario, [escenario.id_equipo])
    original = escenario.primero.post(URL, json=cuerpo, headers=cabeceras)
    assert original.status_code == 201
    repetir = escenario.primero.post(URL, json=cuerpo, headers=cabeceras)
    assert repetir.status_code == 201
    assert repetir.json() == original.json()
    assert original.json()[0]["equipment_id"] != segundo_unidad
    with aplicacion.state.fabrica_sesiones() as sesion:
        assert len(sesion.scalars(select(Reserva)).all()) == 1
        assert len(sesion.scalars(select(ClienteReservaSolicitud)).all()) == 1
        assert len(sesion.scalars(select(ReservaSolicitudReserva)).all()) == 1


def test_repeticion_conjunta_tras_reinicio_conserva_orden_y_estado_real(
    aplicacion: FastAPI,
    ajustes: Configuracion,
    cliente_escenario: ClienteEscenario,
    segundo_unidad: int,
) -> None:
    escenario = cliente_escenario
    otro = otro_modelo(escenario)
    otro_modelo(escenario, 1)
    cuerpo = contenido_envio(escenario, [otro, escenario.id_equipo])
    cabeceras = intencion()
    original = escenario.primero.post(URL, json=cuerpo, headers=cabeceras)
    assert original.status_code == 201
    filas = original.json()
    assert [fila["equipment_id"] for fila in filas] == [otro, escenario.id_equipo]
    canceladas = escenario.primero.post(f"{INDIVIDUAL_URL}/{filas[0]['id']}/cancel")
    assert canceladas.status_code == 200
    assert (
        escenario.administrador_http.patch(
            f"/api/equipment/{otro}", json={"active": False}
        ).status_code
        == 200
    )
    esperado = [canceladas.json(), filas[1]]
    recreada = crear_aplicacion(ajustes)
    recreada.dependency_overrides[obtener_hoy_proveedor] = lambda: lambda: date(2026, 12, 1)
    try:
        with TestClient(recreada) as navegador:
            iniciar_sesion_cliente(navegador, "alicia@example.test")
            repetir = navegador.post(URL, json=cuerpo, headers=cabeceras)
            assert repetir.status_code == 201, repetir.text
            assert repetir.json() == esperado
            assert repetir.headers["location"] == INDIVIDUAL_URL
        with aplicacion.state.fabrica_sesiones() as sesion:
            assert len(sesion.scalars(select(Reserva)).all()) == 2
            solicitud = sesion.scalars(select(ClienteReservaSolicitud)).one()
            assert solicitud.operacion == "batch"
            assert [elemento.id_equipo_solicitado for elemento in solicitud.elementos] == cuerpo[
                "equipment_ids"
            ]
            assert [elemento.posicion for elemento in solicitud.elementos] == [0, 1]
    finally:
        recreada.state.motor.dispose()
    assert segundo_unidad != filas[1]["equipment_id"]


@pytest.mark.parametrize("cambiar", ["order", "products", "start", "end"])
def test_conjunto_clave_reutilizar_con_distinto_original_contenido_envio_es_a_conflicto(
    aplicacion: FastAPI, cliente_escenario: ClienteEscenario, cambiar: str
) -> None:
    escenario = cliente_escenario
    otro = otro_modelo(escenario)
    cuerpo = contenido_envio(escenario, [otro, escenario.id_equipo])
    cabeceras = intencion()
    original = escenario.primero.post(URL, json=cuerpo, headers=cabeceras)
    assert original.status_code == 201
    cambiados = {
        "order": contenido_envio(escenario, [escenario.id_equipo, otro]),
        "products": contenido_envio(escenario, [escenario.id_equipo]),
        "start": contenido_envio(escenario, [otro, escenario.id_equipo], fecha_inicio="2026-11-09"),
        "end": contenido_envio(escenario, [otro, escenario.id_equipo], fecha_fin="2026-11-13"),
    }[cambiar]
    colision = escenario.primero.post(URL, json=cambiados, headers=cabeceras)
    assert colision.status_code == 409
    assert "otros datos" in colision.json()["detail"]
    with aplicacion.state.fabrica_sesiones() as sesion:
        assert len(sesion.scalars(select(Reserva)).all()) == 2
        assert len(sesion.scalars(select(ClienteReservaSolicitud)).all()) == 1


@pytest.mark.parametrize("original_kind", ["single", "batch"])
def test_individual_y_conjunto_comparten_la_cliente_clave_espacio_nombres(
    aplicacion: FastAPI,
    cliente_escenario: ClienteEscenario,
    segundo_unidad: int,
    original_kind: str,
) -> None:
    escenario = cliente_escenario
    cabeceras = intencion()
    conjunto_cuerpo = contenido_envio(escenario, [escenario.id_equipo])
    primero_url = INDIVIDUAL_URL if original_kind == "single" else URL
    primero_cuerpo = escenario.contenido_envio() if original_kind == "single" else conjunto_cuerpo
    siguiente_url = URL if original_kind == "single" else INDIVIDUAL_URL
    siguiente_cuerpo = conjunto_cuerpo if original_kind == "single" else escenario.contenido_envio()
    assert (
        escenario.primero.post(primero_url, json=primero_cuerpo, headers=cabeceras).status_code
        == 201
    )
    respuesta = escenario.primero.post(siguiente_url, json=siguiente_cuerpo, headers=cabeceras)
    assert respuesta.status_code == 409
    assert "otros datos" in respuesta.json()["detail"]
    with aplicacion.state.fabrica_sesiones() as sesion:
        assert len(sesion.scalars(select(Reserva)).all()) == 1
        assert len(sesion.scalars(select(ClienteReservaSolicitud)).all()) == 1
        assert sesion.scalars(select(Reserva)).one().id_equipo != segundo_unidad


def test_clave_conjunta_pertenece_solo_al_cliente_original(
    cliente_escenario: ClienteEscenario, segundo_unidad: int
) -> None:
    escenario = cliente_escenario
    cabeceras = intencion()
    conjunto = escenario.primero.post(
        URL, json=contenido_envio(escenario, [escenario.id_equipo]), headers=cabeceras
    )
    individual = escenario.segundo.post(
        INDIVIDUAL_URL, json=escenario.contenido_envio(), headers=cabeceras
    )
    assert conjunto.status_code == individual.status_code == 201
    assert conjunto.json()[0]["id"] != individual.json()["id"]
    assert individual.json()["equipment_id"] == segundo_unidad
    assert escenario.primero.get(INDIVIDUAL_URL).json() == conjunto.json()
    assert escenario.segundo.get(INDIVIDUAL_URL).json() == [individual.json()]


def test_fallo_conjunto_revierte_reservas_y_permite_reintentar_con_misma_clave(
    aplicacion: FastAPI, cliente_escenario: ClienteEscenario
) -> None:
    escenario = cliente_escenario
    otro = otro_modelo(escenario)
    ocupados = escenario.crear(escenario.segundo, equipment_id=otro)
    cabeceras = intencion()
    cuerpo = contenido_envio(escenario, [escenario.id_equipo, otro])
    respuesta = escenario.primero.post(URL, json=cuerpo, headers=cabeceras)
    assert respuesta.status_code == 409
    assert escenario.primero.get(INDIVIDUAL_URL).json() == []
    with aplicacion.state.fabrica_sesiones() as sesion:
        assert len(sesion.scalars(select(Reserva)).all()) == 1
        assert sesion.scalars(select(ClienteReservaSolicitud)).all() == []
        assert sesion.scalars(select(ReservaSolicitudReserva)).all() == []
    assert escenario.segundo.post(f"{INDIVIDUAL_URL}/{ocupados['id']}/cancel").status_code == 200
    creados = escenario.primero.post(URL, json=cuerpo, headers=cabeceras)
    assert creados.status_code == 201, creados.text
    assert escenario.primero.post(URL, json=cuerpo, headers=cabeceras).json() == creados.json()
    with aplicacion.state.fabrica_sesiones() as sesion:
        assert len(sesion.scalars(select(Reserva)).all()) == 3
        assert len(sesion.scalars(select(ClienteReservaSolicitud)).all()) == 1
        assert len(sesion.scalars(select(ReservaSolicitudReserva)).all()) == 2


def test_conjunto_idempotencia_cabecera_es_validado_y_todavia_requiere_csrf(
    cliente_escenario: ClienteEscenario,
) -> None:
    escenario = cliente_escenario
    cuerpo = contenido_envio(escenario, [escenario.id_equipo])
    assert (
        escenario.primero.post(URL, json=cuerpo, headers={"Idempotency-Key": "invalid"}).status_code
        == 422
    )
    assert (
        escenario.primero.post(
            URL, json=cuerpo, headers={**intencion(), "X-CSRF-Token": "wrong"}
        ).status_code
        == 403
    )
    assert escenario.primero.get(INDIVIDUAL_URL).json() == []
