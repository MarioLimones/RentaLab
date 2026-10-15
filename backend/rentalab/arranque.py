"""Arranque del contenedor: valida los ajustes, migra e inicia un único proceso HTTP."""

import os
import sys
import tempfile
from pathlib import Path

from alembic.config import Config
from pydantic import ValidationError
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

from alembic import command
from rentalab.configuracion import Configuracion


class ArranqueError(Exception):
    """Fallo de arranque que puede mostrarse sin revelar valores de configuración."""


def preparar_arranque(ajustes: Configuracion) -> None:
    # Valida las credenciales antes de crear el directorio de datos o cambiar el esquema.
    ajustes.exigir_autenticacion()
    if (
        ajustes.interfaz_compilada is None
        or not (ajustes.interfaz_compilada / "index.html").is_file()
    ):
        raise ArranqueError("Falta el frontend compilado; comprueba RENTALAB_FRONTEND_DIST")
    try:
        url = make_url(ajustes.url_base_datos)
    except (ArgumentError, ValueError):
        raise ArranqueError(
            "El arranque requiere una base SQLite persistente en un archivo"
        ) from None
    if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:":
        raise ArranqueError("El arranque requiere una base SQLite persistente en un archivo")

    base_datos = Path(url.database).resolve()
    try:
        base_datos.parent.mkdir(parents=True, exist_ok=True)
        # SQLite necesita crear diarios/WAL junto a la base, además de editar el archivo .db.
        with tempfile.NamedTemporaryFile(prefix=".rentalab-write-", dir=base_datos.parent):
            pass
        if base_datos.exists():
            with base_datos.open("r+b"):
                pass
    except OSError:
        raise ArranqueError(
            "Revisa los permisos de escritura del archivo SQLite y su directorio"
        ) from None

    servidor_raiz = Path(__file__).resolve().parents[1]
    migracion_configuracion = Config(str(servidor_raiz / "alembic.ini"))
    migracion_configuracion.set_main_option(
        "sqlalchemy.url", ajustes.url_base_datos.replace("%", "%%")
    )
    try:
        command.upgrade(migracion_configuracion, "head")
    except Exception:
        raise ArranqueError(
            "No se pudieron aplicar las migraciones; el servicio no se ha iniciado"
        ) from None


def principal() -> int:
    # Las bases, copias y archivos auxiliares de SQLite son privados del usuario del servicio.
    os.umask(0o077)
    try:
        ajustes = Configuracion()
        preparar_arranque(ajustes)
    except ValidationError:
        print("La configuración de arranque está ausente o no es válida", file=sys.stderr)
        return 1
    except (ArranqueError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1

    argumentos = [
        sys.executable,
        "-m",
        "uvicorn",
        "rentalab.principal:aplicacion",
        "--host",
        "0.0.0.0",
        "--port",
        str(ajustes.puerto),
        "--workers",
        "1",
        "--proxy-headers",
        "--forwarded-allow-ips",
        ajustes.ips_reenviadas_permitidas,
    ]
    try:
        # Sustituye el PID 1 para que Docker envíe sus señales directamente a Uvicorn.
        os.execv(sys.executable, argumentos)
    except OSError:
        print("No se pudo iniciar el servicio HTTP", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(principal())
