import os
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest
from argon2 import PasswordHasher
from conftest import PRUEBA_CONTRASENA_HASH
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select, text

from rentalab.autenticacion.esquemas import SolicitudRegistro
from rentalab.autenticacion.modelos import Usuario
from rentalab.cargar_datos import cargar_datos_equipo
from rentalab.configuracion import Configuracion
from rentalab.demostracion import (
    DEMOSTRACION_CUENTAS,
    DEMOSTRACION_RESERVAS,
    cargar_datos_demostracion,
)
from rentalab.equipo.modelos import Equipo
from rentalab.incidencias.modelos import Incidencia
from rentalab.reservas.esquemas import CrearReserva, IntervaloFechas
from rentalab.reservas.modelos import Reserva
from rentalab.reservas.repositorio import RepositorioReservas
from rentalab.reservas.servicio import ServicioReservas

BASE_FECHA = date(2040, 3, 1)


def cargar_demostracion(ajustes: Configuracion, *, base_fecha: date = BASE_FECHA):
    return cargar_datos_demostracion(ajustes, base_fecha=base_fecha, hoy=lambda: BASE_FECHA)


def negocio_instantanea(aplicacion: FastAPI) -> dict[str, list[tuple]]:
    with aplicacion.state.fabrica_sesiones() as sesion:
        return {
            tabla: list(sesion.execute(text(f"SELECT * FROM {tabla} ORDER BY id")).tuples())
            for tabla in ("users", "equipment", "reservations", "incidents")
        }


def test_demostracion_crea_propietarios_unidades_fechas_adyacentes_e_historial(
    aplicacion: FastAPI, ajustes: Configuracion
) -> None:
    resultado = cargar_demostracion(ajustes)
    assert resultado.cuentas_creados == tuple(cuenta.correo for cuenta in DEMOSTRACION_CUENTAS)
    assert resultado.equipo_creados == 4
    assert resultado.reservas_creados == 6
    assert resultado.reservas_existentes == 0
    assert resultado.omitidas == ()
    with aplicacion.state.fabrica_sesiones() as sesion:
        usuarios = sesion.scalars(select(Usuario).order_by(Usuario.id)).all()
        assert len(usuarios) == 6
        assert [usuario.rol for usuario in usuarios] == ["admin"] + ["customer"] * 5
        assert all(usuario.activo for usuario in usuarios)
        for usuario, cuenta in zip(usuarios, DEMOSTRACION_CUENTAS, strict=True):
            assert usuario.hash_contrasena.startswith("$argon2id$")
            assert PasswordHasher().verify(usuario.hash_contrasena, cuenta.contrasena)
        unidades = sesion.scalars(select(Equipo)).all()
        assert len({unidad.codigo for unidad in unidades}) == 4
        camaras = sorted(
            (unidad for unidad in unidades if unidad.categoria == "Cámaras"), key=lambda u: u.codigo
        )
        assert len(camaras) == 2
        assert camaras[0].nombre == camaras[1].nombre
        assert camaras[0].id != camaras[1].id
        reservas = sesion.scalars(select(Reserva).order_by(Reserva.id)).all()
        assert len(reservas) == 6
        for reserva, definicion in zip(reservas, DEMOSTRACION_RESERVAS, strict=True):
            assert reserva.id_usuario_cliente == usuarios[definicion.cuenta_indice].id
            assert reserva.correo_cliente == usuarios[definicion.cuenta_indice].correo
            assert reserva.origen == "portal"
            assert reserva.fecha_inicio == BASE_FECHA + timedelta(
                days=definicion.arranque_desplazamiento
            )
            assert reserva.fecha_fin == BASE_FECHA + timedelta(days=definicion.fin_desplazamiento)
            assert reserva.estado == ("cancelled" if definicion.canceladas else "confirmed")
        assert reservas[0].id_equipo == reservas[1].id_equipo
        assert reservas[0].fecha_fin == reservas[1].fecha_inicio
        assert reservas[0].id_equipo != reservas[2].id_equipo
        assert reservas[0].fecha_inicio == reservas[2].fecha_inicio
        assert not any(reserva.id_usuario_cliente == usuarios[-1].id for reserva in reservas)
        canceladas = reservas[-1]
        fechas = IntervaloFechas(
            fecha_inicio=canceladas.fecha_inicio, fecha_fin=canceladas.fecha_fin
        )
    with aplicacion.state.fabrica_sesiones() as sesion:
        assert (
            ServicioReservas(RepositorioReservas(sesion))
            .disponibilidad(canceladas.id_equipo, fechas)
            .disponible
        )


def test_seis_cuentas_demostracion_acceden_y_cliente_nuevo_carece_de_reservas(
    aplicacion: FastAPI, ajustes: Configuracion
) -> None:
    cargar_demostracion(ajustes)
    sesion_ids: set[str] = set()
    for cuenta in DEMOSTRACION_CUENTAS:
        with TestClient(aplicacion) as navegador:
            csrf = navegador.get("/api/auth/csrf").json()["csrf_token"]
            iniciar_sesion = navegador.post(
                "/api/auth/login",
                json={"username": cuenta.correo, "password": cuenta.contrasena},
                headers={"X-CSRF-Token": csrf},
            )
            assert iniciar_sesion.status_code == 200
            identidad = iniciar_sesion.json()
            assert identidad["role"] == cuenta.rol
            assert identidad["user"]["email"] == cuenta.correo
            sesion_ids.add(navegador.cookies["rentalab_session"])
            if cuenta.rol == "customer":
                propia = navegador.get("/api/me/reservations")
                assert propia.status_code == 200
                if cuenta == DEMOSTRACION_CUENTAS[-1]:
                    assert propia.json() == []
                else:
                    assert propia.json()
                assert navegador.get("/api/reservations").status_code == 403
            else:
                assert len(navegador.get("/api/reservations").json()) == 6
    assert len(sesion_ids) == 6


def test_repeticion_preserva_todos_valores_contrasenas_roles_fechas_y_cancelaciones(
    aplicacion: FastAPI, ajustes: Configuracion
) -> None:
    cargar_demostracion(ajustes)
    with aplicacion.state.fabrica_sesiones() as sesion, sesion.begin():
        usuario = sesion.scalar(
            select(Usuario).where(Usuario.correo == DEMOSTRACION_CUENTAS[1].correo)
        )
        assert usuario is not None
        usuario.nombre = "Nombre cambiado por la persona"
        usuario.hash_contrasena = PasswordHasher().hash("changed-local-password")
        unidad = sesion.scalar(select(Equipo).where(Equipo.codigo == "CAM-001"))
        assert unidad is not None
        unidad.nombre = "Unidad editada"
        unidad.activo = False
        reserva = sesion.scalar(
            select(Reserva).where(Reserva.referencia_externa == "RENTALAB-DEMO-01")
        )
        assert reserva is not None
        reserva.estado = "cancelled"
        reserva.fecha_inicio += timedelta(days=100)
        reserva.fecha_fin += timedelta(days=100)
    antes = negocio_instantanea(aplicacion)
    resultado = cargar_demostracion(ajustes, base_fecha=BASE_FECHA + timedelta(days=365))
    assert resultado.cuentas_creados == ()
    assert resultado.equipo_creados == 0
    assert resultado.reservas_creados == 0
    assert resultado.reservas_existentes == 6
    assert resultado.omitidas == ()
    assert negocio_instantanea(aplicacion) == antes


@pytest.mark.parametrize("rol,activo", [("customer", True), ("admin", False)])
def test_existentes_administrador_correo_es_nunca_ascendido_o_reactivado_silenciosamente(
    aplicacion: FastAPI, ajustes: Configuracion, rol: str, activo: bool
) -> None:
    cuenta = DEMOSTRACION_CUENTAS[0]
    existentes = aplicacion.state.autenticacion_servicio.registrar(
        SolicitudRegistro(
            nombre="Cuenta anterior", correo=cuenta.correo, contrasena="existing-password"
        ),
        rol=rol,
    )
    with aplicacion.state.fabrica_sesiones() as sesion, sesion.begin():
        usuario = sesion.get(Usuario, existentes.id)
        usuario.activo = activo
        original_hash = usuario.hash_contrasena
    resultado = cargar_demostracion(ajustes)
    assert len(resultado.cuentas_creados) == 5
    assert any(cuenta.correo in motivo for motivo in resultado.omitidas)
    with aplicacion.state.fabrica_sesiones() as sesion:
        usuario = sesion.get(Usuario, existentes.id)
        assert (usuario.nombre, usuario.rol, usuario.activo, usuario.hash_contrasena) == (
            "Cuenta anterior",
            rol,
            activo,
            original_hash,
        )


def test_demostracion_informa_real_reserva_conflicto_sin_reparando_existentes_datos(
    aplicacion: FastAPI, ajustes: Configuracion
) -> None:
    with aplicacion.state.fabrica_sesiones() as sesion, sesion.begin():
        cargar_datos_equipo(sesion)
        id_equipo = sesion.scalar(select(Equipo.id).where(Equipo.codigo == "CAM-001"))
    with aplicacion.state.fabrica_sesiones() as sesion:
        reserva = ServicioReservas(RepositorioReservas(sesion)).crear(
            CrearReserva(
                id_equipo=id_equipo,
                nombre_cliente="Otra reserva preexistente",
                correo_cliente="other@example.test",
                fecha_inicio=BASE_FECHA + timedelta(days=7),
                fecha_fin=BASE_FECHA + timedelta(days=10),
                referencia_externa="NOT-DEMO",
            )
        )
        id_reserva = reserva.id
    resultado = cargar_demostracion(ajustes)
    assert resultado.reservas_creados == 5
    assert len(resultado.omitidas) == 1
    assert "RENTALAB-DEMO-01" in resultado.omitidas[0]
    with aplicacion.state.fabrica_sesiones() as sesion:
        sin_cambios = sesion.get(Reserva, id_reserva)
        assert sin_cambios.estado == "confirmed"
        assert sin_cambios.nombre_cliente == "Otra reserva preexistente"
        assert sin_cambios.referencia_externa == "NOT-DEMO"
        assert len(sesion.scalars(select(Reserva)).all()) == 6


def test_demostracion_informa_colision_de_correo_sin_apropiarse_del_administrador(
    aplicacion: FastAPI, ajustes: Configuracion
) -> None:
    ajustes = ajustes.model_copy(
        update={
            "usuario_operador": DEMOSTRACION_CUENTAS[0].correo,
            "hash_contrasena_operador": SecretStr(PRUEBA_CONTRASENA_HASH),
        }
    )
    resultado = cargar_demostracion(ajustes)
    assert len(resultado.cuentas_creados) == 5
    assert len(resultado.omitidas) == 1
    assert "operador heredado" in resultado.omitidas[0]
    with aplicacion.state.fabrica_sesiones() as sesion:
        assert (
            sesion.scalar(select(Usuario).where(Usuario.correo == DEMOSTRACION_CUENTAS[0].correo))
            is None
        )
        assert len(sesion.scalars(select(Usuario)).all()) == 5


@pytest.mark.parametrize("bloqueo", ["inactive", "incident"])
def test_demostracion_respeta_compartido_inactivo_y_bloqueante_incidencia_reglas(
    aplicacion: FastAPI, ajustes: Configuracion, bloqueo: str
) -> None:
    with aplicacion.state.fabrica_sesiones() as sesion, sesion.begin():
        cargar_datos_equipo(sesion)
        unidad = sesion.scalar(select(Equipo).where(Equipo.codigo == "CAM-001"))
        if bloqueo == "inactive":
            unidad.activo = False
        else:
            sesion.add(Incidencia(id_equipo=unidad.id, titulo="No alquilar", bloqueante=True))
        unidad_id = unidad.id
    resultado = cargar_demostracion(ajustes)
    assert resultado.reservas_creados == 3
    assert len(resultado.omitidas) == 3
    with aplicacion.state.fabrica_sesiones() as sesion:
        assert not sesion.scalars(select(Reserva).where(Reserva.id_equipo == unidad_id)).all()
        if bloqueo == "inactive":
            assert not sesion.get(Equipo, unidad_id).activo
        else:
            assert sesion.scalar(select(Incidencia)).bloqueante


@pytest.mark.parametrize("base", [BASE_FECHA - timedelta(days=1), date.max])
def test_invalido_base_fechas_fallar_antes_abrir_o_cambiando_base_datos(
    tmp_path: Path, base: date
) -> None:
    base_datos_archivo = tmp_path / "never-created.sqlite3"
    ajustes = Configuracion(
        url_base_datos=f"sqlite:///{base_datos_archivo.as_posix()}", entorno="test"
    )
    with pytest.raises(ValueError):
        cargar_demostracion(ajustes, base_fecha=base)
    assert not base_datos_archivo.exists()


def test_explicito_cli_rechaza_produccion_sin_abrir_base_datos(tmp_path: Path) -> None:
    base_datos_archivo = tmp_path / "never-created.sqlite3"
    entorno = {
        **os.environ,
        "RENTALAB_ENVIRONMENT": "production",
        "RENTALAB_DATABASE_URL": f"sqlite:///{base_datos_archivo.as_posix()}",
    }
    resultado = subprocess.run(
        [sys.executable, "-m", "rentalab.demostracion"],
        cwd=Path(__file__).resolve().parents[1],
        env=entorno,
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )
    assert resultado.returncode == 1
    assert "prohibida en production" in resultado.stderr
    assert "Demo-RentaLab" not in resultado.stdout
    assert not base_datos_archivo.exists()
