"""Creación explícita de cuentas persistentes sin contraseñas en los argumentos de consola."""

import argparse
import getpass
import os
import re
import sys
import warnings

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from rentalab.autenticacion.esquemas import SolicitudRegistro
from rentalab.autenticacion.servicio import DuplicadoUsuarioCorreo, ServicioAutenticacion
from rentalab.base_datos import crear_base_datos_motor
from rentalab.configuracion import Configuracion

DEMOSTRACION_USUARIOS = (
    ("Alicia Demo", "alicia.demo@example.test"),
    ("Bruno Demo", "bruno.demo@example.test"),
)


class SecretoSeguroArgumentoAnalizador(argparse.ArgumentParser):
    def error(instancia, mensaje: str) -> None:
        # argparse mostraría argumentos desconocidos, incluidas contraseñas introducidas por error.
        instancia.exit(
            2, "Argumentos no válidos; consulta --help. No pases contraseñas por argumentos.\n"
        )


def lectura_contrasena(entorno_nombre: str | None) -> str:
    if entorno_nombre is not None:
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", entorno_nombre) is None:
            raise ValueError("El nombre de variable de contraseña no es válido")
        valor = os.environ.get(entorno_nombre)
        if valor is None:
            raise ValueError("La variable de contraseña indicada no está configurada")
        return valor
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        valor = getpass.getpass("Contraseña (8–1024 caracteres): ")
        confirmacion = getpass.getpass("Repite la contraseña: ")
    if valor != confirmacion:
        raise ValueError("Las contraseñas no coinciden")
    return valor


def principal(argumentos: list[str] | None = None) -> int:
    analizador = SecretoSeguroArgumentoAnalizador(
        description="Crear cuentas persistentes explícitamente", allow_abbrev=False
    )
    comandos = analizador.add_subparsers(dest="accion", required=True)
    administrador_http = comandos.add_parser(
        "create-admin", help="Crear un administrador nuevo", allow_abbrev=False
    )
    administrador_http.add_argument("--name", dest="nombre", required=True)
    administrador_http.add_argument("--email", dest="correo", required=True)
    administrador_http.add_argument(
        "--password-env", dest="variable_contrasena", metavar="VARIABLE"
    )
    demostracion = comandos.add_parser(
        "demo-users", help="Crear dos clientes ficticios, sin datos de negocio", allow_abbrev=False
    )
    demostracion.add_argument("--password-env", dest="variable_contrasena", metavar="VARIABLE")
    argumentos = analizador.parse_args(argumentos)
    motor = None
    try:
        contrasena = lectura_contrasena(argumentos.variable_contrasena)
        cuentas = (
            [(argumentos.nombre, argumentos.correo)]
            if argumentos.accion == "create-admin"
            else DEMOSTRACION_USUARIOS
        )
        # Valida antes de abrir la base y nunca imprimas entradas de validación ni secretos.
        contenidos_envio = [
            SolicitudRegistro(nombre=nombre, correo=correo, contrasena=contrasena)
            for nombre, correo in cuentas
        ]
        ajustes = Configuracion()
        motor = crear_base_datos_motor(
            ajustes.url_base_datos, ocupado_espera_ms=ajustes.espera_sqlite_ocupado_ms
        )
        servicio = ServicioAutenticacion(ajustes, sessionmaker(motor, expire_on_commit=False))
        creados = 0
        for contenido_envio in contenidos_envio:
            try:
                servicio.registrar(
                    contenido_envio,
                    rol="admin" if argumentos.accion == "create-admin" else "customer",
                )
                creados += 1
            except DuplicadoUsuarioCorreo:
                if argumentos.accion == "create-admin":
                    print("Ya existe ese correo; no se han alterado sus permisos.", file=sys.stderr)
                    return 1
        print(
            f"Cuentas creadas: {creados}. Las cuentas existentes conservan sus datos y contraseñas."
        )
        return 0
    except ValidationError:
        print(
            "Nombre/correo inválidos o contraseña fuera del rango de 8–1024 caracteres.",
            file=sys.stderr,
        )
        return 1
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 1
    except (EOFError, KeyboardInterrupt, getpass.GetPassWarning):
        print("No se pudo leer la contraseña en una terminal interactiva.", file=sys.stderr)
        return 1
    except SQLAlchemyError:
        print(
            "No se pudo crear la cuenta; comprueba la base y aplica Alembic primero.",
            file=sys.stderr,
        )
        return 1
    finally:
        if motor is not None:
            motor.dispose()


if __name__ == "__main__":
    raise SystemExit(principal())
