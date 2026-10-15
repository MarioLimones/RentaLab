"""Explicit persistent-account provisioning; passwords never enter command arguments."""

import argparse
import getpass
import os
import re
import sys
import warnings

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from rentalab.auth.schemas import RegisterRequest
from rentalab.auth.service import AuthService, DuplicateUserEmail
from rentalab.config import Settings
from rentalab.database import create_database_engine

DEMO_USERS = (
    ("Alicia Demo", "alicia.demo@example.test"),
    ("Bruno Demo", "bruno.demo@example.test"),
)


class SecretSafeArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        # argparse otherwise reflects unknown arguments, including accidental passwords.
        self.exit(
            2, "Argumentos no válidos; consulta --help. No pases contraseñas por argumentos.\n"
        )


def read_password(environment_name: str | None) -> str:
    if environment_name is not None:
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", environment_name) is None:
            raise ValueError("El nombre de variable de contraseña no es válido")
        value = os.environ.get(environment_name)
        if value is None:
            raise ValueError("La variable de contraseña indicada no está configurada")
        return value
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        value = getpass.getpass("Contraseña (8–1024 caracteres): ")
        confirmation = getpass.getpass("Repite la contraseña: ")
    if value != confirmation:
        raise ValueError("Las contraseñas no coinciden")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = SecretSafeArgumentParser(
        description="Crear cuentas persistentes explícitamente", allow_abbrev=False
    )
    commands = parser.add_subparsers(dest="command", required=True)
    admin = commands.add_parser(
        "create-admin", help="Crear un administrador nuevo", allow_abbrev=False
    )
    admin.add_argument("--name", required=True)
    admin.add_argument("--email", required=True)
    admin.add_argument("--password-env", metavar="VARIABLE")
    demo = commands.add_parser(
        "demo-users", help="Crear dos clientes ficticios, sin datos de negocio", allow_abbrev=False
    )
    demo.add_argument("--password-env", metavar="VARIABLE")
    args = parser.parse_args(argv)
    engine = None
    try:
        password = read_password(args.password_env)
        accounts = [(args.name, args.email)] if args.command == "create-admin" else DEMO_USERS
        # Validate before opening a database, and never print validation inputs/secrets.
        payloads = [
            RegisterRequest(name=name, email=email, password=password) for name, email in accounts
        ]
        settings = Settings()
        engine = create_database_engine(
            settings.database_url, busy_timeout_ms=settings.sqlite_busy_timeout_ms
        )
        service = AuthService(settings, sessionmaker(engine, expire_on_commit=False))
        created = 0
        for payload in payloads:
            try:
                service.register(
                    payload, role="admin" if args.command == "create-admin" else "customer"
                )
                created += 1
            except DuplicateUserEmail:
                if args.command == "create-admin":
                    print("Ya existe ese correo; no se han alterado sus permisos.", file=sys.stderr)
                    return 1
        print(
            f"Cuentas creadas: {created}. Las cuentas existentes conservan sus datos y contraseñas."
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
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
