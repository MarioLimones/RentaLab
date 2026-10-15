from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from sqlalchemy import select, text

from rentalab.autenticacion.modelos import Usuario
from rentalab.catalogo_demostracion import (
    CATALOGO_EQUIPO,
    RESERVA_EQUIPO_CODIGOS,
    cargar_datos_catalogo_demostracion,
)
from rentalab.configuracion import Configuracion
from rentalab.demostracion import DEMOSTRACION_CUENTAS, cargar_datos_demostracion
from rentalab.equipo.modelos import Equipo
from rentalab.equipo.repositorio import RepositorioEquipos
from rentalab.equipo.servicio import ServicioEquipos
from rentalab.reservas.esquemas import CrearReserva, IntervaloFechas
from rentalab.reservas.modelos import Reserva
from rentalab.reservas.repositorio import RepositorioReservas
from rentalab.reservas.servicio import ServicioReservas

BASE_FECHA = date(2040, 3, 1)
CATALOGO_REFERENCIAS = tuple(f"RENTALAB-CATALOGUE-{numero:02d}" for numero in range(1, 11))


def cargar_existentes_demostracion(ajustes: Configuracion) -> None:
    cargar_datos_demostracion(ajustes, base_fecha=BASE_FECHA, hoy=lambda: BASE_FECHA)


def cargar_catalogo(ajustes: Configuracion, *, base_fecha: date | None = None):
    return cargar_datos_catalogo_demostracion(
        ajustes, base_fecha=base_fecha, hoy=lambda: BASE_FECHA
    )


def negocio_instantanea(aplicacion: FastAPI) -> dict[str, list[tuple]]:
    with aplicacion.state.fabrica_sesiones() as sesion:
        return {
            tabla: list(sesion.execute(text(f"SELECT * FROM {tabla} ORDER BY id")).tuples())
            for tabla in ("users", "equipment", "reservations", "incidents")
        }


def test_catalogo_anade_veinte_fotografiadas_unidades_y_diez_propia_reservas(
    aplicacion: FastAPI, ajustes: Configuracion
) -> None:
    cargar_existentes_demostracion(ajustes)
    antes = negocio_instantanea(aplicacion)
    resultado = cargar_catalogo(ajustes)
    assert resultado.equipo_creados == 20
    assert resultado.reservas_creados == 10
    assert resultado.reservas_existentes == 0
    assert resultado.omitidas == ()
    assert len(CATALOGO_EQUIPO) == 20
    assert len({elemento.codigo for elemento in CATALOGO_EQUIPO}) == 20
    assert len(RESERVA_EQUIPO_CODIGOS) == len(set(RESERVA_EQUIPO_CODIGOS)) == 10

    with aplicacion.state.fabrica_sesiones() as sesion:
        unidades = sesion.scalars(select(Equipo).order_by(Equipo.id)).all()
        assert len(unidades) == 24
        agregado = {
            unidad.codigo: unidad
            for unidad in unidades
            if unidad.codigo in {elemento.codigo for elemento in CATALOGO_EQUIPO}
        }
        assert len(agregado) == 20
        assert set(RESERVA_EQUIPO_CODIGOS) <= agregado.keys()
        for definicion in CATALOGO_EQUIPO:
            unidad = agregado[definicion.codigo]
            assert unidad.activo
            assert unidad.url_imagen and unidad.url_imagen.startswith("/api/public/images/")
            assert unidad.descripcion_publica
            assert unidad.caracteristicas_tecnicas

        usuarios = sesion.scalars(select(Usuario)).all()
        assert len(usuarios) == 6
        por_id = {usuario.id: usuario for usuario in usuarios}
        cliente_correos = {cuenta.correo for cuenta in DEMOSTRACION_CUENTAS[1:5]}
        reservas = sesion.scalars(
            select(Reserva).where(Reserva.referencia_externa.in_(CATALOGO_REFERENCIAS))
        ).all()
        assert len(reservas) == 10
        assert {reserva.id_equipo for reserva in reservas} == {
            agregado[codigo].id for codigo in RESERVA_EQUIPO_CODIGOS
        }
        assert {reserva.correo_cliente for reserva in reservas} == cliente_correos
        for reserva in reservas:
            propietario = por_id[reserva.id_usuario_cliente]
            assert propietario.rol == "customer" and propietario.activo
            assert reserva.nombre_cliente == propietario.nombre
            assert reserva.correo_cliente == propietario.correo
            assert reserva.correo_cliente in cliente_correos
            assert reserva.estado == "confirmed"
            assert (
                BASE_FECHA
                <= reserva.fecha_inicio
                < reserva.fecha_fin
                <= BASE_FECHA + timedelta(days=14)
            )
        assert len({(reserva.fecha_inicio, reserva.fecha_fin) for reserva in reservas}) > 1
        assert len(sesion.scalars(select(Reserva)).all()) == 16
        assert not sesion.scalars(
            select(Reserva).where(Reserva.correo_cliente == DEMOSTRACION_CUENTAS[-1].correo)
        ).all()
        ocupados = [
            (
                reserva.id_equipo,
                IntervaloFechas(fecha_inicio=reserva.fecha_inicio, fecha_fin=reserva.fecha_fin),
            )
            for reserva in reservas
        ]
        libre_ids = {unidad.id for unidad in agregado.values()} - {
            elemento[0] for elemento in ocupados
        }

    despues = negocio_instantanea(aplicacion)
    assert despues["users"] == antes["users"]
    assert despues["incidents"] == antes["incidents"]
    assert despues["equipment"][:4] == antes["equipment"]
    assert despues["reservations"][:6] == antes["reservations"]
    with aplicacion.state.fabrica_sesiones() as sesion:
        servicio = ServicioReservas(RepositorioReservas(sesion))
        for id_equipo, fechas in ocupados:
            assert not servicio.disponibilidad(id_equipo, fechas).disponible
        completo_periodo = IntervaloFechas(
            fecha_inicio=BASE_FECHA, fecha_fin=BASE_FECHA + timedelta(days=14)
        )
        for id_equipo in libre_ids:
            assert servicio.disponibilidad(id_equipo, completo_periodo).disponible


def test_repeticion_preserva_editados_productos_cliente_perfiles_y_canceladas_reservas(
    aplicacion: FastAPI, ajustes: Configuracion
) -> None:
    cargar_existentes_demostracion(ajustes)
    cargar_catalogo(ajustes)
    with aplicacion.state.fabrica_sesiones() as sesion, sesion.begin():
        unidad = sesion.scalar(select(Equipo).where(Equipo.codigo == RESERVA_EQUIPO_CODIGOS[0]))
        assert unidad is not None
        unidad.nombre = "Unidad editada por administración"
        unidad.activo = False
        unidad.url_imagen = None
        unidad.caracteristicas_tecnicas = {"Estado": "Revisado"}
        reserva = sesion.scalar(
            select(Reserva).where(Reserva.referencia_externa == CATALOGO_REFERENCIAS[0])
        )
        assert reserva is not None
        reserva.estado = "cancelled"
        reserva.fecha_inicio += timedelta(days=100)
        reserva.fecha_fin += timedelta(days=100)
        propietario = sesion.get(Usuario, reserva.id_usuario_cliente)
        propietario.nombre = "Cliente con perfil actualizado"
    antes = negocio_instantanea(aplicacion)
    resultado = cargar_catalogo(ajustes, base_fecha=BASE_FECHA + timedelta(days=365))
    assert resultado.equipo_creados == 0
    assert resultado.reservas_creados == 0
    assert resultado.reservas_existentes == 10
    assert resultado.omitidas == ()
    assert negocio_instantanea(aplicacion) == antes


def test_existentes_conflicto_es_informado_sin_sobrescribir_la_reserva(
    aplicacion: FastAPI, ajustes: Configuracion
) -> None:
    cargar_existentes_demostracion(ajustes)
    definicion = next(
        elemento for elemento in CATALOGO_EQUIPO if elemento.codigo == RESERVA_EQUIPO_CODIGOS[0]
    )
    with aplicacion.state.fabrica_sesiones() as sesion:
        equipo = ServicioEquipos(RepositorioEquipos(sesion)).crear(definicion)
        id_equipo = equipo.id
    with aplicacion.state.fabrica_sesiones() as sesion:
        reserva = ServicioReservas(RepositorioReservas(sesion)).crear(
            CrearReserva(
                id_equipo=id_equipo,
                nombre_cliente="Reserva anterior",
                correo_cliente="existing@example.test",
                fecha_inicio=BASE_FECHA,
                fecha_fin=BASE_FECHA + timedelta(days=15),
                referencia_externa="EXISTING-CATALOGUE-CONFLICT",
            )
        )
        id_reserva = reserva.id
    antes = negocio_instantanea(aplicacion)
    resultado = cargar_catalogo(ajustes)
    assert resultado.equipo_creados == 19
    assert resultado.reservas_creados == 9
    assert resultado.reservas_existentes == 0
    assert len(resultado.omitidas) == 1
    despues = negocio_instantanea(aplicacion)
    assert despues["users"] == antes["users"]
    assert despues["equipment"][:5] == antes["equipment"]
    assert despues["reservations"][:7] == antes["reservations"]
    with aplicacion.state.fabrica_sesiones() as sesion:
        sin_cambios = sesion.get(Reserva, id_reserva)
        assert sin_cambios.referencia_externa == "EXISTING-CATALOGUE-CONFLICT"
        assert sin_cambios.estado == "confirmed"
        assert len(sesion.scalars(select(Reserva)).all()) == 16
        assert not sesion.scalars(
            select(Reserva).where(
                Reserva.id_equipo == id_equipo,
                Reserva.referencia_externa.in_(CATALOGO_REFERENCIAS),
            )
        ).all()


def test_ausente_clientes_fallar_sin_creando_cualquier_negocio_registros(
    aplicacion: FastAPI, ajustes: Configuracion
) -> None:
    antes = negocio_instantanea(aplicacion)
    with pytest.raises(ValueError):
        cargar_catalogo(ajustes)
    assert negocio_instantanea(aplicacion) == antes


@pytest.mark.parametrize("rol,activo", [("admin", True), ("customer", False)])
def test_sin_apto_clientes_falla_antes_anadiendo_productos(
    aplicacion: FastAPI, ajustes: Configuracion, rol: str, activo: bool
) -> None:
    cargar_existentes_demostracion(ajustes)
    with aplicacion.state.fabrica_sesiones() as sesion, sesion.begin():
        clientes = sesion.scalars(select(Usuario).where(Usuario.rol == "customer")).all()
        assert len(clientes) == 5
        for usuario in clientes:
            usuario.rol = rol
            usuario.activo = activo
    antes = negocio_instantanea(aplicacion)
    with pytest.raises(ValueError):
        cargar_catalogo(ajustes)
    assert negocio_instantanea(aplicacion) == antes


@pytest.mark.parametrize("cliente_contar", [1, 2])
def test_una_o_dos_existentes_activo_clientes_son_suficiente_sin_nuevo_cuentas(
    aplicacion: FastAPI, ajustes: Configuracion, cliente_contar: int
) -> None:
    cargar_existentes_demostracion(ajustes)
    with aplicacion.state.fabrica_sesiones() as sesion, sesion.begin():
        clientes = sesion.scalars(
            select(Usuario).where(Usuario.rol == "customer").order_by(Usuario.id)
        ).all()
        selected_ids = {usuario.id for usuario in clientes[:cliente_contar]}
        for usuario in clientes[cliente_contar:]:
            usuario.activo = False
    antes_usuarios = negocio_instantanea(aplicacion)["users"]
    resultado = cargar_catalogo(ajustes)
    assert resultado.equipo_creados == 20
    assert resultado.reservas_creados == 10
    assert resultado.reservas_existentes == 0
    assert resultado.omitidas == ()
    assert negocio_instantanea(aplicacion)["users"] == antes_usuarios
    with aplicacion.state.fabrica_sesiones() as sesion:
        reservas = sesion.scalars(
            select(Reserva).where(Reserva.referencia_externa.in_(CATALOGO_REFERENCIAS))
        ).all()
        assert len(reservas) == 10
        assert {reserva.id_usuario_cliente for reserva in reservas} == selected_ids
        for reserva in reservas:
            propietario = sesion.get(Usuario, reserva.id_usuario_cliente)
            assert propietario.activo and propietario.rol == "customer"
            assert reserva.nombre_cliente == propietario.nombre
            assert reserva.correo_cliente == propietario.correo
            assert reserva.estado == "confirmed"


@pytest.mark.parametrize(
    "entorno,base_fecha",
    [("production", BASE_FECHA), ("test", BASE_FECHA - timedelta(days=1))],
)
def test_produccion_y_pasado_fechas_fallar_antes_abrir_la_base_datos(
    tmp_path: Path, entorno: str, base_fecha: date
) -> None:
    base_datos_archivo = tmp_path / "never-created.sqlite3"
    ajustes = Configuracion(
        url_base_datos=f"sqlite:///{base_datos_archivo.as_posix()}", entorno=entorno
    )
    with pytest.raises(ValueError):
        cargar_catalogo(ajustes, base_fecha=base_fecha)
    assert not base_datos_archivo.exists()
