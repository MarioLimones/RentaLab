"""Datos explícitos de demostración local; el arranque nunca los importa ni ejecuta."""

import argparse
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from rentalab.autenticacion.esquemas import RolUsuario, SolicitudRegistro
from rentalab.autenticacion.modelos import Usuario
from rentalab.autenticacion.servicio import DuplicadoUsuarioCorreo, ServicioAutenticacion
from rentalab.base_datos import crear_base_datos_motor
from rentalab.cargar_datos import cargar_datos_equipo
from rentalab.configuracion import Configuracion
from rentalab.equipo.modelos import Equipo
from rentalab.reloj import madrid_hoy
from rentalab.reservas.esquemas import CrearReserva
from rentalab.reservas.modelos import Reserva
from rentalab.reservas.repositorio import RepositorioReservas
from rentalab.reservas.servicio import ConflictoReserva, ServicioReservas


@dataclass(frozen=True)
class DemostracionCuenta:
    nombre: str
    correo: str
    contrasena: str
    rol: RolUsuario = "customer"


# Credenciales públicas ficticias exclusivas de esta demostración local opcional.
# Cada cuenta es un usuario persistente con su hash de contraseña calculado por separado.
DEMOSTRACION_CUENTAS = (
    DemostracionCuenta(
        "Administración Demo",
        "admin.demo@rentalab.example.test",
        "Demo-RentaLab-Admin-2026!",
        "admin",
    ),
    DemostracionCuenta(
        "Alicia Demo", "alicia.demo@rentalab.example.test", "Demo-RentaLab-Alicia-2026!"
    ),
    DemostracionCuenta(
        "Bruno Demo", "bruno.demo@rentalab.example.test", "Demo-RentaLab-Bruno-2026!"
    ),
    DemostracionCuenta(
        "Carla Demo", "carla.demo@rentalab.example.test", "Demo-RentaLab-Carla-2026!"
    ),
    DemostracionCuenta(
        "Diego Demo", "diego.demo@rentalab.example.test", "Demo-RentaLab-Diego-2026!"
    ),
    DemostracionCuenta(
        "Elena Demo", "elena.demo@rentalab.example.test", "Demo-RentaLab-Elena-2026!"
    ),
)


@dataclass(frozen=True)
class DemostracionReserva:
    referencia: str
    cuenta_indice: int
    codigo_equipo: str
    arranque_desplazamiento: int
    fin_desplazamiento: int
    canceladas: bool = False


# Las referencias omiten deliberadamente la fecha base: otra ejecución conserva
# las fechas, propiedad y estado originales sin generar otro conjunto.
DEMOSTRACION_RESERVAS = (
    DemostracionReserva("RENTALAB-DEMO-01", 1, "CAM-001", 7, 10),
    DemostracionReserva("RENTALAB-DEMO-02", 2, "CAM-001", 10, 13),
    DemostracionReserva("RENTALAB-DEMO-03", 3, "CAM-002", 7, 11),
    DemostracionReserva("RENTALAB-DEMO-04", 4, "AUD-001", 3, 5),
    DemostracionReserva("RENTALAB-DEMO-05", 1, "LGT-001", 15, 17),
    DemostracionReserva("RENTALAB-DEMO-06", 3, "CAM-001", 20, 22, canceladas=True),
)


@dataclass(frozen=True)
class DemostracionCargarDatosResultado:
    base_fecha: date
    cuentas_creados: tuple[str, ...]
    equipo_creados: int
    reservas_creados: int
    reservas_existentes: int
    omitidas: tuple[str, ...]


def cargar_datos_demostracion(
    ajustes: Configuracion,
    *,
    base_fecha: date | None = None,
    hoy: Callable[[], date] = madrid_hoy,
) -> DemostracionCargarDatosResultado:
    """Añade registros ficticios ausentes conservando los registros y contraseñas actuales.

    Los equipos existentes siguen la misma comprobación de disponibilidad que los clientes
    HTTP. Los conflictos se informan sin reparar datos reales.
    """
    if ajustes.entorno == "production":
        raise ValueError("La carga de demostración está prohibida en production")
    actual_dia = hoy()
    base = base_fecha or actual_dia
    if base < actual_dia:
        raise ValueError("La fecha base no puede ser anterior a hoy en Europe/Madrid")
    # Valida todo el intervalo de fechas antes de cambiar la base de datos.
    try:
        intervalos = [
            (
                base + timedelta(days=elemento.arranque_desplazamiento),
                base + timedelta(days=elemento.fin_desplazamiento),
            )
            for elemento in DEMOSTRACION_RESERVAS
        ]
    except OverflowError:
        raise ValueError(
            "La fecha base no permite calcular los intervalos de demostración"
        ) from None

    motor = crear_base_datos_motor(
        ajustes.url_base_datos, ocupado_espera_ms=ajustes.espera_sqlite_ocupado_ms
    )
    fabrica = sessionmaker(motor, expire_on_commit=False)
    creados_cuentas: list[str] = []
    omitidas: list[str] = []
    reservas_creados = reservas_existentes = 0
    try:
        autenticacion = ServicioAutenticacion(ajustes, fabrica)
        for cuenta in DEMOSTRACION_CUENTAS:
            with fabrica() as sesion:
                existentes = sesion.scalar(select(Usuario).where(Usuario.correo == cuenta.correo))
            if existentes is not None:
                if existentes.rol != cuenta.rol or not existentes.activo:
                    omitidas.append(
                        f"{cuenta.correo}: la cuenta existente no es {cuenta.rol} activa; "
                        "se conservan sus permisos y estado"
                    )
                continue
            try:
                autenticacion.registrar(
                    SolicitudRegistro(
                        nombre=cuenta.nombre, correo=cuenta.correo, contrasena=cuenta.contrasena
                    ),
                    rol=cuenta.rol,
                )
                creados_cuentas.append(cuenta.correo)
            except DuplicadoUsuarioCorreo:
                # Otra invocación explícita puede haberlo creado al mismo tiempo.
                with fabrica() as sesion:
                    existentes = sesion.scalar(
                        select(Usuario).where(Usuario.correo == cuenta.correo)
                    )
                if existentes is None:
                    omitidas.append(
                        f"{cuenta.correo}: el correo coincide con el operador heredado; "
                        "no se ha creado otra identidad"
                    )
                elif existentes.rol != cuenta.rol or not existentes.activo:
                    omitidas.append(
                        f"{cuenta.correo}: la cuenta existente no es {cuenta.rol} activa; "
                        "se conservan sus permisos y estado"
                    )
        with fabrica() as sesion, sesion.begin():
            equipo_creados = cargar_datos_equipo(sesion)

        for reserva, (arranque, fin) in zip(DEMOSTRACION_RESERVAS, intervalos, strict=True):
            cuenta = DEMOSTRACION_CUENTAS[reserva.cuenta_indice]
            with fabrica() as sesion:
                existentes = sesion.scalar(
                    select(Reserva.id).where(Reserva.referencia_externa == reserva.referencia)
                )
                if existentes is not None:
                    reservas_existentes += 1
                    continue
                usuario = sesion.scalar(select(Usuario).where(Usuario.correo == cuenta.correo))
                id_equipo = sesion.scalar(
                    select(Equipo.id).where(Equipo.codigo == reserva.codigo_equipo)
                )
                if usuario is None or not usuario.activo or usuario.rol != "customer":
                    omitidas.append(f"{reserva.referencia}: la cuenta no es un cliente activo")
                    continue
                assert id_equipo is not None
                # Los datos actuales del perfil conservan su autoridad, incluido un nombre editado.
                datos = CrearReserva(
                    id_equipo=id_equipo,
                    nombre_cliente=usuario.nombre,
                    correo_cliente=usuario.correo,
                    fecha_inicio=arranque,
                    fecha_fin=fin,
                    referencia_externa=reserva.referencia,
                )
                id_usuario = usuario.id
            try:
                with fabrica() as sesion:
                    servicio = ServicioReservas(RepositorioReservas(sesion))
                    servicio.crear_para_cliente(
                        datos,
                        id_usuario_cliente=id_usuario,
                        hoy=lambda: actual_dia,
                        inicial_estado="cancelled" if reserva.canceladas else "confirmed",
                    )
                reservas_creados += 1
            except ConflictoReserva as error:
                omitidas.append(f"{reserva.referencia}: {error}")
        return DemostracionCargarDatosResultado(
            base,
            tuple(creados_cuentas),
            equipo_creados,
            reservas_creados,
            reservas_existentes,
            tuple(omitidas),
        )
    finally:
        motor.dispose()


def iso_fecha(valor: str) -> date:
    if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", valor) is None:
        raise argparse.ArgumentTypeError("Usa YYYY-MM-DD")
    try:
        return date.fromisoformat(valor)
    except ValueError:
        raise argparse.ArgumentTypeError("La fecha no es válida") from None


def principal(argumentos: list[str] | None = None) -> int:
    analizador = argparse.ArgumentParser(
        description="Crear datos ficticios locales explícitamente; prohibido en production",
        allow_abbrev=False,
    )
    analizador.add_argument(
        "--base-date",
        dest="base_fecha",
        type=iso_fecha,
        help="Fecha base YYYY-MM-DD; por defecto, hoy en Madrid",
    )
    argumentos = analizador.parse_args(argumentos)
    try:
        resultado = cargar_datos_demostracion(Configuracion(), base_fecha=argumentos.base_fecha)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 1
    except SQLAlchemyError:
        print(
            "No se pudo completar la carga; comprueba la base y aplica Alembic primero. "
            "Puedes repetirla sin borrar los registros ya creados.",
            file=sys.stderr,
        )
        return 1
    print(
        f"Demostración local; fecha base {resultado.base_fecha.isoformat()}. "
        f"Cuentas nuevas: {len(resultado.cuentas_creados)}; "
        f"equipos nuevos: {resultado.equipo_creados}; "
        f"reservas nuevas: {resultado.reservas_creados}; "
        f"reservas conservadas: {resultado.reservas_existentes}."
    )
    print("Las cuentas y reservas existentes conservan contraseñas, roles, fechas y estados.")
    for cuenta in DEMOSTRACION_CUENTAS:
        credencial = (
            cuenta.contrasena
            if cuenta.correo in resultado.cuentas_creados
            else "cuenta existente; contraseña conservada"
        )
        print(f"{cuenta.rol}: {cuenta.correo} | {credencial}")
    for motivo in resultado.omitidas:
        print(f"Omitida {motivo}", file=sys.stderr)
    return 1 if resultado.omitidas else 0


if __name__ == "__main__":
    raise SystemExit(principal())
