"""
Solicitudes HTTP autenticadas que compiten sobre archivos SQLite migrados de forma
independiente.
"""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier, Event
from time import monotonic

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event, select
from sqlalchemy.engine import make_url
from test_cuenta_reservas import HOY, ClienteEscenario, iniciar_sesion_cliente
from test_cuenta_reservas import cliente_escenario as cliente_escenario

from rentalab.configuracion import Configuracion
from rentalab.principal import crear_aplicacion
from rentalab.reloj import obtener_hoy_proveedor
from rentalab.reservas.modelos import Reserva


@pytest.mark.parametrize("ronda_numero", range(1, 6))
@pytest.mark.parametrize("distinto_unidades", [False, True], ids=["same-unit", "distinct-units"])
def test_sincronizada_cliente_competencia_tiene_solo_compatibles_persistidos_reservas(
    aplicacion: FastAPI,
    ajustes: Configuracion,
    cliente_escenario: ClienteEscenario,
    ronda_numero: int,
    distinto_unidades: bool,
) -> None:
    escenario = cliente_escenario
    # Cada ronda parametrizada tiene su tmp_path, migraciones reales, usuarios y sesiones.
    base_datos_archivo = make_url(ajustes.url_base_datos).database
    assert base_datos_archivo is not None and base_datos_archivo != ":memory:"
    assert Path(base_datos_archivo).is_file()
    otro_id = escenario.id_equipo
    if distinto_unidades:
        mismo_modelo = escenario.administrador_http.get(
            f"/api/equipment/{escenario.id_equipo}"
        ).json()
        mismo_modelo = {clave: valor for clave, valor in mismo_modelo.items() if clave != "id"}
        mismo_modelo["code"] = f"CAM-TWIN-{ronda_numero}"
        respuesta = escenario.administrador_http.post("/api/equipment", json=mismo_modelo)
        assert respuesta.status_code == 201, respuesta.text
        otro_id = respuesta.json()["id"]

    segundo_aplicacion = crear_aplicacion(ajustes)
    segundo_aplicacion.dependency_overrides[obtener_hoy_proveedor] = lambda: lambda: HOY
    lanzamiento = Barrier(3)
    intentado = [Event(), Event()]
    conexiones: list[set[int]] = [set(), set()]
    acquired: list[int] = []
    engines = [aplicacion.state.motor, segundo_aplicacion.state.motor]
    escuchas = []

    def instalar_observadores(indice: int) -> None:
        def copia_trabajo(conexion, _registro, _proxy):
            conexiones[indice].add(id(conexion))

        def antes(_conexion, _cursor, sentencia, _parametros, _context, _executemany):
            if sentencia.strip().upper() == "BEGIN IMMEDIATE":
                intentado[indice].set()

        def despues(_conexion, _cursor, sentencia, _parametros, _context, _executemany):
            if sentencia.strip().upper() == "BEGIN IMMEDIATE":
                acquired.append(indice)
                # La conexión ganadora mantiene el bloqueo real de escritura de
                # SQLite hasta que ambas conexiones
                # hayan intentado BEGIN, para evitar que la prueba se vuelva
                # secuencial sin detectarlo.
                assert intentado[1 - indice].wait(timeout=5), "Peer never competed for SQLite"

        for nombre, callback in (
            ("checkout", copia_trabajo),
            ("before_cursor_execute", antes),
            ("after_cursor_execute", despues),
        ):
            event.listen(engines[indice], nombre, callback)
            escuchas.append((engines[indice], nombre, callback))

    def enviar(navegador: TestClient, id_equipo: int):
        lanzamiento.wait(timeout=5)
        return navegador.post(
            "/api/me/reservations", json=escenario.contenido_envio(id_equipo=id_equipo)
        )

    try:
        with TestClient(segundo_aplicacion) as otro:
            iniciar_sesion_cliente(otro, "bruno@example.test")
            for navegador, id_equipo in ((escenario.primero, escenario.id_equipo), (otro, otro_id)):
                disponible = navegador.get(
                    f"/api/public/equipment/{id_equipo}/availability",
                    params={
                        clave: valor
                        for clave, valor in escenario.contenido_envio().items()
                        if clave != "equipment_id"
                    },
                )
                assert disponible.status_code == 200
                assert disponible.json()["available"] is True
            instalar_observadores(0)
            instalar_observadores(1)
            try:
                with ThreadPoolExecutor(max_workers=2) as ejecutor:
                    primero = ejecutor.submit(enviar, escenario.primero, escenario.id_equipo)
                    segundo = ejecutor.submit(enviar, otro, otro_id)
                    lanzamiento.wait(timeout=5)
                    respuestas = [primero.result(timeout=10), segundo.result(timeout=10)]
            finally:
                for motor, nombre, callback in escuchas:
                    event.remove(motor, nombre, callback)
            assert all(elemento.is_set() for elemento in intentado)
            assert len(acquired) == 2
            assert conexiones[0] and conexiones[1]
            assert conexiones[0].isdisjoint(conexiones[1])
            assert sorted(respuesta.status_code for respuesta in respuestas) == (
                [201, 201] if distinto_unidades else [201, 409]
            )
            if not distinto_unidades:
                conflicto = next(
                    respuesta for respuesta in respuestas if respuesta.status_code == 409
                )
                assert "consulta la disponibilidad" in conflicto.json()["detail"]
                assert "retry-after" not in conflicto.headers
                assert "alicia@example.test" not in conflicto.text
                assert "bruno@example.test" not in conflicto.text

            with aplicacion.state.fabrica_sesiones() as sesion:
                persistidos = sesion.scalars(select(Reserva)).all()
                assert len(persistidos) == (2 if distinto_unidades else 1)
                for fila in persistidos:
                    assert fila.estado == "confirmed"
                    assert fila.origen == "portal"
                    assert fila.fecha_inicio.isoformat() == "2026-11-10"
                    assert fila.fecha_fin.isoformat() == "2026-11-12"
                    propietario_indice = 0 if fila.id_usuario_cliente == escenario.primero_id else 1
                    assert respuestas[propietario_indice].status_code == 201
                    assert fila.id == respuestas[propietario_indice].json()["id"]
                    assert (
                        fila.id_usuario_cliente
                        == [escenario.primero_id, escenario.segundo_id][propietario_indice]
                    )
                assert len({fila.id_equipo for fila in persistidos}) == len(persistidos)

            # Un reenvío idéntico o un segundo clic tardío no pueden añadir otra fila.
            ganador = next(
                indice
                for indice, respuesta in enumerate(respuestas)
                if respuesta.status_code == 201
            )
            reenviado = [escenario.primero, otro][ganador].post(
                "/api/me/reservations",
                json=escenario.contenido_envio(id_equipo=[escenario.id_equipo, otro_id][ganador]),
            )
            assert reenviado.status_code == 409
            with aplicacion.state.fabrica_sesiones() as sesion:
                assert len(sesion.scalars(select(Reserva)).all()) == len(persistidos)
    finally:
        segundo_aplicacion.state.motor.dispose()


@pytest.mark.parametrize("operacion", ["create", "cancel"])
@pytest.mark.parametrize("bloqueo_tipo", ["writer", "reader-commit"])
def test_espera_por_bloqueo_es_limitada_y_permite_reintentar(
    aplicacion: FastAPI,
    ajustes: Configuracion,
    cliente_escenario: ClienteEscenario,
    operacion: str,
    bloqueo_tipo: str,
) -> None:
    escenario = cliente_escenario
    original = escenario.crear() if operacion == "cancel" else None
    punto_acceso = (
        f"/api/me/reservations/{original['id']}/cancel" if original else "/api/me/reservations"
    )
    segundo_aplicacion = crear_aplicacion(
        ajustes.model_copy(update={"espera_sqlite_ocupado_ms": 25})
    )
    segundo_aplicacion.dependency_overrides[obtener_hoy_proveedor] = lambda: lambda: HOY
    try:
        with TestClient(segundo_aplicacion) as navegador:
            iniciar_sesion_cliente(navegador, "alicia@example.test")
            with aplicacion.state.motor.connect() as bloqueo_propietario:
                if bloqueo_tipo == "writer":
                    bloqueo_propietario.exec_driver_sql("BEGIN IMMEDIATE")
                else:
                    bloqueo_propietario.exec_driver_sql("BEGIN")
                    bloqueo_propietario.exec_driver_sql("SELECT id FROM equipment").all()
                iniciado = monotonic()
                fallido = navegador.post(
                    punto_acceso, json={} if original else escenario.contenido_envio()
                )
                transcurrido = monotonic() - iniciado
                assert fallido.status_code == 503, fallido.text
                assert fallido.headers["Retry-After"] == "1"
                assert "ocupada" in fallido.json()["detail"]
                assert "disponib" not in fallido.json()["detail"]
                assert transcurrido < 2, f"25 ms SQLite timeout took {transcurrido:.3f} s"
                assert escenario.primero.get("/api/me/reservations").json() == (
                    [original] if original else []
                )
                bloqueo_propietario.rollback()
            reintentado = navegador.post(
                punto_acceso, json={} if original else escenario.contenido_envio()
            )
            assert reintentado.status_code == (200 if original else 201), reintentado.text
            assert reintentado.json()["status"] == ("cancelled" if original else "confirmed")
            with aplicacion.state.fabrica_sesiones() as sesion:
                filas = sesion.scalars(select(Reserva)).all()
                assert len(filas) == 1
                assert filas[0].id_usuario_cliente == escenario.primero_id
                assert filas[0].estado == reintentado.json()["status"]
    finally:
        segundo_aplicacion.state.motor.dispose()
